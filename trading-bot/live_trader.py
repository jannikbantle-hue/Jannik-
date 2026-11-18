#!/usr/bin/env python3
"""
live_trader.py — handelt mit ECHTEM Geld über die Alpaca-Broker-API.

  ┌───────────────────────────────────────────────────────────────┐
  │  WARNUNG: Mit --live werden REALE Orders auf deinem echten      │
  │  Alpaca-Konto ausgeführt. Echtes Geld, echter Verlust.          │
  │  OHNE --live läuft alles gegen das Paper-Konto (kein Geld).     │
  │  Automatisiertes Trading macht NICHT zuverlässig Gewinn.        │
  └───────────────────────────────────────────────────────────────┘

Strategie: SMA-Crossover (nur Long), identisch zur Simulation in bot.py.
Schutz:    Stop-Loss je Trade (Bracket-Order), Tagesverlustlimit,
           Mindest-Equity ("Ruin-Stopp"), Positions-Obergrenze, nur eine
           offene Position, Handel nur bei geöffneter Börse.

API-Keys NUR über Umgebungsvariablen setzen (niemals in Code/Git):
    export ALPACA_API_KEY_ID=dein_key
    export ALPACA_API_SECRET_KEY=dein_secret

Beispiele:
    python3 live_trader.py --symbol SPY --selftest        # Logik offline prüfen
    python3 live_trader.py --symbol SPY --dry-run          # Paper, nur anzeigen
    python3 live_trader.py --symbol SPY                    # Paper-Konto, echte API
    python3 live_trader.py --symbol SPY --live --yes       # ECHTES GELD
    python3 live_trader.py --symbol SPY --loop 300         # alle 5 Min. ein Zyklus
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

PAPER_BASE = "https://paper-api.alpaca.markets"
LIVE_BASE = "https://api.alpaca.markets"
DATA_BASE = "https://data.alpaca.markets"


# --------------------------------------------------------------------------- #
#  Reine Logik (ohne Netzwerk) — hier liegt die Entscheidung, gut testbar.
# --------------------------------------------------------------------------- #
def sma(values: list[float], period: int) -> float | None:
    if len(values) < period:
        return None
    return sum(values[-period:]) / period


def decide(closes: list[float], fast: int, slow: int, have_position: bool) -> str:
    """Gibt 'buy', 'sell' oder 'hold' zurück (Regime: Long solange fast > slow)."""
    f, s = sma(closes, fast), sma(closes, slow)
    if f is None or s is None:
        return "hold"
    bullish = f > s
    if bullish and not have_position:
        return "buy"
    if not bullish and have_position:
        return "sell"
    return "hold"


def size_order(equity: float, price: float, risk: float, stop_pct: float,
               max_position: float, buying_power: float) -> int:
    """Ganze Stückzahl aus Risiko-pro-Trade, gedeckelt durch Kaufkraft & Cap."""
    if price <= 0 or stop_pct <= 0:
        return 0
    dollars_at_risk = equity * risk
    per_share_risk = price * stop_pct
    qty = dollars_at_risk / per_share_risk
    cap_dollars = min(max_position, buying_power)
    qty = min(qty, cap_dollars / price)
    return max(0, math.floor(qty))


def risk_gate(equity: float, last_equity: float, min_equity: float,
              daily_loss_limit: float) -> tuple[bool, str]:
    """Darf eine NEUE Position eröffnet werden? (Schließen ist immer erlaubt.)"""
    if equity < min_equity:
        return False, f"💀 Equity {equity:.2f} < Mindest-Equity {min_equity:.2f} — Ruin-Stopp."
    if last_equity > 0:
        day_pl = (equity - last_equity) / last_equity
        if day_pl <= -daily_loss_limit:
            return False, f"🔒 Tagesverlust {day_pl:.1%} ≥ Limit — heute keine neuen Käufe."
    return True, "ok"


# --------------------------------------------------------------------------- #
#  Alpaca-API-Zugriff
# --------------------------------------------------------------------------- #
class Alpaca:
    def __init__(self, base: str, key: str, secret: str):
        self.base, self.key, self.secret = base, key, secret

    def _req(self, method: str, base: str, path: str,
             params: dict | None = None, body: dict | None = None):
        url = base + path
        if params:
            url += "?" + urllib.parse.urlencode(params)
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("APCA-API-KEY-ID", self.key)
        req.add_header("APCA-API-SECRET-KEY", self.secret)
        req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                raw = r.read().decode()
                return json.loads(raw) if raw else None
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            raise SystemExit(f"API-Fehler {e.code} bei {method} {path}: {e.read().decode()}")
        except urllib.error.URLError as e:
            raise SystemExit(f"Netzwerkfehler bei {method} {path}: {e.reason}")

    def account(self) -> dict:
        return self._req("GET", self.base, "/v2/account")

    def clock(self) -> dict:
        return self._req("GET", self.base, "/v2/clock")

    def position(self, symbol: str) -> dict | None:
        return self._req("GET", self.base, f"/v2/positions/{symbol}")

    def bars(self, symbol: str, timeframe: str, limit: int, feed: str) -> list[float]:
        resp = self._req("GET", DATA_BASE, f"/v2/stocks/{symbol}/bars",
                         params={"timeframe": timeframe, "limit": limit, "feed": feed})
        bars = (resp or {}).get("bars") or []
        return [b["c"] for b in bars]

    def open_orders(self, symbol: str) -> list[dict]:
        resp = self._req("GET", self.base, "/v2/orders",
                         params={"status": "open", "symbols": symbol})
        return resp or []

    def cancel_order(self, order_id: str) -> None:
        self._req("DELETE", self.base, f"/v2/orders/{order_id}")

    def submit_bracket_buy(self, symbol: str, qty: int, stop: float,
                           target: float | None) -> dict:
        body = {
            "symbol": symbol, "qty": qty, "side": "buy",
            "type": "market", "time_in_force": "day",
            "order_class": "bracket",
            "stop_loss": {"stop_price": round(stop, 2)},
        }
        if target:
            body["take_profit"] = {"limit_price": round(target, 2)}
        return self._req("POST", self.base, "/v2/orders", body=body)

    def liquidate(self, symbol: str) -> dict:
        return self._req("DELETE", self.base, f"/v2/positions/{symbol}")


# --------------------------------------------------------------------------- #
#  Ein Handels-Zyklus
# --------------------------------------------------------------------------- #
def run_cycle(api: Alpaca, args) -> None:
    def log(m: str) -> None:
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {m}", flush=True)

    clock = api.clock()
    if not clock or not clock.get("is_open"):
        log(f"Börse geschlossen (nächste Öffnung: {clock.get('next_open') if clock else '?'}). "
            f"Nichts getan.")
        return

    acct = api.account()
    equity = float(acct["equity"])
    last_equity = float(acct.get("last_equity") or 0)
    buying_power = float(acct.get("buying_power") or 0)
    log(f"Equity {equity:.2f} | Tag-Start {last_equity:.2f} | Kaufkraft {buying_power:.2f}")

    closes = api.bars(args.symbol, args.timeframe, args.slow + 5, args.feed)
    if len(closes) < args.slow:
        log(f"Zu wenige Kurse für {args.symbol} ({len(closes)}). Zyklus übersprungen.")
        return
    price = closes[-1]

    pos = api.position(args.symbol)
    have = pos is not None and abs(float(pos.get("qty", 0))) > 0
    action = decide(closes, args.fast, args.slow, have)
    log(f"{args.symbol} Kurs {price:.2f} | SMA{args.fast}/{args.slow} → Signal: {action.upper()} "
        f"| Position: {'JA' if have else 'nein'}")

    if action == "buy":
        ok, reason = risk_gate(equity, last_equity, args.min_equity, args.daily_loss_limit)
        if not ok:
            log(reason)
            return
        qty = size_order(equity, price, args.risk, args.stop, args.max_position, buying_power)
        if qty <= 0:
            log("Stückzahl 0 (Kapital/Cap zu klein für diesen Kurs). Kein Kauf.")
            return
        stop = price * (1 - args.stop)
        target = price * (1 + args.stop * args.rr) if args.rr > 0 else None
        if args.dry_run:
            log(f"[DRY-RUN] KAUF {qty} {args.symbol} @ ~{price:.2f} "
                f"| Stop {stop:.2f} | Ziel {target and round(target,2)} — NICHT gesendet.")
            return
        order = api.submit_bracket_buy(args.symbol, qty, stop, target)
        log(f"✅ KAUF gesendet: {qty} {args.symbol} (Order {order.get('id')}) "
            f"| Stop {stop:.2f} | Ziel {target and round(target,2)}")

    elif action == "sell":
        if args.dry_run:
            log(f"[DRY-RUN] SCHLIESSEN {args.symbol} — NICHT gesendet.")
            return
        for o in api.open_orders(args.symbol):      # offene Stop/Ziel-Legs lösen
            api.cancel_order(o["id"])
        api.liquidate(args.symbol)
        log(f"✅ Position {args.symbol} geschlossen (Signal).")
    else:
        log("Nichts zu tun (hold).")


# --------------------------------------------------------------------------- #
#  Selbsttest (offline, ohne Keys/Netz)
# --------------------------------------------------------------------------- #
def selftest() -> int:
    ok = True

    def check(name, cond):
        nonlocal ok
        print(f"  [{'OK ' if cond else 'FAIL'}] {name}")
        ok = ok and cond

    up = [float(i) for i in range(1, 60)]            # steigend → bullisch
    down = [float(i) for i in range(60, 1, -1)]      # fallend → bärisch
    check("Aufwärtstrend ohne Position → buy", decide(up, 10, 30, False) == "buy")
    check("Aufwärtstrend mit Position → hold", decide(up, 10, 30, True) == "hold")
    check("Abwärtstrend mit Position → sell", decide(down, 10, 30, True) == "sell")
    check("Abwärtstrend ohne Position → hold", decide(down, 10, 30, False) == "hold")
    check("Zu wenig Daten → hold", decide([1, 2, 3], 10, 30, False) == "hold")

    # Sizing: 10000 Equity, 1% Risiko, 3% Stop, Preis 100
    # dollars_at_risk=100, per_share_risk=3 → 33 Stück, Cap/Kaufkraft groß genug
    check("Sizing Normalfall = 33", size_order(10000, 100, 0.01, 0.03, 1e9, 1e9) == 33)
    check("Sizing durch Kaufkraft gedeckelt",
          size_order(10000, 100, 0.01, 0.03, 1e9, 500) == 5)
    check("Sizing Preis 0 → 0", size_order(10000, 0, 0.01, 0.03, 1e9, 1e9) == 0)

    # Risiko-Gates
    g_ruin, _ = risk_gate(500, 1000, 700, 0.05)
    check("Ruin-Stopp greift", g_ruin is False)
    g_day, _ = risk_gate(940, 1000, 100, 0.05)       # -6% Tag ≥ 5% Limit
    check("Tagesverlustlimit greift", g_day is False)
    g_ok, _ = risk_gate(1010, 1000, 100, 0.05)
    check("Normalfall erlaubt", g_ok is True)

    print("\nSelbsttest:", "ALLE BESTANDEN ✅" if ok else "FEHLER ❌")
    return 0 if ok else 1


# --------------------------------------------------------------------------- #
#  CLI
# --------------------------------------------------------------------------- #
def main() -> None:
    p = argparse.ArgumentParser(
        description="Alpaca Live-Trading-Bot (echtes Geld mit --live).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--symbol", default="SPY", help="Ticker (Standard: SPY)")
    p.add_argument("--timeframe", default="1Day", help="Bar-Größe (z. B. 1Day, 1Hour, 15Min)")
    p.add_argument("--feed", default="iex", help="Datenfeed (iex=gratis, sip=bezahlt)")
    p.add_argument("--fast", type=int, default=10, help="schneller SMA")
    p.add_argument("--slow", type=int, default=30, help="langsamer SMA")
    p.add_argument("--risk", type=float, default=0.01, help="Risiko pro Trade (Bruchteil Equity)")
    p.add_argument("--stop", type=float, default=0.03, help="Stop-Loss (Bruchteil)")
    p.add_argument("--rr", type=float, default=2.0, help="Chance-Risiko-Verhältnis fürs Ziel (0=aus)")
    p.add_argument("--max-position", type=float, default=1000.0, help="max. Positionswert in $")
    p.add_argument("--daily-loss-limit", type=float, default=0.05, help="Tagesverlustlimit")
    p.add_argument("--min-equity", type=float, default=0.0, help="Ruin-Stopp: unter diesem Equity kein Handel")
    p.add_argument("--loop", type=int, default=0, help="Sekunden zwischen Zyklen (0 = einmal)")
    p.add_argument("--live", action="store_true", help="ECHTES GELD (sonst Paper-Konto)")
    p.add_argument("--yes", action="store_true", help="Live-Bestätigung überspringen")
    p.add_argument("--dry-run", action="store_true", help="Orders nur anzeigen, nicht senden")
    p.add_argument("--selftest", action="store_true", help="Logik offline prüfen und beenden")
    args = p.parse_args()

    if args.selftest:
        sys.exit(selftest())

    key = os.environ.get("ALPACA_API_KEY_ID")
    secret = os.environ.get("ALPACA_API_SECRET_KEY")
    if not key or not secret:
        raise SystemExit(
            "Keine API-Keys gefunden. Setze sie als Umgebungsvariablen:\n"
            "  export ALPACA_API_KEY_ID=dein_key\n"
            "  export ALPACA_API_SECRET_KEY=dein_secret\n"
            "(Keys bekommst du unter alpaca.markets — niemals in den Code schreiben.)"
        )

    base = LIVE_BASE if args.live else PAPER_BASE
    mode = "ECHTES GELD (LIVE)" if args.live else "Paper-Konto (kein echtes Geld)"
    print("=" * 64)
    print(f"  Modus: {mode}")
    print(f"  Symbol {args.symbol} | SMA {args.fast}/{args.slow} | Risiko {args.risk:.1%} "
          f"| Stop {args.stop:.1%} | Cap ${args.max_position:.0f}")
    print("=" * 64)

    if args.live and not args.dry_run and not args.yes:
        print("\n⚠️  Du startest mit ECHTEM GELD. Reale Orders, realer Verlust möglich.")
        if input('   Tippe "ECHTGELD" zum Fortfahren: ').strip() != "ECHTGELD":
            raise SystemExit("Abgebrochen.")

    api = Alpaca(base, key, secret)
    while True:
        try:
            run_cycle(api, args)
        except SystemExit:
            raise
        except Exception as e:                       # ein Zyklus-Fehler killt nicht den Bot
            print(f"[Fehler im Zyklus] {e}", file=sys.stderr, flush=True)
        if args.loop <= 0:
            break
        time.sleep(args.loop)


if __name__ == "__main__":
    main()
