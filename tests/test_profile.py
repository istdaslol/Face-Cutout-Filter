"""JSON-Profile und Marker-Sidecars (ohne Qt)."""
import json

import pytest

from gesichtsfilter.core.settings import Settings
from gesichtsfilter.io import profile as P

M5 = [[.1, .2], [.9, .2], [.5, .5], [.5, .7], [.5, .9]]


def test_profil_roundtrip_mit_relativem_pfad(tmp_path):
    img = tmp_path / "bilder" / "kopf.png"
    img.parent.mkdir()
    img.write_bytes(b"x")
    prof = tmp_path / "profile" / "a.json"
    prof.parent.mkdir()
    s = Settings(mode=2, eye_margin=1.1, mouth_margin=0.9, background="#00ff00")
    P.save_profile(prof, s, {"fps": 24}, {"kind": "file", "path": str(img)}, M5,
                   {"kind": "demo"}, [[.5, .2]])
    raw = json.loads(prof.read_text(encoding="utf-8"))
    assert raw["head"]["path"].replace("\\", "/") == "../bilder/kopf.png"      # relativ gespeichert
    d = P.load_profile(prof)
    assert d["head"] == {"kind": "file", "path": str(img.resolve())}
    assert d["body"] == {"kind": "demo"} and d["head_markers"] == M5 and d["body_marker"] == [[.5, .2]]
    assert Settings.from_dict(d["settings"]) == s and d["performance"] == {"fps": 24}


@pytest.mark.parametrize("inhalt", ["kein json", "[]", '{"kind": "fremd"}',
                                    '{"kind": "gesichtsfilter-profil", "version": 99}'])
def test_kaputte_profile_geben_verstaendliche_fehler(tmp_path, inhalt):
    f = tmp_path / "x.json"
    f.write_text(inhalt, encoding="utf-8")
    with pytest.raises(ValueError):
        P.load_profile(f)
    with pytest.raises(ValueError):
        P.load_profile(tmp_path / "gibt_es_nicht.json")


def test_unsinnige_marker_werden_verworfen_oder_begrenzt(tmp_path):
    f = tmp_path / "x.json"
    f.write_text(json.dumps({"kind": P.PROFILE_KIND, "version": 1, "settings": {},
                             "head_markers": [[0, 0]] * 3,                 # falsche Anzahl
                             "body_marker": [[5, -2]]}), encoding="utf-8")  # ausserhalb 0..1
    d = P.load_profile(f)
    assert d["head_markers"] is None and d["body_marker"] == [[1.0, 0.0]]


def test_sidecar(tmp_path):
    img = tmp_path / "bild.png"
    img.write_bytes(b"x")
    assert P.load_sidecar(img, 5, 5) is None
    P.save_sidecar(img, M5)
    assert P.sidecar_path(img).name == "bild.png.marker.json"
    assert P.load_sidecar(img, 5, 5) == M5
    assert P.load_sidecar(img, 1, 1) is None                              # falsche Anzahl
    P.sidecar_path(img).write_text("kaputt", encoding="utf-8")
    assert P.load_sidecar(img, 5, 5) is None
