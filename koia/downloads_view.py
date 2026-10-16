"""Diálogo de downloads — grade dos wallpapers já baixados.

Varre a pasta configurada (``download.folder`` — a mesma do ⤓ e do
aplicar) por imagens e mostra as mais recentes primeiro. As thumbs são
geradas localmente com ``Gdk.Pixbuf`` já reduzidas: nada de textura 4K
na grade. A decodificação roda em thread própria (entrega via
``GLib.idle_add``), então a grade abre na hora e cada thumb entra
quando pronta. Reconstruído a cada abertura, então nunca fica defasado.

Clicar num card abre a imagem na janela principal como ``file://`` — o
``ImageLoader`` sabe ler arquivo local, e aí lixeira/aplicar/favoritar
funcionam normalmente nela.

Cada card também tem um botão de lixeira no canto superior direito da
thumb (sempre visível): apaga o arquivo do disco **com confirmação** —
é apagamento permanente. Os dois botões são irmãos dentro de um
``Gtk.Overlay`` (padrão GTK4 para ação sobreposta em card): cada um
recebe só o clique da sua área, o resto do card continua abrindo a
imagem e o teclado segue igual.
"""

import os
import threading

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Gdk", "4.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Adw, Gdk, GdkPixbuf, GLib, Gtk  # noqa: E402

from .background import (  # noqa: E402
    is_current_background,
    restore_previous_background,
)
from .favorites_view import (  # noqa: E402
    prender_enter_abre,
    prender_fechamento_por_clique_fora,
    prender_setas,
)

# lado do card de wallpaper (quadrado) — mesmo tamanho dos favoritos
TILE = 180

EXTENSOES = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}

# quantas thumbs decodificam ao mesmo tempo — bastante para a grade
# encher rápido, pouco para a CPU ficar brigando consigo mesma
_THUMB_SLOTS = threading.Semaphore(4)


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

    # feedback de apagar dentro do próprio diálogo (o principal fica
    # atrás do Adw.Dialog e o toast não apareceria)
    toasts = Adw.ToastOverlay()

    cards = {}   # caminho -> card Overlay (para tirar da grade)
    for caminho in itens:
        picture = Gtk.Picture(content_fit=Gtk.ContentFit.COVER)
        picture.set_size_request(TILE, TILE)
        picture.set_can_target(False)   # o clique é do botão
        # sem decode aqui: a thumb chega da thread própria quando
        # pronta — o diálogo abre na hora mesmo com arquivo 4K
        _spawn_thumb(caminho, picture)

        tile = Gtk.Button()
        tile.add_css_class("flat")
        tile.set_child(picture)
        tile.set_tooltip_text(os.path.basename(caminho))
        tile.connect(
            "clicked",
            lambda _tile, p=caminho: _open_tile(p, dialog, on_open),
        )

        # lixeira sobreposta no canto da thumb, sempre visível; os dois
        # botões são IRMÃOS dentro do Overlay (padrão GTK4 para ação
        # sobreposta em card): cada um recebe só o clique da sua área —
        # sem truque de gesto — e o resto do card segue abrindo a imagem
        btn_trash = Gtk.Button.new_from_icon_name("user-trash-symbolic")
        btn_trash.add_css_class("flat")
        btn_trash.add_css_class("koia-trash")
        btn_trash.set_tooltip_text("Apagar do disco")
        btn_trash.set_halign(Gtk.Align.END)
        btn_trash.set_valign(Gtk.Align.START)
        btn_trash.set_margin_top(6)
        btn_trash.set_margin_end(6)
        btn_trash.connect(
            "clicked",
            lambda _btn, p=caminho, d=dialog, c=cards, t=toasts:
                _confirmar_e_apagar(p, d, c, flow, t),
        )
        card = Gtk.Overlay()
        card.set_child(tile)
        card.add_overlay(btn_trash)

        cards[caminho] = card
        flow.append(card)

    scrolled = Gtk.ScrolledWindow()
    scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    scrolled.set_child(flow)
    toasts.set_child(scrolled)
    dialog.set_child(toasts)

    # o foco já abre no primeiro card: setas navegam a grade e o
    # Enter tem alvo
    child = flow.get_first_child()
    if child is not None:
        # o foco vai no botão-card de dentro do Overlay
        dialog.props.focus_widget = child.get_child().get_first_child()
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


def _spawn_thumb(caminho, picture):
    """Decodifica a thumb fora da thread principal e entrega no ``picture``.

    Antes todo o arquivo era decodizado na thread principal ANTES de o
    diálogo abrir — a janela congelava com arquivo 4K. Agora o diálogo
    constrói sem esperar decode e cada thumb entra quando pronta. A
    closure segura a referência do ``picture``, então a entrega chega
    segura mesmo se o diálogo já tiver fechado no meio.
    """
    def work():
        with _THUMB_SLOTS:
            tex = _thumb_local(caminho)
        GLib.idle_add(_entregar_thumb, picture, tex)

    threading.Thread(target=work, daemon=True, name="koia-dl-thumb").start()


def _entregar_thumb(picture, tex):
    """Aplica a thumb pronta (roda na thread principal)."""
    if tex is not None:
        picture.set_paintable(tex)
    return GLib.SOURCE_REMOVE


def _open_tile(caminho, dialog, on_open):
    uri = GLib.filename_to_uri(caminho, None)
    wall = {
        "id": os.path.basename(caminho),
        "path": uri,
        "thumbs": {"large": uri},
    }
    on_open(wall)
    dialog.close()


# ------------------------------------------------------------------
# Apagar da grade (com confirmação — apagamento permanente)
# ------------------------------------------------------------------
def _confirmar_e_apagar(caminho, dialog, cards, flow, toasts):
    """Pede confirmação antes de apagar o arquivo do disco.

    Mesmo texto e mesmo cuidado do ⤓-lixeira da janela principal:
    Cancelar é o padrão e “Apagar” é destrutivo.
    """
    nome = os.path.basename(caminho)
    alert = Adw.AlertDialog.new(
        "Apagar o wallpaper?",
        f"“{nome}” será apagado permanentemente do disco.",
    )
    alert.add_response("cancel", "Cancelar")
    alert.add_response("delete", "Apagar")
    alert.set_response_appearance("delete", Adw.ResponseAppearance.DESTRUCTIVE)
    alert.set_default_response("cancel")
    alert.set_close_response("cancel")
    alert.connect(
        "response",
        lambda _alert, resposta: (
            None if resposta != "delete"
            else _apagar(caminho, cards, flow, toasts)
        ),
    )
    alert.present(dialog)


def _apagar(caminho, cards, flow, toasts):
    """Remove o arquivo, tira o card da grade e conta o resultado."""
    nome = os.path.basename(caminho)
    # era o fundo do sistema? precisa saber ANTES de o arquivo sumir
    era_fundo = is_current_background(caminho)
    try:
        os.remove(caminho)
    except OSError as exc:
        toasts.add_toast(Adw.Toast.new(f"Não foi possível apagar: {exc}"))
        return
    card = cards.pop(caminho, None)
    if card is not None:
        child = card.get_parent()          # FlowBoxChild
        if child is not None:
            flow.remove(child)
    # mesma conta do fluxo da janela: se era o wallpaper do sistema,
    # volta para o fundo anterior (ou nada, se não há)
    msg = f"Apagado: {nome}"
    if era_fundo:
        erro_restore, restaurou = restore_previous_background()
        if restaurou:
            msg = "Apagado — fundo do sistema restaurado"
        elif erro_restore:
            msg = f"{erro_restore} · arquivo apagado"
        else:
            msg = "Apagado — sem fundo anterior para restaurar"
    toasts.add_toast(Adw.Toast.new(msg))
