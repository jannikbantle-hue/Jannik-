#!/usr/bin/env python3
"""
crypto_trader.py — handelt KRYPTO mit ECHTEM Geld über die Kraken-API.

  ┌───────────────────────────────────────────────────────────────┐
  │  WARNUNG: Mit --live werden REALE Krypto-Orders auf deinem      │
  │  echten Kraken-Konto ausgeführt. Echtes Geld, echter Verlust.   │
  │  OHNE --live wird NICHTS gesendet (nur Analyse/Anzeige).        │
  │  Kein Bot kann Verluste ausschließen — er hält sie nur klein.   │
  └───────────────────────────────────────────────────────────────┘

Warum Kraken statt Alpaca für Krypto?
  Kraken platziert einen echten Stop-Loss direkt an der Börse ("conditional
  close"): beim Kauf wird automatisch eine Stop-Loss-Verkaufsorder mitgelegt.
  So ist dein Verlust je Trade exchange-seitig begrenzt — auch wenn der Bot
  gerade nicht läuft oder du schläfst (Krypto handelt 24/7).

Strategie & Risiko: identisch zu den Aktien (siehe strategy.py).

API-Keys NUR über Umgebungsvariablen (niemals in Code/Git):
    export KRAKEN_API_KEY=dein_key
    export KRAKEN_API_SECRET=dein_secret   # der base64-String von Kraken

Beispiele:
    python3 crypto_trader.py --selftest                 # Logik + Signatur offline prüfen
    python3 crypto_trader.py --pair XBTUSD --dry-run     # analysieren, nichts senden
    python3 crypto_trader.py --pair XBTUSD --live --yes  # ECHTES GELD
    python3 crypto_trader.py --pair XBTUSD --loop 300     # alle 5 Min. (24/7)
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

from strategy import decide, risk_gate, selftest_strategy, size_order

API_BASE = "https://api.kraken.com"


# --------------------------------------------------------------------------- #
#  Kraken-Signatur (HMAC-SHA512) — ohne Netzwerk testbar.
# --------------------------------------------------------------------------- #
def kraken_signature(urlpath: str, data: dict, secret_b64: str) -> str:
    postdata = urllib.parse.urlencode(data)
    encoded = (str(data["nonce"]) + postdata).encode()
    message = urlpath.encode() + hashlib.sha256(encoded).digest()
    mac = hmac.new(base64.b64decode(secret_b64), message, hashlib.sha512)
    return base64.b64encode(mac.digest()).decode()


def liquidation_distance(leverage: int, maint: float = 0.0) -> float:
    """Grober Kursabstand bis zur Liquidation einer Long-Position (Bruchteil).
    1.0 = keine Liquidation (Spot). Bei Hebel N ~ 1/N. Nur Näherung!"""
    if leverage <= 1:
        return 1.0
    return max(0.0, (1.0 - maint) / leverage)


def _norm_pair(p: str) -> str:
    """Grobe Normalisierung, damit 'XBTUSD', 'XXBTZUSD', 'BTC/USD' vergleichbar sind."""
    p = p.upper().replace("/", "")
    p = p.replace("XXBT", "BTC").replace("XBT", "BTC")
    p = p.replace("XETH", "ETH")
    p = p.replace("ZUSD", "USD").replace("ZEUR", "EUR")
    return "".join(ch for ch in p if ch.isalnum())


# --------------------------------------------------------------------------- #
#  Kraken-Client
# --------------------------------------------------------------------------- #
class Kraken:
    def __init__(self, key: str, secret: str):
        self.key, self.secret = key, secret
        self._last_nonce = 0

    def _nonce(self) -> int:
        n = int(time.time() * 1000)
        if n <= self._last_nonce:
            n = self._last_nonce + 1
        self._last_nonce = n
        return n

    def _get(self, url: str) -> dict:
        try:
            with urllib.request.urlopen(url, timeout=30) as r:
                return json.loads(r.read().decode())
        except urllib.error.URLError as e:
            raise SystemExit(f"Netzwerkfehler (GET {url}): {e}")

    def _public(self, method: str, params: dict) -> dict:
        url = f"{API_BASE}/0/public/{method}?" + urllib.parse.urlencode(params)
        resp = self._get(url)
        if resp.get("error"):
            raise SystemExit(f"Kraken-Fehler ({method}): {resp['error']}")
        return resp["result"]

    def _private(self, method: str, data: dict | None = None) -> dict:
        data = dict(data or {})
        data["nonce"] = self._nonce()
        urlpath = f"/0/private/{method}"
        body = urllib.parse.urlencode(data).encode()
        req = urllib.request.Request(API_BASE + urlpath, data=body, method="POST")
        req.add_header("API-Key", self.key)
        req.add_header("API-Sign", kraken_signature(urlpath, data, self.secret))
        req.add_header("Content-Type", "application/x-www-form-urlencoded")
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                resp = json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            raise SystemExit(f"API-Fehler {e.code} ({method}): {e.read().decode()}")
        except urllib.error.URLError as e:
            raise SystemExit(f"Netzwerkfehler ({method}): {e.reason}")
        if resp.get("error"):
            raise SystemExit(f"Kraken-Fehler ({method}): {resp['error']}")
        return resp.get("result", {})

    # -- Marktdaten (öffentlich) ------------------------------------------- #
    def closes(self, pair: str, interval: int) -> list[float]:
        result = self._public("OHLC", {"pair": pair, "interval": interval})
        key = next(k for k in result if k != "last")
        return [float(c[4]) for c in result[key]]

    # -- Konto (privat) ---------------------------------------------------- #
    def balance(self) -> dict:
        return {k: float(v) for k, v in self._private("Balance").items()}

    def open_orders_for(self, pair: str) -> list[str]:
        result = self._private("OpenOrders")
        want = _norm_pair(pair)
        out = []
        for txid, o in (result.get("open") or {}).items():
            if _norm_pair(o.get("descr", {}).get("pair", "")) == want:
                out.append(txid)
        return out

    def cancel(self, txid: str) -> None:
        self._private("CancelOrder", {"txid": txid})

    def market_buy_with_stop(self, pair: str, volume: float, stop_price: float,
                             price_prec: int, leverage: int = 1,
                             validate: bool = False) -> dict:
        data = {
            "pair": pair, "type": "buy", "ordertype": "market",
            "volume": f"{volume:.8f}",
            "close[ordertype]": "stop-loss",
            "close[price]": f"{stop_price:.{price_prec}f}",
        }
        if leverage > 1:                      # Margin/Hebel-Position
            data["leverage"] = str(leverage)
        if validate:
            data["validate"] = "true"
        return self._private("AddOrder", data)

    def market_sell(self, pair: str, volume: float, validate: bool = False) -> dict:
        data = {"pair": pair, "type": "sell", "ordertype": "market",
                "volume": f"{volume:.8f}"}
        if validate:
            data["validate"] = "true"
        return self._private("AddOrder", data)

    # -- Margin/Hebel (privat) --------------------------------------------- #
    def trade_balance(self, asset: str) -> dict:
        r = self._private("TradeBalance", {"asset": asset})
        return {"equity": float(r.get("e", 0.0)), "free_margin": float(r.get("mf", 0.0))}

    def long_position_volume(self, pair: str) -> float:
        """Offenes LONG-Volumen der Hebel-Position für dieses Paar (0 = keine)."""
        r = self._private("OpenPositions")
        want = _norm_pair(pair)
        vol = 0.0
        for _txid, p in (r or {}).items():
            if _norm_pair(p.get("pair", "")) == want and p.get("type") == "buy":
                vol += float(p.get("vol", 0)) - float(p.get("vol_closed", 0))
        return vol

    def close_long(self, pair: str, volume: float, leverage: int,
                   validate: bool = False) -> dict:
        """Schließt eine LONG-Hebel-Position (reduce_only, damit nichts gedreht wird)."""
        data = {"pair": pair, "type": "sell", "ordertype": "market",
                "volume": f"{volume:.8f}", "reduce_only": "true"}
        if leverage > 1:
            data["leverage"] = str(leverage)
        if validate:
            data["validate"] = "true"
        return self._private("AddOrder", data)


# --------------------------------------------------------------------------- #
#  Tages-Equity merken (für Tagesverlustlimit) — kleine lokale JSON-Datei.
# --------------------------------------------------------------------------- #
def day_start_equity(state_file: str, equity: float) -> float:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    try:
        with open(state_file, encoding="utf-8") as f:
            st = json.load(f)
        if st.get("date") == today:
            return float(st["day_start_equity"])
    except (OSError, ValueError, KeyError):
        pass
    try:
        with open(state_file, "w", encoding="utf-8") as f:
            json.dump({"date": today, "day_start_equity": equity}, f)
    except OSError:
        pass
    return equity


# --------------------------------------------------------------------------- #
#  Ein Handels-Zyklus
# --------------------------------------------------------------------------- #
def run_cycle(api: Kraken, args) -> None:
    def log(m: str) -> None:
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {m}", flush=True)

    margin = args.leverage > 1

    closes = api.closes(args.pair, args.interval)
    if len(closes) < args.slow:
        log(f"Zu wenige Kurse für {args.pair} ({len(closes)}). Zyklus übersprungen.")
        return
    price = closes[-1]

    if margin:
        tb = api.trade_balance(args.quote_asset)
        equity = tb["equity"]
        buying_power = tb["free_margin"] * args.leverage
        pos_vol = api.long_position_volume(args.pair)
        have = pos_vol >= args.min_volume
        log(f"Equity {equity:.2f} {args.quote_asset} | Hebel {args.leverage}x "
            f"| Long-Position {pos_vol:.8f} | freie Margin {tb['free_margin']:.2f}")
    else:
        bal = api.balance()
        base_amt = bal.get(args.base_asset, 0.0)
        quote_amt = bal.get(args.quote_asset, 0.0)
        equity = quote_amt + base_amt * price
        buying_power = quote_amt
        pos_vol = base_amt
        have = base_amt >= args.min_volume
        log(f"Equity {equity:.2f} {args.quote_asset} | {args.base_asset} {base_amt:.8f} "
            f"| Cash {quote_amt:.2f}")

    ds_equity = day_start_equity(args.state_file, equity)
    action = decide(closes, args.fast, args.slow, have)
    log(f"{args.pair} Kurs {price:.2f} | SMA{args.fast}/{args.slow} → Signal: {action.upper()} "
        f"| Position: {'JA' if have else 'nein'} | Tag-Start {ds_equity:.2f}")

    if action == "buy":
        ok, reason = risk_gate(equity, ds_equity, args.min_equity, args.daily_loss_limit)
        if not ok:
            log(reason)
            return
        vol = size_order(equity, price, args.risk, args.stop, args.max_position,
                         buying_power, whole=False, precision=8)
        if vol < args.min_volume:
            log(f"Volumen {vol:.8f} < Mindestmenge {args.min_volume}. Kein Kauf.")
            return
        stop = price * (1 - args.stop)
        if margin:
            liq = liquidation_distance(args.leverage)
            if args.stop > 0.7 * liq:
                log(f"⚠️ ACHTUNG: Stop {args.stop:.0%} liegt nahe am Liquidationsabstand "
                    f"(~{liq:.0%} bei {args.leverage}x). Die Position kann liquidiert "
                    f"werden, BEVOR der Stop greift!")
        if args.dry_run or not args.live:
            tag = "DRY-RUN" if args.dry_run else "ANALYSE"
            log(f"[{tag}] KAUF {vol:.8f} {args.pair} @ ~{price:.2f} | Stop "
                f"{stop:.{args.price_precision}f} | Hebel {args.leverage}x — NICHT gesendet.")
            return
        order = api.market_buy_with_stop(args.pair, vol, stop, args.price_precision,
                                         leverage=args.leverage, validate=False)
        log(f"✅ KAUF gesendet: {vol:.8f} {args.pair} | exchange-Stop {stop:.{args.price_precision}f} "
            f"| Hebel {args.leverage}x | {order.get('descr', {}).get('order', '')}")

    elif action == "sell":
        if args.dry_run or not args.live:
            tag = "DRY-RUN" if args.dry_run else "ANALYSE"
            log(f"[{tag}] SCHLIESSEN {pos_vol:.8f} {args.pair} — NICHT gesendet.")
            return
        for txid in api.open_orders_for(args.pair):   # offenen Stop-Loss lösen
            api.cancel(txid)
        if margin:
            api.close_long(args.pair, pos_vol, args.leverage)
        else:
            api.market_sell(args.pair, pos_vol)
        log(f"✅ Position {args.pair} geschlossen (Signal): {pos_vol:.8f}.")
    else:
        log("Nichts zu tun (hold).")


# --------------------------------------------------------------------------- #
#  Selbsttest (offline): Strategie + Kraken-Signatur-Testvektor
# --------------------------------------------------------------------------- #
def selftest() -> int:
    print("Selbsttest (gemeinsame Strategie-Logik):")
    ok = selftest_strategy()

    # Offizieller Kraken-Signatur-Testvektor (aus der Kraken-API-Doku):
    print("\nKraken-Signatur (offizieller Testvektor):")
    secret = ("kQH5HW/8p1uGOVjbgWA7FunAmGO8lsSUXNsu3eow76sz84Q18fWxnyRzBHCd3pd5"
              "nE9qa99HAZtuZuj6F1huXg==")
    data = {"nonce": "1616492376594", "ordertype": "limit", "pair": "XBTUSD",
            "price": "37500", "type": "buy", "volume": "1.25"}
    expected = ("4/dpxb3iT4tp/ZCVEwSnEsLxx0bqyhLpdfOpc6fn7OR8+UClSV5n9E6aSS8MPt"
                "nRfp32bAb0nmbRn6H8ndwLUQ==")
    got = kraken_signature("/0/private/AddOrder", data, secret)
    sig_ok = got == expected
    print(f"  [{'OK ' if sig_ok else 'FAIL'}] Signatur stimmt mit Kraken-Doku überein")

    np_ok = _norm_pair("XBTUSD") == _norm_pair("XXBTZUSD") == _norm_pair("BTC/USD")
    print(f"  [{'OK ' if np_ok else 'FAIL'}] Pair-Normalisierung")

    print("\nHebel / Liquidationsabstand:")
    liq_ok = (liquidation_distance(1) == 1.0
              and abs(liquidation_distance(2) - 0.5) < 1e-9
              and abs(liquidation_distance(5) - 0.2) < 1e-9)
    print(f"  [{'OK ' if liq_ok else 'FAIL'}] Spot=1.0, 2x≈50%, 5x≈20%")

    ok = ok and sig_ok and np_ok and liq_ok
    print("\nSelbsttest:", "ALLE BESTANDEN ✅" if ok else "FEHLER ❌")
    return 0 if ok else 1


# --------------------------------------------------------------------------- #
#  CLI
# --------------------------------------------------------------------------- #
def main() -> None:
    p = argparse.ArgumentParser(
        description="Kraken Krypto-Trading-Bot (echtes Geld mit --live).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--pair", default="XBTUSD", help="Kraken-Paar (Standard: XBTUSD)")
    p.add_argument("--base-asset", default="XXBT", help="Kraken-Code der Coin im Bestand")
    p.add_argument("--quote-asset", default="ZUSD", help="Kraken-Code der Währung")
    p.add_argument("--interval", type=int, default=1440, help="Kerzen-Minuten (1440=Tag)")
    p.add_argument("--fast", type=int, default=10, help="schneller SMA")
    p.add_argument("--slow", type=int, default=30, help="langsamer SMA")
    p.add_argument("--risk", type=float, default=0.01, help="Risiko pro Trade (Bruchteil)")
    p.add_argument("--stop", type=float, default=0.05, help="Stop-Loss (Bruchteil, Krypto volatiler)")
    p.add_argument("--leverage", type=int, default=1,
                   help="Hebel (1=Spot/kein Hebel; >1 = Kraken-Margin, Liquidationsrisiko!)")
    p.add_argument("--max-position", type=float, default=100.0, help="max. Positionswert (Quote-Währung)")
    p.add_argument("--daily-loss-limit", type=float, default=0.05, help="Tagesverlustlimit")
    p.add_argument("--min-equity", type=float, default=0.0, help="Ruin-Stopp: darunter kein Handel")
    p.add_argument("--min-volume", type=float, default=0.0001, help="Kraken-Mindestmenge")
    p.add_argument("--price-precision", type=int, default=1, help="Nachkommastellen des Stop-Preises")
    p.add_argument("--state-file", default="crypto_state.json", help="Datei für Tages-Equity")
    p.add_argument("--loop", type=int, default=0, help="Sekunden zwischen Zyklen (0=einmal)")
    p.add_argument("--live", action="store_true", help="ECHTES GELD (sonst nur Analyse)")
    p.add_argument("--yes", action="store_true", help="Live-Bestätigung überspringen")
    p.add_argument("--dry-run", action="store_true", help="nie senden, nur anzeigen")
    p.add_argument("--selftest", action="store_true", help="Logik + Signatur offline prüfen")
    args = p.parse_args()

    if args.selftest:
        sys.exit(selftest())

    if args.leverage < 1:
        raise SystemExit("--leverage muss >= 1 sein (1 = kein Hebel).")

    key = os.environ.get("KRAKEN_API_KEY")
    secret = os.environ.get("KRAKEN_API_SECRET")
    if not key or not secret:
        raise SystemExit(
            "Keine Kraken-Keys gefunden. Setze sie als Umgebungsvariablen:\n"
            "  export KRAKEN_API_KEY=dein_key\n"
            "  export KRAKEN_API_SECRET=dein_secret\n"
            "(Keys bekommst du bei kraken.com unter Settings → API — nie in den Code.)"
        )

    mode = "ECHTES GELD (LIVE)" if args.live else "nur Analyse (nichts wird gesendet)"
    hebel = f"{args.leverage}x Hebel (MARGIN)" if args.leverage > 1 else "ohne Hebel (Spot)"
    print("=" * 64)
    print(f"  Krypto-Bot (Kraken) — Modus: {mode}")
    print(f"  {args.pair} | {hebel} | SMA {args.fast}/{args.slow} | Risiko {args.risk:.1%} "
          f"| Stop {args.stop:.1%} | Cap {args.max_position:.0f} {args.quote_asset}")
    print("=" * 64)

    if args.leverage > 1:
        liq = liquidation_distance(args.leverage)
        print(f"\n⚠️  HEBEL {args.leverage}x: Liquidation grob ab ~{liq:.0%} Gegenbewegung — "
              f"dann ist das eingesetzte Kapital WEG, auch unter dem Stop.")
        print("   Margin muss in deinem Kraken-Konto freigeschaltet sein (in der EU oft")
        print("   gesperrt/eingeschränkt). Die Margin-Logik ist hier nicht live getestet.")

    if args.live and not args.dry_run and not args.yes:
        print("\n⚠️  Du startest mit ECHTEM GELD auf Kraken. Reale Orders, realer Verlust möglich.")
        if input('   Tippe "ECHTGELD" zum Fortfahren: ').strip() != "ECHTGELD":
            raise SystemExit("Abgebrochen.")

    api = Kraken(key, secret)
    while True:
        try:
            run_cycle(api, args)
        except SystemExit:
            raise
        except Exception as e:
            print(f"[Fehler im Zyklus] {e}", file=sys.stderr, flush=True)
        if args.loop <= 0:
            break
        time.sleep(args.loop)


if __name__ == "__main__":
    main()
