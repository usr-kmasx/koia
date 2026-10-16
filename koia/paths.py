"""Caminhos compartilhados — neutro de GTK (usado pelo app GTK4 e pelo tray GTK3).

Só pode depender de GLib: o processo do tray roda GTK3, e o config.py do
app puxa GTK4 — nada aqui pode importar Gtk.
"""

import os

import gi

gi.require_version("GLib", "2.0")
from gi.repository import GLib  # noqa: E402

# pasta do pacote koia/ (a raiz do repo fica um nível acima)
PACKAGE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(PACKAGE_DIR)

SETTINGS_PATH = os.path.join(
    GLib.get_user_config_dir(), "koia", "settings.ini"
)

# ícone do tray: PNG na raiz do projeto
TRAY_ICON_PATH = os.path.join(PROJECT_DIR, "icon.png")

# log do tray: o app spawna o daemon silencioso — sem isto, um crash do
# tray seria invisível (e "veja o log" não existiria)
TRAY_LOG_PATH = os.path.join(
    GLib.get_user_cache_dir(), "koia", "tray.log"
)

# autostart discreto: só o tray, sem janela
AUTOSTART_DIR = os.path.join(GLib.get_user_config_dir(), "autostart")
AUTOSTART_PATH = os.path.join(AUTOSTART_DIR, "com.koia.Tray.desktop")

RUNNER = os.path.join(PROJECT_DIR, "run.py")


def default_download_dir():
    """Pasta padrão dos wallpapers baixados (mesmo critério do config.py)."""
    pictures = GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_PICTURES)
    if not pictures:
        pictures = os.path.expanduser("~/Pictures")
    return os.path.join(pictures, "Wallpapers")


def autostart_desktop():
    """Conteúdo do arquivo XDG autostart do tray (discreto no login)."""
    return "\n".join([
        "[Desktop Entry]",
        "Type=Application",
        "Name=Koia Tray",
        "Comment=Tray e slideshow de wallpapers em segundo plano",
        f"Exec=python3 {RUNNER} --tray",
        "Icon=" + TRAY_ICON_PATH,
        "StartupNotify=false",
        "NoDisplay=true",
        "",
    ])


def ensure_autostart():
    """Cria o autostart na 1ª execução (fora do login nada sobe sozinho).

    Se o arquivo já existe, não reescreve — quem quer desfazer apaga.
    Devolve True só quando criou.
    """
    content = autostart_desktop()
    try:
        with open(AUTOSTART_PATH, "r", encoding="utf-8") as handle:
            if handle.read(-1) == content:
                return False  # já existe e está igual: nada a fazer
        # existe, mas divergente (repositório mudou de lugar? ):
        # NÃO sobrescreve silenciosamente; isso é decisão do usuário
        return False
    except FileNotFoundError:
        pass
    except OSError as exc:
        print(f"[koia-tray] autostart não pôde ser lido: {exc}")
        return False
    try:
        os.makedirs(AUTOSTART_DIR, exist_ok=True)
        tmp = AUTOSTART_PATH + ".koia.tmp"
        with open(tmp, "w", encoding="utf-8") as handle:
            handle.write(content)
        os.replace(tmp, AUTOSTART_PATH)
    except OSError as exc:
        print(f"[koia-tray] autostart não criado: {exc}")
        return False
    return True
