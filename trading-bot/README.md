# Paper-Trading-Bot

Ein Trading-Bot, der mit **Spielgeld** handelt und sauberes Risikomanagement
vorführt. Er **wächst**, wenn er Geld verdient, und **stoppt sich selbst**,
wenn das Kapital unter eine Ruin-Schwelle fällt.

> ⚠️ **Nur zum Lernen.** Der Bot sendet **keine echten Orders** und bewegt
> **kein echtes Geld**. Keine Anlageberatung. Historische oder simulierte
> Ergebnisse sagen nichts über die Zukunft aus.

## Die Idee

Du wolltest einen Bot, der sich *vermehrt, wenn er Geld verdient*, und
*stirbt, wenn nicht*. Hier ist die legale, sichere Übersetzung davon:

| Dein Konzept            | Umsetzung hier                                                        |
|-------------------------|-----------------------------------------------------------------------|
| „vermehrt sich"         | Der Einsatz ist ein Bruchteil des **aktuellen** Kapitals → Gewinne werden reinvestiert (Zinseszins). Jede Kapital-Verdopplung = neue „Generation". |
| „stirbt"                | Fällt das Kapital unter die Ruin-Schwelle (Standard: 70 % des Starts), stoppt der Bot den Handel. |
| „auf unethische Weise"  | **Weggelassen.** Stattdessen: eine ehrliche, regelbasierte Strategie mit Stop-Loss und Verlustlimits. |

## Strategie

Einfacher **Gleitender-Durchschnitt-Crossover** (nur Long):

- Long, solange der schnelle SMA über dem langsamen liegt (bullisches Regime).
- Verkauf, wenn der schnelle SMA darunter fällt — oder wenn der Stop-Loss greift.

Dazu das Risikomanagement, das den Bot am Leben hält:

- **Positionsgröße** = fester Risiko-Anteil des Kapitals pro Trade (Standard 1 %).
- **Stop-Loss** pro Trade (Standard 3 %).
- **Tägliches Verlustlimit** (Standard 5 %): danach heute keine neuen Käufe.
- **Ruin-Schwelle** (Standard 70 %): darunter stoppt der Bot ganz.
- **Gebühren** werden simuliert (Standard 0,1 % je Trade-Seite).

## Benutzung

Reines Python, keine Installation nötig (Python 3.10+):

```bash
# Demo mit synthetischen, reproduzierbaren Kursen
python3 bot.py

# Eigene Kurse aus CSV (Spalten: date,close)
python3 bot.py --csv meine_kurse.csv

# Parameter anpassen
python3 bot.py --capital 5000 --risk 0.02 --stop 0.04 --fast 10 --slow 30
```

Wichtige Optionen: `--capital`, `--risk`, `--stop`, `--fast`, `--slow`,
`--seed`, `--bars`, `--csv`, `--quiet`. Alle mit `python3 bot.py --help`.

## Die zwei Mechaniken live sehen

Demo-Kursreihen erzeugen und laufen lassen:

```bash
python3 make_demo_data.py          # schreibt demo_boom.csv und demo_trap.csv

# VERMEHRUNG: starker Aufwärtstrend -> Kapital verdoppelt sich
python3 bot.py --csv demo_boom.csv
#   🌱 Kapital verdoppelt -> Generation 2
#   Rendite ~ +276 %, Status: LEBT

# TOD: Bullenfalle (lockt rein, stoppt wieder aus) -> Ruin
python3 bot.py --csv demo_trap.csv --risk 0.15 --stop 0.05
#   💀 Ruin-Schwelle unterschritten -> Bot stoppt.
#   Status: GESTORBEN (Ruin)
```

## Nächste Schritte (optional)

- **Echte historische Kurse** testen: CSV mit `date,close` aus einer beliebigen
  Quelle laden (`--csv`). So siehst du, wie die Strategie auf echten Daten lief.
- **Andere Strategien**: die `run()`-Schleife in `bot.py` ist der einzige Ort,
  an dem die Kauf-/Verkauf-Logik steckt — leicht austauschbar (RSI, Breakout …).
- **Live-Paper-Trading** mit echten (verzögerten) Kursen: möglich über einen
  Broker-Paper-Account (z. B. Alpaca Paper) — immer noch ohne echtes Geld.

## Dateien

- `bot.py` — der Bot (Strategie, Risikomanagement, Auswertung).
- `make_demo_data.py` — erzeugt die Demo-Kursreihen.
- `demo_boom.csv`, `demo_trap.csv` — Beispieldaten für die zwei Mechaniken.
