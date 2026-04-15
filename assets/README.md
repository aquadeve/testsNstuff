# Template Images for MobileVisionBot

This directory stores the **template images** used by the Vision Engine for
OpenCV template matching.  Each image represents a UI element (button, dialog,
icon) that the automation rules can detect on device screenshots.

---

## Supported Formats

| Format | Extension | Notes |
|--------|-----------|-------|
| PNG    | `.png`    | **Preferred** — lossless, supports transparency |
| JPEG   | `.jpg`    | Acceptable for full-colour assets without transparency |

---

## How to Capture a Template from a Device Screen

1. Connect your Android device and verify ADB connectivity:
   ```bash
   adb devices
   ```

2. Take a full-screen screenshot:
   ```bash
   adb -s <serial> exec-out screencap -p > screen.png
   ```

3. Open `screen.png` in any image editor (GIMP, Photoshop, Preview, Paint.NET)
   and **crop** the UI element you want to detect, saving it as a new PNG file.

4. Place the cropped file in this `assets/` directory with a descriptive name.

---

## Naming Convention

Template filenames must **exactly match** the `"target"` field in your rule
condition inside `config/rules.json`.

| Rule `"target"` value | File in this directory |
|-----------------------|------------------------|
| `"play_button.png"`   | `assets/play_button.png` |
| `"error_dialog.png"`  | `assets/error_dialog.png` |
| `"loading_spinner.png"` | `assets/loading_spinner.png` |

> **Case sensitivity:** filenames are case-sensitive on Linux/macOS.  Ensure
> the name in the JSON matches the file exactly.

---

## Tips for Good Templates

- **Unique region:** Choose a section of the UI that does not appear elsewhere
  on the screen (avoid generic icons or text).
- **Consistent state:** Capture the template in the exact visual state you want
  to detect (e.g., the play button *not* pressed, *not* grayed out).
- **Appropriate size:** Avoid templates that are too small (< 20 × 20 px) or
  too large, as both can reduce matching accuracy.
- **No device-specific artefacts:** Remove any status-bar icons or system UI
  from the template unless they are part of the intended match area.

---

## Example Files (add your own)

```
assets/
  play_button.png       ← Referenced by "detect_play_button" rule
  error_dialog.png      ← Referenced by "detect_error_dialog" rule
  README.md             ← This file
```
