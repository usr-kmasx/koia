#!/usr/bin/env python3
"""Paridade de idioma — todo texto de UI tem entrada no pt-BR.

O código usa o INGLÊS como língua-fonte: os literais de ``t("...")`` (e
os rótulos das tabelas ``SORTINGS``/``ORDERS``/``TOP_RANGES``) são as
chaves, e o dicionário ``PT_BR`` do ``koia/i18n.py`` traz o português.
Varre a árvore por AST e falha quando:

  1. um ``t("...")`` não tem entrada no pt-BR   → tradução esquecida;
  2. uma chave do dicionário sumiu do código    → tradução morta;
  3. uma tabela de rótulos não traduz;
  4. a opção de idioma não fecha o painel entre "Tema" e "Restaurar
     padrões";
  5. os nomes nativos das línguas não saem intactos;
  6. o tray GTK3 deixa de dividir o módulo de idioma com o app;
  7. trocar o idioma não reconstrói a janela mantendo o estado.

Não há rede e nenhuma janela é apresentada na tela.
"""
import ast
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from koia import config  # noqa: E402
from koia import i18n  # noqa: E402
from koia.i18n import IDIOMAS, PADRAO, PT_BR, decimal, num, set_idioma, t  # noqa: E402

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PACOTE = os.path.join(RAIZ, "koia")

# tabelas cujos rótulos passam por t() no ponto de uso (build_preferences)
TABELAS = (config.SORTINGS, config.ORDERS, config.TOP_RANGES)
NOMES_TABELAS = {"SORTINGS", "ORDERS", "TOP_RANGES"}


def literais_t():
    """Todos os ``t("...")`` da árvore, como o AST os entende.

    O AST já concatena literais adjacentes, então a chave que o teste
    enxerga é EXATAMENTA a que ``t()`` recebe em execução — a forma
    partida em duas linhas do dicionário não passa por aqui.

    Só passa argumento variável quem lê de ``SORTINGS``/``ORDERS``/
    ``TOP_RANGES``: é a única forma do rótulo não ser um literal na
    chamada, e a tabela é conferida à parte (``TABELAS``).
    """
    achados = set()
    for nome in sorted(os.listdir(PACOTE)):
        if not nome.endswith(".py") or nome == "i18n.py":
            continue
        caminho = os.path.join(PACOTE, nome)
        with open(caminho, encoding="utf-8") as fh:
            arvore = ast.parse(fh.read(), filename=caminho)

        pais = {}
        for no in ast.walk(arvore):
            for filho in ast.iter_child_nodes(no):
                pais[filho] = no

        def vem_de_tabela(no):
            # o elt da comprehension NÃO é filho do nó comprehension, então
            # sobe até a lista e olha os geradores dela
            atual = no
            while atual in pais:
                atual = pais[atual]
                if isinstance(atual, (ast.ListComp, ast.SetComp,
                                      ast.DictComp, ast.GeneratorExp)):
                    for comp in atual.generators:
                        if isinstance(comp.iter, ast.Name) and \
                                comp.iter.id in NOMES_TABELAS:
                            return True
            return False

        for no in ast.walk(arvore):
            if not isinstance(no, ast.Call) or \
                    not isinstance(no.func, ast.Name) or no.func.id != "t":
                continue
            for arg in no.args:
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    achados.add((arg.value, nome, no.lineno))
                elif not vem_de_tabela(arg):
                    raise AssertionError(
                        f"{nome}:{no.lineno} — t() com argumento que não é "
                        "literal nem rótulo de tabela; isso passa em "
                        "inglês sem tradução"
                    )
    return achados


def preorder(widget):
    """Percorre os widgets em ordem de documento (DFS).

    Os ``AdwGizmo``/``AdwBreakpointBin`` internos do libadwaita
    reapresentam o MESMO widget em mais de um lugar da árvore, então o
    conjunto de visitados é obrigatório — sem ele o passeio entra em
    ciclo e nunca termina. ``vivos`` segura os wrappers: ``id()`` só
    é estável enquanto o wrapper tem referência.
    """
    vistos = set()
    vivos = []
    pilha = [widget]
    while pilha:
        atual = pilha.pop()
        if atual is None or id(atual) in vistos:
            continue
        vistos.add(id(atual))
        vivos.append(atual)
        yield atual
        irmaos = []
        filho = atual.get_first_child()
        while filho is not None:
            irmaos.append(filho)
            filho = filho.get_next_sibling()
        pilha.extend(reversed(irmaos))


# ---------------------------------------------------------------------------
# 1 e 2 — paridade estática
# ---------------------------------------------------------------------------
def teste_paridade():
    achados = literais_t()
    literais = {texto for texto, _, _ in achados}
    rotulos = {rotulo for tabela in TABELAS for _, rotulo in tabela}
    usados = literais | rotulos

    faltando = sorted(usados - set(PT_BR))
    assert not faltando, (
        "sem entrada no pt-BR (a tela ficaria em inglês):\n  " +
        "\n  ".join(repr(x) for x in faltando)
    )

    mortas = sorted(set(PT_BR) - usados)
    assert not mortas, (
        "chaves mortas — o texto em inglês mudou e a tradução ficou órfã:\n  " +
        "\n  ".join(repr(x) for x in mortas)
    )

    for chave, valor in PT_BR.items():
        assert isinstance(valor, str) and valor, f"valor inválido em {chave!r}"

    print(f"[i18n] {len(literais)} literais t() + {len(rotulos)} rótulos de "
          f"tabela = {len(usados)} textos, {len(PT_BR)} traduções")


# ---------------------------------------------------------------------------
# 3 — comportamento do tradutor
# ---------------------------------------------------------------------------
def teste_tradutor():
    assert PADRAO == "en-US", "o inglês é a língua-fonte e o padrão"
    assert IDIOMAS[0][0] == PADRAO, "o idioma padrão deve ser o primeiro do menu"
    assert config.DEFAULTS["ui.language"] == PADRAO, "DEFAULTS fora de sincronia"

    set_idioma("en-US")
    assert t("Cancel") == "Cancel", "em inglês t() devolve o próprio texto"
    assert t("texto sem tradução") == "texto sem tradução", "fallback quebra"

    set_idioma("pt-BR")
    assert t("Cancel") == "Cancelar"
    assert t("Restore defaults") == "Restaurar padrões"
    assert t("texto sem tradução") == "texto sem tradução", \
        "chave desconhecida deve cair no inglês, nunca estourar"

    # um texto com placeholder precisa preservar a ordem dos %s
    assert t("Deleted: %s") % "a.png" == "Apagado: a.png"
    assert t("End of results — %s wallpapers") % num(1234567) == \
        "Fim dos resultados — 1.234.567 wallpapers"
    assert num(1234567) == "1.234.567" and decimal("12.3 MB") == "12,3 MB"

    set_idioma("en-US")
    assert num(1234567) == "1,234,567" and decimal("12.3 MB") == "12.3 MB"

    set_idioma("xx-XX")   # código desconhecido cai no padrão
    assert i18n.get_idioma() == PADRAO
    set_idioma("en-US")
    print("[i18n] tradutor: en-US, pt-BR, fallback e formatadores ok")


# ---------------------------------------------------------------------------
# 4 — painel de configurações construído nos dois idiomas
# ---------------------------------------------------------------------------
def teste_painel():
    import gi
    gi.require_version("Gtk", "4.0")
    gi.require_version("Adw", "1")
    from gi.repository import Adw, Gio, Gtk

    Gtk.init()
    Adw.init()

    tmp = tempfile.mkdtemp(prefix="koia-i18n-")
    app = Adw.Application(application_id="org.koia.I18nTest",
                          flags=Gio.ApplicationFlags.NON_UNIQUE)
    app.register()

    # largada do app: quem liga o idioma é o Settings, ANTES de existir
    # qualquer widget — um Settings novo relê o arquivo e volta ao idioma
    caminho = os.path.join(tmp, "largada.ini")
    set_idioma(PADRAO)
    primeiros = config.Settings(path=caminho)
    assert i18n.get_idioma() == PADRAO, "DEFAULTS não é o en-US"
    primeiros.set("ui.language", "pt-BR", notify=False)
    set_idioma(PADRAO)                       # simula outro processo subindo
    assert config.Settings(path=caminho) is not None
    assert i18n.get_idioma() == "pt-BR", "Settings não reergueu o idioma salvo"
    set_idioma(PADRAO)

    for idioma, titulo_reset in (
        ("en-US", "Restore defaults"),
        ("pt-BR", "Restaurar padrões"),
    ):
        settings = config.Settings(path=os.path.join(tmp, f"s-{idioma}.ini"))
        set_idioma(idioma)
        # transient_for nunca é mostrado: build_preferences não apresenta
        dialogo = config.build_preferences(Gtk.Window(), settings)

        # o idioma é uma LINHA (formato do "Restaurar padrões"), não um
        # grupo com título — e fecha o painel
        linhas = [w.get_title() for w in preorder(dialogo)
                  if isinstance(w, Adw.PreferencesRow)]
        for esperado in (t("Theme"), t("Language"), titulo_reset):
            assert esperado in linhas, f"{esperado!r} ausente em {idioma}"

        pos_tema = linhas.index(t("Theme"))
        pos_idioma = linhas.index(t("Language"))
        pos_reset = linhas.index(titulo_reset)
        assert pos_tema < pos_idioma < pos_reset, \
            f"'Idioma' deve ficar entre 'Tema' e 'Restaurar padrões' em {idioma}"

        # o rótulo das línguas NÃO traduz: o usuário reconhece a opção
        linha = next(w for w in preorder(dialogo)
                     if isinstance(w, Adw.ComboRow)
                     and w.get_title() == t("Language"))
        opcoes = linha.get_model()
        assert [opcoes.get_string(i) for i in range(opcoes.get_n_items())] == \
            [label for _, label in IDIOMAS], \
            "nomes nativos das línguas não podem ser traduzidos"

        # as tabelas de parâmetro saem no idioma escolhido (o rótulo é
        # item do menu, não título da linha)
        linha_ordem = next(
            w for w in preorder(dialogo)
            if isinstance(w, Adw.ComboRow) and w.get_title() == t("Sort by"))
        opcoes_ordem = linha_ordem.get_model()
        rotulos = [opcoes_ordem.get_string(i)
                   for i in range(opcoes_ordem.get_n_items())]
        esperado = "Relevância" if idioma == "pt-BR" else "Relevance"
        assert esperado in rotulos, \
            f"tabela de sorting não traduziu em {idioma}: {rotulos}"

        # fecha sem apresentar: descarta os widgets deste laço
        dialogo.close()
        print(f"[i18n] painel em {idioma}: linhas, ordem e línguas ok")

    set_idioma("en-US")


# ---------------------------------------------------------------------------
# 5 — o tray compartilha o i18n, mas nunca puxa o config
# ---------------------------------------------------------------------------
def teste_tray():
    """O tray é GTK3 em outro processo: ``Gtk`` 3 e 4 não coexistem.

    Então ele pode importar o ``koia.i18n`` (sem ``gi``) e NÃO pode o
    ``koia.config`` (que puxa GTK4) — é o que permite os dois
    processos falarem o mesmo idioma sem derrubar o tray.
    """
    with open(os.path.join(PACOTE, "tray.py"), encoding="utf-8") as fh:
        arvore = ast.parse(fh.read())

    importados = set()
    for no in ast.walk(arvore):
        if isinstance(no, ast.ImportFrom) and no.module:
            importados.add(no.module)
        elif isinstance(no, ast.Import):
            importados.update(a.name for a in no.names)

    assert "i18n" in importados, "tray.py não importa o módulo de idioma"
    proibidos = {"config", "window", "ui"} & importados
    assert not proibidos, (
        f"tray.py importa {sorted(proibidos)} — GTK4 dentro de um "
        "processo GTK3 derruba o tray na largada"
    )
    print(f"[i18n] tray: importa i18n e não puxa GTK4 ({sorted(importados)})")


# ---------------------------------------------------------------------------
# 6 — trocar o idioma reconstrói a janela e devolve o estado
# ---------------------------------------------------------------------------
def teste_rebuild():
    """A troca vale na hora: os widgets nascem novos, o estado fica.

    É a parte delicada do i18n — o GTK não troca rótulo em runtime, então
    ``window._rebuild_ui`` refaz a árvore e devolve imagem, página,
    sensibilidade do ▦, tela cheia e o diálogo de preferências (que nasceu
    com os textos do idioma anterior).
    """
    import gi
    gi.require_version("Gtk", "4.0")
    gi.require_version("Adw", "1")
    gi.require_version("GdkPixbuf", "2.0")
    from gi.repository import Adw, GdkPixbuf, Gio, GLib, Gtk

    Gtk.init()
    Adw.init()

    import koia.window as W
    from koia.image import ImageLoader

    tmp = tempfile.mkdtemp(prefix="koia-i18n-win-")
    app = Adw.Application(application_id="org.koia.I18nWindowTest",
                          flags=Gio.ApplicationFlags.NON_UNIQUE)
    app.register()

    set_idioma("en-US")
    win = W.KoiaWindow(app, config.Settings(path=os.path.join(tmp, "s.ini")))
    win.images = ImageLoader(os.path.join(tmp, "cache"))

    # injeta uma página de arquivos locais: load_page usa o cache, sem rede
    paredes = []
    for i in range(3):
        caminho = os.path.join(tmp, f"w{i}.png")
        pb = GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, True, 8, 8, 8)
        pb.fill(0x336699FF)
        pb.savev(caminho, "png", [], [])
        uri = GLib.filename_to_uri(caminho, None)
        paredes.append({"id": f"w{i}", "path": uri, "thumbs": {"large": uri}})
    win._fingerprint = win._query_fingerprint()
    win._pages[1] = {"data": paredes,
                     "meta": {"current_page": 1, "last_page": 3, "total": 72}}
    win.load_page(1)
    assert win.page == 1 and len(win.items) == 3

    assert win.btn_fav.get_tooltip_text() == "Favorite"
    assert win.btn_page_header.get_sensitive(), "o ▦ precisaria da página"

    # diálogo aberto durante a troca: precisa fechar E reabrir traduzido
    win.open_preferences()
    dialogo_velho = win.prefs_dialog
    assert dialogo_velho is not None

    win.settings.set("ui.language", "pt-BR")

    assert win.btn_fav.get_tooltip_text() == "Favoritar", "janela não remontou"
    assert win.btn_fs.get_tooltip_text() == "Tela cheia  ·  F"
    assert win.btn_dl.get_tooltip_text() == "Baixar"
    assert (win.page, len(win.items)) == (1, 3), "estado de navegação sumiu"
    assert win.btn_page_header.get_sensitive(), "sensibilidade do ▦ sumiu"
    assert win.prefs_dialog is not None and win.prefs_dialog is not dialogo_velho, \
        "preferências ficaram no idioma antigo"

    # tela cheia é estado da JANELA, não do widget: precisa sobreviver
    win.prefs_dialog.close()
    win.prefs_dialog = None
    win._fullscreen = True
    win.settings.set("ui.language", "en-US")
    assert win._fullscreen, "rebuild zerou o estado de tela cheia"
    assert not win.header.get_visible(), "HeaderBar reapareceu em tela cheia"
    assert win.btn_fs.get_icon_name() == "view-restore-symbolic"
    assert win.btn_fs.get_tooltip_text() == "Leave fullscreen  ·  F"
    assert (win.page, len(win.items)) == (1, 3)

    set_idioma("en-US")
    print("[i18n] rebuild: idioma, estado, ▦, tela cheia e preferências ok")


if __name__ == "__main__":
    teste_paridade()
    teste_tradutor()
    teste_painel()
    teste_tray()
    teste_rebuild()
    print("[i18n] todos os testes passaram")
