#!/usr/bin/env python3
"""
arbitrage.py — EHRLICHER Dreieck-Arbitrage-Scanner für Kraken.

Prüft einen Dreieck-Zyklus (z. B. USD → BTC → ETH → USD) mit ECHTEN Kursen
und ECHTEN Gebühren und sagt dir, ob nach Gebühren überhaupt ein Gewinn
übrig bleibt. Meistens lautet die Antwort: NEIN — und genau das ist der Sinn.

Warum nur ein Scanner und kein Ausführer?
  - Privatleute können Dreieck-Arbitrage praktisch nicht profitabel ausführen:
    Die Spanne ist winzig (1–10 Basispunkte), sekundenschnell weg, und muss
    laut Studien in < 146 ms ausgeführt werden. HFT-Bots gewinnen immer.
  - Gebühren (3 Legs × Taker-Gebühr) fressen die Spanne fast immer auf.
  Ein Scanner zeigt dir die Realität, ohne dass du Geld riskierst.

Öffentliche Kursdaten → KEINE API-Keys nötig.

Beispiele:
    python3 arbitrage.py --selftest           # Rechenlogik offline prüfen
    python3 arbitrage.py                       # USD-BTC-ETH-Dreieck, einmal
    python3 arbitrage.py --taker-fee 0.0026    # eigene Gebühr (Bruchteil)
    python3 arbitrage.py --loop 10             # alle 10 s scannen
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

API_BASE = "https://api.kraken.com"


# --------------------------------------------------------------------------- #
#  Reine Rechenlogik (ohne Netzwerk) — gut testbar.
# --------------------------------------------------------------------------- #
def cycle_net(ask_ba: float, bid_ba: float,
              ask_ca: float, bid_ca: float,
              ask_cb: float, bid_cb: float,
              fee: float) -> tuple[float, float]:
    """
    Nettoergebnis beider Richtungen eines Dreiecks aus Assets A, B, C.
    Paare: B/A (Preis von B in A), C/A, C/B. Start mit 1 Einheit A.
    Rückgabe: (netto_ABC, netto_ACB) als Bruchteil, z. B. 0.001 = +0,1 %.

    'ask' = du kaufst (zahlst den höheren Preis),
    'bid' = du verkaufst (bekommst den niedrigeren Preis).
    Jede der 3 Legs kostet die Taker-Gebühr `fee`.
    """
    keep = 1.0 - fee

    # Richtung 1:  A → B → C → A
    b = (1.0 / ask_ba) * keep          # A kauft B
    c = (b / ask_cb) * keep            # B kauft C (C/B-Markt)
    a1 = (c * bid_ca) * keep           # C verkauft gegen A (C/A-Markt)
    net_abc = a1 - 1.0

    # Richtung 2:  A → C → B → A
    c2 = (1.0 / ask_ca) * keep         # A kauft C
    b2 = (c2 * bid_cb) * keep          # C verkauft gegen B (C/B-Markt)
    a2 = (b2 * bid_ba) * keep          # B verkauft gegen A (B/A-Markt)
    net_acb = a2 - 1.0

    return net_abc, net_acb


# --------------------------------------------------------------------------- #
#  Öffentliche Kraken-Kurse (keine Keys nötig)
# --------------------------------------------------------------------------- #
def fetch_ask_bid(pair: str) -> tuple[float, float]:
    url = f"{API_BASE}/0/public/Ticker?" + urllib.parse.urlencode({"pair": pair})
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            resp = json.loads(r.read().decode())
    except urllib.error.URLError as e:
        raise SystemExit(f"Netzwerkfehler (Ticker {pair}): {e}")
    if resp.get("error"):
        raise SystemExit(f"Kraken-Fehler (Ticker {pair}): {resp['error']}")
    result = resp["result"]
    key = next(iter(result))                 # einziges Paar in der Antwort
    data = result[key]
    return float(data["a"][0]), float(data["b"][0])   # ask, bid


# --------------------------------------------------------------------------- #
#  Ein Scan
# --------------------------------------------------------------------------- #
def scan(args) -> None:
    def log(m: str) -> None:
        print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)

    ask_ba, bid_ba = fetch_ask_bid(args.pair_ba)
    ask_ca, bid_ca = fetch_ask_bid(args.pair_ca)
    ask_cb, bid_cb = fetch_ask_bid(args.pair_cb)

    net_abc, net_acb = cycle_net(ask_ba, bid_ba, ask_ca, bid_ca,
                                 ask_cb, bid_cb, args.taker_fee)

    def verdict(name: str, net: float) -> None:
        pct = net * 100
        if net > 0:
            log(f"🟢 {name}: +{pct:.4f} % NACH Gebühren — theoretisch profitabel "
                f"(prüfe Liquidität/Tempo!)")
        else:
            log(f"🔴 {name}: {pct:.4f} % nach Gebühren — Verlust, lohnt sich nicht.")

    log(f"{args.a}/{args.b}/{args.c} | Taker-Gebühr {args.taker_fee*100:.3f} %/Leg "
        f"(≈ {args.taker_fee*300:.2f} % für 3 Legs)")
    verdict(f"{args.a}→{args.b}→{args.c}→{args.a}", net_abc)
    verdict(f"{args.a}→{args.c}→{args.b}→{args.a}", net_acb)


# --------------------------------------------------------------------------- #
#  Selbsttest (offline)
# --------------------------------------------------------------------------- #
def selftest() -> int:
    ok = True

    def check(name: str, cond: bool) -> None:
        nonlocal ok
        print(f"  [{'OK ' if cond else 'FAIL'}] {name}")
        ok = ok and cond

    # Konsistente Preise (keine Arbitrage): BTC=100, ETH=10, ETH/BTC=0,1.
    # Ohne Gebühren muss der Zyklus ≈ 0 ergeben.
    n1, n2 = cycle_net(100, 100, 10, 10, 0.1, 0.1, fee=0.0)
    check("Konsistente Preise, 0 Gebühr → ~0", abs(n1) < 1e-9 and abs(n2) < 1e-9)

    # Dieselben Preise MIT realer Gebühr → beide Richtungen negativ.
    n1f, n2f = cycle_net(100, 100, 10, 10, 0.1, 0.1, fee=0.004)
    check("Konsistente Preise + Gebühr → Verlust", n1f < 0 and n2f < 0)
    check("Gebühr ≈ 3 Legs (~1,2 %)", -0.013 < n1f < -0.011)

    # Künstliche Fehlbewertung (ETH im BTC-Markt zu billig) → Richtung 1 positiv.
    p1, _ = cycle_net(100, 100, 10, 10, 0.09, 0.09, fee=0.0)
    check("Echte Fehlbewertung ohne Gebühr → profitabel", p1 > 0.1)

    # Selbst diese große Fehlbewertung bleibt mit Gebühr profitabel ...
    p1f, _ = cycle_net(100, 100, 10, 10, 0.09, 0.09, fee=0.004)
    check("… und knapp mit Gebühr (großer Spread nötig)", p1f > 0)

    print("\nSelbsttest:", "ALLE BESTANDEN ✅" if ok else "FEHLER ❌")
    return 0 if ok else 1


# --------------------------------------------------------------------------- #
#  CLI
# --------------------------------------------------------------------------- #
def main() -> None:
    p = argparse.ArgumentParser(
        description="Ehrlicher Dreieck-Arbitrage-Scanner für Kraken (nur Analyse).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--a", default="USD", help="Label Asset A (Start/Ende)")
    p.add_argument("--b", default="BTC", help="Label Asset B")
    p.add_argument("--c", default="ETH", help="Label Asset C")
    p.add_argument("--pair-ba", default="XBTUSD", help="Kraken-Paar B/A")
    p.add_argument("--pair-ca", default="ETHUSD", help="Kraken-Paar C/A")
    p.add_argument("--pair-cb", default="ETHXBT", help="Kraken-Paar C/B")
    p.add_argument("--taker-fee", type=float, default=0.004,
                   help="Taker-Gebühr pro Leg als Bruchteil (Standard 0,40 %)")
    p.add_argument("--loop", type=int, default=0, help="Sekunden zwischen Scans (0=einmal)")
    p.add_argument("--selftest", action="store_true", help="Rechenlogik offline prüfen")
    args = p.parse_args()

    if args.selftest:
        sys.exit(selftest())

    print("=" * 64)
    print("  Dreieck-Arbitrage-Scanner (Kraken) — NUR Analyse, keine Orders")
    print("  Hinweis: profitable Treffer sind fast immer zu klein/zu langsam,")
    print("  um sie als Privatperson wirklich auszuführen. Siehe RISK_NOTES.md.")
    print("=" * 64)

    while True:
        try:
            scan(args)
        except SystemExit:
            raise
        except Exception as e:
            print(f"[Fehler im Scan] {e}", file=sys.stderr, flush=True)
        if args.loop <= 0:
            break
        time.sleep(args.loop)


if __name__ == "__main__":
    main()
