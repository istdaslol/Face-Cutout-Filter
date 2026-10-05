"""Kontrollfluss von install.sh, offline: ein Platzhalter gibt sich als Python 3.11 aus.

Getestet wird nur die Logik des Skripts (venv anlegen/reparieren, Fehlertexte, WSL), nicht
apt oder pip. Nur unter Linux/macOS mit bash (unter Windows uebersprungen).
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
pytestmark = pytest.mark.skipif(sys.platform == "win32" or not shutil.which("bash"),
                                reason="install.sh laeuft nur unter Linux/macOS mit bash")

FAKEPY = """#!/usr/bin/env bash
# Platzhalter-Python: gibt sich als 3.11 aus; "-m venv DIR" legt eine Platzhalter-Umgebung an.
if [[ "${1:-}" == "-m" && "${2:-}" == "venv" ]]; then
  if [[ -n "${FAKEPY_FAIL_VENV:-}" ]]; then
    mkdir -p "$3/lib"; echo "Error: ensurepip is not available" >&2; exit 1
  fi
  mkdir -p "$3/bin"; cp "$0" "$3/bin/python"; chmod +x "$3/bin/python"; exit 0
fi
if [[ "${1:-}" == "-c" ]]; then
  case "${2:-}" in *print*) echo "3.11" ;; esac
fi
exit 0
"""


@pytest.fixture
def proj(tmp_path):
    """Projektordner wie bei einem Anwender (Name wie im gemeldeten Fall) + Platzhalter-Python."""
    p = tmp_path / "Face-Cutout-Filter"
    p.mkdir()
    for f in ("install.sh", "requirements.txt", "run.py"):
        shutil.copy(ROOT / f, p / f)
    fake = tmp_path / "fakepy"
    fake.write_text(FAKEPY)
    fake.chmod(0o755)
    (tmp_path / "home").mkdir()
    return p, fake, tmp_path / "home"


def run_install(proj, *args, extra_env=None):
    p, fake, home = proj
    env = {k: v for k, v in os.environ.items() if k not in ("WSL_DISTRO_NAME", "FAKEPY_FAIL_VENV", "XDG_BIN_HOME",
                                                            "XDG_DATA_HOME", "USER")}
    env["HOME"] = str(home)
    env.update(extra_env or {})
    cmd = ["bash", str(p / "install.sh"), "--allow-root", "--python", str(fake), "--skip-apt", "--no-vcam",
           "--skip-model", *args]
    r = subprocess.run(cmd, cwd=p, env=env, capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=60)
    return r.returncode, r.stdout + r.stderr


def test_syntax_und_hilfe():
    assert subprocess.run(["bash", "-n", str(ROOT / "install.sh")]).returncode == 0
    r = subprocess.run(["bash", str(ROOT / "install.sh"), "--help"], capture_output=True, text=True)
    assert r.returncode == 0 and "--dry-run" in r.stdout and "--uninstall" in r.stdout


def test_frische_installation_legt_venv_startbefehl_und_menueeintrag_an(proj):
    p, _, home = proj
    rc, out = run_install(proj)
    assert rc == 0, out
    assert (p / ".venv" / "bin" / "python").exists()
    launcher = home / ".local" / "bin" / "gesichtsfilter"
    assert launcher.exists() and os.access(launcher, os.X_OK)
    assert str(p / "run.py") in launcher.read_text()
    assert "Exec=" + str(launcher) in (home / ".local/share/applications/gesichtsfilter.desktop").read_text()


def test_fremde_venv_wird_nie_geloescht_windows_venv_im_gemeinsamen_ordner(proj):
    """Entscheidung: kein Erkennen/Reparieren fremder Umgebungen. Eine Windows-venv (Scripts/ statt bin/)
    in einem von Windows und WSL gemeinsam genutzten Ordner muss unberuehrt bleiben. Der Lauf bricht dann
    ab (bekannter, hingenommener Sonderfall) - aber ohne Datenverlust."""
    p, _, _ = proj
    (p / ".venv" / "Scripts").mkdir(parents=True)
    (p / ".venv" / "Scripts" / "python.exe").write_text("windows")
    (p / ".venv" / "pyvenv.cfg").write_text("home = C:\\Python311\n")
    rc, out = run_install(proj)
    assert rc != 0 and "bin/python" in out
    assert (p / ".venv" / "Scripts" / "python.exe").read_text() == "windows"
    assert (p / ".venv" / "pyvenv.cfg").exists()


def test_leere_vorhandene_venv_wird_ebenfalls_nicht_angefasst(proj):
    p, _, _ = proj
    (p / ".venv").mkdir()
    (p / ".venv" / "meine_datei").write_text("x")
    rc, _ = run_install(proj)
    assert rc != 0 and (p / ".venv" / "meine_datei").exists()


def test_linux_venv_mit_unpassender_python_version_wird_neu_angelegt(proj):
    p, _, _ = proj
    (p / ".venv" / "bin").mkdir(parents=True)
    broken = p / ".venv" / "bin" / "python"
    broken.write_text("#!/bin/sh\nexit 1\n")
    broken.chmod(0o755)
    rc, out = run_install(proj)
    assert rc == 0, out
    assert "nicht unterstuetzten Python-Version" in out
    assert (p / ".venv" / "bin" / "python").read_text().startswith("#!/usr/bin/env bash")   # Platzhalter, nicht das kaputte


def test_funktionierende_venv_bleibt_erhalten(proj):
    p, _, _ = proj
    assert run_install(proj)[0] == 0
    (p / ".venv" / "marker").write_text("x")
    rc, out = run_install(proj)
    assert rc == 0 and "neu angelegt" not in out and "No such file" not in out
    assert (p / ".venv" / "marker").exists()


def test_venv_anlegen_scheitert_klare_meldung_und_keine_halbe_umgebung(proj):
    p, _, _ = proj
    rc, out = run_install(proj, extra_env={"FAKEPY_FAIL_VENV": "1"})
    assert rc != 0
    assert "konnte nicht angelegt werden" in out and "python3-venv" in out and "/mnt/c" in out
    assert not (p / ".venv").exists(), "halb angelegte .venv darf nicht zurueckbleiben"
    # Der naechste Lauf (Fehlerursache behoben) funktioniert dann sofort
    rc2, out2 = run_install(proj)
    assert rc2 == 0, out2


def test_ungueltiges_python_bricht_sofort_ab(proj):
    p, _, home = proj
    env = {**os.environ, "HOME": str(home)}
    r = subprocess.run(["bash", str(p / "install.sh"), "--allow-root", "--python", "python2.7", "--skip-apt",
                        "--no-vcam", "--skip-model"], cwd=p, env=env, capture_output=True, text=True, timeout=60)
    assert r.returncode != 0 and "python2.7" in r.stderr and not (p / ".venv").exists()


@pytest.mark.skipif(hasattr(os, "geteuid") and os.geteuid() != 0, reason="Root-Sperre nur als root pruefbar")
def test_root_sperre_ohne_allow_root(proj):
    p, fake, home = proj
    r = subprocess.run(["bash", str(p / "install.sh"), "--python", str(fake), "--skip-apt", "--no-vcam",
                        "--skip-model", "--dry-run"], cwd=p, env={**os.environ, "HOME": str(home)},
                       capture_output=True, text=True, timeout=60)
    assert r.returncode != 0 and "normaler Benutzer" in r.stderr


def test_wsl_ueberspringt_virtuelle_kamera_und_erklaert_einschraenkungen(proj):
    p, fake, home = proj
    env = {**os.environ, "HOME": str(home), "WSL_DISTRO_NAME": "Debian"}
    r = subprocess.run(["bash", str(p / "install.sh"), "--allow-root", "--python", str(fake), "--skip-apt",
                        "--skip-model", "--dry-run"], cwd=p, env=env, capture_output=True, text=True, timeout=60)
    out = r.stdout + r.stderr
    assert r.returncode == 0, out
    assert "WSL erkannt" in out and "uebersprungen" in out
    assert "modprobe" not in out and "v4l2loopback-dkms" not in out and "usermod" not in out
    assert "WSLg" in out and "usbipd" in out
