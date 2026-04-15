"""Vision Engine — image recognition primitives for the automation framework.

Wraps OpenCV operations to provide template matching, colour detection, and
screen-difference detection.  All methods are stateless and thread-safe.
"""

from __future__ import annotations

import logging
from typing import Optional, Tuple

import cv2
import numpy as np

from utils.image import load_template

logger = logging.getLogger(__name__)

# Default confidence threshold for template matching.
DEFAULT_THRESHOLD: float = 0.85


class VisionEngine:
    """Performs visual analysis on captured device screenshots.

    All methods accept OpenCV BGR images as NumPy arrays.  ``find_template``
    and ``detect_color`` accept an optional ``region`` tuple to limit scanning
    to a sub-rectangle, which improves performance on high-resolution screens.

    Args:
        default_threshold: Minimum normalised correlation score (0–1) required
            for a template match to be considered a success.
    """

    def __init__(self, default_threshold: float = DEFAULT_THRESHOLD) -> None:
        self.default_threshold = default_threshold

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def find_template(
        self,
        screen: np.ndarray,
        template_path: str,
        threshold: Optional[float] = None,
        region: Optional[Tuple[int, int, int, int]] = None,
    ) -> Tuple[bool, Tuple[int, int], float]:
        """Search for a template image within a screenshot.

        Uses OpenCV normalised cross-correlation (``TM_CCOEFF_NORMED``).

        Args:
            screen: Full device screenshot as a BGR image array.
            template_path: Path to the template image file.
            threshold: Override the default match threshold (0–1).
            region: Optional ``(x, y, w, h)`` rectangle that limits the search
                area.  Coordinates are relative to the full screen.

        Returns:
            A tuple of ``(found, location, confidence)`` where:
            - ``found``: ``True`` if the best match meets the threshold.
            - ``location``: ``(cx, cy)`` centre pixel of the match in *full-screen*
              coordinates, or ``(0, 0)`` when not found.
            - ``confidence``: Normalised correlation score of the best match.
        """
        min_threshold = threshold if threshold is not None else self.default_threshold

        template = load_template(template_path)
        if template is None:
            # load_template already logs a warning.
            return False, (0, 0), 0.0

        # Optionally restrict scanning to a sub-region.
        if region is not None:
            rx, ry, rw, rh = region
            search_area = screen[ry : ry + rh, rx : rx + rw]
            offset_x, offset_y = rx, ry
        else:
            search_area = screen
            offset_x, offset_y = 0, 0

        # Template must be smaller than the search area.
        th, tw = template.shape[:2]
        sh, sw = search_area.shape[:2]
        if th > sh or tw > sw:
            logger.warning(
                "Template (%dx%d) is larger than search area (%dx%d) — skipping.",
                tw, th, sw, sh,
            )
            return False, (0, 0), 0.0

        result = cv2.matchTemplate(search_area, template, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(result)

        if max_val >= min_threshold:
            # Convert top-left match location to centre coordinates.
            cx = offset_x + max_loc[0] + tw // 2
            cy = offset_y + max_loc[1] + th // 2
            logger.debug(
                "Template '%s' matched at (%d, %d) confidence=%.3f",
                template_path, cx, cy, max_val,
            )
            return True, (cx, cy), float(max_val)

        logger.debug(
            "Template '%s' not matched (best=%.3f < threshold=%.3f)",
            template_path, max_val, min_threshold,
        )
        return False, (0, 0), float(max_val)

    def detect_color(
        self,
        screen: np.ndarray,
        color_hsv: Tuple[int, int, int],
        tolerance: int = 20,
        region: Optional[Tuple[int, int, int, int]] = None,
    ) -> bool:
        """Detect whether a specific colour is present in the screen.

        Converts the image to HSV colour space and checks for pixels within
        ``tolerance`` of ``color_hsv``.

        Args:
            screen: Full device screenshot as a BGR image array.
            color_hsv: Target colour as ``(H, S, V)`` where H∈[0,179],
                S∈[0,255], V∈[0,255].
            tolerance: Per-channel tolerance used to build the lower/upper HSV
                bounds.
            region: Optional ``(x, y, w, h)`` sub-region to search.

        Returns:
            ``True`` if at least one matching pixel is found.
        """
        if region is not None:
            rx, ry, rw, rh = region
            area = screen[ry : ry + rh, rx : rx + rw]
        else:
            area = screen

        hsv = cv2.cvtColor(area, cv2.COLOR_BGR2HSV)
        h, s, v = color_hsv

        lower = np.array(
            [max(0, h - tolerance), max(0, s - tolerance), max(0, v - tolerance)],
            dtype=np.uint8,
        )
        upper = np.array(
            [min(179, h + tolerance), min(255, s + tolerance), min(255, v + tolerance)],
            dtype=np.uint8,
        )

        mask = cv2.inRange(hsv, lower, upper)
        found = bool(cv2.countNonZero(mask) > 0)
        logger.debug("Color detection HSV=%s found=%s", color_hsv, found)
        return found

    def diff_screens(
        self,
        screen1: np.ndarray,
        screen2: np.ndarray,
        threshold: float = 30.0,
    ) -> bool:
        """Compare two frames to detect meaningful visual change.

        Computes the mean absolute difference between two grayscale frames.

        Args:
            screen1: First frame (BGR or grayscale).
            screen2: Second frame (BGR or grayscale).
            threshold: Mean pixel-intensity difference above which frames are
                considered different.

        Returns:
            ``True`` if the screens differ meaningfully (i.e. the mean
            difference exceeds *threshold*).
        """
        def _to_gray(img: np.ndarray) -> np.ndarray:
            if img.ndim == 3:
                return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            return img

        gray1 = _to_gray(screen1)
        gray2 = _to_gray(screen2)

        # Resize if shapes differ (e.g., between rotations).
        if gray1.shape != gray2.shape:
            gray2 = cv2.resize(gray2, (gray1.shape[1], gray1.shape[0]))

        diff = cv2.absdiff(gray1, gray2)
        mean_diff = float(np.mean(diff))
        changed = mean_diff > threshold
        logger.debug("Screen diff mean=%.2f threshold=%.2f changed=%s", mean_diff, threshold, changed)
        return changed
