#!/usr/bin/env bash
# Aktien-Bot (Alpaca) — fertig konfiguriert fuer 100 USD (~100 EUR) Start.
# Waehle eine GUENSTIGE Aktie (unter ~30/Stueck), sonst kauft der Bot nichts.
#   SYMBOL=F ./start_stocks.sh        -> Paper-Konto (Spielgeld, weltweit)
#   SYMBOL=F ./start_stocks.sh live   -> ECHTES GELD (nur falls Alpaca-Live verfuegbar)
set -euo pipefail
cd "$(dirname "$0")"
[ -f .env ] && { set -a; source .env; set +a; }

if [ -z "${SYMBOL:-}" ]; then
  echo "Bitte zuerst eine Aktie waehlen (guenstig genug fuer 100):"
  echo "   SYMBOL=F  ./start_stocks.sh         # Beispiel: Ford (~11 USD)"
  echo "   SYMBOL=SOFI ./start_stocks.sh       # Beispiel: SoFi"
  exit 1
fi

ARGS=(--symbol "$SYMBOL" --risk 0.01 --stop 0.03 --max-position 30
      --daily-loss-limit 0.05 --min-equity 70 --loop 900)

if [ "${1:-paper}" = "live" ]; then
  echo ">>> ECHTES GELD auf Alpaca ($SYMBOL). Nur moeglich mit Alpaca-Live-Konto."
  exec python3 live_trader.py "${ARGS[@]}" --live
else
  echo ">>> Paper-Konto ($SYMBOL, Spielgeld). Fuer echtes Geld:  SYMBOL=$SYMBOL ./start_stocks.sh live"
  exec python3 live_trader.py "${ARGS[@]}"
fi
