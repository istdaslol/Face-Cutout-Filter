#!/usr/bin/env bash
# =============================================================================
# Gesichtsfilter - Installation fuer Ubuntu (apt)
#
# Was das Skript macht:
#   1. Systempakete per apt installieren (Qt-/OpenCV-Bibliotheken, ggf. Python)
#   2. Python 3.10 - 3.12 suchen (Python 3.11 wird bevorzugt) oder installieren
#   3. virtuelle Umgebung .venv anlegen und requirements.txt installieren
#   4. Gesichtsmodell (models/face_landmarker.task) herunterladen
#   5. virtuelle Kamera einrichten: v4l2loopback (/dev/video10, "Gesichtsfilter")
#   6. Startbefehl "gesichtsfilter" und Eintrag im Anwendungsmenue anlegen
#
# Aufruf (als normaler Benutzer, sudo wird bei Bedarf gefragt):
#   ./install.sh                  alles installieren
#   ./install.sh --dry-run        nur anzeigen, was passieren wuerde
#   ./install.sh --help           alle Optionen
#   ./install.sh --uninstall      Startbefehl, Menueeintrag, .venv, Kamera-Einstellungen entfernen
#
# Getestet mit: Ubuntu 24.04 (Python 3.12). Ubuntu 22.04 sollte funktionieren
# (Python 3.10 oder 3.11 ueber deadsnakes). Andere Distributionen: nicht getestet.
# =============================================================================
set -euo pipefail

# ----------------------------------------------------------------------------
# Einstellungen (hier oben anpassen)
# ----------------------------------------------------------------------------
PY_MIN=10                      # kleinste unterstuetzte Python-3-Nebenversion (3.10)
PY_MAX=12                      # groesste unterstuetzte Python-3-Nebenversion (3.12, wegen mediapipe)
PY_PREFERRED=(python3.11 python3.12 python3.10 python3)   # Reihenfolge der Suche
PY_INSTALL_VERSION="3.11"      # wird installiert, wenn nichts Passendes gefunden wird
VCAM_NR=10                     # /dev/video10
VCAM_LABEL="Gesichtsfilter"    # Name der virtuellen Kamera in Zoom, Discord, OBS ...
APP_CMD="gesichtsfilter"       # Name des Startbefehls in ~/.local/bin

# Bibliotheken fuer Qt (xcb), OpenCV und PortAudio (von mediapipe importiert).
# Nicht vorhandene Namen werden uebersprungen (Namen unterscheiden sich je nach Ubuntu-Version).
APT_LIBS=(
  libgl1 libegl1 libglib2.0-0 libdbus-1-3 libfontconfig1 libfreetype6
  libxkbcommon0 libxkbcommon-x11-0 libxcb-cursor0 libxcb-icccm4 libxcb-image0
  libxcb-keysyms1 libxcb-randr0 libxcb-render-util0 libxcb-shape0 libxcb-xinerama0
  libxcb-xkb1 libxcb-xfixes0 libxrender1 libportaudio2
)

# ----------------------------------------------------------------------------
# Hilfsfunktionen
# ----------------------------------------------------------------------------
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$ROOT/.venv"
TARGET_USER="${USER:-$(id -un)}"   # $USER ist in Containern manchmal nicht gesetzt
BIN_DIR="${XDG_BIN_HOME:-$HOME/.local/bin}"
APP_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
LAUNCHER="$BIN_DIR/$APP_CMD"
DESKTOP="$APP_DIR/$APP_CMD.desktop"
MODPROBE_CONF="/etc/modprobe.d/gesichtsfilter-v4l2loopback.conf"
MODLOAD_CONF="/etc/modules-load.d/gesichtsfilter-v4l2loopback.conf"

DRY_RUN=0; SKIP_APT=0; SKIP_VCAM=0; SKIP_MODEL=0; UNINSTALL=0; ALLOW_ROOT=0
PYTHON_ARG=""

if [[ -t 1 ]]; then B=$'\033[1m'; G=$'\033[32m'; Y=$'\033[33m'; R=$'\033[31m'; N=$'\033[0m'; else B=""; G=""; Y=""; R=""; N=""; fi
step() { printf '\n%s==> %s%s\n' "$B" "$*" "$N"; }
info() { printf '    %s\n' "$*"; }
ok()   { printf '    %sOK%s %s\n' "$G" "$N" "$*"; }
warn() { printf '    %sHinweis:%s %s\n' "$Y" "$N" "$*" >&2; }
die()  { printf '%sFehler:%s %s\n' "$R" "$N" "$*" >&2; exit 1; }

# Fuehrt einen Befehl aus - oder zeigt ihn nur an (--dry-run)
run() {
  if (( DRY_RUN )); then
    printf '    [dry-run]'; printf ' %q' "$@"; printf '\n'
  else
    "$@"
  fi
}
# Wie run, aber mit Root-Rechten
as_root() {
  if (( EUID == 0 )); then run "$@"; else run sudo "$@"; fi
}
# Schreibt stdin als Root in eine Datei
write_root_file() {
  local path="$1" content; content="$(cat)"
  if (( DRY_RUN )); then
    printf '    [dry-run] schreibe %s:\n' "$path"; printf '%s\n' "$content" | sed 's/^/        /'
  elif (( EUID == 0 )); then
    printf '%s\n' "$content" > "$path"
  else
    printf '%s\n' "$content" | sudo tee "$path" > /dev/null
  fi
}

usage() {
  cat <<'EOF'
Gesichtsfilter - Installation fuer Ubuntu (apt)

Aufruf: ./install.sh [Optionen]

  --dry-run         Nur anzeigen, was passieren wuerde (aendert nichts)
  --python BEFEHL   Bestimmten Python-Befehl verwenden, z.B. --python python3.11
  --skip-apt        Keine Systempakete installieren (z.B. wenn schon alles da ist)
  --no-vcam         Virtuelle Kamera (v4l2loopback) nicht einrichten
  --skip-model      Gesichtsmodell nicht laden (selbst nach models/ legen)
  --allow-root      Start als root erlauben (nicht empfohlen)
  --uninstall       Startbefehl, Menueeintrag, .venv und Kamera-Einstellungen entfernen
  -h, --help        Diese Hilfe

Danach starten mit:  gesichtsfilter     (oder im Anwendungsmenue: "Gesichtsfilter")
EOF
}

# ----------------------------------------------------------------------------
# Optionen lesen
# ----------------------------------------------------------------------------
while (( $# )); do
  case "$1" in
    --dry-run) DRY_RUN=1 ;;
    --python) shift; PYTHON_ARG="${1:-}"; [[ -n "$PYTHON_ARG" ]] || die "--python braucht einen Befehl, z.B. python3.11" ;;
    --skip-apt) SKIP_APT=1 ;;
    --no-vcam) SKIP_VCAM=1 ;;
    --skip-model) SKIP_MODEL=1 ;;
    --allow-root) ALLOW_ROOT=1 ;;
    --uninstall) UNINSTALL=1 ;;
    -h|--help) usage; exit 0 ;;
    *) usage >&2; die "Unbekannte Option: $1" ;;
  esac
  shift
done

# ----------------------------------------------------------------------------
# Vorpruefungen
# ----------------------------------------------------------------------------
preflight() {
  [[ "$(uname -s)" == "Linux" ]] || die "Dieses Skript ist nur fuer Linux (Ubuntu)."
  if (( EUID == 0 )) && (( ! ALLOW_ROOT )); then
    die "Bitte als normaler Benutzer starten (sudo wird bei Bedarf gefragt). Sonst gehoert die Installation root. Mit --allow-root trotzdem erzwingen."
  fi
  if (( ! SKIP_APT || ! SKIP_VCAM )) && (( EUID != 0 )) && ! command -v sudo >/dev/null 2>&1 && (( ! DRY_RUN )); then
    die "sudo wurde nicht gefunden. Als root mit --allow-root starten oder --skip-apt --no-vcam verwenden."
  fi
  if (( ! SKIP_APT )) && ! command -v apt-get >/dev/null 2>&1; then
    die "apt-get fehlt. Dieses Skript ist nur fuer Ubuntu/Debian gedacht. Mit --skip-apt koennen die Systempakete uebersprungen werden."
  fi
  local id=""; [[ -r /etc/os-release ]] && id="$(. /etc/os-release; echo "${ID:-}")"
  if [[ "$id" != "ubuntu" ]]; then
    warn "Erkannt: '${id:-unbekannt}'. Getestet ist nur Ubuntu. Es geht trotzdem weiter."
  fi
  if [[ -n "$PYTHON_ARG" ]] && ! py_ok "$PYTHON_ARG"; then
    die "'$PYTHON_ARG' fehlt oder ist nicht Python 3.$PY_MIN - 3.$PY_MAX."
  fi
  [[ -f "$ROOT/requirements.txt" && -f "$ROOT/run.py" ]] || die "Bitte im Projektordner ausfuehren (requirements.txt/run.py fehlen)."
  (( ! DRY_RUN )) || info "Trockenlauf: Es wird nichts veraendert."
}

# ----------------------------------------------------------------------------
# 1. Systempakete
# ----------------------------------------------------------------------------
apt_has() {   # gibt es das Paket (auch als virtueller Name, z.B. libglib2.0-0 -> libglib2.0-0t64)?
  # "apt-get -s" simuliert nur und braucht kein root. apt-cache policy kennt virtuelle Namen nicht.
  apt-get -s install "$1" >/dev/null 2>&1
}

apt_install() {   # installiert nur Pakete, die es in den Paketquellen gibt; meldet fehlende
  local want=("$@") have=() miss=() p
  for p in "${want[@]}"; do if apt_has "$p"; then have+=("$p"); else miss+=("$p"); fi; done
  (( ${#miss[@]} == 0 )) || warn "Nicht in den Paketquellen (uebersprungen): ${miss[*]}"
  (( ${#have[@]} )) || return 0
  as_root env DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends "${have[@]}"
}

install_system_packages() {
  step "Systempakete (apt)"
  as_root apt-get update
  apt_install ca-certificates "${APT_LIBS[@]}"
  ok "Bibliotheken installiert"
}

# ----------------------------------------------------------------------------
# 2. Python
# ----------------------------------------------------------------------------
py_ok() {   # Befehl existiert und Version liegt im Bereich 3.PY_MIN .. 3.PY_MAX
  command -v "$1" >/dev/null 2>&1 &&
    "$1" -c "import sys; sys.exit(0 if sys.version_info[0]==3 and $PY_MIN <= sys.version_info[1] <= $PY_MAX else 1)" 2>/dev/null
}
py_version() { "$1" -c 'import sys; print("%d.%d" % sys.version_info[:2])'; }
py_has_venv() { "$1" -c 'import venv, ensurepip' >/dev/null 2>&1; }

find_python() {
  local c
  if [[ -n "$PYTHON_ARG" ]]; then echo "$PYTHON_ARG"; return 0; fi    # in preflight() bereits geprueft
  for c in "${PY_PREFERRED[@]}"; do py_ok "$c" && { echo "$c"; return 0; }; done
  return 1
}

install_python() {   # nichts Passendes gefunden: Python PY_INSTALL_VERSION per apt (ggf. deadsnakes)
  step "Python $PY_INSTALL_VERSION installieren"
  local pkg="python$PY_INSTALL_VERSION"
  (( SKIP_APT )) && die "Kein passendes Python (3.$PY_MIN - 3.$PY_MAX) gefunden und --skip-apt gesetzt."
  if ! apt_has "$pkg"; then
    local id=""; [[ -r /etc/os-release ]] && id="$(. /etc/os-release; echo "${ID:-}")"
    [[ "$id" == "ubuntu" ]] || die "$pkg ist nicht in den Paketquellen. Bitte Python 3.$PY_MIN - 3.$PY_MAX selbst installieren und --python verwenden."
    info "$pkg ist nicht in den Standard-Paketquellen - fuege die deadsnakes-PPA hinzu."
    apt_install software-properties-common
    as_root add-apt-repository -y ppa:deadsnakes/ppa
    as_root apt-get update
  fi
  apt_install "$pkg" "$pkg-venv"
}

ensure_python() {
  step "Python suchen"
  local py
  if ! py="$(find_python)"; then
    (( DRY_RUN )) && { info "Kein passendes Python gefunden - es wuerde $PY_INSTALL_VERSION installiert."; PYTHON="python$PY_INSTALL_VERSION"; return 0; }
    install_python
    py="$(find_python)" || die "Python konnte nicht eingerichtet werden."
  fi
  if ! py_has_venv "$py"; then
    warn "Dem Python '$py' fehlt das Modul venv/ensurepip."
    (( SKIP_APT )) && die "Bitte python3-venv installieren (oder ohne --skip-apt starten)."
    local v; v="$(py_version "$py")"
    if [[ "$py" == "python3" ]]; then apt_install python3-venv; else apt_install "python${v}-venv"; fi
    py_has_venv "$py" || die "venv ist weiterhin nicht verfuegbar fuer '$py'."
  fi
  PYTHON="$py"
  ok "Verwende $PYTHON ($(py_version "$PYTHON" 2>/dev/null || echo "?"))"
}

# ----------------------------------------------------------------------------
# 3. Virtuelle Umgebung + Pakete, 4. Modell
# ----------------------------------------------------------------------------
setup_venv() {
  step "Virtuelle Umgebung und Python-Pakete (kann einige Minuten dauern)"
  if [[ -x "$VENV/bin/python" ]] && ! "$VENV/bin/python" -c "import sys; assert $PY_MIN <= sys.version_info[1] <= $PY_MAX" 2>/dev/null; then
    warn ".venv gehoert zu einer nicht unterstuetzten Python-Version und wird neu angelegt."
    run rm -rf "$VENV"
  fi
  [[ -d "$VENV" ]] || run "$PYTHON" -m venv "$VENV"
  run "$VENV/bin/python" -m pip install --upgrade pip
  run "$VENV/bin/python" -m pip install --default-timeout 100 --retries 5 -r "$ROOT/requirements.txt"
  ok "Pakete installiert"
}

fetch_model() {
  step "Gesichtsmodell"
  local model="$ROOT/models/face_landmarker.task"
  if (( SKIP_MODEL )); then
    if [[ -f "$model" ]]; then ok "Modell vorhanden: $model"
    else warn "Ohne Modell startet die Kamera nicht. Datei nach $model legen."; fi
    return 0
  fi
  run "$VENV/bin/python" "$ROOT/tools/fetch_model.py"
}

verify() {
  step "Pruefung"
  (( DRY_RUN )) && { info "(uebersprungen im Trockenlauf)"; return 0; }
  "$VENV/bin/python" - <<'PY' || die "Ein Paket laesst sich nicht importieren (siehe Meldung oben)."
import cv2, numpy, mediapipe, PySide6, pyvirtualcam
print("    OK  mediapipe", mediapipe.__version__, "| opencv", cv2.__version__, "| numpy", numpy.__version__,
      "| PySide6", PySide6.__version__, "| pyvirtualcam", pyvirtualcam.__version__)
PY
}

# ----------------------------------------------------------------------------
# 5. Virtuelle Kamera (v4l2loopback)
# ----------------------------------------------------------------------------
setup_vcam() {
  step "Virtuelle Kamera (v4l2loopback)"
  if (( ! SKIP_APT )); then
    if ! apt_install v4l2loopback-dkms v4l2loopback-utils "linux-headers-$(uname -r)"; then
      warn "v4l2loopback liess sich nicht installieren (Kernel-Header/DKMS?). Die virtuelle Kamera wird uebersprungen."
      warn "Die Vorschau im Programm funktioniert trotzdem. Spaeter nachholen: ./install.sh --skip-apt   (nach Behebung)"
      return 0
    fi
  fi
  write_root_file "$MODPROBE_CONF" <<EOF
# von Gesichtsfilter install.sh
options v4l2loopback devices=1 video_nr=$VCAM_NR card_label="$VCAM_LABEL" exclusive_caps=1
EOF
  write_root_file "$MODLOAD_CONF" <<EOF
v4l2loopback
EOF
  if [[ -r /proc/modules ]] && grep -q '^v4l2loopback ' /proc/modules; then
    ok "Modul ist bereits geladen"
    [[ -e "/dev/video$VCAM_NR" ]] || warn "Es ist mit anderen Einstellungen geladen (kein /dev/video$VCAM_NR). Neustart oder 'sudo modprobe -r v4l2loopback' und neu laden."
  else
    if as_root modprobe v4l2loopback; then
      ok "Modul geladen"
    else
      warn "Das Modul liess sich nicht laden. Bei aktivem Secure Boot muss das DKMS-Modul signiert werden"
      warn "(beim Paket-Install wurde dazu ein Passwort fuer die MOK-Registrierung abgefragt; danach neu starten)."
      warn "Oder Secure Boot im BIOS ausschalten. Die Vorschau im Programm funktioniert auch ohne virtuelle Kamera."
    fi
  fi
  # Zugriff auf /dev/videoN: Gruppe "video"
  if ! id -nG "$TARGET_USER" 2>/dev/null | tr ' ' '\n' | grep -qx video; then
    as_root usermod -aG video "$TARGET_USER"
    warn "Du wurdest zur Gruppe 'video' hinzugefuegt. Bitte einmal ab- und wieder anmelden."
  fi
}

# ----------------------------------------------------------------------------
# 6. Startbefehl + Menueeintrag
# ----------------------------------------------------------------------------
install_launcher() {
  step "Startbefehl und Menueeintrag"
  run mkdir -p "$BIN_DIR" "$APP_DIR"
  if (( DRY_RUN )); then
    info "[dry-run] schreibe $LAUNCHER und $DESKTOP"
  else
    cat > "$LAUNCHER" <<EOF
#!/usr/bin/env bash
# von Gesichtsfilter install.sh erzeugt
# xcb als Standard: laeuft unter X11 und unter Wayland (XWayland). Mit QT_QPA_PLATFORM=wayland ueberschreibbar.
export QT_QPA_PLATFORM="\${QT_QPA_PLATFORM:-xcb}"
exec "$VENV/bin/python" "$ROOT/run.py" "\$@"
EOF
    chmod +x "$LAUNCHER"
    cat > "$DESKTOP" <<EOF
[Desktop Entry]
Type=Application
Name=Gesichtsfilter
Comment=Augen und Mund auf ein PNG setzen, mit virtueller Kamera
Exec=$LAUNCHER
Icon=camera-web
Terminal=false
Categories=AudioVideo;Video;Graphics;
EOF
    command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database "$APP_DIR" >/dev/null 2>&1 || true
  fi
  ok "Startbefehl: $LAUNCHER"
  case ":$PATH:" in *":$BIN_DIR:"*) ;; *) warn "$BIN_DIR ist nicht in deinem PATH. Neu anmelden oder das Programm ueber das Anwendungsmenue starten." ;; esac
}

# ----------------------------------------------------------------------------
# Deinstallation
# ----------------------------------------------------------------------------
uninstall() {
  step "Deinstallation"
  run rm -f "$LAUNCHER" "$DESKTOP"
  run rm -rf "$VENV"
  if [[ -f "$MODPROBE_CONF" || -f "$MODLOAD_CONF" ]]; then
    as_root rm -f "$MODPROBE_CONF" "$MODLOAD_CONF"
  fi
  command -v update-desktop-database >/dev/null 2>&1 && (( ! DRY_RUN )) && update-desktop-database "$APP_DIR" >/dev/null 2>&1 || true
  ok "Entfernt: Startbefehl, Menueeintrag, .venv, Kamera-Einstellungen"
  info "Nicht entfernt: apt-Pakete (z.B. v4l2loopback-dkms), deine Einstellungen in ~/.gesichtsfilter und dieser Projektordner."
  info "Das geladene Modul wird bis zum Neustart noch aktiv sein:  sudo modprobe -r v4l2loopback"
}

# ----------------------------------------------------------------------------
# Ablauf
# ----------------------------------------------------------------------------
main() {
  preflight
  if (( UNINSTALL )); then uninstall; return 0; fi
  (( SKIP_APT )) || install_system_packages
  ensure_python
  setup_venv
  fetch_model
  verify
  (( SKIP_VCAM )) || setup_vcam
  install_launcher
  printf '\n%sFertig.%s Starten mit:  %s%s%s   (oder im Anwendungsmenue: "Gesichtsfilter")\n' "$G" "$N" "$B" "$APP_CMD" "$N"
  (( SKIP_VCAM )) || info "Virtuelle Kamera: in Zoom/Discord/OBS die Kamera \"$VCAM_LABEL\" (/dev/video$VCAM_NR) waehlen."
}
main
