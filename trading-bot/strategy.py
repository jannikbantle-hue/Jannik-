#!/usr/bin/env python3
"""
strategy.py — gemeinsame, netzwerkfreie Handels- und Risiko-Logik.

Wird von beiden Bots genutzt:
  - live_trader.py   (Aktien, Alpaca)
  - crypto_trader.py (Krypto, Kraken)

So gelten für Aktien und Krypto exakt dieselben getesteten Regeln.
Kein Teil hier kann Verluste ausschließen — er hält einen EINZELNEN
Verlust nur klein und kontrolliert (Stop-Loss, Positionsgröße, Limits).
"""

from __future__ import annotations

import math


def sma(values: list[float], period: int) -> float | None:
    """Einfacher gleitender Durchschnitt der letzten `period` Werte."""
    if len(values) < period:
        return None
    return sum(values[-period:]) / period


def decide(closes: list[float], fast: int, slow: int, have_position: bool) -> str:
    """'buy', 'sell' oder 'hold' (Regime: Long solange fast-SMA > slow-SMA)."""
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
               max_position: float, buying_power: float,
               whole: bool = True, precision: int = 8) -> float:
    """
    Menge aus Risiko-pro-Trade, gedeckelt durch Positions-Cap und Kaufkraft.

    whole=True  -> ganze Stück (Aktien), als float mit .0
    whole=False -> Bruchteile (Krypto), auf `precision` Nachkommastellen
    """
    if price <= 0 or stop_pct <= 0:
        return 0.0
    dollars_at_risk = equity * risk
    per_unit_risk = price * stop_pct
    qty = dollars_at_risk / per_unit_risk
    cap_dollars = min(max_position, buying_power)
    qty = min(qty, cap_dollars / price)
    if qty <= 0:
        return 0.0
    if whole:
        return float(math.floor(qty))
    return max(0.0, math.floor(qty * 10 ** precision) / 10 ** precision)


def risk_gate(equity: float, day_start_equity: float, min_equity: float,
              daily_loss_limit: float) -> tuple[bool, str]:
    """Darf eine NEUE Position eröffnet werden? (Schließen ist immer erlaubt.)"""
    if equity < min_equity:
        return False, f"💀 Equity {equity:.2f} < Mindest-Equity {min_equity:.2f} — Ruin-Stopp."
    if day_start_equity > 0:
        day_pl = (equity - day_start_equity) / day_start_equity
        if day_pl <= -daily_loss_limit:
            return False, f"🔒 Tagesverlust {day_pl:.1%} ≥ Limit — heute keine neuen Käufe."
    return True, "ok"


def selftest_strategy() -> bool:
    """Prüft die reine Logik offline (ohne Keys/Netz). True = alles bestanden."""
    ok = True

    def check(name: str, cond: bool) -> None:
        nonlocal ok
        print(f"  [{'OK ' if cond else 'FAIL'}] {name}")
        ok = ok and cond

    up = [float(i) for i in range(1, 60)]
    down = [float(i) for i in range(60, 1, -1)]
    check("Aufwärtstrend ohne Position → buy", decide(up, 10, 30, False) == "buy")
    check("Aufwärtstrend mit Position → hold", decide(up, 10, 30, True) == "hold")
    check("Abwärtstrend mit Position → sell", decide(down, 10, 30, True) == "sell")
    check("Abwärtstrend ohne Position → hold", decide(down, 10, 30, False) == "hold")
    check("Zu wenig Daten → hold", decide([1, 2, 3], 10, 30, False) == "hold")

    check("Sizing ganze Stück = 33", size_order(10000, 100, 0.01, 0.03, 1e9, 1e9) == 33.0)
    check("Sizing durch Kaufkraft gedeckelt",
          size_order(10000, 100, 0.01, 0.03, 1e9, 500) == 5.0)
    check("Sizing Krypto-Bruchteil",
          size_order(10000, 50000, 0.01, 0.03, 1e9, 1e9, whole=False, precision=8) > 0)
    check("Sizing Preis 0 → 0", size_order(10000, 0, 0.01, 0.03, 1e9, 1e9) == 0.0)

    g_ruin, _ = risk_gate(500, 1000, 700, 0.05)
    check("Ruin-Stopp greift", g_ruin is False)
    g_day, _ = risk_gate(940, 1000, 100, 0.05)
    check("Tagesverlustlimit greift", g_day is False)
    g_ok, _ = risk_gate(1010, 1000, 100, 0.05)
    check("Normalfall erlaubt", g_ok is True)

    return ok


if __name__ == "__main__":
    import sys
    print("Strategie-Selbsttest:")
    passed = selftest_strategy()
    print("\n", "ALLE BESTANDEN ✅" if passed else "FEHLER ❌")
    sys.exit(0 if passed else 1)
