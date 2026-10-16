"""Diálogo de downloads — grade dos wallpapers já baixados.

Varre a pasta configurada (``download.folder`` — a mesma do ⤓ e do
aplicar) por imagens e mostra as mais recentes primeiro. As thumbs são
geradas localmente com ``Gdk.Pixbuf`` já reduzidas: nada de textura 4K
na grade. Reconstruído a cada abertura, então nunca fica defasado.

Clicar num card abre a imagem na janela principal como ``file://`` — o
``ImageLoader`` sabe ler arquivo local, e aí lixeira/aplicar/favoritar
funcionam normalmente nela.
"""

import os

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Gdk", "4.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Adw, Gdk, GdkPixbuf, GLib, Gtk  # noqa: E402

from .favorites_view import (  # noqa: E402
    prender_enter_abre,
    prender_fechamento_por_clique_fora,
    prender_setas,
)

# lado do card de wallpaper (quadrado) — mesmo tamanho dos favoritos
TILE = 180

EXTENSOES = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}


def list_downloads(folder):
    """Arquivos de imagem da pasta, mais recentes primeiro.

    Ignora ``.part`` (temporário de escrita do download) e ocultos.
    """
    try:
        nomes = os.listdir(folder)
    except OSError:
        return []
    itens = []
    for nome in nomes:
        if nome.startswith(".") or nome.endswith(".part"):
            continue
        if os.path.splitext(nome)[1].lower() not in EXTENSOES:
            continue
        caminho = os.path.join(folder, nome)
        if not os.path.isfile(caminho):
            continue
        try:
            mtime = os.path.getmtime(caminho)
        except OSError:
            continue
        itens.append((mtime, caminho))
    itens.sort(reverse=True)
    return [caminho for _mtime, caminho in itens]


def build_downloads_dialog(parent, folder, on_open):
    """Monta o ``Adw.Dialog`` com a grade dos wallpapers baixados.

    - ``folder``: pasta de downloads configurada (lida na abertura).
    - ``on_open``: chamado com o pseudo-wallpaper ``file://`` escolhido;
      a janela principal abre ele e o diálogo se fecha.
    """
    dialog = Adw.Dialog(
        title="Downloads",
        content_width=780,
        content_height=640,
    )
    prender_fechamento_por_clique_fora(dialog)

    itens = list_downloads(folder)
    if not itens:
        dialog.set_child(Adw.StatusPage(
            icon_name="image-x-generic-symbolic",
            title="Nenhum wallpaper baixado ainda",
            description=f"Use o ⤓ para baixar imagens para:\n{folder}",
        ))
        prender_enter_abre(dialog, None)
        prender_setas(dialog, None)
        return dialog

    flow = Gtk.FlowBox()
    flow.set_valign(Gtk.Align.START)
    flow.set_homogeneous(True)
    flow.set_selection_mode(Gtk.SelectionMode.NONE)
    flow.set_min_children_per_line(2)
    flow.set_max_children_per_line(6)
    flow.set_column_spacing(12)
    flow.set_row_spacing(12)
    flow.set_margin_top(18)
    flow.set_margin_bottom(18)
    flow.set_margin_start(18)
    flow.set_margin_end(18)

    for caminho in itens:
        picture = Gtk.Picture(content_fit=Gtk.ContentFit.COVER)
        picture.set_size_request(TILE, TILE)
        picture.set_can_target(False)   # o clique é do botão
        picture.set_paintable(_thumb_local(caminho))

        tile = Gtk.Button()
        tile.add_css_class("flat")
        tile.set_child(picture)
        tile.set_tooltip_text(os.path.basename(caminho))
        tile.connect(
            "clicked",
            lambda _tile, p=caminho: _open_tile(p, dialog, on_open),
        )
        flow.append(tile)

    scrolled = Gtk.ScrolledWindow()
    scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    scrolled.set_child(flow)
    dialog.set_child(scrolled)

    # o foco já abre no primeiro card: setas navegam a grade e o
    # Enter tem alvo
    child = flow.get_first_child()
    if child is not None:
        dialog.props.focus_widget = child.get_child()
    prender_enter_abre(dialog, flow)
    prender_setas(dialog, flow)
    return dialog


def _thumb_local(caminho):
    """``Gdk.Texture`` reduzida do arquivo local (ou ``None``)."""
    try:
        pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(caminho, TILE, TILE)
    except GLib.Error:
        return None
    return Gdk.Texture.new_for_pixbuf(pixbuf)


def _open_tile(caminho, dialog, on_open):
    uri = GLib.filename_to_uri(caminho, None)
    wall = {
        "id": os.path.basename(caminho),
        "path": uri,
        "thumbs": {"large": uri},
    }
    on_open(wall)
    dialog.close()
