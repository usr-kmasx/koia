"""Interface D-Bus do lado do app GTK4.

Bus name: ``com.koia.Koia`` (o próprio ``Gio.Application``, já registrado).
Objeto em ``/com/koia/Koia``, interface ``com.koia.Koia``:

- ``OpenWindow()`` — apresenta a janela (ou cria, se destruída)
- ``CloseWindow()`` — esconde a janela (o app segue vivo)
- ``Quit()`` — encerra o app de verdade
- sinal ``WindowState(b open)`` — emitido quando a visibilidade muda

O módulo não importa Gtk diretamente (só depende de Gio/GLib), então é
seguro de ser importado por quase tudo do app.
"""

import os
import sys

import gi

gi.require_version("Gio", "2.0")
gi.require_version("GLib", "2.0")
from gi.repository import Gio, GLib  # noqa: E402

from . import APP_ID, paths  # noqa: E402

OBJ_PATH = "/com/koia/Koia"

# nome de bus do daemon do tray (koia/tray.py); definido AQUI para o
# lado GTK4 não precisar importar o módulo GTK3
TRAY_BUS = "com.koia.Tray"

NODE = Gio.DBusNodeInfo.new_for_xml("""
<node>
  <interface name="com.koia.Koia">
    <method name="OpenWindow"/>
    <method name="CloseWindow"/>
    <method name="Quit"/>
    <method name="GetWindowState">
      <arg type="b" name="open" direction="out"/>
    </method>
    <signal name="WindowState">
      <arg type="b" name="open" direction="out"/>
    </signal>
  </interface>
</node>
""")

INTERFACE_INFO = NODE.lookup_interface("com.koia.Koia")


class WindowAgent:
    """Exporta a interface e ponteia os métodos do D-Bus para o app."""

    def __init__(self, app):
        self.app = app
        self._reg_id = 0
        self._window = None

    # -- registro --------------------------------------------------------
    def register(self, window):
        """Registra o objeto (no ``do_activate``, quando o nome já existe).
        ``window``: a janela principal — a mesma de ``app.get_active_window``.
        """
        if self._reg_id:
            return
        self._window = window
        connection = self.app.get_dbus_connection()
        if connection is None:
            return
        connection.register_object(
            OBJ_PATH, INTERFACE_INFO, self._on_method_call, None, None,
        )
        self._reg_id = 1
        window.connect("notify::visible", self._on_visible_changed)

    # -- métodos ---------------------------------------------------------
    def _on_method_call(self, connection, sender, path, interface, method,
                        parameters, invocation):
        window = self._window
        if method == "OpenWindow":
            if window is not None:
                window.present()
            invocation.return_value()
        elif method == "CloseWindow":
            if window is not None:
                window.hide()
            invocation.return_value()
        elif method == "Quit":
            invocation.return_value()
            self.app.quit()
        elif method == "GetWindowState":
            # sondagem do tray que sobe DEPOIS do app (autostart): o
            # sinal WindowState do activate já teria passado reto
            open_now = window is not None and window.is_visible()
            invocation.return_value(
                GLib.Variant("(b)", (bool(open_now),))
            )
        else:
            invocation.return_gerror(
                GLib.Error.new_literal(
                    Gio.dbus_error_quark(),
                    int(Gio.DBusError.UNKNOWN_METHOD),
                    f"método desconhecido: {method}",
                )
            )

    def _on_visible_changed(self, window, _pspec):
        self.emit_state(window.is_visible())

    # -- sinal -------------------------------------------------------------
    def emit_state(self, visible):
        connection = self.app.get_dbus_connection()
        if connection is None:
            return
        connection.emit_signal(
            None, OBJ_PATH, "com.koia.Koia", "WindowState",
            # "(b)" é tupla de 1 bool: passar o bool solto levanta
            # TypeError ("bool object is not iterable")
            GLib.Variant("(b)", (bool(visible),)),
        )


def call(method, callback=None):
    """Chamada de fogo-e-esquece do lado do tray (GTK3).

    ``callback(done_ok)`` opcional, chamado no fim.
    """
    def _call(connection, res):
        try:
            connection.call_finish(res)
            ok = True
        except GLib.Error:
            ok = False
        if callback:
            callback(ok)

    def _connected(source, res):
        try:
            connection = Gio.bus_get_finish(res)
        except GLib.Error:
            if callback:
                callback(False)
            return
        connection.call(
            APP_ID, OBJ_PATH, "com.koia.Koia", method,
            None, None, Gio.DBusCallFlags.NONE, -1, None, _call,
        )

    Gio.bus_get(Gio.BusType.SESSION, None, _connected)


# ---------------------------------------------------------------------------
# Subir o daemon do tray quando ele não está rodando
# ---------------------------------------------------------------------------

def _reap(proc, res):
    """Descarta o filho terminado — sem isso ele vira zumbi."""
    try:
        proc.wait_finish(res)
    except GLib.Error:
        pass


def _open_tray_log():
    """Abre o log do tray para anexo (corta se passar de 1 MB).

    Devolve um fd pronto para ``take_fd``, ou ``None`` — sem log é
    melhor spawnar calado do que não spawnar.
    """
    path = paths.TRAY_LOG_PATH
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
    except OSError:
        return None
    # arquivo inexistente é o caso NORMAL da primeira execução — não
    # pode cair no mesmo except que engole falha de disco permissão
    try:
        size = os.path.getsize(path)
    except OSError:
        size = 0
    mode = os.O_WRONLY | os.O_CREAT
    mode |= os.O_TRUNC if size > 1024 * 1024 else os.O_APPEND
    try:
        return os.open(path, mode, 0o644)
    except OSError:
        return None


def _spawn_tray():
    """Sobe ``run.py --tray``; stderr vai para o log, stdout some.

    O log existe porque o spawn é silencioso: sem ele, qualquer crash
    do daemon seria invisível (e o tray "some" sem deixar rastro).
    """
    try:
        launcher = Gio.SubprocessLauncher.new(
            Gio.SubprocessFlags.STDOUT_SILENCE)
        fd = _open_tray_log()
        if fd is not None:
            launcher.take_fd(fd, 2)   # 2 = stderr do filho
        proc = launcher.spawnv([sys.executable, paths.RUNNER, "--tray"])
        proc.wait_async(None, _reap)
    except GLib.Error as exc:
        print(f"[koia] não subiu o tray: {exc.message}")


class _TrayStarter:
    """One-shot por execução do app: só UMA tentativa de subir o tray.

    Se o ``com.koia.Tray`` já está no bus (autostart do login ou um
    ``run.py --tray`` manual), não faz nada. Se não está, spawna uma
    vez — e se o usuário matar o tray depois, NÃO ressuscita: quem
    mandou matar quis morrer ("matar = morrer").
    """

    def __init__(self):
        self._watch_id = 0
        self._spawned = False

    def ensure(self):
        if self._watch_id:
            return  # watch único: ensure é idempotente
        self._watch_id = Gio.bus_watch_name(
            Gio.BusType.SESSION, TRAY_BUS, Gio.BusNameWatcherFlags.NONE,
            self._on_appeared, self._on_vanished,
        )

    def _on_appeared(self, _bus, _name, _owner):
        pass  # tray já rodando: é o caso normal do autostart

    def _on_vanished(self, _bus, _name):
        # o vanished inicial dispara quando o nome ainda não existe —
        # é exatamente aí que o spawn acontece (uma única vez)
        if self._spawned:
            return
        self._spawned = True
        _spawn_tray()


_starter = _TrayStarter()


def ensure_tray_running():
    """Garante o daemon do tray — chamado pelo app GTK4 no ``do_startup``.

    Sem tray, o app ficaria inalcançável depois do X (sem nenhum
    controle visível). Com ele, ``python3 run.py`` uma vez entrega app
    + bandeja; o tray sozinho continua sendo só ``run.py --tray``
    (o autostart de login usa esse caminho).
    """
    _starter.ensure()
