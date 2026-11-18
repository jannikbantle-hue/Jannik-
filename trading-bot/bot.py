#!/usr/bin/env python3
"""
Paper-Trading-Bot mit Risikomanagement und "Überlebens"-Mechanik.

Idee (legal & sicher):
  - Handelt NUR mit Spielgeld. Es werden KEINE echten Orders gesendet.
  - Strategie: einfacher Gleitender-Durchschnitt-Crossover (SMA fast/slow), nur Long.
  - Positionsgröße ist ein fester Bruchteil des AKTUELLEN Kapitals
    -> gewinnt der Bot, wächst der Einsatz automatisch (Zinseszins = "Vermehrung").
  - Schutz: Stop-Loss pro Trade, tägliches Verlustlimit, Ruin-Schwelle.
    Fällt das Kapital unter die Ruin-Schwelle, hört der Bot auf ("stirbt").

Kein echtes Geld. Keine Anlageberatung. Nur zum Lernen.

Beispiele:
  python3 bot.py                 # Demo mit synthetischen Kursen (reproduzierbar)
  python3 bot.py --csv daten.csv # eigene Kurse (Spalten: date,close)
  python3 bot.py --seed 7 --capital 5000 --risk 0.02
"""

from __future__ import annotations

import argparse
import csv
import math
import random
from dataclasses import dataclass, field


# --------------------------------------------------------------------------- #
#  Kursdaten
# --------------------------------------------------------------------------- #
def synthetic_prices(n: int, seed: int, start: float = 100.0) -> list[float]:
    """Reproduzierbarer Zufalls-Kursverlauf (geometrischer Random Walk)."""
    rng = random.Random(seed)
    prices = [start]
    drift = 0.0003          # ganz leichter Aufwärtstrend
    vol = 0.012             # Tagesvolatilität
    for _ in range(n - 1):
        shock = rng.gauss(drift, vol)
        prices.append(round(max(1.0, prices[-1] * (1 + shock)), 2))
    return prices


def load_csv(path: str) -> list[float]:
    """Lädt Schlusskurse aus einer CSV mit Spalte 'close' (oder 2. Spalte)."""
    closes: list[float] = []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader, None)
        close_idx = 1
        if header:
            lower = [h.strip().lower() for h in header]
            if "close" in lower:
                close_idx = lower.index("close")
            else:
                # Kein benannter Header -> erste Zeile war vielleicht schon Daten
                try:
                    closes.append(float(header[close_idx]))
                except (ValueError, IndexError):
                    pass
        for row in reader:
            if len(row) > close_idx:
                try:
                    closes.append(float(row[close_idx]))
                except ValueError:
                    continue
    if len(closes) < 30:
        raise SystemExit("Zu wenige Kurse in der CSV (mindestens ~30 nötig).")
    return closes


def sma(values: list[float], period: int, end: int) -> float | None:
    """Gleitender Durchschnitt der letzten `period` Werte bis Index `end`."""
    if end + 1 < period:
        return None
    window = values[end + 1 - period : end + 1]
    return sum(window) / period


# --------------------------------------------------------------------------- #
#  Bot
# --------------------------------------------------------------------------- #
@dataclass
class Config:
    capital: float = 1000.0     # Startkapital (Spielgeld)
    fast: int = 10              # schneller SMA
    slow: int = 30              # langsamer SMA
    risk_per_trade: float = 0.01   # 1 % des Kapitals pro Trade riskieren
    stop_loss_pct: float = 0.03    # Stop-Loss 3 % unter Einstieg
    daily_loss_limit: float = 0.05 # max. 5 % Verlust pro "Tag"
    ruin_fraction: float = 0.70    # unter 70 % des Startkapitals -> Bot stirbt
    bars_per_day: int = 20         # wie viele Kurs-Schritte ein "Tag" ist
    fee_pct: float = 0.001         # 0,1 % Gebühr pro Trade-Seite


@dataclass
class Trade:
    entry_bar: int
    entry_price: float
    shares: float
    stop: float
    exit_bar: int | None = None
    exit_price: float | None = None
    reason: str = ""

    def pnl(self) -> float:
        if self.exit_price is None:
            return 0.0
        return (self.exit_price - self.entry_price) * self.shares


@dataclass
class Bot:
    cfg: Config
    equity: float = field(init=False)
    cash: float = field(init=False)
    position: Trade | None = field(default=None, init=False)
    trades: list[Trade] = field(default_factory=list, init=False)
    alive: bool = field(default=True, init=False)
    generation: int = field(default=1, init=False)
    day_start_equity: float = field(init=False)
    day_locked: bool = field(default=False, init=False)
    log: list[str] = field(default_factory=list, init=False)

    def __post_init__(self) -> None:
        self.equity = self.cfg.capital
        self.cash = self.cfg.capital
        self.day_start_equity = self.cfg.capital

    # -- Hilfen ------------------------------------------------------------- #
    def _say(self, bar: int, msg: str) -> None:
        self.log.append(f"[Bar {bar:>4}] {msg}")

    def _mark_equity(self, price: float) -> None:
        pos_value = self.position.shares * price if self.position else 0.0
        self.equity = self.cash + pos_value

    def _check_growth(self, bar: int) -> None:
        """Verdopplung des Kapitals = der Bot 'vermehrt' sich (nur kosmetisch)."""
        target = self.cfg.capital * (2 ** self.generation)
        if self.equity >= target:
            self.generation += 1
            self._say(bar, f"🌱 Kapital verdoppelt -> Generation {self.generation} "
                           f"(Equity {self.equity:.2f})")

    def _check_ruin(self, bar: int) -> None:
        ruin_level = self.cfg.capital * self.cfg.ruin_fraction
        if self.equity < ruin_level:
            self.alive = False
            self._say(bar, f"💀 Ruin-Schwelle unterschritten "
                           f"({self.equity:.2f} < {ruin_level:.2f}) -> Bot stoppt.")

    # -- Handel ------------------------------------------------------------- #
    def _open(self, bar: int, price: float) -> None:
        dollars_at_risk = self.equity * self.cfg.risk_per_trade
        # Stop-Distanz bestimmt, wie viele Anteile wir riskieren können ...
        per_share_risk = price * self.cfg.stop_loss_pct
        shares = dollars_at_risk / per_share_risk if per_share_risk > 0 else 0.0
        # ... aber nie mehr als unser Bargeld (kein Hebel).
        max_shares = self.cash / (price * (1 + self.cfg.fee_pct))
        shares = min(shares, max_shares)
        if shares <= 0:
            return
        cost = shares * price
        fee = cost * self.cfg.fee_pct
        self.cash -= cost + fee
        stop = round(price * (1 - self.cfg.stop_loss_pct), 4)
        self.position = Trade(entry_bar=bar, entry_price=price, shares=shares, stop=stop)
        self._say(bar, f"KAUF  {shares:8.3f} @ {price:8.2f} | Stop {stop:8.2f} | "
                       f"Einsatz {cost:8.2f}")

    def _close(self, bar: int, price: float, reason: str) -> None:
        if not self.position:
            return
        t = self.position
        proceeds = t.shares * price
        fee = proceeds * self.cfg.fee_pct
        self.cash += proceeds - fee
        t.exit_bar, t.exit_price, t.reason = bar, price, reason
        self.trades.append(t)
        self.position = None
        self._say(bar, f"VERK  {t.shares:8.3f} @ {price:8.2f} | {reason:<10} | "
                       f"PnL {t.pnl():+8.2f}")

    # -- Hauptschleife ------------------------------------------------------ #
    def run(self, prices: list[float]) -> None:
        cfg = self.cfg
        for bar, price in enumerate(prices):
            # Neuer "Tag"? Verlustsperre zurücksetzen.
            if bar % cfg.bars_per_day == 0:
                self.day_start_equity = self.equity
                self.day_locked = False

            self._mark_equity(price)
            self._check_ruin(bar)
            if not self.alive:
                if self.position:
                    self._close(bar, price, "RUIN")
                break
            self._check_growth(bar)

            # Stop-Loss zuerst prüfen (Schutz vor Verlust).
            if self.position and price <= self.position.stop:
                self._close(bar, price, "STOP")

            # Tagesverlustlimit: ab hier keine neuen Trades mehr heute.
            day_loss = (self.day_start_equity - self.equity) / self.day_start_equity
            if day_loss >= cfg.daily_loss_limit and not self.day_locked:
                self.day_locked = True
                self._say(bar, f"🔒 Tagesverlustlimit erreicht ({day_loss:.1%}) "
                               f"-> heute keine neuen Käufe.")

            fast = sma(prices, cfg.fast, bar)
            slow = sma(prices, cfg.slow, bar)
            if fast is None or slow is None:
                continue

            # Regime-Logik: Long sein, solange fast > slow ("bullisch").
            # So steigt der Bot nach einem Stop-Out im Aufwärtstrend wieder
            # ein, statt auf einen Kreuzungspunkt zu warten, der nie kommt.
            bullish = fast > slow
            # Nicht am selben Bar neu kaufen, an dem gerade ausgestoppt wurde.
            stopped_now = (
                self.trades and self.trades[-1].exit_bar == bar
                and self.trades[-1].reason == "STOP"
            )

            if bullish and not self.position and not self.day_locked and not stopped_now:
                self._open(bar, price)
            elif not bullish and self.position:
                self._close(bar, price, "SIGNAL")

        # Am Ende offene Position glattstellen (Bewertung).
        if self.position and prices:
            self._close(len(prices) - 1, prices[-1], "ENDE")
        self._mark_equity(prices[-1] if prices else 0.0)

    # -- Auswertung --------------------------------------------------------- #
    def report(self) -> str:
        wins = [t for t in self.trades if t.pnl() > 0]
        losses = [t for t in self.trades if t.pnl() <= 0]
        total_pnl = sum(t.pnl() for t in self.trades)
        ret = (self.equity / self.cfg.capital - 1) * 100
        win_rate = (len(wins) / len(self.trades) * 100) if self.trades else 0.0

        # Maximaler Drawdown über die Equity-Kurve der Trades.
        peak, max_dd = self.cfg.capital, 0.0
        running = self.cfg.capital
        for t in self.trades:
            running += t.pnl()
            peak = max(peak, running)
            max_dd = max(max_dd, (peak - running) / peak)

        lines = [
            "",
            "=" * 60,
            "  ERGEBNIS (Spielgeld)",
            "=" * 60,
            f"  Startkapital       : {self.cfg.capital:>12.2f}",
            f"  Endkapital         : {self.equity:>12.2f}",
            f"  Rendite            : {ret:>11.2f} %",
            f"  Trades             : {len(self.trades):>12}",
            f"  davon Gewinner     : {len(wins):>12}  ({win_rate:.1f} %)",
            f"  davon Verlierer    : {len(losses):>12}",
            f"  Summe PnL          : {total_pnl:>+12.2f}",
            f"  Max. Drawdown      : {max_dd*100:>11.2f} %",
            f"  Generation         : {self.generation:>12}  (Kapital-Verdopplungen)",
            f"  Status             : {'LEBT' if self.alive else 'GESTORBEN (Ruin)':>12}",
            "=" * 60,
        ]
        return "\n".join(lines)


# --------------------------------------------------------------------------- #
#  CLI
# --------------------------------------------------------------------------- #
def main() -> None:
    p = argparse.ArgumentParser(description="Paper-Trading-Bot (Spielgeld, kein echtes Geld).")
    p.add_argument("--csv", help="CSV mit Spalte 'close' (sonst synthetische Kurse)")
    p.add_argument("--bars", type=int, default=500, help="Anzahl synthetischer Kurse")
    p.add_argument("--seed", type=int, default=42, help="Zufalls-Seed (Reproduzierbarkeit)")
    p.add_argument("--capital", type=float, default=1000.0, help="Startkapital")
    p.add_argument("--risk", type=float, default=0.01, help="Risiko pro Trade (Bruchteil)")
    p.add_argument("--stop", type=float, default=0.03, help="Stop-Loss (Bruchteil)")
    p.add_argument("--fast", type=int, default=10, help="schneller SMA")
    p.add_argument("--slow", type=int, default=30, help="langsamer SMA")
    p.add_argument("--quiet", action="store_true", help="Trade-Log nicht ausgeben")
    args = p.parse_args()

    prices = load_csv(args.csv) if args.csv else synthetic_prices(args.bars, args.seed)

    cfg = Config(
        capital=args.capital,
        risk_per_trade=args.risk,
        stop_loss_pct=args.stop,
        fast=args.fast,
        slow=args.slow,
    )
    bot = Bot(cfg)
    bot.run(prices)

    print("Paper-Trading-Bot — KEIN echtes Geld, KEINE Anlageberatung.\n")
    if not args.quiet:
        print("\n".join(bot.log))
    print(bot.report())


if __name__ == "__main__":
    main()
