"""ADB utility functions for interacting with Android devices.

Provides wrappers around the ``adb`` command-line tool for device discovery,
screen capture, and input injection.  All public functions handle subprocess
errors gracefully and raise :class:`EnvironmentError` when ADB is unavailable.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import time
from typing import List

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_ADB_TIMEOUT_SECONDS: int = 10
_MAX_RETRIES: int = 3
_RETRY_DELAY_SECONDS: float = 1.0


def _adb_path() -> str:
    """Return the resolved path to the ``adb`` binary.

    Raises:
        EnvironmentError: If ``adb`` is not found on :envvar:`PATH`.
    """
    path = shutil.which("adb")
    if path is None:
        raise EnvironmentError(
            "ADB binary not found in PATH.  "
            "Install Android SDK Platform-Tools and ensure 'adb' is on PATH."
        )
    return path


def _run(
    args: List[str],
    *,
    capture_output: bool = True,
    timeout: int = _ADB_TIMEOUT_SECONDS,
    retries: int = _MAX_RETRIES,
) -> subprocess.CompletedProcess:
    """Execute an ADB command with retry logic.

    Args:
        args: Full argument list, e.g. ``["adb", "-s", serial, "shell", "..."]``.
        capture_output: Whether to capture stdout/stderr.
        timeout: Per-attempt timeout in seconds.
        retries: Maximum number of attempts.

    Returns:
        The completed process result from the last successful attempt.

    Raises:
        subprocess.CalledProcessError: After all retries are exhausted.
    """
    last_exc: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            result = subprocess.run(
                args,
                capture_output=capture_output,
                timeout=timeout,
                check=True,
            )
            return result
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            last_exc = exc
            logger.warning(
                "ADB command failed (attempt %d/%d): %s — %s",
                attempt,
                retries,
                " ".join(str(a) for a in args),
                exc,
            )
            if attempt < retries:
                time.sleep(_RETRY_DELAY_SECONDS)
    raise last_exc  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def list_devices() -> List[str]:
    """Return a list of serial numbers for all connected ADB devices.

    Only devices in the **device** state are returned (not *offline* or
    *unauthorized* entries).

    Returns:
        A list of device serial strings, e.g. ``["emulator-5554", "192.168.1.5:5555"]``.

    Raises:
        EnvironmentError: If ADB is not installed.
    """
    adb = _adb_path()
    result = _run([adb, "devices"])
    lines = result.stdout.decode("utf-8", errors="replace").splitlines()
    serials: List[str] = []
    for line in lines[1:]:  # skip "List of devices attached" header
        parts = line.strip().split()
        if len(parts) >= 2 and parts[1] == "device":
            serials.append(parts[0])
    logger.debug("Discovered %d device(s): %s", len(serials), serials)
    return serials


def screenshot(serial: str) -> bytes:
    """Capture a screenshot from the device and return raw PNG bytes.

    Uses ``exec-out screencap -p`` which streams PNG data directly without
    writing a temporary file on the device.

    Args:
        serial: The ADB device serial number.

    Returns:
        Raw PNG-encoded bytes of the current device screen.

    Raises:
        EnvironmentError: If ADB is not installed.
        subprocess.CalledProcessError: If the screencap command fails.
    """
    adb = _adb_path()
    result = _run(
        [adb, "-s", serial, "exec-out", "screencap", "-p"],
        timeout=15,
    )
    return result.stdout


def tap(serial: str, x: int, y: int) -> None:
    """Send a tap event to the specified screen coordinates.

    Args:
        serial: The ADB device serial number.
        x: Horizontal pixel coordinate.
        y: Vertical pixel coordinate.

    Raises:
        EnvironmentError: If ADB is not installed.
    """
    adb = _adb_path()
    _run([adb, "-s", serial, "shell", "input", "tap", str(x), str(y)])
    logger.debug("Tapped (%d, %d) on device %s", x, y, serial)


def swipe(
    serial: str,
    x1: int,
    y1: int,
    x2: int,
    y2: int,
    duration_ms: int = 300,
) -> None:
    """Send a swipe gesture between two screen coordinates.

    Args:
        serial: The ADB device serial number.
        x1: Start horizontal coordinate.
        y1: Start vertical coordinate.
        x2: End horizontal coordinate.
        y2: End vertical coordinate.
        duration_ms: Gesture duration in milliseconds.

    Raises:
        EnvironmentError: If ADB is not installed.
    """
    adb = _adb_path()
    _run(
        [
            adb, "-s", serial, "shell", "input", "swipe",
            str(x1), str(y1), str(x2), str(y2), str(duration_ms),
        ]
    )
    logger.debug(
        "Swiped (%d,%d)→(%d,%d) dur=%dms on device %s",
        x1, y1, x2, y2, duration_ms, serial,
    )


def launch_app(serial: str, package: str) -> None:
    """Launch an application by package name using the monkey runner.

    Args:
        serial: The ADB device serial number.
        package: Android package name, e.g. ``"com.example.app"``.

    Raises:
        EnvironmentError: If ADB is not installed.
    """
    adb = _adb_path()
    _run(
        [
            adb, "-s", serial, "shell", "monkey",
            "-p", package, "-c", "android.intent.category.LAUNCHER", "1",
        ]
    )
    logger.info("Launched app %s on device %s", package, serial)


def force_stop(serial: str, package: str) -> None:
    """Force-stop an application by package name.

    Args:
        serial: The ADB device serial number.
        package: Android package name.

    Raises:
        EnvironmentError: If ADB is not installed.
    """
    adb = _adb_path()
    _run([adb, "-s", serial, "shell", "am", "force-stop", package])
    logger.info("Force-stopped app %s on device %s", package, serial)
