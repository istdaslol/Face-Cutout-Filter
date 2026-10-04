"""Rig und Modi - Port der Hauptschleife loop() aus gesichts-filter.html.

Eingabe: Kamerabild (BGR, uncodiert/ungespiegelt) und geglaettete Landmarks
(normalisiert 0..1). Ausgabe: fertiges BGR-Bild in Kameraaufloesung.

Modi:
  0 Einfach  - PNG klebt starr am Gesicht
  1 Ein PNG  - Kopf folgt relativ zur Ruhelage, Hals in Streifen gedehnt
  2 Zwei PNG - Kopf-PNG (starr, Pivot) + Koerper-PNG (Hals-Anker)
"""
import math
from dataclasses import dataclass
from typing import Optional

import cv2
import numpy as np

from .. import config as C
from .cutout import cut, stamp
from .geometry import clamp, mean_pt, mat_translate, mat_rotate, mat_scale
from .raster import draw_affine
from .settings import RigAssets, Settings

# Anzahl Streifen im Hals (wie N=12 in der HTML-Datei)
NECK_STRIPS = 12


@dataclass
class RestPose:
    """Ruhelage: Augenmitte, Neigung und Augenabstand (Pixel/Radiant)."""
    x: float
    y: float
    r: float
    d: float


@dataclass
class HeadTransform:
    dx: float
    dy: float
    rot: float
    sc: float


class Rig:
    """Haelt die Ruhelage und rendert einzelne Frames."""

    def __init__(self):
        self.rest: Optional[RestPose] = None
        self._want_rest = False

    def set_rest_pose(self) -> None:
        """Knopf "Ruhelage setzen": gilt ab dem naechsten Frame mit Gesicht."""
        self._want_rest = True

    def reset(self) -> None:
        """Z.B. nach Kamerawechsel."""
        self.rest = None
        self._want_rest = False

    # ------------------------------------------------------------------
    def render(self, cam_bgr: np.ndarray, lm: Optional[np.ndarray],
               s: Settings, assets: RigAssets) -> np.ndarray:
        H, W = cam_bgr.shape[:2]
        frame = cv2.flip(cam_bgr, 1) if s.mirror else cam_bgr
        if s.background == C.BG_CAM:
            out = frame.copy()
        else:
            out = np.empty_like(frame)
            out[:] = C.hex_to_bgr(s.background)
        if lm is None:
            return out

        # Landmarks in Pixel (gespiegelt wie das Bild)
        px = np.asarray(lm, dtype=np.float64).copy()
        if s.mirror:
            px[:, 0] = 1.0 - px[:, 0]
        px[:, 0] *= W
        px[:, 1] *= H

        # Gruppen links/rechts nach x sortiert (Augen mit/ohne Brauen)
        groups = [px[C.EYE_A + (C.BROW_A if s.brows else [])],
                  px[C.EYE_B + (C.BROW_B if s.brows else [])]]
        groups.sort(key=lambda g: mean_pt(g)[0])
        eyes = sorted([mean_pt(px[C.EYE_A]), mean_pt(px[C.EYE_B])], key=lambda e: e[0])
        lips = px[C.LIPS]
        mid = mean_pt(eyes)
        roll = math.atan2(eyes[1][1] - eyes[0][1], eyes[1][0] - eyes[0][0])
        d = max(math.hypot(eyes[1][0] - eyes[0][0], eyes[1][1] - eyes[0][1]), 1e-6)

        if self.rest is None or self._want_rest:
            self.rest = RestPose(mid[0], mid[1], roll, d)
            self._want_rest = False

        head = assets.head
        if head is None:
            return out
        a = assets.head_markers
        if s.mode == 0:
            self._simple(out, frame, s, head, a, groups, lips, mid, roll, d, W, H)
        else:
            self._rig(out, frame, s, assets, a, groups, lips, mid, roll, d, W, H)
        return out

    # ------------------------------------------------------------------
    def _simple(self, out, frame, s, head, a, groups, lips, mid, roll, d, W, H):
        """Modus 0: Bild klebt starr am Gesicht.

        Mit s.track_head == False bleibt das PNG an der Stelle der Ruhelage stehen
        (Position, Groesse; keine Drehung). Augen und Mund kommen weiterhin live aus
        der Kamera: Sie werden aufrecht gedreht und auf die Groesse der Ruhelage
        normiert, damit sie zum feststehenden PNG passen.
        """
        iw, ih = head.w, head.h
        if s.track_head:
            pos, ang, dist = mid, roll, d
            patch_rot, patch_rel = 0.0, 1.0
        else:
            neu = self.rest
            pos, ang, dist = (neu.x, neu.y), 0.0, neu.d
            patch_rot, patch_rel = -roll, neu.d / d
        k = s.image_scale * (dist / (H * .16)) * (H * .6 / ih)
        pv = ((a[0][0] + a[1][0]) / 2, (a[0][1] + a[1][1]) / 2)
        cs, sn = math.cos(ang), math.sin(ang)
        m = (mat_translate(pos[0], pos[1]) @ mat_rotate(ang) @ mat_scale(k)
             @ mat_translate(-pv[0] * iw, -pv[1] * ih))
        draw_affine(out, head.pm, m)

        def sp(q):  # Marker -> Ausgabepixel
            lx, ly = (q[0] - pv[0]) * iw * k, (q[1] - pv[1]) * ih * k
            return pos[0] + lx * cs - ly * sn, pos[1] + lx * sn + ly * cs

        for i in (0, 1):
            p = sp(a[i])
            stamp(out, cut(frame, groups[i], s.eye_margin, s.feather), p[0], p[1],
                  s.eye_scale * patch_rel, patch_rot)
        q = sp(a[2])
        stamp(out, cut(frame, lips, s.mouth_margin, s.feather), q[0], q[1],
              s.mouth_scale * patch_rel, patch_rot)

    # ------------------------------------------------------------------
    def _rig(self, out, frame, s, assets, a, groups, lips, mid, roll, d, W, H):
        """Modus 1 und 2: Kopf relativ zur Ruhelage, Hals gedehnt."""
        neu = self.rest
        f = s.follow
        th = HeadTransform(
            dx=(mid[0] - neu.x) * f,
            dy=(mid[1] - neu.y) * f,
            rot=clamp((roll - neu.r) * f, -.7, .7),
            sc=clamp(1 + (d / neu.d - 1) * f, .6, 1.6))
        im = assets.head
        iw, ih = im.w, im.h
        ps, hr = s.image_scale, s.head_ratio
        two = s.mode == 2
        body = None

        if two:
            Nx, Ny, sB = W / 2, H * .7, ps * H * .5 / ih
            b = assets.body
            if b is not None:
                sB = ps * H * .5 / b.h
                bx, by = (W - b.w * sB) / 2, H - b.h * sB
                Nx = bx + assets.body_marker[0][0] * b.w * sB
                Ny = by + assets.body_marker[0][1] * b.h * sB
                body = (b, sB, bx, by)
            s0 = sB * hr
            x0 = Nx - a[4][0] * iw * s0
            y0 = Ny - a[4][1] * ih * s0
        else:
            s0 = ps * H * .85 / ih
            x0 = (W - iw * s0) / 2
            y0 = H - ih * s0

        yb = a[4][1] * ih                 # Hals unten (Pivot), Bildpixel
        yt = min(a[3][1] * ih, yb)        # Hals oben
        px = a[4][0] * iw

        def strip(u, v, w):
            """Bildzeilen u..v mit Gewicht w zeichnen (1 = Kopf, 0 = Koerper)."""
            if v <= u:
                return
            r0 = int(math.floor(u))
            r1 = min(ih, int(math.ceil(v)))
            if r1 <= r0:
                return
            k = 1 + (th.sc - 1) * w
            m = (mat_translate(x0 + px * s0 + th.dx * w, y0 + yb * s0 + th.dy * w)
                 @ mat_rotate(th.rot * w) @ mat_scale(k)
                 @ mat_translate(-px * s0, -yb * s0)
                 @ mat_scale(s0) @ mat_translate(0, r0))
            draw_affine(out, im.pm[r0:r1], m)

        def draw_body():
            if body:
                b, sB, bx, by = body
                draw_affine(out, b.pm, mat_translate(bx, by) @ mat_scale(sB))

        behind = two and s.behind
        if two and not behind:
            draw_body()
        if two:
            strip(0, ih, 1)
        else:
            N = NECK_STRIPS
            # Kopfstreifen +1 Zeile, wie die Hals-Streifen: verhindert Nahtlinien
            strip(0, min(ih, yt + 1), 1)
            for i in range(N):
                strip(yt + (yb - yt) * i / N,
                      min(ih, yt + (yb - yt) * (i + 1) / N + 1),
                      1 - (i + .5) / N)
            strip(yb, ih, 0)

        # Augen & Mund: Anker durch die Kopf-Transformation schicken
        def hp(u, w):
            cx, cy = x0 + px * s0, y0 + yb * s0
            vx, vy = x0 + u * iw * s0 - cx, y0 + w * ih * s0 - cy
            c, sn = math.cos(th.rot), math.sin(th.rot)
            return (cx + th.dx + (vx * c - vy * sn) * th.sc,
                    cy + th.dy + (vx * sn + vy * c) * th.sc)

        rel = th.sc / (d / neu.d)
        rr = th.rot - roll
        for i in (0, 1):
            p = hp(a[i][0], a[i][1])
            stamp(out, cut(frame, groups[i], s.eye_margin, s.feather), p[0], p[1],
                  s.eye_scale * rel, rr)
        mp = hp(a[2][0], a[2][1])
        stamp(out, cut(frame, lips, s.mouth_margin, s.feather),
              mp[0], mp[1], s.mouth_scale * rel, rr)
        if behind:
            draw_body()
