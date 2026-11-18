#!/usr/bin/env bash
# Krypto-Bot (Kraken, BTC/EUR) — fertig konfiguriert fuer 100 EUR Start.
#   ./start_crypto.sh         -> Analyse-Modus (sicher, KEINE Orders)
#   ./start_crypto.sh live    -> ECHTES GELD (fragt "ECHTGELD" ab)
set -euo pipefail
cd "$(dirname "$0")"
[ -f .env ] && { set -a; source .env; set +a; }

ARGS=(--pair XBTEUR --base-asset XXBT --quote-asset ZEUR --interval 1440
      --risk 0.01 --stop 0.05 --max-position 30 --daily-loss-limit 0.05
      --min-equity 70 --min-volume 0.0001 --price-precision 1 --loop 3600)

if [ "${1:-analyse}" = "live" ]; then
  echo ">>> ECHTES GELD auf Kraken (BTC/EUR). Start-Kapital ~100 EUR. Strg+C bricht ab."
  exec python3 crypto_trader.py "${ARGS[@]}" --live
else
  echo ">>> Analyse-Modus (sicher). Fuer echtes Geld:  ./start_crypto.sh live"
  exec python3 crypto_trader.py "${ARGS[@]}"
fi
