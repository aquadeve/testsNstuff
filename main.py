"""MobileVisionBot — Multi-Device Android Automation Framework.

Entry point and orchestrator.  Run this script to start the automation engine:

    python main.py [--rules config/rules.json] [--fps 10] [--log-dir logs/] [--device SERIAL]

Press Ctrl+C to gracefully shut down all workers.
"""

from __future__ import annotations

import argparse
import logging
import os
import signal
import sys
import time
from typing import Optional

from core.device_manager import DeviceManager


# ── DEMO: Register a custom callback ──────────────────────────────────────
# Uncomment below to use a custom Python callback as a rule action.
#
# def on_play_detected(device_serial: str, match_location: tuple) -> None:
#     print(f"[DEMO] Play button found on {device_serial} at {match_location}")
#
# After worker creation, register it:
# worker.executor.register_callback("play_found", on_play_detected)
# ─────────────────────────────────────────────────────────────────────────


# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------

def _configure_logging(log_dir: str) -> None:
    """Configure root logger with both file and console handlers.

    Args:
        log_dir: Directory where ``automation.log`` will be written.
    """
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, "automation.log")

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)

    fmt = logging.Formatter(
        "%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # File handler — DEBUG and above.
    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)
    root.addHandler(fh)

    # Console handler — INFO and above.
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)
    root.addHandler(ch)

    logging.getLogger(__name__).info("Logging initialised → %s", log_file)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="main.py",
        description="MobileVisionBot — Multi-Device Android Automation Framework",
    )
    parser.add_argument(
        "--rules",
        default="config/rules.json",
        help="Path to the rules JSON file (default: config/rules.json).",
    )
    parser.add_argument(
        "--fps",
        type=int,
        default=10,
        help="Capture loop frequency in frames per second (default: 10).",
    )
    parser.add_argument(
        "--log-dir",
        default="logs/",
        help="Directory for log files (default: logs/).",
    )
    parser.add_argument(
        "--device",
        default=None,
        help="Target a single device serial instead of all connected devices.",
    )
    return parser.parse_args()


# ---------------------------------------------------------------------------
# Status display
# ---------------------------------------------------------------------------

def _print_status_table(manager: DeviceManager) -> None:
    """Print a formatted status table for all managed devices."""
    status = manager.get_status()
    if not status:
        print("  (no active devices)")
        return

    header = f"  {'SERIAL':<25} {'UPTIME':>10}  {'EVENTS':>7}  {'STUCK':>6}"
    print(header)
    print("  " + "-" * (len(header) - 2))
    for serial, info in status.items():
        print(
            f"  {serial:<25} {info['uptime_seconds']:>9.1f}s"
            f"  {info['event_count']:>7}  {str(info['is_stuck']):>6}"
        )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:  # noqa: C901
    args = _parse_args()
    _configure_logging(args.log_dir)
    log = logging.getLogger(__name__)

    # Validate rules file.
    if not os.path.isfile(args.rules):
        print(f"ERROR: Rules file not found: {args.rules}", file=sys.stderr)
        sys.exit(1)

    config = {
        "fps": args.fps,
    }

    manager = DeviceManager(rules_path=args.rules, config=config)

    # If --device was specified, limit discovery to just that serial.
    if args.device:
        from devices.device_worker import DeviceWorker
        log.info("Targeting single device: %s", args.device)
        worker = manager.create_worker(args.device)
        worker.start()
    else:
        # Discover all connected devices.
        serials = manager.discover_devices()
        if not serials:
            print(
                "ERROR: No ADB devices found.  Connect a device or start an emulator.",
                file=sys.stderr,
            )
            sys.exit(1)
        manager.start_all()

    # ── Graceful shutdown ─────────────────────────────────────────────
    shutdown_requested = False

    def _shutdown(signum: int, frame: object) -> None:  # noqa: ARG001
        nonlocal shutdown_requested
        shutdown_requested = True

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    # ── Status loop ───────────────────────────────────────────────────
    log.info("Automation engine running.  Press Ctrl+C to stop.")
    try:
        while not shutdown_requested:
            time.sleep(10)
            print(f"\n{'─' * 60}")
            print(f"  STATUS  ({time.strftime('%H:%M:%S')})")
            print(f"{'─' * 60}")
            _print_status_table(manager)
    except KeyboardInterrupt:
        pass

    # ── Cleanup ───────────────────────────────────────────────────────
    print("\nShutting down…")
    manager.stop_all()
    log.info("Shutdown complete.")


if __name__ == "__main__":
    main()
