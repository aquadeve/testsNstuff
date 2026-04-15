"""Image utility functions for converting and persisting screenshots.

Provides helpers to convert raw ADB screenshot bytes into OpenCV images,
load template images from disk (with caching), and save debug screenshots.
"""

from __future__ import annotations

import logging
import os
from typing import Dict, Optional

import cv2
import numpy as np

logger = logging.getLogger(__name__)

# Module-level template cache: path → loaded BGR image.
_template_cache: Dict[str, np.ndarray] = {}


def bytes_to_cv2(png_bytes: bytes) -> np.ndarray:
    """Convert raw PNG bytes to an OpenCV BGR image array.

    Args:
        png_bytes: Raw PNG-encoded bytes, typically from :func:`utils.adb.screenshot`.

    Returns:
        A NumPy ndarray in BGR colour format (H × W × 3, ``dtype=uint8``).

    Raises:
        ValueError: If the byte buffer cannot be decoded as an image.
    """
    if not png_bytes:
        raise ValueError("Empty PNG byte buffer provided to bytes_to_cv2.")
    buf = np.frombuffer(png_bytes, dtype=np.uint8)
    image = cv2.imdecode(buf, cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("cv2.imdecode returned None — invalid or corrupt PNG data.")
    return image


def load_template(path: str) -> Optional[np.ndarray]:
    """Load a template image from disk, with in-memory caching.

    Returns ``None`` and logs a warning if the file does not exist, so callers
    can gracefully skip matching rather than crashing.

    Args:
        path: Absolute or relative path to the template PNG/JPG file.

    Returns:
        An OpenCV BGR image array, or ``None`` if the file is missing.
    """
    if path in _template_cache:
        return _template_cache[path]

    if not os.path.isfile(path):
        logger.warning("Template file not found: %s", path)
        return None

    image = cv2.imread(path, cv2.IMREAD_COLOR)
    if image is None:
        logger.warning("Failed to decode template image: %s", path)
        return None

    _template_cache[path] = image
    logger.debug("Loaded and cached template: %s", path)
    return image


def save_screenshot(image: np.ndarray, path: str) -> None:
    """Save an OpenCV image to disk as a PNG file.

    Creates intermediate directories if they do not exist.

    Args:
        image: OpenCV BGR image array to save.
        path: Destination file path (should end with ``.png`` or ``.jpg``).
    """
    dir_name = os.path.dirname(os.path.abspath(path))
    if dir_name:
        os.makedirs(dir_name, exist_ok=True)
    success = cv2.imwrite(path, image)
    if success:
        logger.debug("Screenshot saved to %s", path)
    else:
        logger.warning("Failed to write screenshot to %s", path)
