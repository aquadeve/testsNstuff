"""State Manager — per-device runtime state and recovery detection.

Each :class:`~devices.device_worker.DeviceWorker` owns one ``StateManager``
that stores a rolling buffer of recent screenshots, timestamps events, and
exposes stuck-state detection.

All public methods are thread-safe via an internal :class:`threading.Lock`.
"""

from __future__ import annotations

import collections
import logging
import threading
import time
from typing import Any, Deque, Dict, List, Optional, Tuple

import numpy as np

from core.vision_engine import VisionEngine

logger = logging.getLogger(__name__)

_MAX_EVENTS: int = 1000
_DEFAULT_BUFFER_LEN: int = 10


class StateManager:
    """Tracks the runtime state of a single device.

    Args:
        serial: The ADB device serial number.
        vision_engine: Vision engine instance used by :meth:`is_stuck`.
        buffer_len: Maximum number of frames to retain in the rolling buffer.
    """

    def __init__(
        self,
        serial: str,
        vision_engine: VisionEngine,
        buffer_len: int = _DEFAULT_BUFFER_LEN,
    ) -> None:
        self._serial = serial
        self._vision = vision_engine
        self._lock = threading.Lock()
        self._start_time: float = time.monotonic()

        # Rolling deque of (timestamp, grayscale_frame) tuples.
        self._buffer: Deque[Tuple[float, np.ndarray]] = collections.deque(maxlen=buffer_len)

        # In-memory event log.
        self._events: List[Dict[str, Any]] = []

    # ------------------------------------------------------------------
    # Frame updates
    # ------------------------------------------------------------------

    def update(self, screen: np.ndarray) -> None:
        """Add a new captured frame to the rolling buffer.

        Converts the frame to grayscale before storing to reduce memory usage.

        Args:
            screen: Current device screenshot (BGR or grayscale NumPy array).
        """
        import cv2
        if screen.ndim == 3:
            gray = cv2.cvtColor(screen, cv2.COLOR_BGR2GRAY)
        else:
            gray = screen.copy()

        ts = time.monotonic()
        with self._lock:
            self._buffer.append((ts, gray))

    def get_last_screen(self) -> Optional[np.ndarray]:
        """Return the most recently captured grayscale frame, or ``None``.

        Returns:
            The latest grayscale frame stored in the buffer, or ``None`` if the
            buffer is empty.
        """
        with self._lock:
            if not self._buffer:
                return None
            return self._buffer[-1][1]

    # ------------------------------------------------------------------
    # Stuck detection
    # ------------------------------------------------------------------

    def is_stuck(
        self,
        threshold: float = 30.0,
        window: float = 15.0,
    ) -> bool:
        """Return ``True`` if the screen has not changed meaningfully.

        Compares the oldest frame within the last *window* seconds against the
        most recent frame.  Returns ``False`` if fewer than two frames are
        available.

        Args:
            threshold: Mean pixel-intensity difference below which screens are
                considered identical (passed to
                :meth:`~core.vision_engine.VisionEngine.diff_screens`).
            window: Time window in seconds over which to check for change.

        Returns:
            ``True`` if the device appears stuck.
        """
        with self._lock:
            if len(self._buffer) < 2:
                return False

            now = time.monotonic()
            cutoff = now - window

            # Find the oldest frame within the window.
            oldest: Optional[np.ndarray] = None
            for ts, frame in self._buffer:
                if ts >= cutoff:
                    oldest = frame
                    break

            if oldest is None:
                # All frames are older than the window; use the very first one.
                oldest = self._buffer[0][1]

            newest = self._buffer[-1][1]

        # diff_screens is non-blocking and doesn't need the lock.
        changed = self._vision.diff_screens(oldest, newest, threshold=threshold)
        stuck = not changed
        if stuck:
            logger.debug("Device %s appears stuck (no change in %.1fs).", self._serial, window)
        return stuck

    # ------------------------------------------------------------------
    # Event logging
    # ------------------------------------------------------------------

    def record_event(self, event_type: str, detail: str) -> None:
        """Append an event to the in-memory event log.

        The log is capped at :data:`_MAX_EVENTS` entries (oldest entries are
        dropped when the limit is reached).

        Args:
            event_type: Short category string, e.g. ``"rule_triggered"``.
            detail: Human-readable event description.
        """
        event: Dict[str, Any] = {
            "timestamp": time.time(),
            "type": event_type,
            "detail": detail,
        }
        with self._lock:
            if len(self._events) >= _MAX_EVENTS:
                self._events.pop(0)
            self._events.append(event)

    # ------------------------------------------------------------------
    # State summary
    # ------------------------------------------------------------------

    def get_state_summary(self) -> Dict[str, Any]:
        """Return a snapshot of current device state.

        Returns:
            Dictionary with keys: ``serial``, ``uptime_seconds``,
            ``event_count``, ``is_stuck``, and ``state_manager`` (self).
        """
        with self._lock:
            event_count = len(self._events)

        uptime = time.monotonic() - self._start_time
        stuck = self.is_stuck()

        return {
            "serial": self._serial,
            "uptime_seconds": round(uptime, 1),
            "event_count": event_count,
            "is_stuck": stuck,
            # Provide reference to self so RuleEngine no_change condition can call is_stuck().
            "state_manager": self,
        }
