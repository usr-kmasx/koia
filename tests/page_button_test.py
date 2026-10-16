#!/usr/bin/env python3
"""Wiring do ▦ (visor de página) na janela principal.

Constrói a KoiaWindow real (settings/cache em /tmp, sem rede), injeta
uma página no cache e verifica: botão nasce apagado, ação registrada,
fica sensível com página, apaga em contexto de item único,
open_page_view repassa página/índice certos e o salto atualiza o índice.
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Adw, GdkPixbuf, Gio, GLib, Gtk  # noqa: E402

Gtk.init()
Adw.init()

import koia.window as W  # noqa: E402
from koia.config import Settings  # noqa: E402
from koia.image import ImageLoader  # noqa: E402

tmp = tempfile.mkdtemp(prefix="koia-pagebtn-")
app = Adw.Application(application_id="org.koia.PageViewTest",
                      flags=Gio.ApplicationFlags.NON_UNIQUE)
app.register()
win = W.KoiaWindow(app, Settings(path=os.path.join(tmp, "settings.ini")))

# nada no cache real do usuário
win.images = ImageLoader(os.path.join(tmp, "cache"))

btn = win.btn_page_header
assert not btn.get_sensitive(), "botão deve nascer apagado"
assert win.lookup_action("show-page") is not None, "ação win.show-page ausente"

# injeta uma página no cache: load_page(1) usa o cache, sem rede.
# o fingerprint precisa casar ANTES, senão o load_page derruba o cache
walls = []
for i in range(3):
    caminho = os.path.join(tmp, f"w{i}.png")
    pb = GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, True, 8, 8, 8)
    pb.fill(0x336699FF)
    pb.savev(caminho, "png", [], [])
    uri = GLib.filename_to_uri(caminho, None)
    walls.append({"id": f"w{i}", "path": uri, "thumbs": {"large": uri}})
win._fingerprint = win._query_fingerprint()
win._pages[1] = {
    "data": walls,
    "meta": {"current_page": 1, "last_page": 3, "total": 72},
}
win.load_page(1)
assert win.page == 1 and len(win.items) == 3
assert btn.get_sensitive(), "com página carregada o ▦ deve ativar"

# open_page_view repassa página/índice/itens/fetch/last_page certos
chamadas = {}


class FakeDialog:
    def present(self, _parent):
        chamadas["present"] = True


def fake_build(parent, page, items, index, images, on_jump,
               fetch, last_page):
    chamadas.update(page=page, index=index, n=len(items),
                    on_jump=on_jump, fetch=fetch,
                    last_page=last_page, parent=parent)
    return FakeDialog()


real_build = W.build_page_dialog
W.build_page_dialog = fake_build
try:
    win.open_page_view()
finally:
    W.build_page_dialog = real_build
assert chamadas["page"] == 1 and chamadas["n"] == 3
assert chamadas["index"] == win.index and chamadas["present"]
assert chamadas["fetch"] == win.fetch_page, "fetch_page não repassado"
assert chamadas["last_page"] == win.last_page == 3

# salto na MESMA página: troca índice na hora, sem load_page
real_load = win.load_page
buscas_win = []
win.load_page = lambda *a, **k: buscas_win.append((a, k))
try:
    chamadas["on_jump"](1, 2)         # página 1, foto 2
finally:
    win.load_page = real_load
assert win.index == 2 and buscas_win == [] and not win._fav_context

# salto em OUTRA página: carrega ela no lugar (gravador de load_page)
win.load_page = lambda *a, **k: buscas_win.append((a, k))
try:
    win.jump_to(2, 0)
finally:
    win.load_page = real_load
assert buscas_win == [((2,), {"index": 0})], buscas_win

# fetch_page: cache responde na hora; fora do cache, vai pra API
respostas = []
win.fetch_page(1, respostas.append, lambda _e: None)
assert respostas == [win._pages[1]], "cache não usado no fetch_page"
buscas_api = []
win.api.search = lambda **k: buscas_api.append(k)
try:
    win.fetch_page(2, lambda _r: None, lambda _e: None)
finally:
    del win.api.search    # volta pro método real da classe
assert buscas_api and buscas_api[0]["page"] == 2, "fetch sem cache falhou"

# item único (favorito/download): ▦ apaga e open_page_view vira no-op
win.show_wallpaper(walls[0])
assert not btn.get_sensitive(), "item único deve apagar o ▦"
W.build_page_dialog = fake_build
try:
    chamadas.pop("present", None)
    win.open_page_view()
finally:
    W.build_page_dialog = real_build
assert "present" not in chamadas, "open_page_view abriu em item único"

# volta pra página (contexto anterior, em cache): ▦ reativa
win._leave_favorites()
assert btn.get_sensitive(), "voltando pra página, ▦ deve reativar"

print("[koia-pagebtn] wiring do ▦: ok")
