#!/usr/bin/env bash
# E2E do _spawn_tray() REAL: processo tray de verdade, log em
# ~/.cache/koia/tray.log. Rodar sob dbus-run-session (bus privado —
# não mexe na sessão do usuário). Espera: (a) com.koia.Tray no bus
# após 2s (hold funcionou), (b) tray.log com conteúdo (roteamento
# de stderr funcionou).
set -e
D="$(cd "$(dirname "$0")" && pwd)"
REPO="$(dirname "$D")"
W="${TMPDIR:-/tmp}/koia-tests"
mkdir -p "$W"
cp ~/.cache/koia/tray.log "$W/tray.log.before" 2>/dev/null || true

REPO="$REPO" python3 - <<'PY'
import os
import sys
import time
sys.path.insert(0, os.environ["REPO"])
import koia.ipc as ipc
ipc._spawn_tray()
time.sleep(2.5)
PY

echo "--- processo tray ---"
pgrep -af "run.py --tray" || echo "MORTO (falhou)"
echo "--- nome no bus ---"
busctl --user list | grep -i koia || echo "SEM NOME (falhou)"

# limpa: só processos python3 com esse cmdline (nosso bash também casa -f)
for p in $(pgrep -f "run.py --tray"); do
  if [ "$(ps -o comm= -p $p 2>/dev/null)" = "python3" ]; then kill $p; fi
done
echo "--- tray.log (tail) ---"
tail -3 ~/.cache/koia/tray.log 2>/dev/null || echo "SEM LOG (falhou)"
