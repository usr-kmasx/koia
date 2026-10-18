#!/usr/bin/env python3
"""Teste do visor de página navegável (page_view).

Cobre: render inicial (destaque/foco só na página da janela), ‹ › em
loop, campo de página pulando direto, guarda contra fetch em loop,
página vazia mantém a grade + toast, clique pula com (página, índice) e
clique na foto atual só fecha.
"""
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Gdk", "4.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Adw, Gdk, GdkPixbuf, GLib, Gtk  # noqa: E402

Gtk.init()
Adw.init()

from koia import page_view as pv  # noqa: E402
from koia.image import ImageLoader  # noqa: E402
from koia.main import CSS  # noqa: E402


def achar(w, tipo):
    if isinstance(w, tipo):
        return w
    child = w.get_first_child() if isinstance(w, Gtk.Widget) else None
    while child is not None:
        r = achar(child, tipo)
        if r is not None:
            return r
        child = child.get_next_sibling()
    return None


def flow_do(dialog):
    flow = achar(dialog.get_child(), Gtk.FlowBox)
    assert flow is not None, "sem FlowBox no diálogo"
    return flow


def cards(flow):
    out = []
    child = flow.get_first_child()
    while child is not None:
        out.append(child.get_child())   # FlowBoxChild -> botão-card
        child = child.get_next_sibling()
    return out


# --- fixtures: 3 páginas em /tmp (sem rede) --------------------------------
pasta = tempfile.mkdtemp(prefix="koia-page-")


def walls(*nomes):
    out = []
    for nome in nomes:
        caminho = os.path.join(pasta, f"{nome}.png")
        pb = GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, True, 8, 96, 64)
        pb.fill(0x224466FF)
        pb.savev(caminho, "png", [], [])
        uri = GLib.filename_to_uri(caminho, None)
        out.append({"id": nome, "path": uri, "thumbs": {"large": uri}})
    return out


paginas = {
    1: {"data": walls("w0", "w1", "w2"),
        "meta": {"current_page": 1, "last_page": 3, "total": 6}},
    2: {"data": [],                              # página vazia: erro+reverte
        "meta": {"current_page": 2, "last_page": 3, "total": 6}},
    3: {"data": walls("x0", "x1"),
        "meta": {"current_page": 3, "last_page": 3, "total": 6}},
}

buscas = []


def fetch_stub(page, on_done, on_error):
    buscas.append(page)
    on_done(paginas[page])


images = ImageLoader(tempfile.mkdtemp(prefix="koia-page-cache-"))
saltos = []
dialog = pv.build_page_dialog(
    None, 1, paginas[1]["data"], 1, images,
    lambda p, i: saltos.append((p, i)), fetch_stub, 3)

# --- estrutura inicial: página da janela, foto1 destacada -------------------
assert dialog.props.title == "Página 1", dialog.props.title
flow = flow_do(dialog)
tiles = cards(flow)
assert [t.get_tooltip_text() for t in tiles] == ["w0", "w1", "w2"]
atuais = [t for t in tiles if t.has_css_class("koia-current")]
assert atuais == [tiles[1]], "koia-current deve marcar SÓ a foto atual"
assert dialog.props.focus_widget is tiles[1], "foco não é na foto atual"

spin = achar(dialog.get_child(), Gtk.SpinButton)
assert spin is not None, "sem campo de página no rodapé"
assert spin.get_value() == 1 and spin.get_adjustment().get_upper() == 3


def _por_icon(w, nome):
    if isinstance(w, Gtk.Button) and w.get_icon_name() == nome:
        return w
    child = w.get_first_child() if isinstance(w, Gtk.Widget) else None
    while child is not None:
        r = _por_icon(child, nome)
        if r is not None:
            return r
        child = child.get_next_sibling()
    return None


btn_prev = _por_icon(dialog.get_child(), "go-previous-symbolic")
btn_next = _por_icon(dialog.get_child(), "go-next-symbolic")
assert btn_prev is not None and btn_next is not None, "sem ‹ › no rodapé"

# toasts interceptados (página vazia deve avisar)
toasts = []
real_add = Adw.ToastOverlay.add_toast
Adw.ToastOverlay.add_toast = \
    lambda self, t: toasts.append(t.get_title())

# --- › na página 1: tenta 2 → vazia → toast + grade mantida + volta -------
btn_next.emit("clicked")
assert buscas == [2], buscas
assert toasts == ["Página vazia"], toasts
assert spin.get_value() == 1, "página vazia deve reverter o campo"
assert len(cards(flow)) == 3, "página vazia não pode apagar a grade"
assert btn_prev.get_sensitive(), "controles devem religar após erro"

# --- ‹ na página 1: loop pra última (3) -------------------------------------
btn_prev.emit("clicked")
assert buscas == [2, 3], buscas
assert dialog.props.title == "Página 3"
assert spin.get_value() == 3
tiles3 = cards(flow)
assert [t.get_tooltip_text() for t in tiles3] == ["x0", "x1"]
assert not [t for t in tiles3 if t.has_css_class("koia-current")], \
    "outra página não pode herdar o destaque"
assert dialog.props.focus_widget is tiles3[0], \
    "em outra página o foco abre no primeiro card"

# --- › na última: loop volta pra 1 (destaque volta) ------------------------
btn_next.emit("clicked")
assert buscas == [2, 3, 1], buscas
tiles1 = cards(flow)
assert [t.get_tooltip_text() for t in tiles1] == ["w0", "w1", "w2"]
assert tiles1[1].has_css_class("koia-current"), "destaque não voltou"
assert spin.get_value() == 1 and dialog.props.title == "Página 1"

# --- campo de página: +/− só ajusta o número; Enter busca -------------------
def teclas_do_campo(w):
    modelo = w.observe_controllers()
    for i in range(modelo.get_n_items()):
        c = modelo.get_item(i)
        if isinstance(c, Gtk.EventControllerKey):
            return c
    return None


antes = list(buscas)
spin.set_value(3)                       # como clicar nos +/− do campo
assert buscas == antes, "+/− buscou de imediato (tem que esperar Enter)"
assert spin.get_value() == 3
teclas = teclas_do_campo(spin)
assert teclas is not None, "campo sem controlador de teclado"
# outra tecla passa reto (devolve False) e não busca
assert teclas.emit("key-pressed", Gdk.KEY_a, 0, 0) is False
assert buscas == antes, "tecla comum não pode buscar"
# Enter pega o número JÁ no 1º toque (a camada de tecla, não o sinal
# "activate", que só sairia no Enter seguinte)
assert teclas.emit("key-pressed", Gdk.KEY_Return, 0, 0) is True
assert buscas == antes + [3], "Enter não pulou"
assert spin.get_value() == 3 and len(cards(flow)) == 2
# Enter de novo, com o mesmo número: nada a buscar
assert teclas.emit("key-pressed", Gdk.KEY_Return, 0, 0) is True
assert buscas == antes + [3], "Enter com o mesmo número buscou"

# --- clique: pula com (página, índice); foto atual só fecha -----------------
tiles3 = cards(flow)
tiles3[1].emit("clicked")
assert saltos == [(3, 1)], f"clique em outra página/foto: {saltos}"

# --- thumbs assíncronas chegam (file:// pelo ImageLoader) -------------------
ctx = GLib.MainContext.default()
fim = time.time() + 15
while time.time() < fim:
    pics = [t.get_first_child() for t in cards(flow)]
    if all(p.get_paintable() is not None for p in pics):
        break
    ctx.iteration(False)
    time.sleep(0.01)
for t in cards(flow):
    assert t.get_first_child().get_paintable() is not None, \
        "thumb nunca chegou"

Adw.ToastOverlay.add_toast = real_add
assert ".koia-current" in CSS, "CSS sem .koia-current"

# --- retomar: abrir numa página lembrada (!= página da janela) --------------
# o ▦ lembra a página que estava vendo: ao reabrir, ela é BUSCADA (os itens
# da janela não servem), o destaque fica preso à página da janela e o
# callback on_page registra a página exibida.
lembradas = []
vistas = []


def fetch_lembrada(page, on_done, on_error):
    lembradas.append(page)
    on_done(paginas[page])


retomar = pv.build_page_dialog(
    None, 3, paginas[1]["data"], 1, images,
    lambda p, i: None, fetch_lembrada, 3,
    window_page=1, on_page=vistas.append)
assert lembradas == [3], "página lembrada não foi buscada"
assert retomar.props.title == "Página 3"
assert achar(retomar.get_child(), Gtk.SpinButton).get_value() == 3, \
    "campo não mostra a página lembrada"
tiles_r = cards(flow_do(retomar))
assert [t.get_tooltip_text() for t in tiles_r] == ["x0", "x1"], \
    "página lembrada deve ser buscada, não reusar os itens da janela"
assert not [t for t in tiles_r if t.has_css_class("koia-current")], \
    "página diferente da janela não tem foto atual"
assert vistas == [3], vistas

print("[koia-page] visor navegável: ok")
