"""Diálogo de favoritos — grade de thumbs dos wallpapers salvos.

Reconstruído a cada abertura, então nunca fica defasado em relação ao
♡ da barra flutuante. Os cards usam o MESMO ``ImageLoader`` da janela
principal, então as thumbs vêm do cache (ou são gravadas lá, com o
mesmo teto de espaço).
"""

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Gdk", "4.0")
from gi.repository import Adw, Gdk, Gtk  # noqa: E402

from .i18n import t  # noqa: E402
from .image import THUMB_SCALE  # noqa: E402

# lado do card de wallpaper (quadrado)
TILE = 180


def build_favorites_dialog(parent, favorites, images, on_open):
    """Monta o ``Adw.Dialog`` com a grade de favoritos.

    - ``favorites``: ``FavoritesStore`` (lido na hora da construção).
    - ``images``: ``ImageLoader`` da janela principal — reusa o cache.
    - ``on_open``: chamado com o wallpaper escolhido; a janela principal
      abre ele e o diálogo se fecha.
    """
    dialog = Adw.Dialog(
        title=t("Favorites"),
        content_width=780,
        content_height=640,
    )

    # clicar no fundo escurecido — FORA da área do diálogo — fecha; sem
    # botão (Esc já fecha de fábrica)
    prender_fechamento_por_clique_fora(dialog)

    items = favorites.all()
    if not items:
        dialog.set_child(Adw.StatusPage(
            icon_name="koia-heart-symbolic",
            title=t("No favorites yet"),
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

    for wallpaper in items:
        picture = Gtk.Picture(content_fit=Gtk.ContentFit.COVER)
        picture.set_size_request(TILE, TILE)
        picture.set_can_target(False)   # o clique é do botão

        tile = Gtk.Button()
        tile.add_css_class("flat")
        tile.set_child(picture)
        tile.set_tooltip_text(wallpaper["id"])
        tile.connect(
            "clicked",
            lambda _tile, wp=wallpaper: _open_tile(wp, dialog, on_open),
        )
        flow.append(tile)

        images.load(
            wallpaper["thumbs"]["large"],
            lambda tex, pic=picture: pic.set_paintable(tex)
            if tex is not None else None,
            max_side=THUMB_SCALE,
        )

    scrolled = Gtk.ScrolledWindow()
    scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    scrolled.set_child(flow)
    dialog.set_child(scrolled)

    # o foco já abre no primeiro card: setas navegam a grade e o
    # Enter tem alvo
    primeiro = _primeiro_card(flow)
    if primeiro is not None:
        dialog.props.focus_widget = primeiro
    prender_enter_abre(dialog, flow)
    prender_setas(dialog, flow)
    return dialog


def _open_tile(wallpaper, dialog, on_open):
    on_open(wallpaper)
    dialog.close()


def prender_fechamento_por_clique_fora(dialog):
    """Faz o clique no fundo escurecido (FORA da área do diálogo) fechar.

    Sem botão de fechar: Esc já fecha de fábrica. O gesto fica em
    CAPTURE para ver todos os cliques; o teste de coordenadas dentro de
    ``_on_outside_press`` descarta os que caem na área do conteúdo.
    """
    gesto = Gtk.GestureClick()
    gesto.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
    gesto.connect("pressed", _on_outside_press, dialog)
    dialog.add_controller(gesto)


def prender_setas(dialog, flow):
    """Setas movem o foco entre os cards da grade (nos dois diálogos).

    O ``Gtk.FlowBox`` navega por SELEÇÃO — com ``selection_mode=NONE``
    as setas não fazem nada —, então o foco é movido à mão. O
    controlador fica em CAPTURE e reivindica as teclas: elas nunca
    borbulham até a janela principal, cujos atalhos Left/Right
    trocam a imagem atrás do diálogo.
    """
    controlador = Gtk.EventControllerKey()
    controlador.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
    controlador.connect("key-pressed", _on_key_pressed, dialog, flow)
    dialog.add_controller(controlador)


_DESLOCAMENTOS = {
    Gdk.KEY_Left: -1,
    Gdk.KEY_Right: 1,
}


def _on_key_pressed(_controlador, keyval, _keycode, _mods, dialog, flow):
    if flow is None:
        return False                    # vazio: deixa passar
    deslocamento = _DESLOCAMENTOS.get(keyval)
    if deslocamento is None and keyval in (Gdk.KEY_Up, Gdk.KEY_Down):
        colunas = _colunas(flow)
        deslocamento = -colunas if keyval == Gdk.KEY_Up else colunas
    if deslocamento is not None:
        _mover_foco(dialog, flow, deslocamento)
        return True                     # reivindica antes da janela
    if keyval == Gdk.KEY_space:
        # com card focado o próprio botão trata o Space; fora de um
        # botão, consome para o atalho "próxima imagem" da janela não
        # disparar atrás do diálogo
        raiz = dialog.get_root()
        foco = raiz.get_focus() if raiz is not None \
            else dialog.props.focus_widget
        if not isinstance(foco, Gtk.Button):
            return True
    return False


def _mover_foco(dialog, flow, deslocamento):
    """Move o foco entre os cards; nas pontas para (não enrola).

    Devolve o card que recebeu o foco (ou ``None`` se não há cards).
    """
    cartoes = _cartoes(flow)
    if not cartoes:
        return None
    atual = _card_focado(dialog, flow)
    try:
        pos = cartoes.index(atual)
    except ValueError:
        pos = None
    if pos is None:
        alvo = cartoes[0]
    else:
        alvo = cartoes[max(0, min(pos + deslocamento, len(cartoes) - 1))]
    alvo.grab_focus()
    return alvo


def _card_focado(dialog, flow):
    raiz = dialog.get_root()
    foco = raiz.get_focus() if raiz is not None else dialog.props.focus_widget
    for cartao in _cartoes(flow):
        if cartao is foco:
            return cartao
    return None


def _botao_card(flow_child):
    """O botão-card de dentro de um filho do FlowBox.

    Nos favoritos o filho É o botão; na grade de downloads é um
    ``Gtk.Overlay`` (botão-card por baixo, lixeira por cima) — em
    ambos resolve ao botão que abre a imagem.
    """
    filho = flow_child.get_child()
    if isinstance(filho, Gtk.Overlay):
        return filho.get_first_child()
    return filho


def _cartoes(flow):
    """Botões-card da grade, na ordem."""
    cartoes = []
    if flow is None:
        return cartoes
    child = flow.get_first_child()
    while child is not None:
        botao = _botao_card(child)
        if botao is not None:
            cartoes.append(botao)
        child = child.get_next_sibling()
    return cartoes


def _colunas(flow):
    """Quantas colunas a grade tem agora (conta a primeira linha)."""
    primeiro = flow.get_first_child() if flow is not None else None
    if primeiro is None:
        return 1
    y0 = primeiro.get_allocation().y
    n = 0
    child = flow.get_first_child()
    while child is not None and child.get_allocation().y == y0:
        n += 1
        child = child.get_next_sibling()
    return max(n, 1)


def prender_enter_abre(dialog, flow):
    """Enter/KP_Enter abre o card focado — ou o primeiro, se nada focado.

    Os botões do GTK4 já ativam com Enter quando têm foco; este atalho
    cobre o resto (foco no ScrolledWindow, por exemplo). Sem fogo
    duplo: se o botão focalizado consumir a tecla, o evento não
    borbulha até aqui.
    """
    controlador = Gtk.ShortcutController()
    for tecla in ("Return", "KP_Enter"):
        controlador.add_shortcut(Gtk.Shortcut(
            trigger=Gtk.ShortcutTrigger.parse_string(tecla),
            action=Gtk.CallbackAction.new(
                lambda _c, _args, d=dialog, f=flow: _ativa_enter(d, f)),
        ))
    dialog.add_controller(controlador)


def _ativa_enter(dialog, flow):
    raiz = dialog.get_root()
    foco = raiz.get_focus() if raiz is not None else dialog.props.focus_widget
    if isinstance(foco, Gtk.Button):
        foco.emit("clicked")
        return True
    primeiro = _primeiro_card(flow)
    if primeiro is not None:
        primeiro.emit("clicked")
        return True
    return False


def _primeiro_card(flow):
    """Primeiro botão-card da grade (ou ``None``)."""
    if flow is None:
        return None
    child = flow.get_first_child()
    if child is None:
        return None
    return _botao_card(child)   # FlowBoxChild -> botão (via Overlay, se houver)


def _on_outside_press(_gesto, _n_press, x, y, dialog):
    """Fecha só quando o clique caiu FORA da área do diálogo."""
    filho = dialog.get_child()
    if filho is None:
        dialog.close()
        return
    origem_x, origem_y = _posicao_no_dialogo(dialog, filho)
    aloc = filho.get_allocation()
    dentro = (origem_x <= x <= origem_x + aloc.width
              and origem_y <= y <= origem_y + aloc.height)
    if not dentro:
        dialog.close()


def _posicao_no_dialogo(dialog, widget):
    """Posição do widget em coordenadas do diálogo: no GTK4 a alocação
    de cada widget é relativa ao pai, então sobe a cadeia somando."""
    x = y = 0
    node = widget
    while node is not None and node is not dialog:
        aloc = node.get_allocation()
        x += aloc.x
        y += aloc.y
        node = node.get_parent()
    return x, y
