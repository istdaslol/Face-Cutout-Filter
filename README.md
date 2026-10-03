# Face Cutout Filter

Eine Browser App, welche Augen und Mund ausschneidet und auf ein beliebiges PNG einfügt. Das PNG folgt der Kopfbeweung.
Inspiriert von "TheBurntPeanut"

## Benutzung

1. `gesichts-filter.html` im Browser oeffnen.
2. "Kamera starten" klicken und den Kamerazugriff erlauben.
3. Ein PNG laden (Button, Drag & Drop oder Strg+V).
4. Drei Marker auf dem Bild setzen: linkes Auge, rechtes Auge, Mund.
5. Mit den Reglern feinjustieren.

## Funktionen

- Augen (optional mit Augenbrauen) und Mund werden live ausgeschnitten und
  auf die Marker gesetzt
- Das Bild folgt Kopfposition, Neigung und Abstand zur Kamera
- Regler: Bildgrösse, Augengrösse, Mundgrösse, Ausschnitt-Rand,
  weiche Kante
- Spiegeln an/aus
- Hintergrund: Kamerabild, Greenscreen, Schwarz, Weiss
- Modus "Nur Ausgabe" fürs Streaming (blendet die Bedienung aus,
  Esc zum Zurückkehren)

## Streaming mit OBS

Seite oeffnen, "Nur Ausgabe (für OBS)" klicken und das Browserfenster
per Fensteraufnahme oder Anzeigeaufnahme erfassen. Für einen
freigestellten Look den Greenscreen-Hintergrund waehlen und in OBS einen
Chroma-Key-Filter hinzufügen.

## Voraussetzungen

- Ein aktueller Chromium-basierter Browser oder Firefox
- Eine Webcam
- Internetzugang beim ersten Start (siehe unten)

## Funktionsweise

Die Gesichtspunkte (478 Stück) werden mit Google MediaPipe Face Landmarker
erkannt. Die Bereiche um Augen und Mund werden maskiert, weich ausgeblendet
und an den Markerpositionen gezeichnet. Das Bild wird anhand der Augenlinie
gedreht und skaliert.

Alles läuft lokal im Browser. Es werden keine Video- oder Bilddaten
hochgeladen.

## Externe Ressourcen

Beim Start werden diese Dateien geladen:

- `@mediapipe/tasks-vision` (JavaScript und WASM) von cdn.jsdelivr.net
- Das Modell `face_landmarker.task` von storage.googleapis.com

MediaPipe steht unter der Apache-2.0-Lizenz von Google.

## Einschränkungen

- Das Bild ist flach, es gibt keine echte 3D-Drehung
- Es wird nur ein Gesicht erfasst
- Die weiche Kante braucht einen Browser mit Canvas-Filter-Unterstuetzung
  (nicht Safari)
- Nicht auf allen Browsern, Kameras und Lichtverhaeltnissen getestet

## KI-Hinweis

Dieses Projekt wurde mit Hilfe von KI erstellt (Claude von Anthropic).
Der Code kann Fehler oder unerwartetes Verhalten enthalten. Er wird so
bereitgestellt, wie er ist, ohne jegliche Gewaehrleistung. Bitte pruefe
den Code, bevor du dich darauf verlaesst.
