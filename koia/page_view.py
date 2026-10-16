"""Visor de página — grade navegável das páginas de resultados.

Aberto pelo ícone de grade da HeaderBar (▦), mostra uma página inteira
de resultados com a foto que está na janela principal destacada
(``koia-current``) e o foco nela. O rodapé navega: ‹ › passam página a
página (em loop) e o campo de página salta direto pro número digitado —
tudo SEM mexer na janela de trás (as páginas vêm do cache ou da rede
pelo ``fetch`` sem trocar o contexto). Clicar numa foto salta pra ela:
a janela troca a imagem como se o usuário tivesse navegado até lá —
setas/baixar/favoritar seguem normais da nova foto.

As thumbs vêm do MESMO ``ImageLoader`` da janela (cache reaproveitado),
no mesmo molde dos favoritos.
"""

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Gdk", "4.0")
from gi.repository import Adw, Gdk, GLib, Gtk  # noqa: E402

from .favorites_view import (  # noqa: E402
    prender_enter_abre,
    prender_fechamento_por_clique_fora,
    prender_setas,
)
from .image import THUMB_SCALE  # noqa: E402

# lado do card de wallpaper (quadrado) — mesmo tamanho dos outros grids
TILE = 180


def build_page_dialog(parent, page, items, index, images, on_jump,
                      fetch, last_page):
    """Monta o ``Adw.Dialog`` com a grade navegável de páginas.

    - ``page``/``items``/``index``: página que a janela está mostrando
      (abre nela; a foto ``index`` é a destacada).
    - ``images``: ``ImageLoader`` da janela — reusa o cache.
    - ``on_jump``: chamado com ``(page, index)`` da foto escolhida; a
      janela salta pra ela e o diálogo se fecha.
    - ``fetch``: ``(page, on_done, on_error)`` — busca página SEM trocar
      o que a janela mostra (cache primeiro, rede depois).
    - ``last_page``: total de páginas conhecido.
    """
    last_page = max(1, int(last_page or 1))
    page = max(1, min(int(page), last_page))

    dialog = Adw.Dialog(
        title=f"Página {page}",
        content_width=780,
        content_height=640,
    )
    prender_fechamento_por_clique_fora(dialog)

    estado = {
        "page": page,
        "last": last_page,
        # página/foto da JANELA principal — o destaque koia-current só
        # existe quando a grade está mostrando exatamente ela
        "janela_page": page,
        "janela_index": max(0, min(int(index), len(items) - 1)) if items else 0,
        "busy": False,
        "on_jump": on_jump,
    }

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

    scrolled = Gtk.ScrolledWindow()
    scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    scrolled.set_child(flow)
    scrolled.set_vexpand(True)

    # rodapé: [indicador] [‹] [página] [›] — ‹ › em loop, o campo
    # aceita número direto (clampa no intervalo 1..N)
    indicador = Adw.Spinner()
    indicador.set_visible(False)
    btn_prev = Gtk.Button.new_from_icon_name("go-previous-symbolic")
    btn_prev.set_tooltip_text("Página anterior")
    btn_prev.add_css_class("flat")
    btn_next = Gtk.Button.new_from_icon_name("go-next-symbolic")
    btn_next.set_tooltip_text("Página seguinte")
    btn_next.add_css_class("flat")
    spin = Gtk.SpinButton.new_with_range(1, last_page, 1)
    spin.set_tooltip_text("Ir para a página — digite o número e Enter")
    spin.set_width_chars(4)
    rodape = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
    rodape.set_halign(Gtk.Align.CENTER)
    rodape.set_margin_top(6)
    rodape.set_margin_bottom(12)
    for w in (indicador, btn_prev, spin, btn_next):
        rodape.append(w)

    caixa = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
    caixa.append(scrolled)
    caixa.append(rodape)
    toasts = Adw.ToastOverlay()
    toasts.set_child(caixa)
    dialog.set_child(toasts)

    def controles(ligados):
        indicador.set_visible(not ligados)
        for w in (btn_prev, btn_next, spin):
            w.set_sensitive(ligados)

    def ir_para(nova):
        """Troca a página do diálogo (com loop nas pontas)."""
        if estado["busy"]:
            return
        nova = ((int(nova) - 1) % estado["last"]) + 1
        if nova == estado["page"]:
            return
        estado["busy"] = True
        controles(False)
        fetch(
            nova,
            on_done=lambda resultado, p=nova: chegou(p, resultado),
            on_error=errou,
        )

    def chegou(pagina, resultado):
        dados = resultado.get("data") or []
        if not dados:
            errou("Página vazia")
            return
        meta = resultado.get("meta") or {}
        estado["last"] = max(1, int(meta.get("last_page", estado["last"])
                                    or estado["last"]))
        estado["page"] = pagina
        renderizar(pagina, dados)
        spin.set_range(1, estado["last"])
        spin.set_value(pagina)
        dialog.set_title(f"Página {pagina}")
        estado["busy"] = False
        controles(True)

    def errou(erro):
        toasts.add_toast(Adw.Toast.new(
            getattr(erro, "message", str(erro))))
        spin.set_value(estado["page"])   # volta pra página em exibição
        estado["busy"] = False
        controles(True)

    def renderizar(pagina, dados):
        while True:
            filho = flow.get_first_child()
            if filho is None:
                break
            flow.remove(filho)

        card_atual = None
        primeiro = None
        for i, wallpaper in enumerate(dados):
            picture = Gtk.Picture(content_fit=Gtk.ContentFit.COVER)
            picture.set_size_request(TILE, TILE)
            picture.set_can_target(False)   # o clique é do botão

            tile = Gtk.Button()
            tile.add_css_class("flat")
            tile.set_child(picture)
            tile.set_tooltip_text(wallpaper.get("id", str(i + 1)))
            if (pagina == estado["janela_page"]
                    and i == estado["janela_index"]):
                tile.add_css_class("koia-current")
                card_atual = tile
            if primeiro is None:
                primeiro = tile
            tile.connect(
                "clicked",
                lambda _tile, p=pagina, pos=i: escolher(p, pos),
            )
            flow.append(tile)

            images.load(
                wallpaper["thumbs"]["large"],
                lambda tex, pic=picture: pic.set_paintable(tex)
                if tex is not None else None,
                max_side=THUMB_SCALE,
            )

        # foco e rolagem começam na foto da janela (quando a grade é
        # dela); noutra página, no primeiro card
        alvo = card_atual if card_atual is not None else primeiro
        if alvo is not None:
            dialog.props.focus_widget = alvo
        if card_atual is not None:
            GLib.idle_add(_rolar_ate, scrolled, card_atual)

    def escolher(pagina, pos):
        """Fecha o diálogo; pula só quando clicou em OUTRA foto."""
        if not (pagina == estado["janela_page"]
                and pos == estado["janela_index"]):
            estado["on_jump"](pagina, pos)
        dialog.close()

    btn_prev.connect("clicked", lambda _b: ir_para(estado["page"] - 1))
    btn_next.connect("clicked", lambda _b: ir_para(estado["page"] + 1))
    # o campo é "pendente": ‹ › navegam na hora; o número (digitado ou
    # ajustado pelos +/- do próprio campo) só vale com Enter — os +/-
    # não buscam de imediato (fariam o mesmo que ‹ › e confundiam)
    def ir_campo(campo):
        campo.update()               # commita o texto digitado, se houver
        ir_para(int(campo.get_value()))
    spin.connect("activate", ir_campo)

    renderizar(page, items)
    prender_enter_abre(dialog, flow)
    prender_setas(dialog, flow)
    return dialog


def _rolar_ate(scrolled, tile, tentativa=0):
    """Rola a grade até o card atual (centraliza quando dá).

    A alocação só existe depois do layout — o idle pode chegar antes,
    então tenta de novo nas próximas iterações (com teto).
    """
    child = tile.get_parent()          # FlowBoxChild
    if child is None or child.get_allocated_height() == 0:
        if tentativa < 10:
            GLib.idle_add(_rolar_ate, scrolled, tile, tentativa + 1)
        return GLib.SOURCE_REMOVE
    vadj = scrolled.get_vadjustment()
    alvo = child.get_allocation().y - (vadj.get_page_size() - TILE) / 2
    alvo = max(vadj.get_lower(), min(
        alvo, vadj.get_upper() - vadj.get_page_size()))
    vadj.set_value(alvo)
    return GLib.SOURCE_REMOVE
