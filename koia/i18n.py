"""Idioma do Koia — módulo NEUTRO de GTK.

O app é GTK4 mas o tray (``koia/tray.py``) é um daemon GTK3 em outro
processo e não pode importar nada que puxe GTK4 — então a tradução mora
aqui, sem ``gi``, e os dois compartilham o mesmo dicionário.

A língua-fonte é o INGLÊS: os literais no código já são as chaves e o
dicionário ``PT_BR`` traduz de volta. Chave ausente cai no inglês — um
texto esquecido aparece no idioma errado, nunca quebra a interface.
``tests/i18n_test.py`` varre o código e falha antes disso acontecer.
"""

IDIOMAS = (("en-US", "English (US)"), ("pt-BR", "Português (Brasil)"))
PADRAO = "en-US"

_atual = PADRAO


def set_idioma(lang):
    """Escolhe o idioma ativo (valor desconhecido cai no padrão)."""
    global _atual
    _atual = lang if any(lang == code for code, _label in IDIOMAS) else PADRAO


def get_idioma():
    return _atual


def t(texto):
    """Traduz ``texto`` para o idioma ativo (em en-US, devolve ele mesmo)."""
    if _atual == PADRAO:
        return texto
    return PT_BR.get(texto, texto)


def num(n):
    """Número com o separador do idioma: 1,024 (en) / 1.024 (pt)."""
    bruto = f"{n:,}"
    return bruto.replace(",", ".") if _atual == "pt-BR" else bruto


def decimal(texto):
    """Separador decimal do idioma: 12.3 MB (en) / 12,3 MB (pt)."""
    return texto.replace(".", ",") if _atual == "pt-BR" else texto


# ---------------------------------------------------------------------------
# pt-BR  (inglês -> português)
# ---------------------------------------------------------------------------
PT_BR = {
    # -- api.py ----------------------------------------------------------
    "Network failure: %s": "Falha de rede: %s",
    "Rate limit reached (45/min). Please wait a moment.":
        "Limite de requisições atingido (45/min). Aguarde um instante.",
    "The API key was rejected by wallhaven.cc.":
        "A chave de API foi recusada pelo wallhaven.cc.",
    "Page not found.": "Página não encontrada.",
    "wallhaven.cc returned HTTP %s.": "O wallhaven.cc respondeu HTTP %s.",
    "Invalid response from the server.": "Resposta inválida do servidor.",

    # -- downloader.py ---------------------------------------------------
    "folder unreachable: %s": "pasta inacessível: %s",
    "network failure: %s": "falha de rede: %s",
    "transfer interrupted: %s": "transferência interrompida: %s",
    "could not write: %s": "não foi possível gravar: %s",
    "empty file": "arquivo vazio",
    "could not save: %s": "não foi possível salvar: %s",

    # -- background.py ---------------------------------------------------
    "wallpaper file not found": "arquivo do wallpaper não encontrado",
    "this environment can't apply a wallpaper (GNOME only)":
        "este ambiente não suporta aplicar wallpaper (só GNOME)",
    "could not apply: %s": "não foi possível aplicar: %s",
    "could not restore: %s": "não foi possível restaurar: %s",

    # -- window.py -------------------------------------------------------
    "No wallpapers found with these filters":
        "Nenhum wallpaper encontrado com estes filtros",
    "End of results — %s wallpapers": "Fim dos resultados — %s wallpapers",
    "Previous": "Anterior",
    "Next": "Próxima",
    "Favorite": "Favoritar",
    "Download": "Baixar",
    "Fullscreen  ·  F": "Tela cheia  ·  F",
    "Leave fullscreen  ·  F": "Sair da tela cheia  ·  F",
    "Apply wallpaper": "Aplicar wallpaper",
    "Settings  ·  Ctrl+,": "Configurações  ·  Ctrl+,",
    "View the page": "Ver a página",
    "Delete from disk": "Apagar do disco",
    "Downloading to apply…": "Baixando para aplicar…",
    "Wallpaper applied": "Wallpaper aplicado",
    "Downloaded: %s": "Baixado: %s",
    "Download failed: %s": "Falha ao baixar: %s",
    "Folder unreachable: %s": "Pasta inacessível: %s",
    "Delete the wallpaper?": "Apagar o wallpaper?",
    "“%s” will be permanently deleted from disk.":
        "“%s” será apagado permanentemente do disco.",
    "Cancel": "Cancelar",
    "Delete": "Apagar",
    "Could not delete: %s": "Não foi possível apagar: %s",
    "Deleted: %s": "Apagado: %s",
    "Deleted — system background restored":
        "Apagado — fundo do sistema restaurado",
    "Deleted — no previous background to restore":
        "Apagado — sem fundo anterior para restaurar",
    "%s · file deleted": "%s · arquivo apagado",
    "Added to favorites": "Favoritado",
    "Removed from favorites": "Removido dos favoritos",
    "Remove from favorites": "Remover dos favoritos",

    # -- favorites_view.py -----------------------------------------------
    "Favorites": "Favoritos",
    "No favorites yet": "Nenhum favorito ainda",

    # -- downloads_view.py -----------------------------------------------
    "No wallpapers downloaded yet": "Nenhum wallpaper baixado ainda",

    # -- page_view.py ----------------------------------------------------
    "Page %s": "Página %s",
    "Previous page": "Página anterior",
    "Next page": "Página seguinte",
    "Go to page": "Ir para a página",
    "Empty page": "Página vazia",

    # -- tray.py (chaves próprias: "Next" da janela é "Próxima") ----------
    "Open": "Abrir",
    "Close": "Fechar",
    "Next wallpaper": "Próximo",
    "Previous wallpaper": "Anterior",
    "Pause": "Pausar",
    "Resume": "Retomar",
    "Quit": "Sair",
    "Koia slide": "Slide koia",
    "Off": "Desligado",
    "Seconds": "Segundos",
    "Minutes": "Minutos",

    # -- config.py -------------------------------------------------------
    "Settings": "Configurações",
    "Search": "Busca",
    "Search term": "Termo de busca",
    "Purity": "Pureza",
    "SFW (safe)": "SFW (seguro)",
    "Sketchy (risky)": "Sketchy (duvidoso)",
    "NSFW (adult)": "NSFW (adulto)",
    "Requires a wallhaven.cc API key": "Requer chave de API do wallhaven.cc",
    "Using your API key": "Ativo — usando sua chave de API",
    "Sorting": "Ordenação",
    "Sort by": "Ordenar por",
    "Relevance": "Relevância",
    "Random": "Aleatório",
    "Date added": "Data de adição",
    "Most viewed": "Mais vistos",
    "Most favorited": "Mais favoritados",
    # idêntico nos dois idiomas — entrada explícita para o teste de
    # paridade não tratar a ausência como tradução esquecida
    "Toplist": "Toplist",
    "Direction": "Direção",
    "Descending": "Descendente",
    "Ascending": "Ascendente",
    "Toplist period": "Período da toplist",
    "Last day": "Último dia",
    "Last 3 days": "Últimos 3 dias",
    "Last week": "Última semana",
    "Last month": "Último mês",
    "Last 3 months": "Últimos 3 meses",
    "Last 6 months": "Últimos 6 meses",
    "Last year": "Último ano",
    "Size": "Tamanho",
    "Minimum resolution": "Resolução mínima",
    "Any": "Qualquer",
    "Exact resolutions": "Resoluções exatas",
    "Aspect ratios": "Proporções",
    "Colors": "Cores",
    "Dominant colors": "Cores predominantes",
    "Custom color": "Cor personalizada",
    "Choose a color": "Escolher cor",
    "API key (optional)": "Chave de API (opcional)",
    "Destination folder": "Pasta de destino",
    "Choose…": "Escolher…",
    "Select": "Selecionar",
    "Disk cache cap": "Teto do cache em disco",
    "In use now": "Em uso agora",
    "Clear": "Limpar",
    "%s file(s) removed from the cache":
        "%s arquivo(s) removido do cache",
    "Appearance": "Aparência",
    "Theme": "Tema",
    "Follow the system": "Seguir o sistema",
    "Light": "Claro",
    "Dark": "Escuro",
    "Language": "Idioma",
    "Restore defaults": "Restaurar padrões",
    "Restore": "Restaurar",
    "Restore defaults?": "Restaurar padrões?",
    "All settings will return to their initial values.":
        "Todas as configurações voltarão ao valor inicial.",
}
