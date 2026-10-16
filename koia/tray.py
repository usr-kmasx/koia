"""Tray/daemon do Koia — processo GTK3 independente.

Lançamento: ``python3 run.py --tray``. Mantém o ícone de bandeja (o
``icon.png`` da raiz), o menu de controle e o slideshow de wallpapers
JÁ BAIXADOS (pasta de download). Nada é baixado pelo tray — sem
permissão de rede e sem contato com o wallhaven.

Não mantém nada rodando sozinho: o item "Sair" mata o processo do tray
e pede ``Quit()`` ao app GTK4 (via D-Bus, ``ipc.py``). O autostart
apenas sobe o tray no login; morrer é morrer.

GTK3 é obrigatório aqui: libayatana-appindicator só expõe Gtk3 no
Python (um namespace Gtk não pode ser carregado em duas versões no
mesmo processo) e o app principal é GTK4.
"""

import os
import sys

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gio", "2.0")
gi.require_version("GLib", "2.0")
gi.require_version("AyatanaAppIndicator3", "0.1")
from gi.repository import AyatanaAppIndicator3, Gio, GLib, Gtk  # noqa: E402

from . import paths  # noqa: E402
from .background import set_as_background  # noqa: E402
from .ipc import APP_ID, OBJ_PATH, TRAY_BUS  # noqa: E402

# escolha do slide guardada como "5s|10s|15s|30s|60s|1m|3m|5m|30m|60m|"
# (o vazio é "Desligado") — o radio do menu volta marcado nesta forma
CHOICES = [
    ("5s", "5 s", 5),
    ("10s", "10 s", 10),
    ("15s", "15 s", 15),
    ("30s", "30 s", 30),
    ("60s", "60 s", 60),
    ("1m", "1 min", 60),
    ("3m", "3 min", 180),
    ("5m", "5 min", 300),
    ("30m", "30 min", 1800),
    ("60m", "60 min", 3600),
]
CHOICE_EMPTY = ""

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp"}


def scan_wallpapers(folder):
    """Caminhos de wallpapers baixados, alfabético (casefold).

    Só arquivos diretos da pasta, extensão de imagem, tamanho > 0.
    Pasta inexistente ou vazia devolve ``[]``.
    """
    if not folder:
        return []
    try:
        names = os.listdir(folder)
    except OSError:
        return []
    result = []
    for name in names:
        path = os.path.join(folder, name)
        if not os.path.isfile(path):
            continue
        if os.path.splitext(name)[1].lower() not in IMAGE_EXT:
            continue
        try:
            if os.path.getsize(path) <= 0:
                continue
        except OSError:
            continue
        result.append(path)
    result.sort(key=lambda p: os.path.basename(p).casefold())
    return result


def read_gsettings_path():
    """Wallpaper do GNOME como caminho no disco, ou ``None``."""
    source = Gio.SettingsSchemaSource.get_default()
    if source is None:
        return None
    schema = source.lookup("org.gnome.desktop.background", True)
    if schema is None:
        return None
    settings = Gio.Settings.new_full(schema, None, None)
    uri = settings.get_string("picture-uri")
    if not uri or not uri.startswith("file://"):
        return None
    try:
        return Gio.File.new_for_uri(uri).get_path() or None
    except GLib.Error:
        return None


def navigate_index(current_path, wallpapers, step):
    """Índice do próximo/anterior na lista circular.

    `current_path` forasteiro (não está na lista) parte do item 0 —
    então “Próximo” entrega o primeiro da lista, coerente. Lista de um
    só elemento não tem ahead/back: devolve None (no-op).
    """
    if not wallpapers:
        return None
    try:
        index = wallpapers.index(current_path)
    except ValueError:
        index = 0
    if len(wallpapers) == 1:
        return None
    return (index + step) % len(wallpapers)


def _selftest():
    """Matemática de navegação — ``python3 -m koia.tray --selftest``.

    Sem janela, sem D-Bus, sem gsettings: só asserts puros.
    """
    import tempfile
    d = tempfile.mkdtemp(prefix="koia-selftest-")
    assert scan_wallpapers(d) == [], "pasta vazia → lista vazia"
    assert scan_wallpapers("/nonexistent-dir/xyz") == []

    for name in ("a.webp", "b.PNG", "c.jpg", "d.jpeg", "e.png"):
        with open(os.path.join(d, name), "wb") as f:
            f.write(b"x")
    with open(os.path.join(d, "f.gif"), "wb") as f:  # fora: gif
        f.write(b"x")
    with open(os.path.join(d, "g.txt"), "wb") as f:  # fora: txt
        f.write(b"x")
    with open(os.path.join(d, "h.png"), "wb"):       # fora: 0 bytes
        pass
    with open(os.path.join(d, "zzsub"), "wb") as f:  # fora: sem .ext
        f.write(b"x")

    files = scan_wallpapers(d)
    basenames = [os.path.basename(p) for p in files]
    assert basenames == ["a.webp", "b.PNG", "c.jpg", "d.jpeg", "e.png"], \
        basenames

    # circular (forasteiro parte do item 0: Próximo=1, Anterior=último)
    assert navigate_index(None, files, 1) == 1
    assert navigate_index(None, files, -1) == len(files) - 1
    assert navigate_index(files[0], files, 1) == 1
    assert navigate_index(files[-1], files, 1) == 0   # wrap
    assert navigate_index(files[0], files, -1) == len(files) - 1
    assert navigate_index("/tmp/outro.png", files, 1) == 1  # forasteiro

    single = [files[0]]
    assert navigate_index(single[0], single, 1) is None      # 1 = no-op
    assert navigate_index(None, [], 1) is None                # vazio

    seconds = {key: secs for key, _label, secs in CHOICES}
    assert seconds["60m"] == 3600 and seconds["1m"] == 60
    assert seconds["5s"] == 5
    assert "" not in seconds  # Desligado não é uma escolha do timer
    print("[koia-tray] selftest ok")


# ---------------------------------------------------------------------------
# settings.ini direto com GKeyFile (o config.py do app puxa GTK4 e não
# pode ser importado neste processo)
# ---------------------------------------------------------------------------

def _read_key(key, default):
    keyfile = GLib.KeyFile.new()
    try:
        keyfile.load_from_file(paths.SETTINGS_PATH, GLib.KeyFileFlags.NONE)
    except GLib.Error:
        return default
    group, _, name = key.partition(".")
    try:
        return keyfile.get_string(group, name)
    except GLib.Error:
        return default


def _write_key(key, value):
    keyfile = GLib.KeyFile.new()
    try:
        keyfile.load_from_file(paths.SETTINGS_PATH, GLib.KeyFileFlags.NONE)
    except GLib.Error:
        pass
    group, _, name = key.partition(".")
    keyfile.set_string(group, name, value)
    try:
        keyfile.save_to_file(paths.SETTINGS_PATH)
    except GLib.Error as exc:
        print(f"[koia-tray] settings não salvos: {exc}")


class KoiaTray(Gtk.Application):
    """O daemon: ícone + menu + slideshow de wallpapers baixados."""

    def __init__(self):
        super().__init__(
            application_id=TRAY_BUS,
            # única: segunda ``run.py --tray`` reativa esta instância em
            # vez de criar um segundo ícone de bandeja
            flags=Gio.ApplicationFlags.DEFAULT_FLAGS,
        )
        self.indicator = None
        self.menu_items = {}
        self.slide_off_item = None

        self.proxy = None
        self._child = None               # subprocesso do app primário
        self.window_open = None          # None = ainda não se sabe

        self._slide_source = 0
        self._slide_choice = _read_key("tray.slide-choice", CHOICE_EMPTY) \
            or CHOICE_EMPTY
        self._paused = _read_key("tray.slide-paused", "false") == "true"

    # ------------------------------------------------------------------
    def do_startup(self):
        Gtk.Application.do_startup(self)
        # O daemon não tem JANELAS: sem hold, o run() do Gtk.Application
        # vê use-count zero e encerra no instante seguinte ao activate —
        # o tray nascia e morria (exit 0, invisível). O "Sair" chama
        # self.quit(), que encerra mesmo com o hold pendente.
        self.hold()
        paths.ensure_autostart()
        self._build_indicator_and_menu()
        self._watch_main_app()
        if self._slide_choice and not self._paused:
            self._start_slide_timer(first_immediate=False)

    def do_activate(self):
        self._refresh_menu_state()

    # ------------------------------------------------------------------
    # Ícone + menu
    # ------------------------------------------------------------------
    def _build_indicator_and_menu(self):
        self.indicator = AyatanaAppIndicator3.Indicator.new(
            "koia-tray",
            paths.TRAY_ICON_PATH,
            AyatanaAppIndicator3.IndicatorCategory.APPLICATION_STATUS,
        )
        self.indicator.set_title("Koia Tray")
        self.indicator.set_status(AyatanaAppIndicator3.IndicatorStatus.ACTIVE)

        menu = Gtk.Menu()

        item1 = Gtk.MenuItem(label="Abrir")
        item1.connect("activate", self._on_open_close)
        menu.append(item1)
        self.menu_items["open_close"] = item1

        item2 = Gtk.MenuItem(label="Próximo")
        item2.connect("activate", self._on_next)
        menu.append(item2)
        self.menu_items["next"] = item2

        item3 = Gtk.MenuItem(label="Anterior")
        item3.connect("activate", self._on_prev)
        menu.append(item3)
        self.menu_items["prev"] = item3

        menu.append(self._build_slide_submenu())

        item5 = Gtk.MenuItem(label="Pausar")
        item5.connect("activate", self._on_pause_resume)
        menu.append(item5)
        self.menu_items["pause"] = item5

        menu.append(Gtk.SeparatorMenuItem())

        item6 = Gtk.MenuItem(label="Sair")
        item6.connect("activate", self._on_quit)
        menu.append(item6)
        self.menu_items["quit"] = item6

        menu.show_all()
        self.indicator.set_menu(menu)

        self._refresh_menu_state()

    def _build_slide_submenu(self):
        """Menu 4: Slide koia → Desligado | Segundos ▸ | Minutos ▸."""
        root_item = Gtk.MenuItem(label="Slide koia")
        submenu = Gtk.Menu()

        # grupo único: todos os radios dividem o grupo do Desligado
        off_item = Gtk.RadioMenuItem(label="Desligado", group=None)
        off_item.set_active(not self._slide_choice)
        off_item.connect("toggled", self._on_slide_off)
        submenu.append(off_item)
        self.slide_off_item = off_item

        for title, filter_fn in (("Segundos", lambda k: k.endswith("s")),
                                 ("Minutos", lambda k: k.endswith("m"))):
            parent = Gtk.MenuItem(label=title)
            submenu.append(parent)
            child = Gtk.Menu()
            for key, label, _secs in CHOICES:
                if not filter_fn(key):
                    continue
                item = Gtk.RadioMenuItem(label=label, group=off_item)
                item.set_active(self._slide_choice == key)
                item.connect("toggled", self._on_slide_choice, key)
                child.append(item)
            parent.set_submenu(child)

        submenu.show_all()
        root_item.set_submenu(submenu)
        return root_item

    # ------------------------------------------------------------------
    # Estado → labels/sensibilidade
    # ------------------------------------------------------------------
    def _refresh_menu_state(self):
        open_close = self.menu_items["open_close"]
        wallpapers = scan_wallpapers(self._download_folder())
        has_wallpapers = len(wallpapers) > 0

        open_close.set_label(
            "Fechar" if self.window_open is True else "Abrir")
        self.menu_items["next"].set_sensitive(has_wallpapers)
        self.menu_items["prev"].set_sensitive(has_wallpapers)
        self.menu_items["pause"].set_sensitive(bool(self._slide_choice))
        self.menu_items["pause"].set_label(
            "Retomar" if self._paused else "Pausar")

    def _download_folder(self):
        folder = _read_key("download.folder", paths.default_download_dir())
        return folder.strip() or paths.default_download_dir()

    # ------------------------------------------------------------------
    # Navegar os baixados e aplicar
    # ------------------------------------------------------------------
    def _jump_and_apply(self, step):
        wallpapers = scan_wallpapers(self._download_folder())
        if not wallpapers:
            return False
        target = navigate_index(read_gsettings_path(), wallpapers, step)
        if target is None:
            return False
        error = set_as_background(wallpapers[target])
        if error is not None:
            print(f"[koia-tray] não aplicou: {error}")
            return False
        return True

    def _on_next(self, *args):
        if self._jump_and_apply(1):
            self._restart_slide_timer()

    def _on_prev(self, *args):
        if self._jump_and_apply(-1):
            self._restart_slide_timer()

    # ------------------------------------------------------------------
    # Slide
    # ------------------------------------------------------------------
    def _slide_interval(self):
        for key, _label, seconds in CHOICES:
            if key == self._slide_choice:
                return seconds
        return 0

    def _start_slide_timer(self, first_immediate=True):
        self._stop_slide_timer()
        if self._paused:
            return
        seconds = self._slide_interval()
        if not seconds:
            return
        if first_immediate:
            self._jump_and_apply(1)
        self._slide_source = GLib.timeout_add_seconds(
            seconds, self._on_slide_tick)

    def _stop_slide_timer(self):
        if self._slide_source:
            GLib.source_remove(self._slide_source)
        self._slide_source = 0

    def _restart_slide_timer(self):
        """Depois de navegar manual: reinicia o intervalo completo."""
        if self._slide_choice and not self._paused:
            self._start_slide_timer(first_immediate=False)

    def _on_slide_tick(self):
        self._slide_source = 0
        self._jump_and_apply(1)
        self._start_slide_timer(first_immediate=False)
        return GLib.SOURCE_REMOVE

    def _on_slide_choice(self, item, key):
        if not item.get_active():
            return
        if key == self._slide_choice:
            return  # re-clicar no item já ativo não repete nada
        self._slide_choice = key
        self._paused = False
        _write_key("tray.slide-choice", key)
        _write_key("tray.slide-paused", "false")
        self._start_slide_timer()
        self._refresh_menu_state()

    def _on_slide_off(self, item):
        if not item.get_active():
            return
        if not self._slide_choice:
            return
        self._stop_slide_timer()
        self._slide_choice = CHOICE_EMPTY
        self._paused = False
        _write_key("tray.slide-choice", CHOICE_EMPTY)
        _write_key("tray.slide-paused", "false")
        self._refresh_menu_state()

    def _on_pause_resume(self, *args):
        if not self._slide_choice:
            return
        self._paused = not self._paused
        _write_key("tray.slide-paused", "true" if self._paused else "false")
        if self._paused:
            self._stop_slide_timer()
        else:
            self._start_slide_timer(first_immediate=False)
        self._refresh_menu_state()

    # ------------------------------------------------------------------
    # Abrir/fechar a janela do app principal
    # ------------------------------------------------------------------
    def _watch_main_app(self):
        """Observa ``com.koia.Koia``: apareceu → proxy; sumiu → 'Abrir'."""
        Gio.bus_watch_name(
            Gio.BusType.SESSION, APP_ID, Gio.BusNameWatcherFlags.NONE,
            self._on_app_appeared, self._on_app_vanished,
        )

    def _on_app_appeared(self, _bus, _name, _owner):
        try:
            self.proxy = Gio.DBusProxy.new_sync(
                Gio.bus_get_sync(Gio.BusType.SESSION, None),
                Gio.DBusProxyFlags.NONE, None, APP_ID, OBJ_PATH,
                "com.koia.Koia", None,
            )
            self.proxy.connect("g-signal", self._on_app_signal)
        except GLib.Error as exc:
            self.proxy = None
            print(f"[koia-tray] proxy do app falhou: {exc.message}")
            return
        # o app pode estar aberto ANTES do tray (autostart chegou depois):
        # o WindowState do activate já teria passado reto — sonda agora
        self.proxy.call("GetWindowState", None, Gio.DBusCallFlags.NONE, -1,
                        None, self._on_state_queried)
        self._refresh_menu_state()

    def _on_state_queried(self, proxy, res):
        try:
            reply = proxy.call_finish(res)
            self.window_open = bool(reply.unpack()[0])
        except GLib.Error:
            return  # app morto no meio do caminho: vanished cuida disso
        self._refresh_menu_state()

    def _on_app_vanished(self, *_args):
        self.proxy = None
        self.window_open = False
        self._refresh_menu_state()

    def _on_app_signal(self, _proxy, _sender, signal, message):
        if signal == "WindowState":
            # "(b)": acessa via unpack — get_boolean() não serve em tupla
            self.window_open = bool(message.unpack()[0])
            self._refresh_menu_state()

    def _on_open_close(self, *args):
        if self.proxy:
            method = "CloseWindow" if self.window_open is True \
                else "OpenWindow"
            self.proxy.call(method, None, Gio.DBusCallFlags.NONE, -1,
                            None, None)
            return
        self._spawn_main_app()

    def _spawn_main_app(self):
        """Sobe o app GTK4; o sinal WindowState atualiza o menu."""
        try:
            child = Gio.Subprocess.new(
                [sys.executable, paths.RUNNER],
                Gio.SubprocessFlags.STDOUT_SILENCE |
                Gio.SubprocessFlags.STDERR_SILENCE,
            )
            # espera em background: sem isso o filho vira zumbi no exit
            child.wait_async(None, self._on_child_exited)
        except GLib.Error as exc:
            print(f"[koia-tray] não abriu o app: {exc.message}")

    @staticmethod
    def _on_child_exited(child, res):
        try:
            child.wait_finish(res)
        except GLib.Error:
            pass

    # ------------------------------------------------------------------
    # Sair — nada fica em segundo plano
    # ------------------------------------------------------------------
    def _on_quit(self, *args):
        """Sair mata o tray E o app. Não mantém nada em segundo plano.

        O Quit() precisa ser ENTREGUE antes do loop morrer: se o tray
        saísse no mesmo tick, a mensagem poderia ficar no buffer e o app
        GTK4 sobreviveria sem ninguém pra mandá-lo embora. Por isso só
        ``self.quit()`` na resposta — com fallback de 1,5 s se o app
        não responder (app travado/morto), o tray sai mesmo assim.
        """
        self._stop_slide_timer()
        if self.proxy:
            self.proxy.call("Quit", None, Gio.DBusCallFlags.NONE, -1,
                            None, self._quit_reply)
            GLib.timeout_add(1500, self._quit_fallback)
        else:
            self.quit()

    def _quit_reply(self, _proxy, res):
        try:
            self.proxy.call_finish(res)
        except GLib.Error:
            pass  # app já morreu: tanto faz
        self.quit()

    def _quit_fallback(self):
        self.quit()
        return GLib.SOURCE_REMOVE


def main(argv=None):
    argv = argv if argv is not None else sys.argv
    if "--selftest" in argv:
        _selftest()
        return 0
    tray = KoiaTray()
    tray.run([])
    return 0


if __name__ == "__main__":
    sys.exit(main())
