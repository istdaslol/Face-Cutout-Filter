# Gesichtsfilter

Gesichtsfilter turns your webcam into a cartoon character: your eyes and mouth are cut out of the live
camera image and placed onto a PNG picture (a drawing, a photo, a mascot), which follows your head.
The result can be sent to Zoom, Teams, Discord, OBS and similar programs as a virtual camera.

This is the native Windows port (Python, PySide6) of the browser version `gesichts-filter.html`.
The user interface is in German. Everything runs locally on your computer, no image data is sent anywhere,
and the face model is bundled (no download at runtime).

Deutsche Version: [README.de.md](README.de.md)

> **Notice:** This software was generated with the help of AI (Claude by Anthropic). It is provided as is,
> without warranty of any kind. Please test it yourself before relying on it.

Current version: 0.3.0

## Features

- Three modes: "Einfach" (one PNG follows the face, no body), one PNG with markers (head, neck, body),
  or two PNGs (head + body).
- Eyes and mouth are live from the camera, with separate size and cut-out margin controls for eyes and mouth.
- Optional eyebrows, mirroring, soft edges, rest pose, head-following strength, head tracking on/off.
- Backgrounds: camera image, green screen, black, white.
- Output as virtual camera (OBS Virtual Camera, Unity Capture on Windows, v4l2loopback on Linux).
- Photo button and "Foto in 3 s" (saved to your Pictures folder, subfolder `Gesichtsfilter`).
- Save and load profiles (all settings) as files. Markers are stored per image (by checksum), not next to the image.
- Performance options: frame rate limit, tracking every frame or every 2nd frame, CPU/GPU tracking,
  low priority, preview on/off.

## Installation (Windows 10/11, 64 bit)

1. Download `Gesichtsfilter-Setup-<version>.exe` from the
   [Releases](../../releases) page and run it.
2. In the installer choose a virtual camera option (see below).
3. Start "Gesichtsfilter" from the Start menu.

Windows SmartScreen may warn about an unknown publisher, because the installer is not code-signed.
Each release also contains a `.sha256` file to verify the download:

    certutil -hashfile Gesichtsfilter-Setup-<version>.exe SHA256

### Virtual camera: prerequisite

To use the filtered picture in other programs, ONE virtual camera driver is needed:

- **OBS Studio** (https://obsproject.com), installed once and started at least once so that
  "OBS Virtual Camera" is registered. You do not need to keep OBS open. OR
- **Unity Capture**: an optional component of this installer ("Unity Capture (virtuelle Kamera)"; not
  selected by default). You can choose the camera name, default "Gesichtsfilter". Unity Capture is
  MIT-licensed (license text is installed with the program).

Without a virtual camera driver the program still works (preview, photos); it only shows a hint
instead of the virtual camera. In the program you can pick the backend ("Automatisch", OBS Virtual Camera
or Unity Capture) and, for Unity Capture, the device name.

Silent installation (for administrators):

    Gesichtsfilter-Setup-<version>.exe /VERYSILENT /COMPONENTS="main,unity" /CAMNAME="My camera"

## Quick start

1. Choose your camera and click "Kamera starten".
2. Choose a mode and load a PNG ("Eigene Datei", "Erdnuss" example, or "Demo"). Drag and drop and Ctrl+V also work.
3. Set the markers (eyes, mouth, and in the other modes head/neck/body anchors) by dragging them in the editor.
4. Sit straight in front of the camera and click "Ruhelage setzen".
5. Click "Virtuelle Kamera starten" and select the camera "Gesichtsfilter" (or "OBS Virtual Camera")
   in your video program.

## Where data is stored

| What | Windows | Linux |
| --- | --- | --- |
| Last used settings | `%APPDATA%\Gesichtsfilter\zuletzt.json` | `~/.gesichtsfilter/` |
| Markers per image | `%APPDATA%\Gesichtsfilter\marker\<sha256>.json` | `~/.gesichtsfilter/marker/` |
| Log file | `%APPDATA%\Gesichtsfilter\log.txt` | `~/.gesichtsfilter/` |
| Photos | `Pictures\Gesichtsfilter` | `~/Pictures/Gesichtsfilter` |

To reset the settings, delete `zuletzt.json`.

## Linux (Ubuntu, apt)

    chmod +x install.sh
    ./install.sh --dry-run     # shows what would happen
    ./install.sh               # system packages, Python 3.11-3.13, .venv, packages, model, v4l2loopback
    gesichtsfilter             # starts the program
    ./install.sh --uninstall

The script creates the virtual camera `/dev/video10` named "Gesichtsfilter" (v4l2loopback). With Secure
Boot the kernel module must be signed (the script tells you). Tested on Ubuntu 24.04; other distributions
are untested. Under WSL2 there is no webcam and no virtual camera; use the Windows version there.
More options: `./install.sh --help`.

## Development

Requirements: Python 3.11 (64 bit) for Windows builds; Python 3.11-3.13 for running from source.

    py -3.11 -m venv .venv
    .\.venv\Scripts\Activate.ps1
    pip install -r requirements-dev.txt
    python tools\fetch_model.py
    pytest -q
    python run.py

Build the installer locally (needs [Inno Setup 6](https://jrsoftware.org/isdl.php)):

    python packaging\make_installer.py

This fetches the model and the Unity Capture filters (pinned commit, SHA256 verified), builds with
PyInstaller in `--onedir` mode, runs the built program's `--selftest`, and compiles
`installer_out\Gesichtsfilter-Setup-<version>.exe`. See `SETUP_ENTWICKLUNG.txt` for details.

### Releases

Pushing a tag `v<version>` (for example `v0.3.0`; it must match `__version__` in
`src/gesichtsfilter/__init__.py`) starts the GitHub Actions workflow `.github/workflows/release.yml`.
It runs the tests, builds the program and the installer on `windows-latest`, and attaches
`Gesichtsfilter-Setup-<version>.exe` plus a SHA256 file to a GitHub release.

## Troubleshooting

- **Hint "Es wurde keine virtuelle Kamera gefunden":** install OBS Studio and start it once, or reinstall with the
  Unity Capture component.
- **Camera name not shown in the video program:** restart the video program after starting the virtual camera.
- **Program does not start:** look at `%APPDATA%\Gesichtsfilter\log.txt`; run
  `Gesichtsfilter.exe --selftest report.txt` and check `report.txt`.
- **No face detected:** better light, face the camera; for GPU problems choose "Tracking auf CPU".

## Third-party components

MediaPipe (Apache-2.0, face landmark model), OpenCV, NumPy, PySide6 / Qt (LGPL), pyvirtualcam,
Unity Capture by Bernhard Schelling (MIT). Please check the respective licenses before redistributing.

## License

Gesichtsfilter is licensed under the GNU General Public License v3.0 (GPL-3.0); see the `LICENSE` file in the repository.
The third-party components above keep their own licenses, which are compatible with the GPL-3.0.
