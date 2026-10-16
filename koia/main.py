"""Aplicação Koia."""

import os
import sys

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Gdk", "4.0")
from gi.repository import Adw, Gdk, Gio, GLib, Gtk  # noqa: E402

from . import APP_ID  # noqa: E402
from .config import Settings  # noqa: E402
from .ipc import WindowAgent, ensure_tray_running  # noqa: E402
from .window import KoiaWindow  # noqa: E402

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")

CSS = """
.koia-stage {
    background-color: @view_bg_color;
}

.koia-controls {
    background-color: alpha(@headerbar_bg_color, 0.72);
    border: 1px solid alpha(@borders, 0.5);
    border-radius: 14px;
    padding: 6px;
    box-shadow: 0 2px 10px alpha(#000, 0.18);
}

.koia-control {
    min-width: 36px;
    min-height: 36px;
    border-radius: 10px;
}

.koia-downloaded {
    color: #2ec27e;
}

.koia-trash {
    color: #e01b24;
}

.koia-fav {
    color: #e01b24;
}

/* foto atual no visor de página: contorno por cima da borda do card,
   sem mudar o layout (offset negativo) */
.koia-current {
    outline-style: solid;
    outline-width: 2px;
    outline-color: @accent_color;
    outline-offset: -2px;
}
"""


def _install_icon_theme():
    """Registra os ícones embutidos (o Adwaita não tem ``heart-symbolic``)."""
    icons = os.path.join(DATA_DIR, "icons")
    if not os.path.isdir(icons):
        return
    display = Gdk.Display.get_default()
    if display is None:
        return
    theme = Gtk.IconTheme.get_for_display(display)
    theme.add_search_path(icons)


def _install_css():
    provider = Gtk.CssProvider()
    provider.load_from_data(CSS)
    display = Gdk.Display.get_default()
    if display is None:
        return
    Gtk.StyleContext.add_provider_for_display(
        display,
        provider,
        Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
    )


class KoiaApp(Adw.Application):
    def __init__(self):
        super().__init__(
            application_id=APP_ID,
            flags=Gio.ApplicationFlags.DEFAULT_FLAGS,
        )
        self.settings = Settings()
        self.agent = WindowAgent(self)
        self._window = None

    # ------------------------------------------------------------------
    def do_startup(self):
        Adw.Application.do_startup(self)
        # daemon do tray pede abertura/encerramento por D-Bus: o app
        # sobrevive mesmo com TODAS as janelas fechadas (o "Sair" do
        # tray chama Quit() e encerra de verdade)
        self.hold()
        # sem tray o app ficaria inalcançável depois do X — garante o
        # daemon (se já rodando, o watch vê o nome e não faz nada)
        ensure_tray_running()
        _install_css()
        _install_icon_theme()
        self._apply_color_scheme()
        self.settings.connect(
            lambda key: self._apply_color_scheme()
            if key == "appearance.color-scheme" else None
        )
        self._install_accels()
        self.connect("shutdown", lambda *_: self.settings.save())

    def do_activate(self):
        # com o X escondendo (e não destruindo) a janela, precisa
        # lembrá-la: active_window é None na reativação e recriar uma
        # segunda janela duplicaria a navegação da sessão
        if self._window is None:
            self._window = KoiaWindow(self, self.settings)
        self._window.present()
        # expõe OpenWindow/CloseWindow/Quit ao tray e emite o estado
        # imediato da visibilidade (registro único, protegido no agent)
        self.agent.register(self._window)
        self.agent.emit_state(self._window.is_visible())
        # o carregamento inicial acontece no "map" da própria janela

    # ------------------------------------------------------------------
    def _apply_color_scheme(self):
        mapping = {
            "light": Adw.ColorScheme.FORCE_LIGHT,
            "dark": Adw.ColorScheme.FORCE_DARK,
        }
        style_manager = Adw.StyleManager.get_default()
        style_manager.set_color_scheme(
            mapping.get(self.settings.get("appearance.color-scheme"),
                        Adw.ColorScheme.DEFAULT)
        )

    def _install_accels(self):
        self.set_accels_for_action("win.go-prev", ["Left"])
        self.set_accels_for_action("win.go-next", ["Right", "space"])
        # sem atalho para baixar/apagar: destruir arquivo com uma tecla
        # só é fácil demais de bater sem querer — e favoritar também é
        # só pelo clique no ♡ (sem atalho)
        self.set_accels_for_action("win.reload", ["F5"])
        self.set_accels_for_action("win.preferences", ["<Primary>comma"])
        # F alterna; Esc só sai (nunca entra) da tela cheia
        self.set_accels_for_action("win.fullscreen", ["f"])
        self.set_accels_for_action("win.leave-fullscreen", ["Escape"])


def main(argv=None):
    return KoiaApp().run(argv or sys.argv)
