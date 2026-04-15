"""Device Manager — central orchestrator for all device workers.

Discovers connected Android devices via ADB, creates a
:class:`~devices.device_worker.DeviceWorker` for each one, and provides
lifecycle management (start/stop all) plus a status overview.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import utils.adb as adb
from devices.device_worker import DeviceWorker

logger = logging.getLogger(__name__)


class DeviceManager:
    """Central controller that manages a pool of per-device worker threads.

    Args:
        rules_path: Path to the ``config/rules.json`` file shared by all workers.
        config: Optional configuration dict forwarded to each worker (e.g.
            ``{"fps": 10, "recovery_package": "com.example.app"}``).
    """

    def __init__(
        self,
        rules_path: str,
        config: Optional[Dict[str, Any]] = None,
    ) -> None:
        self._rules_path = rules_path
        self._config = config or {}
        self._workers: Dict[str, DeviceWorker] = {}

    # ------------------------------------------------------------------
    # Device discovery
    # ------------------------------------------------------------------

    def discover_devices(self) -> List[str]:
        """Return serial numbers of all currently connected ADB devices.

        Returns:
            List of device serial strings, e.g.
            ``["emulator-5554", "192.168.1.5:5555"]``.
        """
        serials = adb.list_devices()
        logger.info("Discovered %d device(s): %s", len(serials), serials)
        return serials

    # ------------------------------------------------------------------
    # Worker lifecycle
    # ------------------------------------------------------------------

    def create_worker(self, serial: str) -> DeviceWorker:
        """Instantiate (but do not start) a :class:`DeviceWorker` for *serial*.

        Args:
            serial: ADB device serial number.

        Returns:
            The newly created (idle) worker instance.
        """
        worker = DeviceWorker(serial, self._rules_path, config=self._config)
        self._workers[serial] = worker
        logger.debug("Created worker for device %s", serial)
        return worker

    def start_all(self) -> None:
        """Discover devices, create workers, and start them all.

        If no devices are found, a warning is logged but no exception is raised.
        """
        serials = self.discover_devices()
        if not serials:
            logger.warning("No ADB devices found — no workers started.")
            return

        for serial in serials:
            worker = self.create_worker(serial)
            worker.start()
            logger.info("Started worker for device %s", serial)

    def stop_all(self) -> None:
        """Signal all workers to stop and block until they terminate."""
        for serial, worker in self._workers.items():
            logger.info("Stopping worker for device %s", serial)
            worker.stop()
        self._workers.clear()
        logger.info("All workers stopped.")

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def get_status(self) -> Dict[str, Dict[str, Any]]:
        """Return a status snapshot for every managed device.

        Returns:
            Dict mapping device serial → state summary dict from
            :meth:`~core.state_manager.StateManager.get_state_summary`.
        """
        return {
            serial: worker.get_status()
            for serial, worker in self._workers.items()
        }
