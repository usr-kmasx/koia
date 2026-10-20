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
    GSETTINGS_BACKEND=memory python3 tests/i18n_test.py

- `downloads_delete_test` — grade de downloads: cards Overlay, lixeira
  (um alerta, Cancelar/Apagar), foco/teclado, estado vazio.
- `downloads_timing_test` — build do diálogo sem decode na thread
  principal + thumbs assíncronas entregues (≤ TILE).
- `page_view_test` — visor ▦ navegável: destaque da foto da janela,
  ‹ › em loop, campo de página (pendente até o Enter — e já no 1º
  toque), página vazia (toast + revert), salto (página, índice) e
  reabertura numa página lembrada (diferente da da janela).
- `page_button_test` — wiring na janela real: ▦ nasce apagado, ação
  `win.show-page`, sensibilidade por contexto, `fetch_page`
  cache-first, `jump_to` (mesma página vs. outra) e a lembrança do ▦
  (vale só enquanto a janela segue na mesma página).
- `i18n_test` — paridade de idioma: varre o código por `t("...")` por
  AST (todo literal tem entrada no pt-BR, nenhuma chave fica órfã),
  o painel nos dois idiomas (a opção Idioma fecha o painel antes de
  "Restaurar padrões", nomes nativos intactos), a regra do tray (GTK3
  importa o `i18n` mas nunca o `config`) e a troca em runtime
  (reconstrói a janela e devolve imagem, página, ▦, tela cheia e
  preferências).

## Instalador (sem tocar no sistema real)

    python3 tests/installer_test.py

- `installer_test` — install.sh/uninstall.sh: a tabela de pacotes das
  três famílias (apt/dnf/pacman, com shims que registram as chamadas em
  vez de chamar gerenciador de verdade), a árvore instalada num DESTDIR
  falso (código, wrapper com shebang+exec, `.desktop` com `Icon=` que
  existe, PNG no tamanho declarado no diretório), `--dry-run` que não
  escreve, a bandeja como opcional (ayatana ausente → avisa e o núcleo
  entra mesmo assim), o smoke check com o runtime de verdade, e o
  uninstall que some com programa + dados do usuário **sem tocar em
  `~/Pictures/Wallpapers`** (só avisa) e é idempotente.

## Alocador (puro, sem GUI)

    python3 tests/malloc_tune_test.py

- `malloc_tune_test` — `koia/malloc_tune.py`: o `mallopt` do glibc é
  aplicado (e é idempotente), o `run.py` chama o ajuste antes de
  importar app/tray, e decodes simultâneos com os tamanhos reais de
  imagem não deixam memória retida no processo (a regressão do RSS
  que subia a cada visualização e nunca descia: blocos grandes presos
  nos arenas por thread do glibc, sem `munmap`).

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
