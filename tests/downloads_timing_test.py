#!/usr/bin/env python3
"""Teste de timing da grade de downloads (thumb assíncrona).

Garante que o build do diálogo NÃO decodifica nada na thread principal
(o bug que congelava a janela no clique do 🖼) e que todas as thumbs
chegam pela via assíncrona, com tamanho ≤ TILE.
"""
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Adw, GdkPixbuf, GLib, Gtk  # noqa: E402

Gtk.init()
Adw.init()

from koia import downloads_view as dv  # noqa: E402


def find_flowbox(w):
    if isinstance(w, Gtk.FlowBox):
        return w
    child = w.get_first_child() if isinstance(w, Gtk.Widget) else None
    while child is not None:
        r = find_flowbox(child)
        if r is not None:
            return r
        child = child.get_next_sibling()
    return None


def pictures(flow):
    """Gtk.Picture de cada card (FlowBoxChild -> Overlay -> tile -> Picture)."""
    out = []
    child = flow.get_first_child()
    while child is not None:
        card = child.get_child()            # Overlay
        tile = card.get_first_child()       # botão-card
        out.append(tile.get_first_child())  # Gtk.Picture
        child = child.get_next_sibling()
    return out


# --- fixtures 4K em /tmp ----------------------------------------------------
pasta = tempfile.mkdtemp(prefix="koia-dl-timing-")
grande = GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, True, 8, 3840, 2160)
grande.fill(0x336699FF)
png = os.path.join(pasta, "grande.png")
jpg = os.path.join(pasta, "grande.jpg")
grande.savev(png, "png", [], [])
grande.savev(jpg, "jpeg", ["quality"], ["85"])

# referência: o custo que ANTES rodava na thread principal do build
for nome, caminho in (("png", png), ("jpeg", jpg)):
    t0 = time.perf_counter()
    assert dv._thumb_local(caminho) is not None
    print(f"[koia-dl-timing] decode {nome} 4K: "
          f"{(time.perf_counter() - t0) * 1000:.0f} ms "
          f"(agora em thread, fora da UI)")

# --- build síncrono precisa ser só construção de widgets --------------------
t0 = time.perf_counter()
dialog = dv.build_downloads_dialog(None, pasta, lambda _w: None)
build_ms = (time.perf_counter() - t0) * 1000
flow = find_flowbox(dialog.get_child())
assert flow is not None, "sem FlowBox no diálogo"
pics = pictures(flow)
assert len(pics) == 2, f"esperava 2 cards, veio {len(pics)}"

# nada pode ter sido decodificado ainda: idle_add não roda sem o main loop
for pic in pics:
    assert pic.get_paintable() is None, "thumb decodificada de forma síncrona"
assert build_ms < 300, f"build demorou {build_ms:.0f} ms (decode voltou pra UI?)"
print(f"[koia-dl-timing] build síncrono: {build_ms:.0f} ms (2 cards 4K)")

# --- entrega assíncrona -----------------------------------------------------
ctx = GLib.MainContext.default()
fim = time.time() + 15
while time.time() < fim:
    if all(pic.get_paintable() is not None for pic in pics):
        break
    ctx.iteration(False)
    time.sleep(0.01)

for pic in pics:
    tex = pic.get_paintable()
    assert tex is not None, "thumb nunca chegou (entrega assíncrona quebrada)"
    assert max(tex.get_width(), tex.get_height()) <= dv.TILE, \
        f"thumb {tex.get_width()}x{tex.get_height()} passou de {dv.TILE}"

print("[koia-dl-timing] build sem decode + thumbs entregues: ok")
