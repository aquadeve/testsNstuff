"""Device Worker — per-device automation thread.

Each :class:`DeviceWorker` runs an independent capture-analyse-act loop inside
a :class:`threading.Thread`.  All component instances (vision engine, rule
engine, action executor, state manager) are owned by the worker so that state
is fully isolated between devices.

Loop sequence per iteration:
    1. Record loop start time.
    2. Capture screenshot via :func:`utils.adb.screenshot`.
    3. Convert raw bytes to OpenCV image.
    4. Update :class:`~core.state_manager.StateManager` with new frame.
    5. Check for stuck state → trigger recovery if configured.
    6. Evaluate all rules → execute triggered actions in priority order.
    7. Sleep for the remainder of the frame interval.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Dict, Optional

import utils.adb as adb
from utils.image import bytes_to_cv2
from core.vision_engine import VisionEngine
from core.rule_engine import RuleEngine
from core.action_executor import ActionExecutor
from core.state_manager import StateManager

logger = logging.getLogger(__name__)

_DEFAULT_FPS: int = 10
_ADB_FAILURE_THRESHOLD: int = 3
_ADB_FAILURE_SLEEP: float = 5.0


class DeviceWorker:
    """Automation worker for a single Android device.

    Args:
        serial: The ADB device serial number.
        rules_path: Path to the ``config/rules.json`` rules file.
        config: Optional configuration overrides.  Recognised keys:

            - ``"fps"`` (:class:`int`) — capture loop frequency (default 10).
            - ``"recovery_package"`` (:class:`str`) — package to restart on
              stuck detection.
    """

    def __init__(
        self,
        serial: str,
        rules_path: str,
        config: Optional[Dict[str, Any]] = None,
    ) -> None:
        self._serial = serial
        self._rules_path = rules_path
        self._config: Dict[str, Any] = config or {}

        self._fps: int = int(self._config.get("fps", _DEFAULT_FPS))
        self._frame_interval: float = 1.0 / max(self._fps, 1)

        # Per-device logger.
        self._log = logging.getLogger(f"device.{serial}")

        # Component instances.
        self.vision: VisionEngine = VisionEngine()
        self.rules: RuleEngine = RuleEngine(self.vision)
        self.executor: ActionExecutor = ActionExecutor(serial)
        self.state: StateManager = StateManager(serial, self.vision)

        # Thread control.
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Load rules and start the worker thread."""
        self.rules.load_rules(self._rules_path)
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run,
            name=f"worker-{self._serial}",
            daemon=True,
        )
        self._thread.start()
        self._log.info("Worker started (fps=%d).", self._fps)

    def stop(self) -> None:
        """Signal the worker to stop and wait for the thread to finish."""
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=15.0)
            if self._thread.is_alive():
                self._log.warning("Worker thread did not terminate within timeout.")
        self._log.info("Worker stopped.")

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    def _run(self) -> None:
        """Main capture-analyse-act loop executed in the worker thread."""
        adb_failures: int = 0

        while not self._stop_event.is_set():
            loop_start = time.monotonic()

            # ── Step 1: Capture screenshot ────────────────────────────
            try:
                raw_bytes = adb.screenshot(self._serial)
                screen = bytes_to_cv2(raw_bytes)
                adb_failures = 0  # Reset on success.
            except Exception as exc:  # noqa: BLE001
                adb_failures += 1
                self._log.error(
                    "Screenshot failed (consecutive failures: %d): %s",
                    adb_failures, exc,
                )
                if adb_failures >= _ADB_FAILURE_THRESHOLD:
                    self._log.warning(
                        "Too many consecutive ADB failures — sleeping %.1fs.", _ADB_FAILURE_SLEEP
                    )
                    time.sleep(_ADB_FAILURE_SLEEP)
                    adb_failures = 0
                self._sleep_remainder(loop_start)
                continue

            # ── Step 2: Update state manager ─────────────────────────
            self.state.update(screen)

            # ── Step 3: Stuck detection & recovery ───────────────────
            if self.state.is_stuck():
                self._log.warning("Device appears stuck — triggering recovery.")
                self.state.record_event("stuck_detected", "No visual change detected.")
                self._attempt_recovery()

            # ── Step 4: Rule evaluation ───────────────────────────────
            state_summary = self.state.get_state_summary()
            triggered_rules = self.rules.evaluate(screen, state_summary)

            for rule, location in triggered_rules:
                rule_name: str = rule["name"]
                action: Dict[str, Any] = rule["action"]
                self._log.info("Executing action for rule '%s'.", rule_name)
                self.state.record_event("rule_triggered", rule_name)
                self.executor.execute(action, match_location=location)
                self.rules.mark_triggered(rule_name)

            # ── Step 5: Sleep to maintain target FPS ─────────────────
            self._sleep_remainder(loop_start)

    def _sleep_remainder(self, loop_start: float) -> None:
        """Sleep for whatever remains of the current frame interval."""
        elapsed = time.monotonic() - loop_start
        remaining = self._frame_interval - elapsed
        if remaining > 0:
            time.sleep(remaining)

    def _attempt_recovery(self) -> None:
        """Execute a recovery action (restart app if package is configured)."""
        package: Optional[str] = self._config.get("recovery_package")
        if package:
            self._log.info("Recovery: restarting app %s.", package)
            try:
                adb.force_stop(self._serial, package)
                time.sleep(1.0)
                adb.launch_app(self._serial, package)
            except Exception as exc:  # noqa: BLE001
                self._log.error("Recovery action failed: %s", exc)
        else:
            self._log.info("Recovery: no package configured, skipping restart.")

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def get_status(self) -> Dict[str, Any]:
        """Return the current state summary for this device.

        Returns:
            Dict from :meth:`~core.state_manager.StateManager.get_state_summary`.
        """
        return self.state.get_state_summary()
