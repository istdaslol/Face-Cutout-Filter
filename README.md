# Gesichtsfilter

Gesichtsfilter macht aus deiner Webcam eine Comicfigur: Augen und Mund werden live aus dem Kamerabild
ausgeschnitten und auf ein PNG-Bild gesetzt (Zeichnung, Foto, Maskottchen), das deinem Kopf folgt.
Das Ergebnis kann als virtuelle Kamera an Zoom, Teams, Discord, OBS und aehnliche Programme gesendet werden.

Dies ist die native Windows-Version (Python, PySide6) der Browser-Version `gesichts-filter.html`.
Die Oberflaeche ist deutsch. Alles laeuft lokal auf deinem Rechner, es werden keine Bilddaten gesendet,
und das Gesichtsmodell ist mitgeliefert (kein Download zur Laufzeit).

English version: [README.md](README.md)

> **Hinweis:** Diese Software wurde mit Hilfe von KI (Claude von Anthropic) erstellt. Sie wird so, wie sie
> ist, ohne jegliche Gewaehr bereitgestellt. Bitte teste sie selbst, bevor du dich darauf verlaesst.

Aktuelle Version: 0.3.0

## Funktionen

- Drei Modi: "Einfach" (ein PNG folgt dem Gesicht, ohne Koerper), ein PNG mit Markern (Kopf, Hals, Koerper)
  oder zwei PNGs (Kopf + Koerper).
- Augen und Mund kommen live von der Kamera; Groesse und Ausschnitt-Rand sind fuer Augen und Mund getrennt einstellbar.
- Optional: Augenbrauen, Spiegeln, weiche Kante, Ruhelage, Staerke des Kopf-Folgens, Kopfverfolgung an/aus.
- Hintergruende: Kamerabild, Greenscreen, Schwarz, Weiss.
- Ausgabe als virtuelle Kamera (OBS Virtual Camera, Unity Capture unter Windows, v4l2loopback unter Linux).
- Foto-Knopf und "Foto in 3 s" (gespeichert im Bilder-Ordner, Unterordner `Gesichtsfilter`).
- Profile (alle Einstellungen) als Datei speichern und laden. Marker werden pro Bild (ueber die Pruefsumme)
  gespeichert und nicht neben dem Bild.
- Leistungsoptionen: Bildratenlimit, Tracking jeden oder jeden 2. Frame, Tracking auf CPU/GPU,
  niedrige Prioritaet, Vorschau an/aus.

## Installation (Windows 10/11, 64 Bit)

1. `Gesichtsfilter-Setup-<Version>.exe` von der Seite
   [Releases](../../releases) herunterladen und ausfuehren.
2. Im Installer eine Option fuer die virtuelle Kamera waehlen (siehe unten).
3. "Gesichtsfilter" im Startmenue starten.

Windows SmartScreen kann vor einem unbekannten Herausgeber warnen, weil der Installer nicht signiert ist.
Jedes Release enthaelt eine `.sha256`-Datei zur Pruefung des Downloads:

    certutil -hashfile Gesichtsfilter-Setup-<Version>.exe SHA256

### Virtuelle Kamera: Voraussetzung

Um das gefilterte Bild in anderen Programmen zu nutzen, wird EIN Treiber fuer eine virtuelle Kamera benoetigt:

- **OBS Studio** (https://obsproject.com), einmal installiert und mindestens einmal gestartet, damit
  "OBS Virtual Camera" registriert wird. OBS muss danach nicht geoeffnet bleiben. ODER
- **Unity Capture**: optionale Komponente dieses Installers ("Unity Capture (virtuelle Kamera)"; standardmaessig
  nicht ausgewaehlt). Der Kameraname ist waehlbar, Standard ist "Gesichtsfilter". Unity Capture steht unter
  der MIT-Lizenz (der Lizenztext wird mit installiert).

Ohne Treiber fuer eine virtuelle Kamera funktioniert das Programm weiterhin (Vorschau, Fotos); es zeigt
statt der virtuellen Kamera nur einen Hinweis an. Im Programm kann das Verfahren gewaehlt werden
("Automatisch", OBS Virtual Camera oder Unity Capture) und bei Unity Capture der Geraetename.

Stille Installation (fuer Administratoren):

    Gesichtsfilter-Setup-<Version>.exe /VERYSILENT /COMPONENTS="main,unity" /CAMNAME="Meine Kamera"

## Schnellstart

1. Kamera waehlen und "Kamera starten" klicken.
2. Modus waehlen und ein PNG laden ("Eigene Datei", Beispiel "Erdnuss" oder "Demo"). Drag & Drop und Strg+V gehen auch.
3. Marker setzen (Augen, Mund und in den anderen Modi Kopf-/Hals-/Koerper-Anker) und im Editor verschieben.
4. Gerade vor der Kamera sitzen und "Ruhelage setzen" klicken.
5. "Virtuelle Kamera starten" klicken und im Videoprogramm die Kamera "Gesichtsfilter" (oder "OBS Virtual Camera")
   auswaehlen.

## Wo Daten gespeichert werden

| Was | Windows | Linux |
| --- | --- | --- |
| Zuletzt benutzte Einstellungen | `%APPDATA%\Gesichtsfilter\zuletzt.json` | `~/.gesichtsfilter/` |
| Marker pro Bild | `%APPDATA%\Gesichtsfilter\marker\<sha256>.json` | `~/.gesichtsfilter/marker/` |
| Log-Datei | `%APPDATA%\Gesichtsfilter\log.txt` | `~/.gesichtsfilter/` |
| Fotos | `Bilder\Gesichtsfilter` | `~/Pictures/Gesichtsfilter` |

Zum Zuruecksetzen der Einstellungen `zuletzt.json` loeschen.

## Linux (Ubuntu, apt)

    chmod +x install.sh
    ./install.sh --dry-run     # zeigt nur, was passieren wuerde
    ./install.sh               # Systempakete, Python 3.11-3.13, .venv, Pakete, Modell, v4l2loopback
    gesichtsfilter             # startet das Programm
    ./install.sh --uninstall

Das Skript richtet die virtuelle Kamera `/dev/video10` mit dem Namen "Gesichtsfilter" ein (v4l2loopback).
Bei aktivem Secure Boot muss das Kernelmodul signiert sein (das Skript gibt einen Hinweis). Getestet mit
Ubuntu 24.04; andere Distributionen sind ungetestet. Unter WSL2 gibt es keine Webcam und keine virtuelle
Kamera; dort bitte die Windows-Version nutzen. Weitere Optionen: `./install.sh --help`.

## Entwicklung

Voraussetzung: Python 3.11 (64 Bit) fuer Windows-Builds; zum Starten aus dem Quelltext Python 3.11-3.13.

    py -3.11 -m venv .venv
    .\.venv\Scripts\Activate.ps1
    pip install -r requirements-dev.txt
    python tools\fetch_model.py
    pytest -q
    python run.py

Installer lokal bauen (benoetigt [Inno Setup 6](https://jrsoftware.org/isdl.php)):

    python packaging\make_installer.py

Das holt Modell und Unity-Capture-Filter (fester Commit, SHA256 geprueft), baut mit PyInstaller im
`--onedir`-Modus, fuehrt den `--selftest` des gebauten Programms aus und erzeugt
`installer_out\Gesichtsfilter-Setup-<Version>.exe`. Einzelheiten stehen in `SETUP_ENTWICKLUNG.txt`.

### Releases

Ein Tag `v<Version>` (zum Beispiel `v0.3.0`; er muss zu `__version__` in
`src/gesichtsfilter/__init__.py` passen) startet den GitHub-Actions-Workflow `.github/workflows/release.yml`.
Er fuehrt die Tests aus, baut Programm und Installer auf `windows-latest` und haengt
`Gesichtsfilter-Setup-<Version>.exe` samt SHA256-Datei an ein GitHub-Release.

## Fehlersuche

- **Hinweis "Es wurde keine virtuelle Kamera gefunden":** OBS Studio installieren und einmal starten oder
  den Installer mit der Komponente Unity Capture erneut ausfuehren.
- **Kameraname erscheint im Videoprogramm nicht:** Videoprogramm nach dem Start der virtuellen Kamera neu starten.
- **Programm startet nicht:** `%APPDATA%\Gesichtsfilter\log.txt` ansehen; `Gesichtsfilter.exe --selftest bericht.txt`
  ausfuehren und `bericht.txt` pruefen.
- **Kein Gesicht erkannt:** besseres Licht, zur Kamera schauen; bei GPU-Problemen "Tracking auf CPU" waehlen.

## Komponenten von Drittanbietern

MediaPipe (Apache-2.0, Gesichtsmodell), OpenCV, NumPy, PySide6 / Qt (LGPL), pyvirtualcam,
Unity Capture von Bernhard Schelling (MIT). Bitte vor einer Weitergabe die jeweiligen Lizenzen pruefen.

## Lizenz

Gesichtsfilter steht unter der GNU General Public License v3.0 (GPL-3.0); siehe Datei `LICENSE` im Repository.
Die oben genannten Komponenten von Drittanbietern behalten ihre eigenen Lizenzen, die mit der GPL-3.0 vereinbar sind.
