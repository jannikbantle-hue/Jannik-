# Start mit 100 € — Schritt für Schritt

Zwei Bots, je ~100 € Startkapital. Beide sind fertig konfiguriert (Risiko 1 %
pro Trade, Stop-Loss, Tagesverlustlimit 5 %, Ruin-Stopp bei 70). Du startest
jeden mit **einem Befehl**.

> ⚠️ Der **erste Start ist immer sicher** (Analyse bzw. Paper, keine echten
> Orders). Echtes Geld schaltest du bewusst mit `live` ein. Kein Bot kann
> Verluste ausschließen — 100 € ist ein Test, kein Sparplan.

---

## Einmalig: vorbereiten

```bash
cd trading-bot
cp .env.example .env     # danach deine echten Keys in .env eintragen
```

Prüfen, dass alles läuft (keine Keys nötig):
```bash
python3 strategy.py && python3 crypto_trader.py --selftest && python3 live_trader.py --selftest
```

---

## Bot 1: Krypto (Kraken, BTC/EUR) — der echte 100-€-Bot

Krypto passt zu 100 €: Bruchteile von Coins, EUR-Paar, in Deutschland nutzbar.
Bei ~100 € kauft der Bot pro Trade eine **~20-€-Position und riskiert ~1 €**.

1. Konto: [kraken.com](https://www.kraken.com) → verifizieren → **100 € einzahlen**.
2. API-Keys: **Settings → API** → neuen Key, Rechte *Query* + *Create/Modify
   Orders*. **Withdraw-Recht NICHT** aktivieren (Sicherheit). In `.env` eintragen:
   `KRAKEN_API_KEY=...` und `KRAKEN_API_SECRET=...`
3. Erst sicher testen, dann scharf schalten:
   ```bash
   ./start_crypto.sh          # Analyse: zeigt Signale, sendet NICHTS
   ./start_crypto.sh live     # ECHTES GELD (tippe "ECHTGELD" zum Bestätigen)
   ```
   Läuft dann alle 60 Minuten (24/7). Stoppen: `Strg+C`.

---

## Bot 2: Aktien (Alpaca) — ehrlich: eher Paper

Zwei Einschränkungen bei 100 €:
- **Alpaca-Live ist v. a. für US-Kunden.** Als EU-Bürger kannst du oft **kein
  echtes** Konto eröffnen — das **Paper-Konto (Spielgeld) geht aber weltweit**
  und nutzt echte Kurse. Für echte EU-Aktien bräuchtest du später einen
  anderen Broker (kann ich einbauen).
- Der Bot kauft **ganze Aktien** (für den Stop-Loss). Mit 100 € nur bei Aktien
  **unter ~30 €/Stück** sinnvoll (z. B. `F` ≈ 11 USD). Bei teuren wie `SPY`
  kauft er nichts.

1. Konto: [alpaca.markets](https://alpaca.markets) → **Paper-Keys** erstellen
   (für echtes Geld separate Live-Keys). In `.env`:
   `ALPACA_API_KEY_ID=...` und `ALPACA_API_SECRET_KEY=...`
2. Günstige Aktie wählen und starten:
   ```bash
   SYMBOL=F ./start_stocks.sh         # Paper (Spielgeld, 100 USD virtuell)
   SYMBOL=F ./start_stocks.sh live    # echtes Geld (nur mit Alpaca-Live-Konto)
   ```
   Läuft während der US-Börsenzeiten, prüft alle 15 Min. Stoppen: `Strg+C`.

---

## „Wie weit kommen wir nach oben?" — Fortschritt sehen

- **Kraken**: App/Website → *Portfolio* zeigt deinen Kontostand live.
- **Alpaca**: Dashboard zeigt Paper- bzw. Live-Equity.
- Der Bot schreibt jeden Zyklus eine Zeile ins Terminal (Equity, Signal,
  Käufe/Verkäufe). Lass ihn in einem Terminal laufen und schau rein.

Lauf beide am besten erst **1–2 Wochen im sicheren Modus** und vergleiche, ob
sie nach Gebühren überhaupt im Plus wären, bevor du auf `live` gehst. Das ist
genau der Schritt, den die meisten überspringen (siehe `RISK_NOTES.md`).

## Die eingebauten Stopps (gelten automatisch)

| Schutz              | Wert    | Bedeutung                                      |
|---------------------|---------|------------------------------------------------|
| Risiko pro Trade    | 1 %     | ~1 € max. Verlust pro Trade bei 100 €          |
| Stop-Loss           | 3–5 %   | automatischer Ausstieg bei Verlust             |
| Tagesverlustlimit   | 5 %     | danach heute keine neuen Käufe                 |
| Ruin-Stopp          | 70      | fällt das Konto auf 70, hört der Bot auf       |
| Positions-Cap       | 30      | nie mehr als ~30 in einer Position             |
