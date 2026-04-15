"""Script compiler — converts a list of :class:`~core.block_model.BlockData`
objects into the rules.json format consumed by the MobileVisionBot engine.

The compiler scans blocks in order and pairs each *condition* block with the
*action* block that immediately follows it.  An action block without a
preceding condition is emitted with an ``"always"`` condition so it fires
every evaluation cycle.

Usage::

    compiler = ScriptCompiler()
    rules = compiler.compile(canvas.get_blocks(), rule_name="my_flow")
    json_str = compiler.to_json(rules)

The output list is directly compatible with ``config/rules.json`` and can be
written to disk for use by :class:`~core.rule_engine.RuleEngine`.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from core.block_model import BlockData

logger = logging.getLogger(__name__)


class ScriptCompiler:
    """Compile a canvas block sequence to JSON rule dicts."""

    def compile(
        self,
        blocks: List[BlockData],
        rule_name: str = "visual_rule",
        priority: int = 1,
        cooldown: float = 2.0,
    ) -> List[Dict[str, Any]]:
        """Compile *blocks* into a list of rule dicts.

        Args:
            blocks:     Ordered block list from the canvas.
            rule_name:  Base name for generated rules (index-suffixed).
            priority:   Priority for all generated rules.
            cooldown:   Cooldown seconds for all generated rules.

        Returns:
            List of rule dicts ready to save as ``config/rules.json``.
        """
        rules: List[Dict[str, Any]] = []
        enabled = [b for b in blocks if b.enabled]

        i = 0
        rule_index = 0
        while i < len(enabled):
            block = enabled[i]
            condition_dict: Optional[Dict[str, Any]] = None
            action_dict: Optional[Dict[str, Any]] = None

            if block.category == "condition":
                # Pair this condition with the next action if present.
                condition_dict = self._compile_condition(block)
                i += 1
                if i < len(enabled) and enabled[i].category == "action":
                    action_dict = self._compile_action(enabled[i])
                    i += 1

            elif block.category == "action":
                # Standalone action — always condition.
                condition_dict = {"type": "always"}
                action_dict = self._compile_action(block)
                i += 1

            else:
                # Control blocks — reserved for future nested compilation.
                i += 1
                continue

            if action_dict is None:
                logger.debug(
                    "Condition block '%s' has no following action — skipping.",
                    block.label,
                )
                continue

            rules.append(
                {
                    "name": f"{rule_name}_{rule_index}",
                    "enabled": True,
                    "priority": priority,
                    "cooldown": cooldown,
                    "condition": condition_dict,
                    "action": action_dict,
                }
            )
            rule_index += 1

        logger.info(
            "Compiled %d rule(s) from %d block(s).", len(rules), len(blocks)
        )
        return rules

    # ── Serialisation ─────────────────────────────────────────────────

    def to_json(self, rules: List[Dict[str, Any]]) -> str:
        """Return a pretty-printed JSON string of *rules*."""
        return json.dumps(rules, indent=2)

    # ── Condition compilers ───────────────────────────────────────────

    def _compile_condition(self, block: BlockData) -> Dict[str, Any]:
        p = block.params
        if block.subtype == "image_appears":
            return {
                "type": "image",
                "target": p.get("image", ""),
                "threshold": float(p.get("threshold", 0.85)),
                "region": p.get("region"),
            }
        if block.subtype == "image_not_appears":
            return {
                "type": "image_not",
                "target": p.get("image", ""),
                "threshold": float(p.get("threshold", 0.85)),
                "region": p.get("region"),
            }
        if block.subtype == "color_detected":
            return {
                "type": "color",
                "color_hsv": p.get("color_hsv", [0, 0, 0]),
                "tolerance": int(p.get("tolerance", 20)),
                "region": p.get("region"),
            }
        if block.subtype == "screen_unchanged":
            return {"type": "no_change", "window": float(p.get("window", 15.0))}
        return {"type": block.subtype}

    # ── Action compilers ──────────────────────────────────────────────

    def _compile_action(self, block: BlockData) -> Dict[str, Any]:
        p = block.params
        if block.subtype == "tap":
            return {"type": "tap", "position": p.get("position", "center_of_match")}
        if block.subtype == "swipe":
            return {
                "type": "swipe",
                "from": p.get("from", [0, 0]),
                "to": p.get("to", [0, 0]),
                "duration": int(p.get("duration", 300)),
            }
        if block.subtype == "wait":
            return {"type": "wait", "duration": float(p.get("seconds", 2.0))}
        if block.subtype == "restart_app":
            return {"type": "restart_app", "package": p.get("package", "")}
        return {"type": block.subtype}
