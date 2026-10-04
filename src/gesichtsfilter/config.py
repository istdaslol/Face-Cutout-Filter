"""Zentrale Konstanten. Alles, was man anpassen moechte, steht hier oben.

Die Werte sind 1:1 aus gesichts-filter.html uebernommen (Landmark-Indizes,
Marker-Standardpositionen, Demo-Farben).
"""

# ======================================================================
# DEMO-BILD (entspricht den Konstanten oben in der HTML-Datei)
# ======================================================================
HAUTFARBE = "#f1cfb0"   # z.B. #fbe3d0 (sehr hell), #f1cfb0 (hell), #e0ac84 (mittel)
KONTUR = "#b98e6a"      # Umrisslinie der Haut
SHIRT = "#3d5a80"       # Farbe des Oberteils
SHIRT_BREITE = 420      # Breite in Pixeln, maximal 600
SHIRT_HOEHE = 180       # Sichtbare Hoehe ab dem Halsansatz, maximal 330
SHIRT_RUNDUNG = 70      # Rundung der Ecken

# ======================================================================
# STANDARDWERTE DER REGLER (wie value="..." in der HTML-Datei)
# ======================================================================
DEFAULT_MODE = 1            # 0 = Einfach, 1 = Ein PNG mit Markern, 2 = Zwei PNGs
DEFAULT_FOLLOW = 1.0        # "Kopf folgt (Staerke)"      0 .. 1.5
DEFAULT_IMAGE_SCALE = 1.0   # "Bildgroesse"               0.3 .. 1.5
DEFAULT_HEAD_RATIO = 1.0    # "Kopf zu Koerper (Groesse)" 0.4 .. 2.5
DEFAULT_EYE_SCALE = 1.0     # "Augengroesse"              0.4 .. 3
DEFAULT_MOUTH_SCALE = 1.0   # "Mundgroesse"               0.4 .. 3
# Ausschnitt = konvexe Huelle der Landmarks, um ihren Mittelpunkt skaliert.
# 1.0 = genau die Landmarks, >1 = mehr Umgebung, <1 = enger. Augen und Mund
# sind getrennt einstellbar. (Frueher: ein Regler, Mund = Augen + 0.1.)
DEFAULT_EYE_MARGIN = 1.25   # "Augen-Ausschnitt"          0.7 .. 2.2
DEFAULT_MOUTH_MARGIN = 1.35 # "Mund-Ausschnitt"           0.7 .. 2.2
LEGACY_MOUTH_EXTRA = 0.1    # nur zum Umrechnen alter Profile mit "margin"
DEFAULT_FEATHER = 8         # "Weiche Kante"              0 .. 20 (Pixel)
DEFAULT_BROWS = True        # "Augenbrauen mitnehmen"
DEFAULT_MIRROR = True       # "Spiegeln"
DEFAULT_BEHIND = False      # "Kopf hinter Koerper"
DEFAULT_TRACK_HEAD = True   # "PNG folgt dem Kopf" (nur Modus "Einfach"); aus = PNG bleibt stehen
DEFAULT_BACKGROUND = "cam"  # "cam" oder Hex-Farbe

# Hintergrund-Auswahl: (Anzeigename, Wert)
BACKGROUNDS = [
    ("Kamerabild", "cam"),
    ("Greenscreen", "#00ff00"),
    ("Schwarz", "#000000"),
    ("Wei\u00df", "#ffffff"),
]
BG_CAM = "cam"

# Wertebereiche (Min, Max, Schritt) fuer die Regler der Oberflaeche
RANGES = {
    "follow": (0.0, 1.5, 0.01),
    "image_scale": (0.3, 1.5, 0.01),
    "head_ratio": (0.4, 2.5, 0.01),
    "eye_scale": (0.4, 3.0, 0.01),
    "mouth_scale": (0.4, 3.0, 0.01),
    "eye_margin": (0.7, 2.2, 0.01),
    "mouth_margin": (0.7, 2.2, 0.01),
    "feather": (0, 20, 1),
}

# ======================================================================
# PERFORMANCE
# ======================================================================
TRACK_SIZE = (640, 360)     # Tracking laeuft auf diesem verkleinerten Bild
DEFAULT_FPS = 30            # fps-Limit der Ausgabe
DEFAULT_TRACK_EVERY = 1     # 1 = jeden Frame, 2 = jeden 2. Frame (mit Vorhersage)
SMOOTHING = 0.6             # Glaettung der Landmarks (wie 0.6 in der HTML-Datei)

# ======================================================================
# FOTO
# ======================================================================
PHOTO_DELAY_S = 3           # Verzoegerung des Knopfs "Foto in 3 s" (nur im Hintergrund, ohne Anzeige)
PHOTO_PREFIX = "Foto"       # Dateiname: Foto_JJJJMMTT_HHMMSS.png
PHOTO_SUBDIR = "Gesichtsfilter"   # Unterordner im Bilder-Ordner des Benutzers

# ======================================================================
# LANDMARK-INDIZES (MediaPipe FaceMesh, 478 Punkte)
# ======================================================================
EYE_A = [33, 7, 163, 144, 145, 153, 154, 155, 133, 173, 157, 158, 159, 160, 161, 246]
BROW_A = [70, 63, 105, 66, 107, 46, 53, 52, 65, 55]
EYE_B = [263, 249, 390, 373, 374, 380, 381, 382, 362, 466, 388, 387, 386, 385, 384, 398]
BROW_B = [300, 293, 334, 296, 336, 276, 283, 282, 295, 285]
LIPS = [61, 146, 91, 181, 84, 17, 314, 405, 321, 375, 291, 409, 270, 269, 267, 0, 37, 39, 40, 185]

# Maximale Kantenlaenge eines Ausschnitts (wie 700 in der HTML-Datei)
MAX_PATCH = 700

# ======================================================================
# MARKER
# ======================================================================
# Name, Farbe (Hex), Kuerzel - Reihenfolge = Marker-Index 0..4
MARKER_DEFS = [
    ("Auge links", "#4cc9f0", "L"),
    ("Auge rechts", "#80ed99", "R"),
    ("Mund", "#ff6b81", "M"),
    ("Hals oben", "#ffd166", "H"),
    ("Hals unten", "#c77dff", "P"),
]
# Im Zwei-PNG-Modus heisst Marker 4 "Hals-Pivot", das Koerper-Bild hat "Hals-Anker"
PIVOT_DEF = ("Hals-Pivot", "#c77dff", "P")
BODY_ANCHOR_DEF = ("Hals-Anker", "#ffd166", "A")

# Standard-Marker (relativ 0..1): Auge L/R, Mund, Hals oben, Hals unten
DEFAULT_MARKERS = [[.4, .27], [.6, .27], [.5, .4], [.5, .475], [.5, .59]]
DEFAULT_BODY_MARKER = [[.5, .1]]
PEANUT_MARKERS = [[.38, .29], [.62, .29], [.5, .68], [.5, .9], [.5, .97]]

# Welche Marker-Indizes pro Modus/Ansicht sichtbar sind
MARKER_INDICES = {
    "body": [0],
    0: [0, 1, 2],
    1: [0, 1, 2, 3, 4],
    2: [0, 1, 2, 4],
}

# Maximale Kantenlaenge geladener Bilder (Speicher/Geschwindigkeit)
MAX_IMAGE_SIDE = 1600


def hex_to_bgr(h: str):
    """'#rrggbb' -> (b, g, r) fuer OpenCV."""
    h = h.lstrip("#")
    return int(h[4:6], 16), int(h[2:4], 16), int(h[0:2], 16)
