# Trading-Bots: Aktien & Krypto

Drei Bausteine, eine gemeinsame Strategie- und Risiko-Logik (`strategy.py`):

| Datei              | Was                        | Börse  | Geld                      | Stop-Loss            |
|--------------------|----------------------------|--------|---------------------------|----------------------|
| `bot.py`           | Simulation / Backtest      | —      | Spielgeld                 | simuliert            |
| `live_trader.py`   | **Aktien** live            | Alpaca | Paper **oder** echt       | Bracket-Order        |
| `crypto_trader.py` | **Krypto** live            | Kraken | nur Analyse **oder** echt | nativ an der Börse   |

> ⚠️ **Wichtig, ehrlich gesagt:** Kein Bot kann Verluste ausschließen — bei
> Krypto erst recht nicht. Gutes Risikomanagement hält einen *einzelnen*
> Verlust klein (Stop-Loss, Positionsgröße, Limits), verhindert ihn aber
> nicht. Wer dir einen „verlustfreien" Bot verspricht, betrügt dich.
> Riskiere nur Geld, dessen Totalverlust du verkraftest. Keine Anlageberatung.

Warum für Krypto eine **andere Börse (Kraken)**? Weil ein Krypto-Bot ohne
echten Stop-Loss sinnlos ist — und Alpaca das für Krypto nicht bietet. Kraken
legt beim Kauf automatisch eine Stop-Loss-Order an der Börse mit ab
(„conditional close"), die auch dann greift, wenn der Bot gerade nicht läuft.

---

## Teil 1: Simulation (`bot.py`)

Ein Bot, der mit **Spielgeld** handelt und sauberes Risikomanagement vorführt.
Er **wächst**, wenn er Geld verdient, und **stoppt sich selbst**, wenn das
Kapital unter eine Ruin-Schwelle fällt.

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

## Teil 2: Aktien live (`live_trader.py`, Alpaca)

> 🛑 **Lies das zuerst.** `live_trader.py` sendet mit `--live` **reale Orders**
> auf dein echtes Alpaca-Konto. **Echtes Geld, echter Verlust.**
> Automatisiertes Trading mit einer simplen Strategie wie dieser macht
> **nicht zuverlässig Gewinn** — nach Gebühren und Slippage verliert so etwas
> im Schnitt eher Geld. Starte **immer zuerst auf dem Paper-Konto** und riskiere
> nur Geld, dessen Totalverlust du verkraftest.

### Einrichtung

1. Konto bei [alpaca.markets](https://alpaca.markets) anlegen (Paper ist gratis).
2. API-Keys erstellen (**Paper und Live haben getrennte Keys**).
3. Keys als Umgebungsvariablen setzen — **nie in den Code, nie ins Git**:
   ```bash
   cp .env.example .env     # .env ist per .gitignore ausgeschlossen
   # Keys in .env eintragen, dann:
   set -a; source .env; set +a
   ```

### Benutzung

```bash
python3 live_trader.py --symbol SPY --selftest   # Logik offline prüfen (kein Konto nötig)
python3 live_trader.py --symbol SPY --dry-run    # Paper: Signal + Order nur anzeigen
python3 live_trader.py --symbol SPY              # Paper-Konto: echte API, kein echtes Geld
python3 live_trader.py --symbol SPY --loop 300   # alle 5 Min. ein Zyklus (Paper)

# ECHTES GELD — verlangt Eintippen von "ECHTGELD" (oder --yes):
python3 live_trader.py --symbol SPY --live
```

### Eingebaute Schutzmechanismen

- **Stop-Loss je Trade** als Bracket-Order (geht direkt mit an die Börse).
- **Positions-Obergrenze** (`--max-position`, Standard 1000 $).
- **Tagesverlustlimit** (`--daily-loss-limit`, Standard 5 %): danach keine neuen Käufe.
- **Ruin-Stopp** (`--min-equity`): fällt das Konto darunter, kauft der Bot nicht mehr.
- **Nur eine offene Position**, nur Long, nur bei geöffneter Börse.
- **Paper als Standard** — echtes Geld nur mit explizitem `--live` + Bestätigung.

### Was dieser Bot NICHT ist

Keine Gewinngarantie, kein Geldautomat. Er ist eine saubere, geschützte
Umsetzung einer bekannten Strategie — ob sie in deinem Markt Geld verdient,
musst du **erst auf Paper über Wochen messen**, bevor du echtes Geld riskierst.

## Teil 3: Krypto live (`crypto_trader.py`, Kraken)

> 🛑 Mit `--live` **reale Krypto-Orders** auf deinem echten Kraken-Konto.
> Krypto ist **volatiler** als Aktien und handelt **24/7** — es kann nachts
> stark fallen, während du schläfst. Genau deshalb der exchange-seitige Stop.

### Einrichtung

1. Konto bei [kraken.com](https://www.kraken.com) anlegen.
2. API-Keys erstellen unter **Settings → API** (Rechte: Query + Create/Modify
   Orders; **kein** Withdraw-Recht nötig — lass es aus Sicherheit weg).
3. Keys in `.env` eintragen (`KRAKEN_API_KEY`, `KRAKEN_API_SECRET`) und laden:
   ```bash
   set -a; source .env; set +a
   ```

### Benutzung

```bash
python3 crypto_trader.py --selftest              # Logik + Signatur offline prüfen
python3 crypto_trader.py --pair XBTUSD --dry-run # BTC/USD analysieren, nichts senden
python3 crypto_trader.py --pair XBTUSD           # analysieren (ohne --live kein Senden)
python3 crypto_trader.py --pair XBTUSD --loop 300  # 24/7, alle 5 Min. ein Zyklus

# ECHTES GELD — verlangt Eintippen von "ECHTGELD" (oder --yes):
python3 crypto_trader.py --pair XBTUSD --live
```

Andere Coins: z. B. Ethereum mit
`--pair XETHZUSD --base-asset XETH --quote-asset ZUSD`.
Die Kraken-Asset-Codes (`XXBT`, `XETH`, `ZUSD`, `ZEUR` …) findest du in deiner
Kraken-Kontoübersicht.

### Unterschiede zum Aktien-Bot

- **Stop-Loss** wird als echte Order **an der Börse** mitgegeben (nicht nur im Bot).
- **Bruchteile** von Coins statt ganzer Stück.
- **24/7** — keine Börsenöffnungszeiten-Sperre; sinnvoll mit `--loop`.
- Höherer Standard-Stop (`--stop 0.05`), weil Krypto stärker schwankt.
- Tages-Equity wird lokal in `crypto_state.json` gemerkt (nicht committen).

## Nächste Schritte (optional)

- **Echte historische Kurse** testen: CSV mit `date,close` aus einer beliebigen
  Quelle laden (`--csv`). So siehst du, wie die Strategie auf echten Daten lief.
- **Andere Strategien**: die `run()`-Schleife in `bot.py` ist der einzige Ort,
  an dem die Kauf-/Verkauf-Logik steckt — leicht austauschbar (RSI, Breakout …).
- **Live-Paper-Trading** mit echten (verzögerten) Kursen: möglich über einen
  Broker-Paper-Account (z. B. Alpaca Paper) — immer noch ohne echtes Geld.

## Dateien

- `strategy.py` — **gemeinsame** Strategie- & Risiko-Logik (von beiden Live-Bots genutzt).
- `bot.py` — Simulations-Bot (Strategie, Risikomanagement, Auswertung).
- `live_trader.py` — **Aktien** live über die Alpaca-API (Paper & Live).
- `crypto_trader.py` — **Krypto** live über die Kraken-API (Analyse & Live).
- `make_demo_data.py` — erzeugt die Demo-Kursreihen.
- `demo_boom.csv`, `demo_trap.csv` — Beispieldaten für die zwei Mechaniken.
- `.env.example` — Vorlage für die API-Keys (echte `.env` wird nie committet).

## Selbsttests

Alle reine Logik ist offline testbar (keine Keys/Netz nötig):

```bash
python3 strategy.py                      # gemeinsame Logik
python3 live_trader.py --selftest        # Aktien-Bot
python3 crypto_trader.py --selftest      # Krypto-Bot + Kraken-Signatur-Testvektor
```
