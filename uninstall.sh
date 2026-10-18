#!/usr/bin/env bash
# Desinstala o Koia: programa, atalho, ícones e TODOS os dados do app.
#
# Remove:
#   /opt/koia, /usr/bin/koia, o .desktop e os ícones do hicolor
#   ~/.config/koia, ~/.cache/koia, ~/.config/autostart/com.koia.Tray.desktop
#
# NUNCA mexe em ~/Pictures/Wallpapers: os wallpapers baixados são do
# usuário e apagá-los é irreversível — o script só avisa que a pasta
# existe. (Decisão explícita: "pasta de downloads não mexe".)
#
# O daemon da bandeja não exporta interface D-Bus própria (só o app GTK4
# exporta com.koia.Koia), então ele é encerrado por pkill no padrão
# exato do processo; antes ainda se tenta um Quit() gentil no app, para
# que ele salve as settings no shutdown.
#
# Sob sudo o HOME vira /root — os dados do usuário saem de SUDO_USER.
#
# Idempotente: sem instalação, avisa e sai com 0.
#
# Hooks de teste: DESTDIR (árvore falsa). Flag: --dry-run.
set -euo pipefail

OPT_DIR="/opt/koia"
BIN="/usr/bin/koia"
APP_DIR="/usr/share/applications"
ICON_DIR="/usr/share/icons/hicolor"
DESKTOP="$APP_DIR/com.koia.Koia.desktop"
ICON_NAME="com.koia.Koia"
ICON_SIZES=(16 24 32 48 64 96 128 256 512)

DRY=0

info() { printf 'koia: %s\n' "$*"; }
warn() { printf 'koia: WARNING: %s\n' "$*" >&2; }
die()  { printf 'koia: ERROR: %s\n' "$*" >&2; exit 1; }

for arg in "$@"; do
    case $arg in
        --dry-run) DRY=1 ;;
        -h | --help)
            awk 'NR > 1 { if ($0 !~ /^#/) exit; sub(/^# ?/, ""); print }' \
                "${BASH_SOURCE[0]}"
            exit 0
            ;;
        *) die "unknown option: $arg (supported: --dry-run)" ;;
    esac
done

# sudo troca o HOME por /root; os dados apagados são do dono original
target_home() {
    if [ -n "${SUDO_USER:-}" ] && [ "${SUDO_USER}" != "root" ]; then
        getent passwd "$SUDO_USER" | cut -d: -f6
    else
        printf '%s\n' "${HOME:-/root}"
    fi
}

REMOVED=0
# DESTDIR é o prefixo dos caminhos DE SISTEMA (árvore falsa de teste);
# os dados do usuário saem de HOME/SUDO_USER e nunca são prefixados
ROOT="${DESTDIR:-}"

_drop() {
    local path=$1
    if [ -e "$path" ] || [ -L "$path" ]; then
        if [ "$DRY" -eq 1 ]; then
            printf 'koia: [dry-run] remove %s\n' "$path"
        else
            rm -rf -- "$path"
            info "removed $path"
        fi
        REMOVED=$((REMOVED + 1))
    fi
}

# /opt, /usr: caminho de sistema, prefixado pelo DESTDIR de teste
drop_sys() { _drop "$ROOT$1"; }
# dados do usuário: vêm do HOME/SUDO_USER, DESTDIR não entra (nunca)
drop_user() { _drop "$1"; }

# ---------------------------------------------------------------------------
# sem root não sai /opt nem /usr; re-exec sozinho, igual ao install.sh.
# DESTDIR (árvore de teste) e --dry-run não exigem root
if [ "$DRY" -eq 0 ] && [ -z "$ROOT" ] && [ "$(id -u)" -ne 0 ]; then
    if command -v sudo >/dev/null 2>&1; then
        info "root is required — retrying with sudo"
        exec sudo "$0" "$@"
    fi
    die "run as root: sudo $0"
fi

# para o que estiver rodando: pedir é melhor do que deixar órfão apontando
# para arquivo que já não existe
if [ "$DRY" -eq 0 ]; then
    if command -v gdbus >/dev/null 2>&1; then
        gdbus call --session --dest com.koia.Koia --object-path /com/koia/Koia \
            --method com.koia.Koia.Quit >/dev/null 2>&1 || true
    fi
    if command -v pkill >/dev/null 2>&1; then
        # o padrão cobre o app E o tray: os dois são "python3 /opt/koia/run.py"
        if pkill -f "$OPT_DIR/run.py" >/dev/null 2>&1; then
            # SIGTERM entregue: dá tempo do processo fechar antes de apagar
            sleep 1
        fi
    fi
fi

# --- programa ---------------------------------------------------------------
drop_sys "$OPT_DIR"
drop_sys "$BIN"
drop_sys "$DESKTOP"
for size in "${ICON_SIZES[@]}"; do
    drop_sys "$ICON_DIR/${size}x${size}/apps/$ICON_NAME.png"
done

# --- dados do usuário (sempre; ver cabeçalho) --------------------------------
USER_HOME=$(target_home)
drop_user "$USER_HOME/.config/koia"
drop_user "$USER_HOME/.cache/koia"
drop_user "$USER_HOME/.config/autostart/com.koia.Tray.desktop"

# caches de desktop/ícone só valem no sistema real
if [ "$DRY" -eq 0 ] && [ -z "${DESTDIR:-}" ]; then
    if command -v update-desktop-database >/dev/null 2>&1; then
        update-desktop-database "$APP_DIR" >/dev/null 2>&1 || true
    fi
    if command -v gtk-update-icon-cache >/dev/null 2>&1; then
        gtk-update-icon-cache -f -t "$ICON_DIR" >/dev/null 2>&1 || true
    fi
fi

# --- downloads: intocáveis, só informados ------------------------------------
# sem guarda de DESTDIR aqui: o prefixo é só para caminhos de sistema, e
# downloads são dados do usuário (vêm de HOME, como drop_user)
DOWNLOADS="$USER_HOME/Pictures/Wallpapers"
if [ -d "$DOWNLOADS" ]; then
    info "your downloaded wallpapers were left untouched: $DOWNLOADS"
fi

if [ "$REMOVED" -eq 0 ]; then
    info "nothing to remove — Koia is not installed"
else
    info "done — $REMOVED item(s) removed"
fi
