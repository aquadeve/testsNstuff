# MobileVisionBot — Multi-Device Android Automation Framework

![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-blue?logo=python)
![OpenCV](https://img.shields.io/badge/OpenCV-4.8%2B-green?logo=opencv)
![ADB](https://img.shields.io/badge/ADB-Android%20Platform%20Tools-orange)

---

## Overview

**MobileVisionBot** is a reactive, event-driven automation engine for Android
lab testing.  It connects to one or more Android devices via ADB, continuously
captures their screens at up to 10 FPS, and executes declarative rules whenever
specific UI elements or visual conditions are detected.

This is **not** a linear macro player.  Rules evaluate every frame and fire
whenever their conditions are met, making the system suitable for resilient,
long-running test automation where screen state is unpredictable.

---

## Features

- 📱 **Multi-device support** — connects to any number of USB or WiFi-ADB devices simultaneously
- 🔍 **Image recognition** — OpenCV template matching with configurable thresholds and sub-regions
- 🎨 **Colour detection** — HSV-space colour presence checks
- 🔄 **Stuck detection & recovery** — automatically restarts apps when the screen stops changing
- 📋 **Declarative rules** — define automation logic entirely in `config/rules.json`
- ⚡ **Priority & cooldowns** — rules are prioritised and rate-limited to prevent spam
- 🐍 **Python callback hooks** — register custom Python functions as rule actions
- 🧵 **Thread-per-device** — each device runs an independent capture-analyse-act loop
- 📝 **Structured logging** — per-device log streams to both console and rotating log files

---

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/aquadeve/testsNstuff.git
cd testsNstuff
```

### 2. Install Python dependencies

```bash
pip install -r requirements.txt
```

> Requires **Python 3.11+**.  A virtual environment is recommended:
> ```bash
> python -m venv .venv && source .venv/bin/activate
> ```

### 3. Install ADB (Android Platform Tools)

- **macOS:** `brew install android-platform-tools`
- **Ubuntu/Debian:** `sudo apt install adb`
- **Windows:** Download from [developer.android.com/tools/releases/platform-tools](https://developer.android.com/tools/releases/platform-tools)

Verify installation:

```bash
adb version
adb devices
```

---

## Quick Start

1. Connect an Android device (USB debugging enabled) or start an emulator.
2. Confirm the device is visible: `adb devices`
3. Add template images to `assets/` (see [Template Images](#adding-template-images))
4. Edit `config/rules.json` to define your automation rules.
5. Run the framework:

```bash
python main.py
```

---

## Rules JSON Schema Reference

Each entry in `config/rules.json` is a rule object:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | ✅ | Unique rule identifier |
| `enabled` | bool | — | Set to `false` to disable without deleting (default `true`) |
| `priority` | int | — | Lower number = higher priority (default 99) |
| `cooldown` | float | — | Minimum seconds between consecutive triggers (default 0) |
| `condition` | object | ✅ | Condition that must be satisfied to trigger the rule |
| `action` | object | ✅ | Action to execute when the condition is met |

### Condition types

#### `"image"` — template matching

```json
{
  "type": "image",
  "target": "play_button.png",
  "threshold": 0.85,
  "region": null
}
```

| Key | Type | Description |
|-----|------|-------------|
| `target` | string | Filename inside `assets/` |
| `threshold` | float | Match confidence 0–1 (default 0.85) |
| `region` | `[x, y, w, h]` or `null` | Restrict search to a sub-rectangle |

#### `"color"` — HSV colour detection

```json
{
  "type": "color",
  "color_hsv": [120, 100, 100],
  "tolerance": 30,
  "region": [0, 1700, 1080, 200]
}
```

#### `"no_change"` — stuck-state detection

```json
{
  "type": "no_change",
  "window": 15
}
```

`window` is the number of seconds over which the screen must remain static.

### Action types

| `type` | Extra keys | Description |
|--------|-----------|-------------|
| `"tap"` | `"position": "center_of_match"` or `[x, y]` | Tap a screen coordinate |
| `"swipe"` | `"from": [x,y]`, `"to": [x,y]`, `"duration": ms` | Swipe gesture |
| `"wait"` | `"duration": seconds` | Sleep the worker thread |
| `"restart_app"` | `"package": "com.example.app"` | Force-stop + relaunch |
| `"callback"` | `"name": "callback_name"` | Invoke a registered Python function |

---

## Adding Template Images

Place PNG or JPG screenshots of UI elements you want to detect inside the
`assets/` directory.  The filename must **exactly match** the `"target"` field
in your rule.

See [`assets/README.md`](assets/README.md) for detailed capture instructions.

---

## Registering Python Callbacks

Callbacks allow arbitrary Python code to run when a rule fires.

```python
# In main.py, after creating the DeviceManager but before start_all():
def on_play_detected(device_serial: str, match_location: tuple) -> None:
    print(f"[CALLBACK] Play button found on {device_serial} at {match_location}")

# Retrieve the worker and register:
worker = manager._workers.get("your-device-serial")
if worker:
    worker.executor.register_callback("play_found", on_play_detected)
```

Then in `config/rules.json`, add an action:

```json
{
  "type": "callback",
  "name": "play_found"
}
```

---

## CLI Usage

```
usage: main.py [-h] [--rules RULES] [--fps FPS] [--log-dir LOG_DIR] [--device DEVICE]

MobileVisionBot — Multi-Device Android Automation Framework

options:
  -h, --help         show this help message and exit
  --rules RULES      Path to the rules JSON file (default: config/rules.json)
  --fps FPS          Capture loop frequency in frames per second (default: 10)
  --log-dir LOG_DIR  Directory for log files (default: logs/)
  --device DEVICE    Target a single device serial instead of all connected devices
```

**Examples:**

```bash
# Run with defaults (all connected devices, 10 FPS)
python main.py

# Run at 5 FPS targeting a single device
python main.py --fps 5 --device emulator-5554

# Use a custom rules file
python main.py --rules my_rules.json

# Save logs to a custom directory
python main.py --log-dir /var/log/mobilebot/
```

---

## Project Structure

```
/core
    __init__.py
    device_manager.py     Central orchestrator — creates and manages workers
    vision_engine.py      OpenCV template matching, colour & diff detection
    rule_engine.py        JSON rule loading, evaluation, cooldowns
    action_executor.py    ADB action dispatch (tap, swipe, restart, callback)
    state_manager.py      Per-device frame buffer & stuck detection
/devices
    __init__.py
    device_worker.py      Per-device threaded capture-analyse-act loop
/config
    rules.json            Sample automation rules
/utils
    __init__.py
    adb.py                ADB subprocess wrappers (with retries)
    image.py              PNG ↔ OpenCV conversion + template caching
/assets
    README.md             Template image documentation
main.py                   CLI entry point
requirements.txt
README.md
```

---

## Troubleshooting

### ADB not found

```
EnvironmentError: ADB binary not found in PATH.
```

Install Android Platform Tools and ensure `adb` is on your `PATH`:

```bash
export PATH="$PATH:/path/to/platform-tools"
adb version
```

### Device not detected

```
ERROR: No ADB devices found.
```

- Check USB debugging is enabled on the device (**Settings → Developer Options → USB Debugging**).
- Accept the RSA key prompt on the device screen if present.
- Try: `adb kill-server && adb start-server && adb devices`
- For WiFi ADB: `adb connect <device-ip>:5555`

### Low FPS / slow captures

- Reduce `--fps` (e.g. `--fps 5`) to ease ADB pressure.
- Use `"region"` in image/colour conditions to limit search areas.
- Ensure USB 3.0 cable is used for wired devices.

### Template not matching

- Verify the template file exists in `assets/` and the filename matches `"target"` exactly.
- Capture the template **at the same screen resolution** as your test device.
- Try lowering `"threshold"` slightly (e.g. `0.80`) to allow for minor rendering differences.
- Use `"region"` to focus on the area of the screen where the element appears.
