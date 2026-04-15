"""Action Executor — translates rule actions into ADB commands.

Each :class:`~devices.device_worker.DeviceWorker` owns one ``ActionExecutor``
bound to a single device serial.  It maps declarative action dicts (from
``config/rules.json``) to the low-level ADB utility functions in
:mod:`utils.adb`.

Supported action types:
    ``"tap"``          — touch a point or the centre of a template match.
    ``"swipe"``        — drag between two points.
    ``"wait"``         — sleep for a given number of seconds.
    ``"restart_app"``  — force-stop then relaunch an application.
    ``"callback"``     — invoke a registered Python callable.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Callable, Dict, Optional, Tuple

import utils.adb as adb

logger = logging.getLogger(__name__)

# Type alias for action dictionaries.
ActionDict = Dict[str, Any]
# Callback signature: fn(device_serial, match_location) -> None
CallbackFn = Callable[[str, Tuple[int, int]], None]


class ActionExecutor:
    """Executes automation actions for a single Android device.

    Args:
        serial: The ADB device serial number this executor is bound to.
    """

    def __init__(self, serial: str) -> None:
        self._serial = serial
        self._callbacks: Dict[str, CallbackFn] = {}

    # ------------------------------------------------------------------
    # Callback registry
    # ------------------------------------------------------------------

    def register_callback(self, name: str, fn: CallbackFn) -> None:
        """Register a Python callable that can be triggered by a ``"callback"`` action.

        The callable will be invoked as ``fn(device_serial, match_location)``
        where ``match_location`` is an ``(x, y)`` tuple.

        Args:
            name: The callback name referenced in the rule's ``action.name``.
            fn: A callable with signature ``(serial: str, location: tuple) -> None``.
        """
        self._callbacks[name] = fn
        logger.debug("Registered callback '%s' for device %s", name, self._serial)

    # ------------------------------------------------------------------
    # Action dispatch
    # ------------------------------------------------------------------

    def execute(
        self,
        action: ActionDict,
        match_location: Tuple[int, int] = (0, 0),
    ) -> None:
        """Execute a single action dict.

        Dispatches to the appropriate handler based on ``action["type"]``.

        Args:
            action: Action dictionary from a rule, e.g.
                ``{"type": "tap", "position": "center_of_match"}``.
            match_location: ``(cx, cy)`` centre coordinates of the template
                match, used when ``"position"`` is ``"center_of_match"``.
        """
        action_type: str = action.get("type", "")

        handlers = {
            "tap": self._do_tap,
            "swipe": self._do_swipe,
            "wait": self._do_wait,
            "restart_app": self._do_restart_app,
            "callback": self._do_callback,
        }

        handler = handlers.get(action_type)
        if handler is None:
            logger.warning("Unknown action type '%s' on device %s", action_type, self._serial)
            return

        try:
            handler(action, match_location)
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "Action '%s' failed on device %s: %s",
                action_type, self._serial, exc,
                exc_info=True,
            )

    # ------------------------------------------------------------------
    # Individual action handlers
    # ------------------------------------------------------------------

    def _do_tap(self, action: ActionDict, match_location: Tuple[int, int]) -> None:
        """Handle ``"tap"`` action."""
        position = action.get("position", "center_of_match")

        if position == "center_of_match":
            x, y = match_location
        elif isinstance(position, (list, tuple)) and len(position) == 2:
            x, y = int(position[0]), int(position[1])
        else:
            logger.warning(
                "Unsupported tap position '%s' on device %s, using match location.",
                position, self._serial,
            )
            x, y = match_location

        adb.tap(self._serial, x, y)
        logger.info("Tap (%d, %d) executed on device %s", x, y, self._serial)

    def _do_swipe(self, action: ActionDict, _match_location: Tuple[int, int]) -> None:
        """Handle ``"swipe"`` action."""
        from_pos = action.get("from", [0, 0])
        to_pos = action.get("to", [0, 0])
        duration: int = int(action.get("duration", 300))

        x1, y1 = int(from_pos[0]), int(from_pos[1])
        x2, y2 = int(to_pos[0]), int(to_pos[1])

        adb.swipe(self._serial, x1, y1, x2, y2, duration_ms=duration)
        logger.info(
            "Swipe (%d,%d)→(%d,%d) dur=%dms executed on device %s",
            x1, y1, x2, y2, duration, self._serial,
        )

    def _do_wait(self, action: ActionDict, _match_location: Tuple[int, int]) -> None:
        """Handle ``"wait"`` action — blocks the worker thread briefly."""
        duration: float = float(action.get("duration", 1.0))
        logger.debug("Wait %.2fs on device %s", duration, self._serial)
        time.sleep(duration)

    def _do_restart_app(self, action: ActionDict, _match_location: Tuple[int, int]) -> None:
        """Handle ``"restart_app"`` action — force-stop then relaunch."""
        package: Optional[str] = action.get("package")
        if not package:
            logger.warning("restart_app action missing 'package' on device %s", self._serial)
            return

        logger.info("Restarting app %s on device %s", package, self._serial)
        adb.force_stop(self._serial, package)
        time.sleep(1.0)  # Brief pause to let the OS clean up.
        adb.launch_app(self._serial, package)

    def _do_callback(self, action: ActionDict, match_location: Tuple[int, int]) -> None:
        """Handle ``"callback"`` action — call a registered Python function."""
        name: str = action.get("name", "")
        fn = self._callbacks.get(name)
        if fn is None:
            logger.warning(
                "Callback '%s' not registered for device %s — ignoring.", name, self._serial
            )
            return

        logger.debug("Invoking callback '%s' on device %s", name, self._serial)
        fn(self._serial, match_location)
