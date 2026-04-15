"""Block data model for the Visual Automation Studio.

Each :class:`BlockData` represents a single block on the canvas — a
condition, action, or control element.

``BLOCK_DEFINITIONS`` is the single source of truth for every available
block type: its label, colour, icon, default parameters, and tooltip text.
"""

from __future__ import annotations

import copy
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict


# ── Block registry ────────────────────────────────────────────────────────
#
# Key   → subtype identifier used in serialisation and compilation.
# Value → metadata dict:
#     label           Human-readable name shown on the block tile.
#     category        "condition" | "action" | "control"
#     color           Hex colour for the block background.
#     icon            Emoji icon (single character / emoji).
#     default_params  Dict copied for each new block instance.
#     description     Tooltip text for beginners.

BLOCK_DEFINITIONS: Dict[str, Dict[str, Any]] = {
    # ── Conditions ──────────────────────────────────────────────────────
    "image_appears": {
        "label": "IF Image Appears",
        "category": "condition",
        "color": "#1976D2",
        "icon": "🔍",
        "default_params": {
            "image": "",
            "threshold": 0.85,
            "region": None,
        },
        "description": "Fires when a template image is detected on screen.",
    },
    "image_not_appears": {
        "label": "IF Image NOT Appears",
        "category": "condition",
        "color": "#1565C0",
        "icon": "🚫",
        "default_params": {
            "image": "",
            "threshold": 0.85,
            "region": None,
        },
        "description": "Fires when a template image is NOT found on screen.",
    },
    "color_detected": {
        "label": "IF Color Detected",
        "category": "condition",
        "color": "#0288D1",
        "icon": "🎨",
        "default_params": {
            "color_hsv": [120, 100, 100],
            "tolerance": 30,
            "region": None,
        },
        "description": "Fires when a specific HSV colour is present on screen.",
    },
    "screen_unchanged": {
        "label": "IF Screen Unchanged",
        "category": "condition",
        "color": "#01579B",
        "icon": "⏸",
        "default_params": {
            "window": 15.0,
        },
        "description": "Fires when the screen has not changed for N seconds.",
    },
    # ── Actions ─────────────────────────────────────────────────────────
    "tap": {
        "label": "Tap",
        "category": "action",
        "color": "#2E7D32",
        "icon": "👆",
        "default_params": {
            "position": [540, 960],
        },
        "description": "Tap at a specific (x, y) position on the device screen.",
    },
    "swipe": {
        "label": "Swipe",
        "category": "action",
        "color": "#1B5E20",
        "icon": "👋",
        "default_params": {
            "from": [540, 1800],
            "to": [540, 400],
            "duration": 300,
        },
        "description": "Swipe from one position to another.",
    },
    "wait": {
        "label": "Wait",
        "category": "action",
        "color": "#388E3C",
        "icon": "⏱",
        "default_params": {
            "seconds": 2.0,
        },
        "description": "Pause execution for a number of seconds.",
    },
    "restart_app": {
        "label": "Restart App",
        "category": "action",
        "color": "#33691E",
        "icon": "🔄",
        "default_params": {
            "package": "com.example.app",
        },
        "description": "Force-stop and relaunch an Android application.",
    },
    # ── Controls ────────────────────────────────────────────────────────
    "loop": {
        "label": "LOOP",
        "category": "control",
        "color": "#E65100",
        "icon": "🔁",
        "default_params": {
            "repeat": 0,  # 0 = infinite
        },
        "description": "Repeat enclosed blocks N times.  0 = loop forever.",
    },
    "wait_until": {
        "label": "WAIT UNTIL",
        "category": "control",
        "color": "#BF360C",
        "icon": "⌛",
        "default_params": {
            "timeout": 30.0,
        },
        "description": "Wait until a condition is met, up to timeout seconds.",
    },
}

# Human-readable section headers for the palette.
CATEGORY_LABELS: Dict[str, str] = {
    "condition": "Conditions",
    "action": "Actions",
    "control": "Control",
}


# ── BlockData dataclass ───────────────────────────────────────────────────

@dataclass
class BlockData:
    """Runtime representation of a single canvas block.

    Attributes:
        subtype:   Key into :data:`BLOCK_DEFINITIONS`.
        params:    Configurable parameters (deep-copied from defaults).
        block_id:  Unique short identifier (8-char UUID fragment).
        enabled:   Whether this block participates in rule compilation.
    """

    subtype: str
    params: Dict[str, Any] = field(default_factory=dict)
    block_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    enabled: bool = True

    # ── Factory ───────────────────────────────────────────────────────

    @classmethod
    def from_subtype(cls, subtype: str) -> "BlockData":
        """Create a :class:`BlockData` with default params for *subtype*."""
        defn = BLOCK_DEFINITIONS.get(subtype, {})
        return cls(
            subtype=subtype,
            params=copy.deepcopy(defn.get("default_params", {})),
        )

    # ── Convenience properties ────────────────────────────────────────

    @property
    def definition(self) -> Dict[str, Any]:
        """Return the :data:`BLOCK_DEFINITIONS` entry for this block."""
        return BLOCK_DEFINITIONS.get(self.subtype, {})

    @property
    def label(self) -> str:
        return self.definition.get("label", self.subtype)

    @property
    def color(self) -> str:
        return self.definition.get("color", "#555577")

    @property
    def category(self) -> str:
        return self.definition.get("category", "action")

    @property
    def icon(self) -> str:
        return self.definition.get("icon", "")

    # ── Serialisation ─────────────────────────────────────────────────

    def to_dict(self) -> Dict[str, Any]:
        return {
            "block_id": self.block_id,
            "subtype": self.subtype,
            "params": copy.deepcopy(self.params),
            "enabled": self.enabled,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BlockData":
        return cls(
            subtype=data["subtype"],
            params=copy.deepcopy(data.get("params", {})),
            block_id=data.get("block_id", str(uuid.uuid4())[:8]),
            enabled=data.get("enabled", True),
        )
