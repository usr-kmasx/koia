"""Lógica do ensure_tray_running em bus PRIVADO (dbus-run-session).

Cenários:
  A) sem com.koia.Tray no bus   → ensure() spawna EXATAMENTE 1x
  B) ensure() repetido          → idempotente (watch único, 1 spawn)
  C) nome adquirido e solto     → vanish tardio NÃO ressuscita (one-shot)
  D) starter novo com nome já presente → 0 spawns (caso do autostart)
Spawn real interceptado: nenhum tray/processo visual é criado.
"""
import os
import sys

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import koia.ipc as ipc  # noqa: E402

spawns = []
ipc._spawn_tray = lambda: spawns.append(1)   # intercepta o spawn real

loop = GLib.MainLoop()
own_id = [0]


def phase_a():
    assert spawns == [1], f"A: devia ser exatamente 1 spawn, foi {spawns}"
    # C: adquire o nome (simula o tray subindo) → appeared sem ação
    own_id[0] = Gio.bus_own_name(
        Gio.BusType.SESSION, "com.koia.Tray", Gio.BusNameOwnerFlags.NONE,
        None, None, None)
    return False


def phase_c():
    assert spawns == [1], "C: appeared não pode spawnar"
    Gio.bus_unown_name(own_id[0])   # "usuário matou o tray"
    return False


def phase_c2():
    assert spawns == [1], "C: vanish tardio ressuscitou o tray!"
    # D: nome de novo no bus, starter NOVO (outro app) → 0 spawns
    own_id[0] = Gio.bus_own_name(
        Gio.BusType.SESSION, "com.koia.Tray", Gio.BusNameOwnerFlags.NONE,
        None, None, None)
    return False


def phase_d():
    starter2 = ipc._TrayStarter()
    starter2.ensure()
    assert starter2._watch_id, "D: watch não registrado"
    return False


def phase_d2():
    assert spawns == [1], "D: tray já presente → não deve spawnar"
    # sanity estática do comando de spawn
    assert os.path.exists(ipc.paths.RUNNER), "run.py não encontrado"
    assert ipc.TRAY_BUS == "com.koia.Tray"
    import koia.tray as tray_mod
    assert tray_mod.TRAY_BUS is ipc.TRAY_BUS, "TRAY_BUS duplicado/diferente"
    print("[koia-tray-starter] cenários A/B/C/D ok")
    loop.quit()
    return False


starter = ipc._TrayStarter()
starter.ensure()
starter.ensure()          # B: idempotente
assert starter._watch_id  # B: watch registrado

GLib.timeout_add(150, phase_a)     # A
GLib.timeout_add(450, phase_c)     # C (1)
GLib.timeout_add(750, phase_c2)    # C (2) + início de D
GLib.timeout_add(1050, phase_d)
GLib.timeout_add(1350, phase_d2)
GLib.timeout_add_seconds(8, lambda: (loop.quit(),
                                     sys.exit(1), False)[1])
loop.run()
