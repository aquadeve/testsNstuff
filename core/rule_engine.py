"""Rule Engine — declarative, JSON-driven rule evaluation for device automation.

Rules are loaded from a JSON file and evaluated each capture loop.  Each rule
maps a *condition* (image match, colour detection, or stuck-state check) to an
*action* that the :class:`~core.action_executor.ActionExecutor` will carry out.

Supported condition types:
    ``"image"``      — OpenCV template matching via :class:`~core.vision_engine.VisionEngine`.
    ``"color"``      — HSV colour presence detection.
    ``"no_change"``  — Stuck-state detection using per-device screen history.

Supported action types (executed by ActionExecutor):
    ``"tap"``, ``"swipe"``, ``"wait"``, ``"restart_app"``, ``"callback"``
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from core.vision_engine import VisionEngine

logger = logging.getLogger(__name__)

# Type aliases for clarity.
Rule = Dict[str, Any]
StateDict = Dict[str, Any]


class RuleEngine:
    """Loads, validates and evaluates automation rules against captured frames.

    Each :class:`~devices.device_worker.DeviceWorker` owns one ``RuleEngine``
    instance so that cooldown state remains per-device.

    Args:
        vision_engine: Shared (or per-worker) :class:`~core.vision_engine.VisionEngine`
            instance used for image and colour checks.
    """

    def __init__(self, vision_engine: VisionEngine) -> None:
        self._vision = vision_engine
        self._rules: List[Rule] = []
        # Maps rule_name → last trigger timestamp (monotonic).
        self._last_triggered: Dict[str, float] = {}

    # ------------------------------------------------------------------
    # Rule loading
    # ------------------------------------------------------------------

    def load_rules(self, path: str) -> None:
        """Load and validate rules from a JSON file.

        Rules with missing required fields are skipped with a warning.  The
        loaded list is sorted by ``priority`` (ascending, lower = higher).

        Args:
            path: Path to the rules JSON file.

        Raises:
            FileNotFoundError: If the specified file does not exist.
            json.JSONDecodeError: If the file contains invalid JSON.
        """
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)

        raw_rules: List[Rule] = data if isinstance(data, list) else data.get("rules", [])
        validated: List[Rule] = []

        for raw in raw_rules:
            if not self._validate_rule(raw):
                continue
            validated.append(raw)

        # Sort by priority (lower number = higher priority, defaults to 99).
        validated.sort(key=lambda r: r.get("priority", 99))
        self._rules = validated
        logger.info("Loaded %d rule(s) from %s", len(self._rules), path)

    @staticmethod
    def _validate_rule(rule: Rule) -> bool:
        """Return ``True`` if the rule has all required fields."""
        for field in ("name", "condition", "action"):
            if field not in rule:
                logger.warning("Rule missing required field '%s', skipping: %s", field, rule)
                return False
        if "type" not in rule.get("condition", {}):
            logger.warning("Rule '%s' condition missing 'type' field, skipping.", rule.get("name"))
            return False
        if "type" not in rule.get("action", {}):
            logger.warning("Rule '%s' action missing 'type' field, skipping.", rule.get("name"))
            return False
        return True

    # ------------------------------------------------------------------
    # Cooldown management
    # ------------------------------------------------------------------

    def is_on_cooldown(self, rule_name: str) -> bool:
        """Check whether a rule is still within its cooldown window.

        Args:
            rule_name: The ``name`` field of the rule.

        Returns:
            ``True`` if the rule triggered recently and must not fire again yet.
        """
        rule = self._get_rule_by_name(rule_name)
        if rule is None:
            return False
        cooldown: float = rule.get("cooldown", 0.0)
        last = self._last_triggered.get(rule_name)
        if last is None:
            return False
        return (time.monotonic() - last) < cooldown

    def mark_triggered(self, rule_name: str) -> None:
        """Record the current time as the last trigger time for a rule.

        Args:
            rule_name: The ``name`` field of the rule.
        """
        self._last_triggered[rule_name] = time.monotonic()
        logger.debug("Marked rule '%s' as triggered.", rule_name)

    # ------------------------------------------------------------------
    # Rule evaluation
    # ------------------------------------------------------------------

    def evaluate(
        self,
        screen: np.ndarray,
        device_state: StateDict,
    ) -> List[Tuple[Rule, Tuple[int, int]]]:
        """Evaluate all enabled, non-cooldown rules against the current frame.

        Args:
            screen: Current device screenshot as a BGR image array.
            device_state: State dictionary from
                :meth:`~core.state_manager.StateManager.get_state_summary` plus
                extra keys that condition evaluators may need
                (e.g. ``"screen_buffer"``).

        Returns:
            List of ``(rule, match_location)`` tuples for every rule whose
            condition is satisfied, in priority order (already sorted when
            :meth:`load_rules` was called).
        """
        triggered: List[Tuple[Rule, Tuple[int, int]]] = []

        for rule in self._rules:
            if not rule.get("enabled", True):
                continue
            if self.is_on_cooldown(rule["name"]):
                logger.debug("Rule '%s' is on cooldown, skipping.", rule["name"])
                continue

            matched, location = self._evaluate_condition(rule["condition"], screen, device_state)
            if matched:
                logger.info(
                    "Rule '%s' condition satisfied at location %s.",
                    rule["name"], location,
                )
                triggered.append((rule, location))

        return triggered

    # ------------------------------------------------------------------
    # Condition evaluators
    # ------------------------------------------------------------------

    def _evaluate_condition(
        self,
        condition: Dict[str, Any],
        screen: np.ndarray,
        device_state: StateDict,
    ) -> Tuple[bool, Tuple[int, int]]:
        """Dispatch condition evaluation based on ``type``.

        Returns:
            ``(matched, location)`` tuple.  ``location`` is ``(0, 0)`` for
            non-spatial conditions.
        """
        ctype = condition.get("type", "")

        if ctype == "image":
            return self._eval_image(condition, screen)
        elif ctype == "color":
            return self._eval_color(condition, screen)
        elif ctype == "no_change":
            return self._eval_no_change(condition, device_state)
        else:
            logger.warning("Unknown condition type '%s', treating as unmatched.", ctype)
            return False, (0, 0)

    def _eval_image(
        self,
        condition: Dict[str, Any],
        screen: np.ndarray,
    ) -> Tuple[bool, Tuple[int, int]]:
        """Evaluate an ``"image"`` condition using template matching."""
        target: str = condition.get("target", "")
        threshold: Optional[float] = condition.get("threshold")
        region_raw: Optional[List[int]] = condition.get("region")
        region = tuple(region_raw) if region_raw else None  # type: ignore[arg-type]

        # Resolve template path relative to assets/ directory.
        import os
        assets_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets")
        template_path = os.path.join(assets_dir, target)

        found, location, _ = self._vision.find_template(
            screen, template_path, threshold=threshold, region=region  # type: ignore[arg-type]
        )
        return found, location

    def _eval_color(
        self,
        condition: Dict[str, Any],
        screen: np.ndarray,
    ) -> Tuple[bool, Tuple[int, int]]:
        """Evaluate a ``"color"`` condition using HSV colour detection."""
        color_hsv_raw: List[int] = condition.get("color_hsv", [0, 0, 0])
        color_hsv = tuple(color_hsv_raw)  # type: ignore[arg-type]
        tolerance: int = condition.get("tolerance", 20)
        region_raw: Optional[List[int]] = condition.get("region")
        region = tuple(region_raw) if region_raw else None  # type: ignore[arg-type]

        found = self._vision.detect_color(screen, color_hsv, tolerance=tolerance, region=region)  # type: ignore[arg-type]
        return found, (0, 0)

    def _eval_no_change(
        self,
        condition: Dict[str, Any],
        device_state: StateDict,
    ) -> Tuple[bool, Tuple[int, int]]:
        """Evaluate a ``"no_change"`` condition using the screen history buffer.

        Checks whether the device appears stuck by delegating to
        :meth:`~core.state_manager.StateManager.is_stuck`.
        """
        window: float = float(condition.get("window", 15.0))
        # device_state may carry a reference to the StateManager.
        state_manager = device_state.get("state_manager")
        if state_manager is None:
            logger.debug("no_change condition: state_manager not in device_state, skipping.")
            return False, (0, 0)

        stuck = state_manager.is_stuck(window=window)
        return stuck, (0, 0)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_rule_by_name(self, name: str) -> Optional[Rule]:
        """Return the rule dict with the given name, or ``None``."""
        for rule in self._rules:
            if rule.get("name") == name:
                return rule
        return None
