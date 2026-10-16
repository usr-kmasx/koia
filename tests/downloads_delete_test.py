#!/usr/bin/env python3
"""Teste do botão de lixeira na grade de downloads.

Cobre: estrutura dos cards (Overlay com botão-card e lixeira como
IRMÃOS, contrato do teclado intacto), clique na lixeira -> UM alerta
de confirmação -> apagar do disco + card sai da grade, Cancelar não
apaga nada e estado vazio continua de pé.
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Adw, GdkPixbuf, Gtk  # noqa: E402

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


def cards(flow):
    out = []
    child = flow.get_first_child()
    while child is not None:
        out.append(child)
        child = child.get_next_sibling()
    return out


def achar_card(flow, nome):
    for child in cards(flow):
        card = child.get_child()
        if card.get_first_child().get_tooltip_text() == nome:
            return child
    raise AssertionError(f"card {nome} não encontrado")


def lixeira_de(card):
    """FlowBoxChild -> Overlay -> botão de lixeira (irmão do tile)."""
    return card.get_child().get_last_child()


# pastinha falsa com 2 imagens
pasta = tempfile.mkdtemp(prefix="koia-dl-test-")
for nome in ("a.png", "b.png"):
    pb = GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, True, 8, 8, 8)
    pb.fill(0x336699FF)
    pb.savev(os.path.join(pasta, nome), "png", [], [])

dialog = dv.build_downloads_dialog(None, pasta, lambda _w: None)
# Adw.Dialog só monta a árvore interna ao ser apresentado — o child
# setado via set_child é a âncora confiável para a travessia
flow = find_flowbox(dialog.get_child())
assert flow is not None, "sem FlowBox no diálogo"
assert len(cards(flow)) == 2, f"esperava 2 cards, veio {len(cards(flow))}"

# estrutura: FlowBoxChild -> Overlay[tile Button | lixeira Button]
card0 = cards(flow)[0].get_child()
assert isinstance(card0, Gtk.Overlay), "card não é Gtk.Overlay"
tile = card0.get_first_child()
assert isinstance(tile, Gtk.Button), "tile não é Gtk.Button (contrato)"
assert tile.get_tooltip_text() in ("a.png", "b.png"), tile.get_tooltip_text()
lixeira = card0.get_last_child()
assert isinstance(lixeira, Gtk.Button), "sem botão de lixeira na thumb"
assert lixeira is not tile, "lixeira e card não são irmãos"
assert lixeira.get_icon_name() == "user-trash-symbolic", \
    lixeira.get_icon_name()
assert "koia-trash" in lixeira.get_css_classes(), "sem o vermelho da lixeira"

# foco inicial aponta pro botão-card (via teclado o Enter abre ele)
foco = dialog.props.focus_widget
assert foco is tile, "foco inicial não é o botão-card"

# clique na lixeira -> UM alerta destrutivo correto (sem UI real)
capturado = {}
real_present = Adw.AlertDialog.present
Adw.AlertDialog.present = lambda self, w: capturado.update({"alert": self})
try:
    lixeira_de(achar_card(flow, "a.png")).emit("clicked")
finally:
    Adw.AlertDialog.present = real_present
alert = capturado.get("alert")
assert alert is not None, "clique na lixeira não abriu o alerta"
assert alert.props.heading == "Apagar o wallpaper?", alert.props.heading
assert "permanentemente" in alert.props.body, alert.props.body
assert alert.get_response_appearance("delete") == \
    Adw.ResponseAppearance.DESTRUCTIVE, "Apagar não é destrutivo"

alvo = os.path.join(pasta, "a.png")
assert os.path.exists(alvo)
alert.emit("response", "cancel")
assert os.path.exists(alvo), "Cancelar apagou o arquivo!"
assert len(cards(flow)) == 2, "Cancelar tirou card da grade"

capturado.clear()
Adw.AlertDialog.present = lambda self, w: capturado.update({"alert": self})
try:
    lixeira_de(achar_card(flow, "a.png")).emit("clicked")
finally:
    Adw.AlertDialog.present = real_present
assert capturado.get("alert") is not None, "segundo clique sem alerta"
capturado["alert"].emit("response", "delete")
assert not os.path.exists(alvo), "arquivo não foi apagado"
assert len(cards(flow)) == 1, "card continuou na grade"
assert os.path.exists(os.path.join(pasta, "b.png")), "b.png foi junto"

# estado vazio continua de pé
vazio = tempfile.mkdtemp(prefix="koia-dl-vazio-")
dialog_vazio = dv.build_downloads_dialog(None, vazio, lambda _w: None)
assert isinstance(dialog_vazio.get_child(), Adw.StatusPage)

print("[koia-dl] lixeira da grade: ok")
