# Reel-Cutter

Eine kleine Web-App, die aus dem Transkript eines Rohvideos einen Schnittplan für ein Instagram-Reel (30–60 Sekunden) macht.

## Was sie macht

1. **Hook**: der stärkste Einstiegssatz, mit Hinweis, falls du ihn nach vorne ziehen musst
2. **Schnittliste**: jeder Satz mit BEHALTEN oder RAUS, bei RAUS mit Grund in 3–5 Wörtern
3. **Reihenfolge**: die behaltenen Sätze in Schnittreihenfolge
4. **Text oben im Bild**: 3 Varianten mit höchstens 6 Wörtern
5. **Untertitel**: sauberer Text in Zeilen mit höchstens 4 Wörtern, auch als `.srt`-Datei
6. **Ende**: geschätzte Länge und der beste Abschlusssatz

## Damit nichts erfunden wird

- Das Transkript wird im Browser in nummerierte Sätze zerlegt. Claude wählt nur Satznummern aus und schreibt keine eigenen Sätze.
- Jede bereinigte Untertitel-Fassung wird geprüft. Enthält sie ein Wort, das du in diesem Satz nicht gesagt hast, wird stattdessen dein Originalsatz verwendet und ein Hinweis angezeigt.
- Untertitel-Zeilen, Reel-Länge (ca. 2,6 Wörter pro Sekunde) und Hook-Position werden lokal berechnet.

## Benutzung

1. `index.html` im Browser öffnen (Doppelklick reicht).
2. Anthropic API-Key eintragen (bekommst du unter console.anthropic.com). Der Key bleibt in deinem Browser.
3. Transkript einfügen und auf **Schnittplan erstellen** klicken.

**Ohne API-Key:** Mit **Prompt kopieren** wird der komplette Prompt mit deinem Transkript kopiert. Den kannst du direkt in die Claude-App einfügen.

Hat dein Transkript keine Satzzeichen, setz pro Satz eine neue Zeile.
