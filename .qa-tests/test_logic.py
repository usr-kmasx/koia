#!/usr/bin/env python3
"""Koia — suíte de lógica.

Roda SEM rede e SEM tocar no desktop nem na configuração real: cada
execução cria XDG_* temporários frescos em /tmp/opencode — nada vaza
entre runs, nada sai da pasta temporária. Nada é apresentado na tela.

Quem testa o visual é o usuário, no app de verdade.
"""
import os
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix="koia-qa-", dir="/tmp/opencode")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_TMP, "config")
os.environ["XDG_CONFIG_DIRS"] = os.path.join(_TMP, "config-dirs")
os.environ["XDG_CACHE_HOME"] = os.path.join(_TMP, "cache")
os.environ["XDG_DATA_HOME"] = os.path.join(_TMP, "data")

sys.path.insert(0, "/home/usr/Projects/koia")

import gi  # noqa: E402

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Adw, GdkPixbuf, Gio, GLib, Gtk  # noqa: E402

from koia import background as bg  # noqa: E402
from koia import main as koia_main  # noqa: E402
from koia.background import (  # noqa: E402
    restore_previous_background,
    set_as_background,
)
from koia.config import Settings  # noqa: E402
from koia.downloads_view import build_downloads_dialog, list_downloads  # noqa: E402
from koia.downloader import destination_for, filename_of  # noqa: E402
from koia.favorites import FavoritesStore  # noqa: E402
from koia.favorites_view import TILE, build_favorites_dialog  # noqa: E402
from koia.image import THUMB_SCALE, ImageLoader  # noqa: E402
from koia.window import KoiaWindow  # noqa: E402

TOTAL = {"ok": 0, "falhou": 0}


def secao(titulo):
    print(f"\n=== {titulo} ===")


def check(nome, cond, detalhe=""):
    if cond:
        TOTAL["ok"] += 1
        print(f"  ok    {nome}")
    else:
        TOTAL["falhou"] += 1
        print(f"  FALHOU {nome}  [{detalhe}]")


def wp(ident, pagina, n):
    """Wallpaper fake no formato cru do wallhaven."""
    return {
        "id": f"id{ident}",
        "path": f"http://x/{pagina}/{n}.jpg",
        "thumbs": {"large": f"http://x/thumb/{pagina}/{n}.jpg"},
    }


class FakeAPI:
    def __init__(self):
        self.calls = 0

    def search(self, page=1, on_done=None, on_error=None):
        self.calls += 1
        on_done({
            "data": [wp(f"{page}{i}", page, i) for i in range(3)],
            "meta": {"current_page": page, "last_page": 2, "total": 6},
        })


class FakeImages:
    """Loader sem rede: devolve None (a UI ignora)."""

    def load(self, url, callback, max_side=None, persist=True):
        callback(None)

    def prefetch(self, url):
        pass


def parent_of(root, widget):
    """Procura o container direto do widget em qualquer profundidade."""
    node = root.get_first_child()
    while node is not None:
        child = node.get_first_child()
        while child is not None:
            if child is widget:
                return node
            child = child.get_next_sibling()
        achado = parent_of(node, widget)
        if achado is not None:
            return achado
        node = node.get_next_sibling()
    return None


def index_of(container, widget):
    if container is None:
        return -1
    idx, child = 0, container.get_first_child()
    while child is not None:
        if child is widget:
            return idx
        idx += 1
        child = child.get_next_sibling()
    return -1


# ---------------------------------------------------------------------------
# ambiente
# ---------------------------------------------------------------------------
app = Adw.Application(application_id="com.koia.Qa",
                      flags=Gio.ApplicationFlags.DEFAULT_FLAGS)
settings = Settings()
win = KoiaWindow(app, settings)
win.api = FakeAPI()
# sem rede: a exibição é lógica de estado; o visual é teste manual
win.show_current = lambda: None

# ---------------------------------------------------------------------------
secao("1. store de favoritos (isolado em temp)")
store = FavoritesStore(path=os.path.join(_TMP, "fav-logic.json"))
check("vazio no início", len(store) == 0)
a, b = wp("a", 1, 0), wp("b", 1, 1)
check("toggle vira favorito", store.toggle(a) is True)
check("contains acha", store.contains("ida"))
check("toggle de novo remove", store.toggle(a) is False)
check("não contém mais", not store.contains("ida"))
store.add(a)
store.add(b)
check("len = 2", len(store) == 2)
check("all devolve 2", len(store.all()) == 2)
store.remove("ida")
check("remove de verdade", not store.contains("ida"))
store2 = FavoritesStore(path=os.path.join(_TMP, "fav-logic.json"))
check("persistiu no disco", store2.contains("idb"))
store2.add(wp("b", 9, 9))
check("id duplicado não duplica item", len(store2) == 1)

# ---------------------------------------------------------------------------
secao("2. header: engrenagem à direita, coração à esquerda")
check("config virou engrenagem",
      win.config_button.get_icon_name() == "preferences-system-symbolic",
      win.config_button.get_icon_name())
check("config segue na ação win.preferences",
      win.config_button.get_action_name() == "win.preferences")
check("coração da header usa symbolic",
      win.btn_fav_header.get_icon_name() == "koia-heart-symbolic")
check("coração da header abre favoritos",
      win.btn_fav_header.get_action_name() == "win.show-favorites")
check("downloads usa ícone de imagens",
      win.btn_downloads_header.get_icon_name() == "image-x-generic-symbolic")
check("downloads abre a ação win.show-downloads",
      win.btn_downloads_header.get_action_name() == "win.show-downloads")
pai_conf = parent_of(win.header, win.config_button)
pai_fav = parent_of(win.header, win.btn_fav_header)
pai_dl = parent_of(win.header, win.btn_downloads_header)
check("os três no mesmo fim da barra",
      pai_conf is not None and pai_conf is pai_fav is pai_dl,
      f"conf={pai_conf} fav={pai_fav} dl={pai_dl}")
check("ordem visual [downloads][coração][engrenagem]",
      index_of(pai_dl, win.btn_downloads_header)
      < index_of(pai_fav, win.btn_fav_header)
      < index_of(pai_conf, win.config_button),
      f"dl={index_of(pai_dl, win.btn_downloads_header)} "
      f"fav={index_of(pai_fav, win.btn_fav_header)} "
      f"conf={index_of(pai_conf, win.config_button)}")

# ---------------------------------------------------------------------------
secao("3. favoritar pelo coração flutuante (♡ / S)")
win.load_page(1, index=0)
atual = win.current()
check("página fake carregada (3 itens)",
      atual is not None and len(win.items) == 3)
check("ícone inicial em contorno",
      win.btn_fav.get_icon_name() == "koia-heart-symbolic")
win.toggle_favorite()
check("favoritou no store", win.favorites.contains(atual["id"]))
check("ícone virou preenchido",
      win.btn_fav.get_icon_name() == "koia-heart-filled-symbolic")
check("fav ganhou o vermelho (.koia-fav)",
      win.btn_fav.has_css_class("koia-fav"))
check("tooltip virou Remover", win.btn_fav.get_tooltip_text() == "Removido dos favoritos"
      or win.btn_fav.get_tooltip_text() == "Remover dos favoritos",
      win.btn_fav.get_tooltip_text())
check("badge devolve True", win._refresh_fav_badge() is True)
win.toggle_favorite()
check("desfavoritou de novo", not win.favorites.contains(atual["id"]))
check("ícone voltou ao contorno",
      win.btn_fav.get_icon_name() == "koia-heart-symbolic")
check("vermelho removido ao desfavoritar",
      not win.btn_fav.has_css_class("koia-fav"))
sem_erro = True
win.items = []
win.index = 0
try:
    win.toggle_favorite()
except Exception as exc:  # noqa: BLE001
    sem_erro = False
    print("     ", exc)
check("toggle sem wallpaper não lança", sem_erro)

# ---------------------------------------------------------------------------
secao("4. abrir favorito como página de um item; setas voltam")
win.load_page(1, index=1)
pagina_antes, indice_antes = win.page, win.index
alvo = wp("fav1", 7, 1)
win.show_wallpaper(alvo)
check("current é o favorito", win.current() is alvo)
check("página de um item",
      len(win.items) == 1 and win.page == 1 and win.last_page == 1)
check("contexto de favorito ligado", win._fav_context)
win.go_next()
check("seta devolveu para a busca", not win._fav_context)
check("voltou na página/índice certos",
      win.page == pagina_antes and win.index == indice_antes,
      f"page={win.page} index={win.index}")
check("mesmas imagens (cache de páginas)", len(win.items) == 3)

win.show_wallpaper(alvo)
win.show_wallpaper(wp("fav2", 7, 2))
check("trocar de favorito mantém o retorno",
      win._return_to == (pagina_antes, indice_antes)
      and win.current()["id"] == "idfav2")
win.go_prev()
check("saiu de novo para a busca",
      not win._fav_context and win.page == pagina_antes)

win._drop_page_cache()
win.items = []
win.show_wallpaper(alvo)
win.go_next()
check("sem retorno salvo: recarrega a busca",
      not win._fav_context and len(win.items) == 3)

# ---------------------------------------------------------------------------
secao("5. diálogo de favoritos")
store_vazio = FavoritesStore(path=os.path.join(_TMP, "fav-vazio.json"))
d0 = build_favorites_dialog(win, store_vazio, FakeImages(), lambda _wp: None)
check("vazio mostra StatusPage", isinstance(d0.get_child(), Adw.StatusPage))

store3 = FavoritesStore(path=os.path.join(_TMP, "fav3.json"))
favoritados = [wp("g1", 3, 0), wp("g2", 3, 1), wp("g3", 3, 2)]
for f in favoritados:
    store3.add(f)

abertos = []
d3 = build_favorites_dialog(win, store3, FakeImages(), abertos.append)
check("com favoritos é Adw.Dialog", isinstance(d3, Adw.Dialog))
scrolled = d3.get_child()
check("conteúdo é ScrolledWindow", isinstance(scrolled, Gtk.ScrolledWindow))
grade = scrolled.get_child()
if isinstance(grade, Gtk.Viewport):
    # o ScrolledWindow embrulha quem não rola sozinho num Viewport
    grade = grade.get_child()
cards = []
child = grade.get_first_child()
while child is not None:
    cards.append(child)
    child = child.get_next_sibling()
check("3 cards na grade", len(cards) == 3, f"cards={len(cards)}")
tile = cards[0].get_child()          # FlowBoxChild -> botão do card
picture = tile.get_child()
check(f"card de {TILE}px", picture.get_size_request() == (TILE, TILE),
      str(picture.get_size_request()))
cards[1].get_child().emit("clicked")
check("clique abre o wallpaper certo",
      len(abertos) == 1 and abertos[0]["id"] == "idg2",
      f"abertos={[w['id'] for w in abertos]}")


def achar_gesto_clique(dialogo):
    lista = dialogo.observe_controllers()
    for i in range(lista.get_n_items()):
        ctrl = lista.get_item(i)
        if isinstance(ctrl, Gtk.GestureClick):
            return ctrl
    return None


# clique fora da área fecha (sem botão). O diálogo é apresentado numa
# janela NÃO mapeada: fica invisível, nada aparece na tela
d4 = build_favorites_dialog(win, store3, FakeImages(), abertos.append)
check("diálogo tem gesto de clique", achar_gesto_clique(d4) is not None)
fechou = []
d4.connect("closed", lambda *_: fechou.append(True))
d4.present(win)
achar_gesto_clique(d4).emit("pressed", 1, 9999.0, 9999.0)
check("clique FORA da área fecha o diálogo", bool(fechou))

d5 = build_favorites_dialog(win, store3, FakeImages(), abertos.append)
fechou5 = []
d5.connect("closed", lambda *_: fechou5.append(True))
d5.present(win)
achar_gesto_clique(d5).emit("pressed", 1, 0.0, 0.0)
check("clique DENTRO da área NÃO fecha", not fechou5, str(fechou5))
d5.close()

dv = build_favorites_dialog(win, store_vazio, FakeImages(), lambda _wp: None)
fechou_vazio = []
dv.connect("closed", lambda *_: fechou_vazio.append(True))
dv.present(win)
achar_gesto_clique(dv).emit("pressed", 1, 9999.0, 9999.0)
check("com lista vazia o clique fora também fecha", bool(fechou_vazio))

# Enter: abre o card focado — ou o primeiro, se nada focado
from koia.favorites_view import _ativa_enter  # noqa: E402

d6 = build_favorites_dialog(win, store3, FakeImages(), abertos.append)
check("foco inicial no primeiro card",
      d6.props.focus_widget is not None
      and d6.props.focus_widget.get_tooltip_text() == "idg1",
      str(d6.props.focus_widget))
grade6 = d6.get_child().get_child()
if isinstance(grade6, Gtk.Viewport):
    grade6 = grade6.get_child()
card2 = grade6.get_first_child().get_next_sibling().get_child()

d6.props.focus_widget = card2
abertos_antes = len(abertos)
check("Enter com card focado abre ESSE card",
      _ativa_enter(d6, grade6) is True
      and len(abertos) == abertos_antes + 1
      and abertos[-1]["id"] == "idg2",
      f"abertos={[w['id'] for w in abertos[abertos_antes:]]}")

d6.props.focus_widget = d6.get_child()   # ScrolledWindow: sem card focado
abertos_antes = len(abertos)
check("Enter sem card focado abre o primeiro",
      _ativa_enter(d6, grade6) is True
      and len(abertos) == abertos_antes + 1
      and abertos[-1]["id"] == "idg1",
      f"abertos={[w['id'] for w in abertos[abertos_antes:]]}")

check("Enter em diálogo vazio não faz nada",
      _ativa_enter(d0, None) is False)

# setas movem o foco entre os cards (com clamp nas pontas)
from koia.favorites_view import _colunas, _mover_foco  # noqa: E402

check("_colunas conta a linha inteira", _colunas(grade6) == 3,
      f"colunas={_colunas(grade6)}")

d7 = build_favorites_dialog(win, store3, FakeImages(), lambda _wp: None)
grade7 = d7.get_child().get_child()
if isinstance(grade7, Gtk.Viewport):
    grade7 = grade7.get_child()
cartoes = []
_child = grade7.get_first_child()
while _child is not None:
    cartoes.append(_child.get_child())
    _child = _child.get_next_sibling()

d7.props.focus_widget = cartoes[0]
check("seta → move o foco pro próximo card",
      _mover_foco(d7, grade7, 1) is cartoes[1])
check("seta ← volta", _mover_foco(d7, grade7, -1) is cartoes[0])
check("na ponta esquerda para (não enrola)",
      _mover_foco(d7, grade7, -1) is cartoes[0])
d7.props.focus_widget = cartoes[2]
check("na ponta direita também para",
      _mover_foco(d7, grade7, 4) is cartoes[2])
d7.props.focus_widget = d7.get_child()   # ScrolledWindow: sem card focado
check("sem card focado, seta foca o primeiro",
      _mover_foco(d7, grade7, 1) is cartoes[0])
check("sem grade (diálogo vazio) não há o que mover",
      _mover_foco(d0, None, 1) is None)

# ---------------------------------------------------------------------------
secao("6. CSS embutido")
css = koia_main.CSS
check("tem .koia-trash (lixeira)", ".koia-trash" in css)
check("tem .koia-downloaded (monitor)", ".koia-downloaded" in css)
check("tem .koia-fav (coração vermelho)", ".koia-fav" in css)
check("sem .koia-config (classe morta)", ".koia-config" not in css)

# ---------------------------------------------------------------------------
secao("7. ícones de coração symbolic")
icon_dir = os.path.join(os.path.dirname(koia_main.__file__), "data", "icons")
check("koia-heart-symbolic.svg existe",
      os.path.exists(os.path.join(icon_dir, "koia-heart-symbolic.svg")))
check("koia-heart-filled-symbolic.svg existe",
      os.path.exists(os.path.join(icon_dir, "koia-heart-filled-symbolic.svg")))
check("nomes antigos (pretos) removidos",
      not os.path.exists(os.path.join(icon_dir, "koia-heart.svg"))
      and not os.path.exists(os.path.join(icon_dir, "koia-heart-filled.svg")))

# ---------------------------------------------------------------------------
secao("8. atalhos no app real")
app_real = koia_main.KoiaApp()
app_real._install_accels()
check("favoritar SEM atalho (S removido)",
      app_real.get_accels_for_action("win.toggle-favorite") == [],
      str(app_real.get_accels_for_action("win.toggle-favorite")))
check("favoritos sem atalho",
      app_real.get_accels_for_action("win.show-favorites") == [],
      str(app_real.get_accels_for_action("win.show-favorites")))
check("downloads sem atalho",
      app_real.get_accels_for_action("win.show-downloads") == [],
      str(app_real.get_accels_for_action("win.show-downloads")))
check("config segue Ctrl+,",
      app_real.get_accels_for_action("win.preferences") == ["<Control>comma"],
      str(app_real.get_accels_for_action("win.preferences")))
check("baixar/apagar sem atalho",
      app_real.get_accels_for_action("win.download") == [])
check("tela cheia segue f",
      app_real.get_accels_for_action("win.fullscreen") == ["f"])

# ---------------------------------------------------------------------------
secao("9. ⤓ vira lixeira vermelha (com confirmação)")
pasta_dl = tempfile.mkdtemp(prefix="koia-dl-", dir="/tmp/opencode")
settings.set("download.folder", pasta_dl)
win.load_page(1, index=0)
dest = os.path.join(pasta_dl, "0.jpg")
check("sem arquivo: ícone de download",
      win.btn_dl.get_icon_name() == "document-save-symbolic"
      and not win.btn_dl.has_css_class("koia-trash"),
      win.btn_dl.get_icon_name())
with open(dest, "wb") as fh:
    fh.write(b"fake")
win._refresh_download_badge()
check("com arquivo: vira lixeira",
      win.btn_dl.get_icon_name() == "user-trash-symbolic"
      and win.btn_dl.has_css_class("koia-trash"))
check("tooltip: Apagar do disco",
      win.btn_dl.get_tooltip_text() == "Apagar do disco")
win.start_download()
check("clique NÃO apaga sem confirmar", os.path.exists(dest))
win._on_delete_response("cancel", dest, "0.jpg")
check("cancelar mantém o arquivo", os.path.exists(dest))
win._on_delete_response("delete", dest, "0.jpg")
check("confirmar apaga de verdade", not os.path.exists(dest))
check("volta ao ícone de download",
      win.btn_dl.get_icon_name() == "document-save-symbolic"
      and not win.btn_dl.has_css_class("koia-trash"))

# ---------------------------------------------------------------------------
secao("10. monitor verde só quando o atual é o aplicado")
with open(dest, "wb") as fh:
    fh.write(b"fake")
win._applied_path = dest
win._refresh_apply_badge()
check("verde quando o da tela é o aplicado",
      win.btn_apply.has_css_class("koia-downloaded"))
win.go_next()
win._refresh_apply_badge()
check("branco em imagem diferente",
      not win.btn_apply.has_css_class("koia-downloaded"))
win.go_prev()
os.remove(dest)
win._refresh_apply_badge()
check("branco se o aplicado sumiu do disco",
      not win.btn_apply.has_css_class("koia-downloaded"))
win._applied_path = None

# ---------------------------------------------------------------------------
secao("11. fundo anterior (nunca toca no sistema)")
estado = os.path.join(_TMP, "bg-estado.json")
check("restaurar sem estado = (None, False)",
      restore_previous_background(state_path=estado) == (None, False))
bg._push_previous("file:///nao/existe-fundo.jpg", estado)
check("anterior inexistente = (None, False), não aplica nada",
      restore_previous_background(state_path=estado) == (None, False))
check("estado consumido", bg._load_state(estado) == [])
bg._push_previous("file:///a.jpg", estado)
bg._push_previous("file:///a.jpg", estado)
check("pilha não duplica o topo", bg._load_state(estado) == ["file:///a.jpg"])
bg._push_previous("file:///b.jpg", estado)
check("pilha na ordem",
      bg._load_state(estado) == ["file:///a.jpg", "file:///b.jpg"])
check("pop devolve o último", bg._pop_previous(estado) == "file:///b.jpg")
check("set_as_background com arquivo inexistente vira mensagem",
      set_as_background("/nao/existe.jpg") is not None)
check("arquivo nosso NÃO é o fundo do sistema",
      bg.is_current_background(dest) is False)
uri = bg.get_current_uri()
check("get_current_uri devolve str ou None",
      uri is None or isinstance(uri, str), repr(uri))

# ---------------------------------------------------------------------------
secao("12. destino do download")
check("destination_for usa o basename do path",
      destination_for(wp("z", 1, 23), "/pasta") == "/pasta/23.jpg",
      destination_for(wp("z", 1, 23), "/pasta"))
check("filename_of", filename_of(wp("z", 1, 23)) == "23.jpg")

# ---------------------------------------------------------------------------
secao("13. filtros e cache de páginas")
calls = win.api.calls
win.load_page(1, index=0)
check("página veio do cache, sem rede", win.api.calls == calls,
      f"calls={win.api.calls} antes={calls}")
settings.set("search.q", "gato")
check("filtro novo refaz a busca", win.api.calls == calls + 1,
      f"calls={win.api.calls}")
check("páginas do filtro antigo descartadas", len(win._pages) <= 1,
      f"paginas={len(win._pages)}")
win.load_page(2)
check("página 2 guardada", 2 in win._pages)
calls = win.api.calls
win.load_page(1)
check("página 1 voltou do cache (mesmas imagens)",
      win.api.calls == calls and len(win.items) == 3,
      f"calls={win.api.calls} antes={calls}")
settings.set("search.q", "")

# ---------------------------------------------------------------------------
secao("14. settings")
s2 = Settings()
check("get devolve o padrão",
      s2.get("appearance.color-scheme") == "default")
s2.set("appearance.color-scheme", "dark")
check("set grava e relê", Settings().get("appearance.color-scheme") == "dark")
s2.set("cache.max-mb", "abc")
check("get_int tolera lixo e devolve o padrão",
      Settings().get_int("cache.max-mb", 100) == 100)

# ---------------------------------------------------------------------------
secao("15. ação abrir favoritos não lança em janela não mapeada")
acao = win.lookup_action("show-favorites")
check("ação win.show-favorites existe", acao is not None)
sem_erro = True
try:
    acao.activate(None)
except Exception as exc:  # noqa: BLE001
    sem_erro = False
    print("     ", exc)
check("ativar a ação não lança exceção", sem_erro)

# ---------------------------------------------------------------------------
secao("16. diálogo de downloads (pasta local, sem rede)")


def png_minimo(caminho, cor):
    pix = GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, False, 8, 8, 8)
    pix.fill(cor)
    pix.savev(caminho, "png", [], [])


pasta_gal = tempfile.mkdtemp(prefix="koia-gal-", dir="/tmp/opencode")
png_minimo(os.path.join(pasta_gal, "antigo.png"), 0xFF0000FF)
png_minimo(os.path.join(pasta_gal, "meio.png"), 0x00FF00FF)
png_minimo(os.path.join(pasta_gal, "novo.png"), 0x0000FFFF)
os.utime(os.path.join(pasta_gal, "antigo.png"), (1000, 1000))
os.utime(os.path.join(pasta_gal, "meio.png"), (2000, 2000))
os.utime(os.path.join(pasta_gal, "novo.png"), (3000, 3000))
with open(os.path.join(pasta_gal, "metade.png.part"), "wb") as fh:
    fh.write(b"x")
with open(os.path.join(pasta_gal, "notas.txt"), "w") as fh:
    fh.write("x")
with open(os.path.join(pasta_gal, ".oculto.png"), "wb") as fh:
    fh.write(b"x")

lista = list_downloads(pasta_gal)
check("lista só imagens, sem .part/texto/oculto",
      [os.path.basename(p) for p in lista]
      == ["novo.png", "meio.png", "antigo.png"],
      str([os.path.basename(p) for p in lista]))

pasta_vazia = tempfile.mkdtemp(prefix="koia-gal0-", dir="/tmp/opencode")
dvazio = build_downloads_dialog(win, pasta_vazia, lambda _wp: None)
check("pasta vazia mostra StatusPage",
      isinstance(dvazio.get_child(), Adw.StatusPage))

dgal = build_downloads_dialog(win, pasta_gal, lambda _wp: None)
check("com imagens o conteúdo é ScrolledWindow",
      isinstance(dgal.get_child(), Gtk.ScrolledWindow))
grade = dgal.get_child().get_child()
if isinstance(grade, Gtk.Viewport):
    grade = grade.get_child()
cards = []
child = grade.get_first_child()
while child is not None:
    cards.append(child)
    child = child.get_next_sibling()
check("3 cards na grade de downloads", len(cards) == 3, f"cards={len(cards)}")
check("thumb local carregada (paintable não nulo)",
      cards[0].get_child().get_child().get_paintable() is not None)
check("foco inicial no primeiro card dos downloads",
      dgal.props.focus_widget is not None
      and dgal.props.focus_widget.get_tooltip_text() == "novo.png",
      str(dgal.props.focus_widget))

# as setas também estão ligadas nos downloads
dgal4 = build_downloads_dialog(win, pasta_gal, lambda _wp: None)
grade4 = dgal4.get_child().get_child()
if isinstance(grade4, Gtk.Viewport):
    grade4 = grade4.get_child()
dgal4.props.focus_widget = grade4.get_first_child().get_child()
check("downloads: seta → move o foco entre os cards",
      _mover_foco(dgal4, grade4, 1)
      is grade4.get_first_child().get_next_sibling().get_child())

# clique abre o arquivo na janela principal como file://
dgal2 = build_downloads_dialog(win, pasta_gal, win.show_wallpaper)
grade2 = dgal2.get_child().get_child()
if isinstance(grade2, Gtk.Viewport):
    grade2 = grade2.get_child()
grade2.get_first_child().get_child().emit("clicked")
atual = win.current()
check("clique abriu o wallpaper local (file://, mais recente primeiro)",
      atual is not None and atual["path"].startswith("file://")
      and atual["path"].endswith("novo.png"),
      atual["path"] if atual else "None")
check("thumbs apontam pro mesmo file://",
      atual is not None and atual["thumbs"]["large"] == atual["path"])
check("entrou no mesmo contexto de visualização", win._fav_context)

# loader real lê file:// sem rede
loader = ImageLoader(os.path.join(_TMP, "cache-img"),
                     max_bytes=10 * 1024 * 1024)
uri_novo = GLib.filename_to_uri(os.path.join(pasta_gal, "novo.png"), None)
tex = loader._load_blocking(uri_novo, THUMB_SCALE, False)
check("loader leu file:// (textura não nula)", tex is not None)
check("persist=False não gravou nada em disco",
      not os.path.exists(loader.cache_path(uri_novo)))
tex2 = loader._load_blocking(uri_novo, THUMB_SCALE, True)
check("persist=True gravou a cópia no cache de thumbs",
      tex2 is not None and os.path.exists(loader.cache_path(uri_novo)))

# ---------------------------------------------------------------------------
print()
print(f"RESULTADO: {TOTAL['ok']} passaram, {TOTAL['falhou']} falharam")
sys.exit(1 if TOTAL["falhou"] else 0)
