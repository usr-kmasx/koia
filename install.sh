#!/usr/bin/env bash
# Instala o Koia no sistema: dependências, código, atalho e ícone.
#
# Suporta Debian/Ubuntu (apt), Fedora (dnf) e Arch (pacman); a distro é
# detectada pelo /etc/os-release e só o que falta é instalado.
#
# Layout instalado:
#   /opt/koia/                                    run.py + koia/ + icon.png
#   /usr/bin/koia                                 wrapper → /opt/koia/run.py
#   /usr/share/applications/com.koia.Koia.desktop
#   /usr/share/icons/hicolor/<NxN>/apps/com.koia.Koia.png
#
# O wrapper existe porque run.py usa os.path.abspath(__file__), que NÃO
# resolve symlink: um `ln -s /opt/koia/run.py /usr/bin/koia` faria
# sys.path apontar para /usr/bin e o `from koia.main import` falharia.
#
# A bandeja é tratada como opcional de propósito: o daemon GTK3 roda em
# processo separado e o app vive sem ele. Se o pacote ayatana não existir
# na distro (Fedora < 40) o install avisa e segue, nunca aborta.
#
# Hooks de teste (nunca usar à mão numa instalação real):
#   DESTDIR=/caminho    prefixo em todo caminho de sistema (árvore falsa)
#   KOIA_FORCE_PM=PM    força apt|dnf|pacman em vez de detectar
#   KOIA_SKIP_DEPS=1    não toca no gerenciador nem roda o smoke check
#
# Flags: --dry-run (mostra tudo que faria, não escreve nada).
set -euo pipefail

PROJETO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

OPT_DIR="/opt/koia"
BIN="/usr/bin/koia"
APP_DIR="/usr/share/applications"
ICON_DIR="/usr/share/icons/hicolor"
DESKTOP="$APP_DIR/com.koia.Koia.desktop"
ICON_NAME="com.koia.Koia"
# tamanhos do tema hicolor; o fonte tem 1254px e é reduzido na hora
ICON_SIZES=(16 24 32 48 64 96 128 256 512)

DRY=0

# prefixo dos caminhos de sistema: vazio na instalação real, caminho da
# árvore falsa no teste. Existe UMA variável para isto porque `set -u`
# derruba o script num "$DESTDIR" cru — o uninstall.sh usa o mesmo nome
ROOT="${DESTDIR:-}"

info() { printf 'koia: %s\n' "$*"; }
warn() { printf 'koia: WARNING: %s\n' "$*" >&2; }
die()  { printf 'koia: ERROR: %s\n' "$*" >&2; exit 1; }

# Toda escrita passa por aqui: em --dry-run só imprime a intenção.
step() {
    local desc=$1
    shift
    if [ "$DRY" -eq 1 ]; then
        printf 'koia: [dry-run] %s\n' "$desc"
    else
        "$@"
    fi
}

# ---------------------------------------------------------------------------
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

# ID/ID_LIKE cobrem as derivadas (Mint→Ubuntu, EndeavourOS→Arch). Os
# espaços nas pontas evitam casar sufixos dentro de palavras maiores.
detect_pm() {
    local id like
    id=$(. /etc/os-release 2>/dev/null && printf '%s' "${ID:-}") || true
    like=$(. /etc/os-release 2>/dev/null && printf '%s' "${ID_LIKE:-}") || true
    case " $id $like " in
        *" debian "* | *" ubuntu "*) printf 'apt\n' ;;
        *" fedora "* | *" rhel "*)   printf 'dnf\n' ;;
        *" arch "*)                  printf 'pacman\n' ;;
        *)                           printf '\n' ;;
    esac
}

if [ -n "${KOIA_FORCE_PM:-}" ]; then
    PM=$KOIA_FORCE_PM
else
    PM=$(detect_pm)
fi
[ -n "$PM" ] || die "unsupported distribution (this installer handles Debian, Ubuntu, Fedora and Arch)"

case $PM in
    apt)
        # gir1.2-adw-1 é o libadwaita; o ayatana traz a lib por dependência
        CORE_PKGS=(python3 python3-gi gir1.2-gtk-4.0 gir1.2-adw-1
                   gir1.2-soup-3.0 gir1.2-gdkpixbuf-2.0)
        TRAY_PKGS=(gir1.2-gtk-3.0 gir1.2-ayatanaappindicator3-0.1)
        ;;
    dnf)
        CORE_PKGS=(python3 python3-gobject gtk4 libadwaita libsoup3 gdk-pixbuf2)
        TRAY_PKGS=(gtk3 libayatana-appindicator-gtk3)
        ;;
    pacman)
        CORE_PKGS=(python python-gobject gtk4 libadwaita libsoup3 gdk-pixbuf2)
        TRAY_PKGS=(gtk3 libayatana-appindicator)
        ;;
    *) die "unknown package manager: $PM" ;;
esac
info "package manager: $PM"

# ---------------------------------------------------------------------------
pkg_installed() {
    case $PM in
        apt)    dpkg -s "$1" >/dev/null 2>&1 ;;
        dnf)    rpm -q "$1" >/dev/null 2>&1 ;;
        pacman) pacman -Qi "$1" >/dev/null 2>&1 ;;
    esac
}

# existe no repositório? só para o bloco da bandeja, que é opcional
pkg_available() {
    case $PM in
        apt)    apt-cache show "$1" >/dev/null 2>&1 ;;
        dnf)    dnf info "$1" >/dev/null 2>&1 ;;
        pacman) pacman -Si "$1" >/dev/null 2>&1 ;;
    esac
}

install_pkgs() {
    [ "$#" -gt 0 ] || return 0
    info "installing: $*"
    case $PM in
        apt)
            step "apt-get update" env DEBIAN_FRONTEND=noninteractive \
                apt-get update -q
            step "apt-get install $*" env DEBIAN_FRONTEND=noninteractive \
                apt-get install -y --no-install-recommends "$@"
            ;;
        dnf)
            step "dnf install $*" dnf install -y "$@"
            ;;
        pacman)
            step "pacman -S $*" pacman -S --needed --noconfirm "$@"
            ;;
    esac
}

# instala só o que falta (idempotente: rodar de novo é atualização)
missing=()
for pkg in ${CORE_PKGS[@]+"${CORE_PKGS[@]}"}; do
    pkg_installed "$pkg" || missing+=("$pkg")
done
if [ "${#missing[@]}" -gt 0 ]; then
    install_pkgs "${missing[@]}"
else
    info "core dependencies already present"
fi

missing=()
for pkg in ${TRAY_PKGS[@]+"${TRAY_PKGS[@]}"}; do
    if ! pkg_installed "$pkg"; then
        if pkg_available "$pkg"; then
            missing+=("$pkg")
        else
            warn "$pkg is not in this distribution's repositories"
            warn "the tray will not work — the app itself is unaffected"
        fi
    fi
done
install_pkgs ${missing[@]+"${missing[@]}"}

# ---------------------------------------------------------------------------
# pré-condições do runtime: sem elas não adianta copiar arquivo nenhum
command -v python3 >/dev/null 2>&1 || die "python3 not found"
PY_VER=$(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])')
python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' \
    || die "Python $PY_VER is too old — 3.10+ is required (Debian 11 and Ubuntu 20.04 have neither Python 3.10 nor libadwaita/libsoup3)"
info "python $PY_VER"

# DESTDIR é árvore de teste/estágio: nada de sudo e nada no sistema real.
# --dry-run também não exige root: quem só quer VER as ações não pode
# ser obrigado a digitar senha
if [ "$DRY" -eq 0 ] && [ -z "$ROOT" ] && [ "$(id -u)" -ne 0 ]; then
    if command -v sudo >/dev/null 2>&1; then
        info "root is required — retrying with sudo"
        exec sudo "$0" "$@"
    fi
    die "run as root: sudo $0"
fi

if [ "${KOIA_SKIP_DEPS:-0}" != "1" ]; then
    # a tabela de pacotes é uma aposta, o import é o fato: core aborta,
    # bandeja só avisa (o daemon é opcional)
    info "checking the runtime imports"
    python3 - <<'PY' || die "GTK 4 / libadwaita / libsoup 3 are not importable — install aborted before copying any file"
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Soup", "3.0")
from gi.repository import Adw, GdkPixbuf, GLib, Gtk, Soup  # noqa: F401
PY
    python3 - <<'PY' || warn "the tray runtime is not importable — installing without the tray"
import gi
gi.require_version("Gtk", "3.0")
gi.require_version("AyatanaAppIndicator3", "0.1")
from gi.repository import AyatanaAppIndicator3, Gtk  # noqa: F401
PY
fi

# ---------------------------------------------------------------------------
# código: lista explícita, nunca `cp -r .` (o repo tem tests/, .qa-tests/
# e arquivos locais que não pertencem à instalação)
if [ "$DRY" -eq 1 ]; then
    printf 'koia: [dry-run] copy run.py + icon.png + koia/ (no __pycache__) → %s/\n' \
        "$OPT_DIR"
else
    step "create $OPT_DIR" install -d -m755 "$ROOT$OPT_DIR"
    tar -C "$PROJETO" --exclude='__pycache__' --exclude='*.pyc' \
        -cf - run.py icon.png koia | tar -C "$ROOT$OPT_DIR" -xf -
    info "code installed in $OPT_DIR"
fi

# wrapper e não symlink — ver o cabeçalho
if [ "$DRY" -eq 1 ]; then
    printf 'koia: [dry-run] write %s (wrapper → %s/run.py)\n' "$BIN" "$OPT_DIR"
else
    step "create $(dirname "$BIN")" install -d -m755 "$(dirname "$ROOT$BIN")"
    cat > "$ROOT$BIN" <<EOF
#!/bin/sh
# Koia — wrapper gerado pelo install.sh (não editar: remova e reinstale)
exec python3 $OPT_DIR/run.py "\$@"
EOF
    step "chmod 755 $BIN" chmod 755 "$ROOT$BIN"
    info "command available as: koia"
fi

step "install $DESKTOP" \
    install -Dm644 "$PROJETO/com.koia.Koia.desktop" "$ROOT$DESKTOP"

# ícone: o fonte tem 1254x1254 (1,5 MB) e não cabe em nenhum diretório
# do hicolor; reduzir na hora com GdkPixbuf custa zero dependência nova
# (python3-gi já é requisito do app) e evita ImageMagick
if [ "$DRY" -eq 1 ]; then
    printf 'koia: [dry-run] generate icons %s from icon.png → %s/\n' \
        "${ICON_SIZES[*]}" "$ICON_DIR"
elif python3 - "$PROJETO/icon.png" "$ROOT$ICON_DIR" "$ICON_NAME" \
    "$(IFS=,; printf '%s' "${ICON_SIZES[*]}")" <<'PY'
import os
import sys

import gi

gi.require_version("GdkPixbuf", "2.0")
from gi.repository import GdkPixbuf

source, root, name = sys.argv[1], sys.argv[2], sys.argv[3]
sizes = [int(v) for v in sys.argv[4].split(",")]
base = GdkPixbuf.Pixbuf.new_from_file(source)
for size in sizes:
    scaled = base.scale_simple(size, size, GdkPixbuf.InterpType.BILINEAR)
    if scaled is None:
        raise SystemExit(f"could not scale the icon to {size}x{size}")
    folder = os.path.join(root, f"{size}x{size}", "apps")
    os.makedirs(folder, exist_ok=True)
    scaled.savev(os.path.join(folder, f"{name}.png"), "png", [], [])
print(f"koia: icons generated ({len(sizes)} sizes)")
PY
then
    :
else
    # fallback honesto: o original é válido, o tema escala; avisa porque
    # a janela do app usará um ícone grande demais
    warn "icon generation failed — installing the original as 512x512"
    step "install 512x512 icon" install -Dm644 "$PROJETO/icon.png" \
        "$ROOT$ICON_DIR/512x512/apps/$ICON_NAME.png"
fi

# caches só no sistema real: a árvore de ROOT não é a que o desktop lê.
# E nunca em --dry-run: a flag promete não tocar em nada
if [ -z "$ROOT" ] && [ "$DRY" -eq 0 ]; then
    if command -v update-desktop-database >/dev/null 2>&1; then
        update-desktop-database "$APP_DIR" >/dev/null 2>&1 || true
    fi
    if command -v gtk-update-icon-cache >/dev/null 2>&1; then
        gtk-update-icon-cache -f -t "$ICON_DIR" >/dev/null 2>&1 || true
    fi
fi

info "done — launch 'koia' from your app menu"
info "the tray creates its autostart entry on the first run"
