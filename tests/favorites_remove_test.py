#!/usr/bin/env python3
"""Coração de desfavoritar na grade: ação isolada, persistência, foco e vazio."""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Gdk", "4.0")
from gi.repository import Adw, Gdk, Gtk  # noqa: E402

Gtk.init()
Adw.init()

from koia.favorites import FavoritesStore  # noqa: E402
from koia import favorites_view as fv  # noqa: E402


class FakeImages:
    def load(self, _url, _callback, **_kwargs):
        pass


def find_flow(widget):
    if isinstance(widget, Gtk.FlowBox):
        return widget
    child = widget.get_first_child()
    while child is not None:
        found = find_flow(child)
        if found is not None:
            return found
        child = child.get_next_sibling()
    return None


def cards(flow):
    out = []
    child = flow.get_first_child()
    while child is not None:
        out.append(child)
        child = child.get_next_sibling()
    return out


def parts(child):
    overlay = child.get_child()
    assert isinstance(overlay, Gtk.Overlay)
    return overlay.get_first_child(), overlay.get_last_child()


root = tempfile.mkdtemp(prefix="koia-favorites-heart-")
store = FavoritesStore(os.path.join(root, "favorites.json"))
files = []
for i in range(3):
    path = os.path.join(root, f"{i}.png")
    with open(path, "wb") as f:
        f.write(b"preserve wallpaper bytes")
    files.append(path)
    store.add({"id": f"img-{i}", "path": path, "thumbs": {"large": path}})

opened = []
badge_updates = []
dialog = fv.build_favorites_dialog(
    None, store, FakeImages(), opened.append,
    on_remove=lambda: badge_updates.append(len(store)),
)
flow = find_flow(dialog.get_child())
assert flow is not None and len(cards(flow)) == 3

for child in cards(flow):
    tile, heart = parts(child)
    assert not child.get_focusable(), "FlowBoxChild duplicou foco"
    assert tile.get_focusable(), "botão da imagem perdeu foco"
    assert heart.get_focusable(), "botão de desfavoritar inacessível"
    assert heart.get_icon_name() == "koia-heart-filled-symbolic"
    assert heart.get_tooltip_text() == "Remove from favorites"
    assert heart.has_css_class("koia-fav")
    assert heart.get_halign() == Gtk.Align.END
    assert heart.get_valign() == Gtk.Align.START
    assert heart.get_margin_top() == heart.get_margin_end() == 6

# O coração é um segundo botão, NÃO um clique na imagem.
tile0, heart0 = parts(cards(flow)[0])
heart0.emit("clicked")
assert not opened, "clicar no coração abriu a imagem"
assert not store.contains("img-0") and len(store) == 2
assert len(cards(flow)) == 2 and badge_updates == [2]
assert dialog.props.focus_widget is parts(cards(flow)[0])[0]
assert all(os.path.isfile(p) for p in files), "desfavoritar apagou arquivo"
assert len(FavoritesStore(store.path)) == 2, "remoção não persistiu no disco"

# Seta com coração focado entende o índice da imagem, não um item extra.
tile1, heart1 = parts(cards(flow)[0])
dialog.props.focus_widget = heart1
assert fv._card_focado(dialog, flow) is tile1
assert fv._mover_foco(dialog, flow, 1) is parts(cards(flow)[1])[0]

# Remover o último card transfere foco para o anterior.
_, heart2 = parts(cards(flow)[1])
heart2.emit("clicked")
assert len(cards(flow)) == 1 and store.contains("img-1")
assert dialog.props.focus_widget is parts(cards(flow)[0])[0]
assert badge_updates == [2, 1]

# Ao zerar, o diálogo continua aberto com estado vazio.
_, heart1 = parts(cards(flow)[0])
heart1.emit("clicked")
assert len(store) == 0 and badge_updates == [2, 1, 0]
assert isinstance(dialog.get_child(), Adw.StatusPage)
assert dialog.get_child().get_title() == "No favorites yet"
assert not opened
assert all(os.path.isfile(p) for p in files)

# Sem favoritos já na abertura, mesmo estado vazio.
empty = fv.build_favorites_dialog(None, store, FakeImages(), opened.append)
assert isinstance(empty.get_child(), Adw.StatusPage)

# Abrir uma imagem segue separado de desfavoritar.
store.add({"id": "other", "path": files[0], "thumbs": {"large": files[0]}})
open_dialog = fv.build_favorites_dialog(None, store, FakeImages(), opened.append)
open_flow = find_flow(open_dialog.get_child())
tile, _ = parts(cards(open_flow)[0])
# Evita fechar diálogo que nunca foi apresentado na sessão de teste.
real_close = Adw.Dialog.close
Adw.Dialog.close = lambda _dialog: None
try:
    tile.emit("clicked")
finally:
    Adw.Dialog.close = real_close
assert opened and opened[-1]["id"] == "other"
assert store.contains("other"), "abrir imagem removeu dos favoritos"

print("[koia-favorites-heart] coração, foco, remoção e persistência: ok")
