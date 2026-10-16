"""Client-side tests num bus PRIVADO — dois caminhos:

1. proxy (o que o tray faz): DBusProxy.new_sync + call + g-signal
2. helper koia.ipc.call() (callback de done/ok)

Sequência (sem corrida — tudo ANTES do Quit do server):
  t=0    proxy.call OpenWindow   → server emite WindowState(True)
  t=400  proxy.call CloseWindow  → server emite WindowState(False)
  t=700  ipc.call("OpenWindow")  → server emite WindowState(True)
  t=1000 proxy.call Quit         → server encerra
  t=1300 veredito: todas as calls ok=True e states==[True, False, True]

Sai com código 0 só se passar em tudo.
"""
import os
import sys

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import koia.ipc  # noqa: E402
from koia.ipc import APP_ID, OBJ_PATH  # noqa: E402

calls_ok = []
states = []


def on_state_queried(proxy, res):
    try:
        reply = proxy.call_finish(res)
        value = bool(reply.unpack()[0])
    except GLib.Error as exc:
        print(f"CLIENT: GetWindowState ERRO: {exc.message}", flush=True)
        calls_ok.append(False)
        return
    print(f"CLIENT: GetWindowState → {value}", flush=True)
    calls_ok.append(value is True)  # falso = falha (fake responde True)


def on_signal(proxy, sender, signal, message):
    if signal == "WindowState":
        value = bool(message.unpack()[0])
        print(f"CLIENT: sinal WindowState({value})", flush=True)
        states.append(value)


def key_on(source, res, label):
    ok = True
    try:
        source.call_finish(res)
    except GLib.Error as exc:
        print(f"CLIENT: {label} ERRO: {exc.message}", flush=True)
        ok = False
    print(f"CLIENT: call {label} ok={ok}", flush=True)
    calls_ok.append(ok)


def do_close(proxy):
    proxy.call("CloseWindow", None, Gio.DBusCallFlags.NONE, -1, None,
               lambda s, r: key_on(s, r, "CloseWindow"))
    return GLib.SOURCE_REMOVE


def do_helper_call(proxy):
    koia.ipc.call("OpenWindow",
                  lambda ok: (print(f"CLIENT: ipc.call OpenWindow ok={ok}",
                                    flush=True),
                              calls_ok.append(ok)))
    return GLib.SOURCE_REMOVE


def do_quit(proxy):
    proxy.call("Quit", None, Gio.DBusCallFlags.NONE, -1, None,
               lambda s, r: key_on(s, r, "Quit"))
    return GLib.SOURCE_REMOVE


def verdict():
    passed = all(calls_ok) and states == [True, False, True] \
        and len(calls_ok) == 5
    print(f"RESULT calls_ok={calls_ok} states={states} pass={passed}",
          flush=True)
    sys.exit(0 if passed else 1)


def proxy_ready(source, res):
    try:
        proxy = Gio.DBusProxy.new_finish(res)
    except GLib.Error as exc:
        print(f"CLIENT: proxy falhou: {exc.message}", flush=True)
        sys.exit(1)
    proxy.connect("g-signal", on_signal)
    # sondagem inicial (fluxo autostart: tray depois do app)
    proxy.call("GetWindowState", None, Gio.DBusCallFlags.NONE, -1, None,
               on_state_queried)
    proxy.call("OpenWindow", None, Gio.DBusCallFlags.NONE, -1, None,
               lambda s, r: key_on(s, r, "OpenWindow"))
    GLib.timeout_add(400, do_close, proxy)
    GLib.timeout_add(700, do_helper_call, proxy)
    GLib.timeout_add(1000, do_quit, proxy)
    GLib.timeout_add(1300, verdict)


Gio.bus_watch_name(
    Gio.BusType.SESSION, APP_ID, Gio.BusNameWatcherFlags.NONE,
    lambda *a: Gio.DBusProxy.new_for_bus(
        Gio.BusType.SESSION, Gio.DBusProxyFlags.NONE, None, APP_ID,
        OBJ_PATH, "com.koia.Koia", None, proxy_ready),
    # vanished dispara UMA vez no início (nome ainda não adquirido) —
    # é o estado normal; a falha real é coberta pelo backstop de 8s
    lambda *a: None,
)

loop = GLib.MainLoop.new(None, True)
# backstop: se o veredito não disparou, sai com erro em 8s
GLib.timeout_add_seconds(8, lambda: (sys.exit(1), False)[1])
loop.run()
sys.exit(1)
