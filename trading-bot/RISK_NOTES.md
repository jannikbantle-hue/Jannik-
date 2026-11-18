# Was die besten Trader wirklich tun (und wie man wenig verliert)

Recherche-Zusammenfassung, destilliert auf das, was belegbar ist. Ehrlich:
Es gibt **keinen Trick, der Verluste ausschließt**. Die Profis verlieren
*ständig* — nur klein. Gewinnen tun sie, weil die Gewinne größer sind als die
vielen kleinen Verluste. Das ist das ganze Geheimnis.

> ⚠️ Die meisten frei verfügbaren Quellen sind Trading-Blogs oder Anbieter mit
> Verkaufsinteresse. Konkrete Zahlen unten sind **Faustregeln**, keine Gesetze.

---

## 1. Die eine Regel, die zählt: Positionsgröße

Nicht die Strategie entscheidet übers Überleben, sondern **wie viel du pro
Trade riskierst**. Der Profi-Standard:

- **Riskiere höchstens 1 % (max. 2 %) deines Kapitals pro Trade.**
  „Riskieren" heißt: der Verlust bis zu deinem Stop-Loss, nicht der Einsatz.
- **Rechne die Größe vom Stop her**, nicht umgekehrt:
  ```
  Positionsgröße = (Kapital × Risiko%) / (Einstieg − Stop-Preis)
  ```
  Beispiel: 10.000 € Kapital, 1 % Risiko = 100 € max. Verlust. Stop 3 % unter
  Einstieg bei 50 € → Risiko/Stück 1,50 € → 100 / 1,50 ≈ **66 Stück**.

→ In unseren Bots: `--risk 0.01` und `--stop 0.03`. Genau diese Formel steckt
in `strategy.py → size_order()`.

## 2. Warum 1 % und nicht 5 %: Risk of Ruin

„Risk of Ruin" = Wahrscheinlichkeit, dass du pleite gehst, *bevor* dein
Vorteil sich auszahlt. Sie steigt **überproportional** mit der Positionsgröße:

| Risiko pro Trade | grobe Ruin-Wahrscheinlichkeit (moderater Vorteil) |
|------------------|---------------------------------------------------|
| 1 %              | nahe 0                                            |
| 2 %              | ~5–7 %                                            |
| 4 %              | ~25–30 %                                          |
| 5 %              | ~13 % (bei 55 % Trefferquote, 2:1)                |

Die Zahlen schwanken je nach Quelle und Annahmen — aber die **Richtung** ist
eindeutig: doppelt so groß gewettet heißt viel mehr als doppeltes Ruin-Risiko.

→ In unseren Bots: `--min-equity` (Ruin-Stopp) + `--daily-loss-limit`.

## 3. Expectancy (Erwartungswert) ≠ Überleben

Zwei verschiedene Fragen:

- **Expectancy**: Was verdient ein Trade *im Durchschnitt* über tausende Trades?
  ```
  Expectancy = (Trefferquote × Ø-Gewinn) − (Verlustquote × Ø-Verlust)
  ```
  Ist das negativ, verliert die Strategie langfristig garantiert — egal wie gut
  das Risikomanagement ist. **Erst messen, ob positiv, dann skalieren.**
- **Risk of Ruin**: Überlebst du lange genug, um den Durchschnitt zu erreichen?

Ein positiver Erwartungswert nützt nichts, wenn eine Pechsträhne dich vorher
rauswirft. Deshalb: kleine Positionen **und** positiver Erwartungswert.

## 4. Kelly-Kriterium: Obergrenze, kein Ziel

Die Kelly-Formel sagt die „mathematisch optimale" Wettgröße für maximales
Wachstum. **Kein Profi nutzt volles Kelly** — es ist viel zu schwankend. In der
Praxis: Kelly als *Diagnose* („wette ich zu groß?"), und real meist
**¼-Kelly oder weniger**. Unsere 1-%-Regel liegt praktisch immer darunter.

## 5. Die vier Schutzschichten (so bauen es Profis)

1. **Positionsgröße** — wie viel pro Trade (1 %).
2. **Stop-Loss** — wo du einen Verlust-Trade verlässt (vorher festgelegt).
3. **Tages-/Wochen-Verlustlimit** — wann du für heute aufhörst.
4. **Drawdown-Management** — kleiner werden, wenn das Konto fällt.

Alle vier sind in unseren Bots umgesetzt (`strategy.py`, `--daily-loss-limit`,
`--min-equity`, Positionsgröße als Bruchteil des *aktuellen* Kapitals).

## 6. Mentale Regeln, die immer wiederkehren

- **Verluste sind Betriebskosten**, keine Fehler. Plane sie ein.
- **Nie den Stop nach unten verschieben**, um einen Verlust zu vermeiden.
- **Nicht „nachkaufen", um den Schnitt zu senken** (Averaging down) — so werden
  kleine Verluste zu großen.
- **Korrelierte Positionen zählen als eine** (3× Krypto = 1 großes Risiko).
- **Weniger handeln** ist oft besser. Gebühren und Fehler summieren sich.

---

## 7. Zur Krypto-Arbitrage (ehrliche Faktenlage)

Du wolltest einen Arbitrage-Bot. Die Belege, warum das für Privatleute fast nie
funktioniert:

- **Geschwindigkeit**: Eine Uni-Studie (Bamberg) fand auf Binance in einer
  Woche tausende scheinbare Dreieck-Arbitragen — profitabel aber nur, wenn man
  **in ≤ 146 Millisekunden** ausführt. Menschen und normale Bots sind viel zu
  langsam; HFT-Firmen mit Servern direkt neben der Börse gewinnen.
- **Gebühren fressen die Spanne**: Pro Leg ~0,1–0,4 % Taker-Gebühr. Ein Dreieck
  hat 3 Legs → ~0,3–1,2 % Gebühren. Die Brutto-Spanne ist aber nur **1–10
  Basispunkte (0,01–0,10 %)** und sekundenschnell weg. Rechnung geht fast immer
  negativ auf.
- **Fazit**: Der Arbitrage-Scanner (`arbitrage.py`) rechnet genau das mit
  **echten Gebühren** nach und zeigt dir meistens: **lohnt sich nicht.** Das ist
  kein Bug, das ist die Realität — und schützt dich vor der häufigsten Falle.

---

## Quellen

- [Risk Management Rules (heygotrade)](https://www.heygotrade.com/en/blog/risk-management-rules-every-trader-should-know)
- [Risk Management Complete Guide (TradeZella)](https://tradezella.com/blog/risk-management-trading)
- [Risk of Ruin erklärt (daytradingtoolkit)](https://daytradingtoolkit.com/beginners-guide/risk-of-ruin-math-explained)
- [Traders' Survival Guide (tradingsetupsreview)](https://tradingsetupsreview.com/traders-survival-guide-primer-risk-management)
- [Triangular Arbitrage: Transaktionskosten-Studie (Uni Bamberg, PDF)](https://fis.uni-bamberg.de/bitstreams/8b9ae900-017a-4bed-94b9-609c16e89945/download)
- [Crypto Arbitrage Guide (DEXTools)](https://www.dextools.io/news/what-is-crypto-arbitrage-trading-guide-2026)
- [Kraken Fee Schedule (offiziell)](https://www.kraken.com/features/fee-schedule)

*Zahlen sind Faustregeln aus teils werblichen Quellen — prüfe Gebühren immer
direkt bei deiner Börse. Keine Anlageberatung.*
