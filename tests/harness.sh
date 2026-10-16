#!/usr/bin/env bash
# Par app↔tray (koia.ipc) num bus PRIVADO: server fake + client real.
# Sai com código 0 só se todas as calls e states passarem.
set -e
D="$(cd "$(dirname "$0")" && pwd)"
W="${TMPDIR:-/tmp}/koia-tests"
mkdir -p "$W"
rm -f "$W/server.out" "$W/client.out"

python3 "$D/server.py" > "$W/server.out" 2>&1 &
SRV=$!

CLT=0
python3 "$D/client.py" > "$W/client.out" 2>&1 || CLT=$?

kill $SRV 2>/dev/null || true
wait $SRV 2>/dev/null || true

echo "--- server.out ---"
cat "$W/server.out"
echo "--- client.out ---"
cat "$W/client.out"
echo "EXIT_CLIENT=$CLT"
exit $CLT
