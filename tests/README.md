# Suíte de regressão do Koia

Testes headless dos fluxos GTK/D-Bus. Rodoam na máquina do usuário
(display real, nenhuma janela é apresentada) e escrevem só em `/tmp`
(fixtures) — nada fora do repo. Todos os testes resolvem o caminho do
pacote pela própria localização, então podem rodar de qualquer lugar.

## GTK (display real; sem rede)

    GSETTINGS_BACKEND=memory python3 tests/downloads_delete_test.py
    GSETTINGS_BACKEND=memory python3 tests/downloads_timing_test.py
    GSETTINGS_BACKEND=memory python3 tests/page_view_test.py
    GSETTINGS_BACKEND=memory python3 tests/page_button_test.py

- `downloads_delete_test` — grade de downloads: cards Overlay, lixeira
  (um alerta, Cancelar/Apagar), foco/teclado, estado vazio.
- `downloads_timing_test` — build do diálogo sem decode na thread
  principal + thumbs assíncronas entregues (≤ TILE).
- `page_view_test` — visor ▦ navegável: destaque da foto da janela,
  ‹ › em loop, campo de página (pendente até Enter), página vazia
  (toast + revert), salto (página, índice).
- `page_button_test` — wiring na janela real: ▦ nasce apagado, ação
  `win.show-page`, sensibilidade por contexto, `fetch_page`
  cache-first, `jump_to` (mesma página vs. outra).

## Tray/bandeja (bus PRIVADO por processo)

    python3 -m koia.tray --selftest
    dbus-run-session -- python3 tests/tray_starter_test.py
    dbus-run-session -- bash tests/harness.sh
    dbus-run-session -- python3 tests/smoke_test.py

- `tray_starter_test` — `--tray` em 4 cenários (A–D).
- `harness.sh` (+ `server.py`/`client.py`) — par koia.ipc: calls,
  sinais e Quit com veredito no exit code. Saídas em `/tmp/koia-tests/`.
- `smoke_test` — menu/lógica do tray com indicador stub.

## E2E (processo tray real; sob bus privado)

    dbus-run-session -- bash tests/spawn_e2e.sh

- `spawn_e2e` — `_spawn_tray()` de verdade: hold (nome no bus após 2s)
  e roteamento do `~/.cache/koia/tray.log`.
