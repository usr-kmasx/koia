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

    # ------------------------------------------------------------------
    def do_startup(self):
        Adw.Application.do_startup(self)
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
        window = self.props.active_window
        if window is None:
            window = KoiaWindow(self, self.settings)
        window.present()
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
