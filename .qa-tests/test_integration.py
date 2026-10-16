#!/usr/bin/env python3
"""Koia — teste de integração.

Fluxos reais da UI (janela, favoritos, diálogo, apagar, fundo) com
API fake e imagens stubadas: sem rede, sem tocar no desktop, sem nada
apresentado na tela. Os testes visuais são manuais, pelo usuário.
"""
import os
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix="koia-int-", dir="/tmp/opencode")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_TMP, "config")
os.environ["XDG_CONFIG_DIRS"] = os.path.join(_TMP, "config-dirs")
os.environ["XDG_CACHE_HOME"] = os.path.join(_TMP, "cache")
os.environ["XDG_DATA_HOME"] = os.path.join(_TMP, "data")

sys.path.insert(0, "/home/usr/Projects/koia")

import gi  # noqa: E402

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Adw, GdkPixbuf, Gio, Gtk  # noqa: E402

from koia import background as bg  # noqa: E402
from koia.config import Settings  # noqa: E402
from koia.downloads_view import build_downloads_dialog  # noqa: E402
from koia.downloader import destination_for, filename_of  # noqa: E402
from koia.favorites_view import build_favorites_dialog  # noqa: E402
from koia.window import KoiaWindow  # noqa: E402

erros = []


def expect(cond, msg):
    if cond:
        print(f"  ok    {msg}")
    else:
        erros.append(msg)
        print(f"  FALHOU {msg}")


def wp(ident, pagina, n):
    return {
        "id": f"id{ident}",
        "path": f"http://x/{pagina}/{n}.jpg",
        "thumbs": {"large": f"http://x/thumb/{pagina}/{n}.jpg"},
    }


class FakeAPI:
    def search(self, page=1, on_done=None, on_error=None):
        on_done({
            "data": [wp(f"{page}{i}", page, i) for i in range(3)],
            "meta": {"current_page": page, "last_page": 2, "total": 6},
        })


# ---------------------------------------------------------------------------
app = Adw.Application(application_id="com.koia.Integracao",
                      flags=Gio.ApplicationFlags.DEFAULT_FLAGS)
settings = Settings()
win = KoiaWindow(app, settings)
win.api = FakeAPI()

# stub do loader: registra os pedidos e devolve None (sem rede, sem thread)
carregadas = []


def stub_load(url, callback, max_side=None, persist=True):
    carregadas.append((url, persist))
    callback(None)


win.images.load = stub_load
win.images.prefetch = lambda _url: None

# -- fluxo 1: carrega e exibe -------------------------------------------
win.load_page(1)
expect(len(win.items) == 3, "página 1 carregada com 3 itens")
expect(any("thumb" in url for url, _ in carregadas),
       "thumbnail pedida ao loader")
win._schedule_full(win.current()["path"], win._gen)
expect(any(not persist for _url, persist in carregadas),
       "completa pedida com persist=False (só RAM)")

# -- fluxo 2: favoritar -> diálogo -> abrir -> seta volta ---------------
win.toggle_favorite()
favorito_id = win.current()["id"]
expect(win.favorites.contains(favorito_id), "favoritou pelo ♡")
expect(win.btn_fav.get_icon_name() == "koia-heart-filled-symbolic",
       "coração flutuante virou preenchido")
expect(win.btn_fav.has_css_class("koia-fav"),
       "coração flutuante ficou vermelho")

d = build_favorites_dialog(win, win.favorites, win.images, win.show_wallpaper)
scrolled = d.get_child()
grade = scrolled.get_child() if isinstance(scrolled, Gtk.ScrolledWindow) else None
if isinstance(grade, Gtk.Viewport):
    grade = grade.get_child()   # ScrolledWindow embrulha em Viewport
cards = 0
if grade is not None:
    child = grade.get_first_child()
    while child is not None:
        cards += 1
        child = child.get_next_sibling()
expect(cards == 1, f"diálogo com exatamente 1 card (veio {cards})")

if grade is not None and grade.get_first_child() is not None:
    grade.get_first_child().get_child().emit("clicked")
    expect(win.current()["id"] == favorito_id, "clique no card abriu o favorito")
    expect(win._fav_context, "entrou no contexto de favorito")
    win.go_prev()
    expect(not win._fav_context and len(win.items) == 3,
           "seta devolveu para a busca com as mesmas imagens")

# -- fluxo 3: apagar download com confirmação ---------------------------
pasta = tempfile.mkdtemp(prefix="koia-int-dl-", dir="/tmp/opencode")
settings.set("download.folder", pasta)
dest = destination_for(win.current(), pasta)
with open(dest, "wb") as fh:
    fh.write(b"fake")
win._refresh_download_badge()
expect(win.btn_dl.get_icon_name() == "user-trash-symbolic",
       "⤓ virou lixeira com o arquivo em disco")
win._on_delete_response("cancel", dest, filename_of(win.current()))
expect(os.path.exists(dest), "cancelar manteve o arquivo")
win._on_delete_response("delete", dest, filename_of(win.current()))
expect(not os.path.exists(dest), "confirmar apagou o arquivo")
expect(win.btn_dl.get_icon_name() == "document-save-symbolic",
       "⤓ voltou ao ícone de download")

# -- fluxo 4: fundo anterior (arquivos inexistentes nunca tocam o sistema)
estado = os.path.join(_TMP, "bg.json")
expect(bg.restore_previous_background(state_path=estado) == (None, False),
       "restaurar sem estado não aplica nada")
bg._push_previous("file:///nao/existe.jpg", estado)
expect(bg.restore_previous_background(state_path=estado) == (None, False),
       "anterior inexistente não aplica nada")

# -- fluxo 5: desfavoritar ----------------------------------------------
win.toggle_favorite()
expect(not win.favorites.contains(favorito_id), "desfavoritou")
expect(win.btn_fav.get_icon_name() == "koia-heart-symbolic",
       "coração voltou ao contorno")
expect(not win.btn_fav.has_css_class("koia-fav"),
       "vermelho removido ao desfavoritar")

# -- fluxo 6: diálogo de downloads ---------------------------------------
pasta_gal = tempfile.mkdtemp(prefix="koia-int-gal-", dir="/tmp/opencode")
pix = GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, False, 8, 8, 8)
pix.fill(0x3366CCFF)
pix.savev(os.path.join(pasta_gal, "guardado.png"), "png", [], [])
settings.set("download.folder", pasta_gal)

dg = build_downloads_dialog(win, pasta_gal, win.show_wallpaper)
grade = dg.get_child().get_child()
if isinstance(grade, Gtk.Viewport):
    grade = grade.get_child()
n_cards = 0
child = grade.get_first_child()
while child is not None:
    n_cards += 1
    child = child.get_next_sibling()
expect(n_cards == 1, f"diálogo de downloads com 1 card (veio {n_cards})")

if n_cards:
    grade.get_first_child().get_child().emit("clicked")
    atual = win.current()
    expect(atual is not None and atual["path"].startswith("file://")
           and atual["path"].endswith("guardado.png"),
           "clique abriu o arquivo baixado na janela principal")
    dest_gal = destination_for(atual, pasta_gal)
    expect(os.path.exists(dest_gal),
           "badge/lixeira batem com o arquivo real (destination_for)")
    win._refresh_download_badge()
    expect(win.btn_dl.get_icon_name() == "user-trash-symbolic",
           "⤓ aparece como lixeira para o arquivo aberto")

# ---------------------------------------------------------------------------
print()
if erros:
    print(f"RESULTADO: {len(erros)} FALHAS")
    sys.exit(1)
print("RESULTADO: integração ok")
