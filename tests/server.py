"""Server-side fake do app GTK4 num bus PRIVADO (dbus-run-session).

Valida a interface de koia/ipc.py isoladamente, sem Gtk e sem display:
- dono do nome com.koia.Koia
- register_object em /com/koia/Koia com a NODE de ipc.py
- OpenWindow → devolve Void e emite WindowState(True)
- CloseWindow → devolve Void e emite WindowState(False)
- Quit → devolve Void e termina o processo
"""
import os
import sys

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from koia.ipc import APP_ID, OBJ_PATH, INTERFACE_INFO  # noqa: E402

loop = GLib.MainLoop.new(None, True)


def on_method_call(connection, sender, path, interface, method,
                   parameters, invocation):
    print(f"SERVER: {method} →", flush=True)
    if method == "GetWindowState":
        # app "aberto" no fake — cliente deve receber (True,)
        invocation.return_value(GLib.Variant("(b)", (True,)))
        return
    invocation.return_value()
    if method == "OpenWindow":
        connection.emit_signal(
            None, OBJ_PATH, "com.koia.Koia", "WindowState",
            GLib.Variant("(b)", (True,)))
    elif method == "CloseWindow":
        connection.emit_signal(
            None, OBJ_PATH, "com.koia.Koia", "WindowState",
            GLib.Variant("(b)", (False,)))
    elif method == "Quit":
        GLib.idle_add(loop.quit)
        return False


def breadcrumb_backstop():
    print("SERVER: fim (backstop)", flush=True)
    loop.quit()
    return False


def ready():
    bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
    # primeiro o objeto, depois o nome: o cliente só "enxerga" o
    # serviço quando o dono do nome aparece — o objeto precisa existir
    # nesse instante
    reg = bus.register_object(OBJ_PATH, INTERFACE_INFO,
                              on_method_call, None, None)
    assert reg, "register_object falhou"
    Gio.bus_own_name_on_connection(bus, APP_ID, Gio.BusNameOwnerFlags.NONE,
                                   None, None)
    print("SERVER: pronto", flush=True)
    return False  # one-shot


Gio.bus_get(Gio.BusType.SESSION, None,
            lambda s, r: (Gio.bus_get_finish(r), ready()))
GLib.timeout_add_seconds(10, breadcrumb_backstop)
loop.run()
print("SERVER: fim", flush=True)
