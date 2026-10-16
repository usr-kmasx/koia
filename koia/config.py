"""Persistência das preferências e painel de configuração.

As preferências ficam em ``~/.config/koia/settings.ini`` (GKeyFile).
O painel cobre **todos** os parâmetros de busca aceitos pela API
``/api/v1/search`` do wallhaven.cc.
"""

import os

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, GLib, Gtk  # noqa: E402


# ---------------------------------------------------------------------------
# Valores padrão
# ---------------------------------------------------------------------------

def _default_download_dir():
    pictures = GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_PICTURES)
    if not pictures:
        pictures = os.path.expanduser("~/Pictures")
    return os.path.join(pictures, "Wallpapers")


DEFAULTS = {
    # --- busca (espelha os parâmetros da API) ---
    "search.q": "",              # q
    "search.categories": "111",  # categories  (general|anime|people)
    "search.purity": "100",      # purity      (sfw|sketchy|nsfw)
    "search.sorting": "toplist",  # sorting
    "search.order": "desc",      # order       (asc|desc)
    "search.toprange": "1w",     # topRange    (1d 3d 1w 1M 3M 6M 1y)
    "search.atleast": "",        # atleast    (ex.: 1920x1080)
    "search.resolutions": "",    # resolutions (exata, ex.: 1920x1080,2560x1440)
    "search.ratios": "",         # ratios      (ex.: 16x9,4x3)
    "search.colors": "",         # colors      (ex.: 660000,2196f3)
    "search.apikey": "",         # apikey      (opcional)

    # --- download ---
    "download.folder": _default_download_dir(),

    # --- cache em disco (LRU por data de uso, em MB) ---
    "cache.max-mb": "100",

    # --- aparência e janela ---
    "appearance.color-scheme": "default",  # default | light | dark
    "window.maximized": "true",
    "behavior.autoload": "true",
}


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

class Settings:
    """Chave/valor tipado com persistência em disco e notificação de mudanças."""

    def __init__(self, path=None):
        self._path = path or os.path.join(
            GLib.get_user_config_dir(), "koia", "settings.ini"
        )
        self._data = dict(DEFAULTS)
        self._listeners = []
        os.makedirs(os.path.dirname(self._path), exist_ok=True)
        self._load()

    # -- io ---------------------------------------------------------------
    def _load(self):
        keyfile = GLib.KeyFile.new()
        try:
            keyfile.load_from_file(self._path, GLib.KeyFileFlags.NONE)
        except GLib.Error:
            return  # primeiro uso: mantém padrões
        available = set()
        groups = keyfile.get_groups()[0]
        for group in groups:
            for key in keyfile.get_keys(group)[0]:
                available.add((group, key))
        for key in DEFAULTS:
            group, _, name = key.partition(".")
            if (group, name) not in available:
                continue
            try:
                self._data[key] = keyfile.get_string(group, name)
            except GLib.Error:
                pass

    def save(self):
        keyfile = GLib.KeyFile.new()
        for key, value in sorted(self._data.items()):
            group, _, name = key.partition(".")
            keyfile.set_string(group, name, value)
        try:
            keyfile.save_to_file(self._path)
        except GLib.Error as exc:  # pragma: no cover - disco cheio/sem permissão
            print(f"[koia] não foi possível salvar configurações: {exc}")

    # -- acesso ------------------------------------------------------------
    def get(self, key, default=""):
        return self._data.get(key, DEFAULTS.get(key, default))

    def get_bool(self, key, default=False):
        raw = self.get(key, "true" if default else "false").strip().lower()
        return raw in ("1", "true", "yes", "on")

    def get_int(self, key, default=0):
        try:
            return int(float(self.get(key, str(default))))
        except ValueError:
            return default

    def set(self, key, value, notify=True):
        value = "" if value is None else str(value)
        if self._data.get(key) == value:
            return
        self._data[key] = value
        self.save()
        if notify:
            self._emit(key)

    def reset(self):
        self._data = dict(DEFAULTS)
        self.save()
        for key in DEFAULTS:
            self._emit(key)

    # -- observadores --------------------------------------------------------
    def connect(self, callback):
        """Registra um observador. Devolve o callback para permitir o
        ``disconnect`` — sem isso, cada abertura do diálogo de configuração
        deixaria callbacks órfãos apontando para widgets já destruídos."""
        self._listeners.append(callback)
        return callback

    def disconnect(self, callback):
        try:
            self._listeners.remove(callback)
        except ValueError:
            pass

    def _emit(self, key):
        for cb in list(self._listeners):
            try:
                cb(key)
            except Exception as exc:  # pragma: no cover
                print(f"[koia] listener de configuração falhou: {exc}")


# ---------------------------------------------------------------------------
# Constantes de UI
# ---------------------------------------------------------------------------

SORTINGS = [
    ("relevance", "Relevância"),
    ("random", "Aleatório"),
    ("date_added", "Data de adição"),
    ("views", "Mais vistos"),
    ("favorites", "Mais favoritados"),
    ("toplist", "Toplist"),
]

ORDERS = [("desc", "Descendente"), ("asc", "Ascendente")]

TOP_RANGES = [
    ("1d", "Último dia"), ("3d", "Últimos 3 dias"), ("1w", "Última semana"),
    ("1M", "Último mês"), ("3M", "Últimos 3 meses"),
    ("6M", "Últimos 6 meses"), ("1y", "Último ano"),
]

ATLEAST = [
    "", "640x480", "800x600", "1024x768", "1280x720", "1280x800",
    "1366x768", "1920x1080", "1920x1200", "2560x1080", "2560x1440",
    "2560x1600", "3440x1440", "3840x2160", "5120x1440", "5120x2880",
    "7680x4320",
]

RESOLUTIONS = [
    "800x600", "1024x768", "1280x720", "1280x800", "1366x768",
    "1920x1080", "1920x1200", "2560x1080", "2560x1440", "2560x1600",
    "3440x1440", "3840x2160", "5120x1440", "5120x2880", "7680x4320",
]

RATIOS = [
    "16x9", "16x10", "16x15", "4x3", "5x4", "3x2", "2x1", "21x9",
    "32x9", "48x9", "9x16", "9x18", "1x1",
]

# Paleta de amostras do wallhaven.cc
COLORS = [
    "660000", "990000", "cc0000", "ff0000", "f44336", "e91e63",
    "9c27b0", "673ab7", "3f51b5", "2196f3", "03a9f4", "00bcd4",
    "009688", "4caf50", "8bc34a", "cddc39", "ffc107", "ff9800",
    "ff5722", "795548", "9e9e9e", "607d8b", "333333", "000000",
    "ffffff",
]


# ---------------------------------------------------------------------------
# Helpers de UI
# ---------------------------------------------------------------------------

def _combo_row(title, subtitle, options, current, on_change):
    """options: lista de (valor, rótulo)."""
    row = Adw.ComboRow(title=title)
    if subtitle:
        row.set_subtitle(subtitle)
    values = [v for v, _ in options]
    row.set_model(Gtk.StringList.new([label for _, label in options]))
    try:
        row.set_selected(values.index(current))
    except ValueError:
        row.set_selected(0)

    def _changed(row, _pspec):
        idx = row.get_selected()
        if idx < len(values):
            on_change(values[idx])

    row.connect("notify::selected", _changed)
    return row


def _switch_row(title, subtitle, active, on_change):
    row = Adw.SwitchRow(title=title, active=active)
    if subtitle:
        row.set_subtitle(subtitle)
    row.connect("notify::active", lambda r, _p: on_change(r.get_active()))
    return row


def _check_row(parent_group, expander, title, selected, on_toggle):
    """Linha com caixa de seleção usada nas listas multi-seleção."""
    row = Adw.ActionRow(title=title)
    check = Gtk.CheckButton(active=selected)
    row.add_suffix(check)
    row.set_activatable_widget(check)
    check.connect("toggled", lambda c: on_toggle(title, c.get_active()))
    expander.add_row(row)
    return row


def _swatch_row(expander, hexcolor, selected, on_toggle):
    row = Adw.ActionRow(title=f"#{hexcolor.upper()}")
    swatch = Gtk.Box()
    swatch.set_size_request(30, 22)
    provider = Gtk.CssProvider()
    provider.load_from_data(
        "* {"
        f"  background-color: #{hexcolor};"
        "  border-radius: 6px;"
        "  border: 1px solid alpha(@borders, 0.7);"
        "}"
    )
    swatch.get_style_context().add_provider(
        provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
    )
    check = Gtk.CheckButton(active=selected)
    check.set_valign(Gtk.Align.CENTER)
    row.add_prefix(swatch)
    row.add_suffix(check)
    row.set_activatable_widget(check)
    check.connect("toggled", lambda c: on_toggle(hexcolor, c.get_active()))
    expander.add_row(row)
    return row


def _bitmask_group(settings, key, specs, group, keep=None, force=0):
    """Três caixas de seleção ligadas a um bitmask de 3 dígitos da API.

    ``specs``: [(título, subtítulo|None)] nos índices 0, 1 e 2.
    ``keep``: predicado que diz se um valor é aceitável; se recusar,
              o índice ``force`` é religado.
    Devolve ``(caixas, linhas, sincronizar)``.

    O guard ``syncing`` é o que impede o loop que congelava a janela:
    sincronizar as caixas a partir do settings dispara ``toggled``, e sem
    o guard cada ``toggled`` voltava a gravar o settings — que disparava
    outra sincronização ... até ``RecursionError`` dentro do handler do
    GTK. Somado ao fato de cada caixa ter guardado a sua *própria* cópia
    do bitmask (desatualizada), as três acabavam brigando entre si.
    """
    state = {"syncing": False}
    checks = []
    rows = []

    def _read():
        raw = (settings.get(key) or "").strip()
        raw = raw.ljust(3, "0")[:3]
        if len(raw) != 3 or any(c not in "01" for c in raw):
            return ["1", "1", "1"] if key.endswith("categories") else ["1", "0", "0"]
        return list(raw)

    def _apply(value):
        # gravar nas caixas dispara "toggled", mas o guard os torna no-op
        for i, check in enumerate(checks):
            wanted = value[i] == "1"
            if check.get_active() != wanted:
                check.set_active(wanted)

    def sync():
        if state["syncing"]:
            return
        state["syncing"] = True
        try:
            value = _read()
            if keep is not None and not keep(value):
                value[force] = "1"
            _apply(value)
        finally:
            state["syncing"] = False

    for index, (title, subtitle) in enumerate(specs):
        initial = _read()
        check = Gtk.CheckButton(active=initial[index] == "1")
        row = Adw.ActionRow(title=title)
        if subtitle:
            row.set_subtitle(subtitle)
        row.add_suffix(check)
        row.set_activatable_widget(check)
        group.add(row)

        def on_toggled(_check, idx=index):
            if state["syncing"]:
                return
            state["syncing"] = True
            try:
                value = _read()
                value[idx] = "1" if checks[idx].get_active() else "0"
                if keep is not None and not keep(value):
                    value[force] = "1"
                settings.set(key, "".join(value))
                _apply(value)   # alinha as demais caixas, sem novo evento
            finally:
                state["syncing"] = False

        check.connect("toggled", on_toggled)
        checks.append(check)
        rows.append(row)

    return checks, rows, sync


def _csv(value):
    return [v for v in (value or "").split(",") if v]


def _join(items):
    return ",".join(items)


def _human(size):
    """Tamanho legível em português (ponto decimal vira vírgula)."""
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.0f} KB"
    return f"{size / (1024 * 1024):.1f} MB".replace(".", ",")


# ---------------------------------------------------------------------------
# Janela de preferências
# ---------------------------------------------------------------------------

def build_preferences(parent, settings):
    """Monta e retorna o ``Adw.PreferencesWindow`` já conectado ao Settings."""
    dialog = Adw.PreferencesWindow(
        transient_for=parent,
        modal=True,
        search_enabled=True,
        default_width=620,
        default_height=680,
        title="Configurações",
    )

    page = Adw.PreferencesPage(title="Configurações", icon_name="preferences-system-symbolic")

    # ---------------- Busca ----------------
    g_search = Adw.PreferencesGroup(
        title="Busca",
        description="Parâmetro q — palavras-chave, #tag, @usuário, type:jpg, like:id",
    )
    entry = Adw.EntryRow(title="Termo de busca")
    entry.set_text(settings.get("search.q"))
    entry.connect(
        "changed",
        lambda e: settings.set("search.q", e.get_text()),
    )
    g_search.add(entry)

    cat_checks, cat_rows, sync_categories = _bitmask_group(
        settings, "search.categories",
        [("General", None), ("Anime", None), ("People", None)],
        g_search,
        keep=lambda v: any(bit == "1" for bit in v),
        force=0,
    )
    check_gen, check_ani, check_ppl = cat_checks
    page.add(g_search)

    # ---------------- Pureza ----------------
    g_purity = Adw.PreferencesGroup(
        title="Pureza",
        description="Parâmetro purity — SFW, NSFW e Sketchy",
    )

    pur_checks, pur_rows, sync_purity = _bitmask_group(
        settings, "search.purity",
        [("SFW (seguro)", None),
         ("Sketchy (duvidoso)", None),
         ("NSFW (adulto)", "Requer chave de API do wallhaven.cc")],
        g_purity,
        # exige SFW ou Sketchy: NSFW sozinho devolve 0 resultados sem chave
        keep=lambda v: v[0] == "1" or v[1] == "1",
        force=0,
    )
    check_sfw, check_sketchy, check_nsfw = pur_checks
    row_sfw, row_sketchy, row_nsfw = pur_rows
    page.add(g_purity)

    # ---------------- Ordenação ----------------
    g_sort = Adw.PreferencesGroup(title="Ordenação")
    row_sorting = _combo_row(
        "Ordenar por", "Parâmetro sorting", SORTINGS,
        settings.get("search.sorting"),
        lambda v: (settings.set("search.sorting", v), _sync_toprange()),
    )
    row_order = _combo_row(
        "Direção", "Parâmetro order", ORDERS,
        settings.get("search.order"),
        lambda v: settings.set("search.order", v),
    )
    row_toprange = _combo_row(
        "Período da toplist", "Parâmetro topRange", TOP_RANGES,
        settings.get("search.toprange"),
        lambda v: settings.set("search.toprange", v),
    )
    g_sort.add(row_sorting)
    g_sort.add(row_order)
    g_sort.add(row_toprange)

    def _sync_toprange():
        row_toprange.set_sensitive(settings.get("search.sorting") == "toplist")

    _sync_toprange()
    page.add(g_sort)

    # ---------------- Resolução e proporção ----------------
    g_size = Adw.PreferencesGroup(
        title="Tamanho",
        description="Parâmetros atleast, resolutions e ratios",
    )
    atleast_options = [("", "Qualquer")] + [(r, r) for r in ATLEAST if r]
    g_size.add(
        _combo_row(
            "Resolução mínima", "Parâmetro atleast", atleast_options,
            settings.get("search.atleast"),
            lambda v: settings.set("search.atleast", v),
        )
    )

    exp_res = Adw.ExpanderRow(title="Resoluções exatas", subtitle="Parâmetro resolutions")
    selected_res = set(_csv(settings.get("search.resolutions")))

    def _toggle_res(value, active):
        current = set(_csv(settings.get("search.resolutions")))
        current.add(value) if active else current.discard(value)
        settings.set("search.resolutions", _join(sorted(current)))

    for res in RESOLUTIONS:
        _check_row(g_size, exp_res, res, res in selected_res, _toggle_res)
    g_size.add(exp_res)

    exp_ratio = Adw.ExpanderRow(title="Proporções", subtitle="Parâmetro ratios")
    selected_ratios = set(_csv(settings.get("search.ratios")))

    def _toggle_ratio(value, active):
        current = set(_csv(settings.get("search.ratios")))
        current.add(value) if active else current.discard(value)
        settings.set("search.ratios", _join(sorted(current)))

    for ratio in RATIOS:
        _check_row(g_size, exp_ratio, ratio, ratio in selected_ratios, _toggle_ratio)
    g_size.add(exp_ratio)
    page.add(g_size)

    # ---------------- Cores ----------------
    g_colors = Adw.PreferencesGroup(
        title="Cores",
        description="Parâmetro colors — pode combinar várias cores",
    )
    exp_colors = Adw.ExpanderRow(title="Cores predominantes")
    selected_colors = set(_csv(settings.get("search.colors")))

    def _toggle_color(value, active):
        current = set(_csv(settings.get("search.colors")))
        current.add(value) if active else current.discard(value)
        settings.set("search.colors", _join(sorted(current)))
        sync_color_checks()

    color_checks = {}
    for hexcolor in COLORS:
        color_checks[hexcolor] = _swatch_row(
            exp_colors, hexcolor, hexcolor in selected_colors, _toggle_color
        )

    row_custom = Adw.ActionRow(title="Cor personalizada")
    dialog_button = Gtk.ColorDialogButton(dialog=Gtk.ColorDialog(title="Escolher cor"))
    row_custom.add_suffix(dialog_button)
    exp_colors.add_row(row_custom)

    def _on_custom_color(button, _pspec):
        rgba = button.get_rgba()
        hexcolor = "%02x%02x%02x" % (
            round(rgba.red * 255), round(rgba.green * 255), round(rgba.blue * 255)
        )
        _toggle_color(hexcolor, True)

    dialog_button.connect("notify::rgba", _on_custom_color)

    def sync_color_checks():
        current = set(_csv(settings.get("search.colors")))
        for hexcolor, row in color_checks.items():
            check = row.get_activatable_widget()
            if check and check.get_active() != (hexcolor in current):
                check.set_active(hexcolor in current)

    g_colors.add(exp_colors)
    page.add(g_colors)

    # ---------------- Chave de API ----------------
    g_api = Adw.PreferencesGroup(
        title="Chave de API (opcional)",
        description="Sem chave o app funciona normalmente, com 45 requisições por "
                    "minuto. Colar a chave libera NSFW e aumenta o limite.",
    )
    key_row = Adw.EntryRow(title="apikey")
    key_row.set_text(settings.get("search.apikey"))
    key_row.connect("changed", lambda e: settings.set("search.apikey", e.get_text()))
    g_api.add(key_row)

    def _sync_nsfw():
        has_key = bool(settings.get("search.apikey").strip())
        check_nsfw.set_sensitive(has_key)
        row_nsfw.set_subtitle(
            "Ativo — usando sua chave de API"
            if has_key else
            "Requer chave de API do wallhaven.cc"
        )

    _sync_nsfw()
    page.add(g_api)

    # ---------------- Download ----------------
    g_dl = Adw.PreferencesGroup(title="Download", description="Onde e como salvar")

    folder_row = Adw.ActionRow(title="Pasta de destino")
    current_folder = settings.get("download.folder")
    folder_row.set_subtitle(current_folder)
    folder_button = Gtk.Button(label="Escolher…")
    folder_button.set_valign(Gtk.Align.CENTER)
    folder_button.add_css_class("pill")
    folder_row.add_suffix(folder_button)

    def _pick_folder(_btn):
        fc = Gtk.FileChooserNative(
            title="Pasta de destino",
            transient_for=dialog,
            action=Gtk.FileChooserAction.SELECT_FOLDER,
            accept_label="Selecionar",
            cancel_label="Cancelar",
        )

        def _on_response(chooser, response):
            if response == Gtk.ResponseType.ACCEPT:
                file = chooser.get_file()
                if file:
                    path = file.get_path()
                    settings.set("download.folder", path)
                    folder_row.set_subtitle(path)
            chooser.destroy()

        fc.connect("response", _on_response)
        fc.show()

    folder_button.connect("clicked", _pick_folder)
    g_dl.add(folder_row)
    page.add(g_dl)

    # ---------------- Cache ----------------
    g_cache = Adw.PreferencesGroup(
        title="Cache",
        description="Só as miniaturas vão para o disco. As imagens completas "
                    "ficam apenas em memória — nada é recomprimido, então a "
                    "qualidade original fica intacta.",
    )
    images = getattr(parent, "images", None)

    cache_row = Adw.SpinRow(
        title="Teto do cache em disco",
        subtitle="As miniaturas menos usadas saem primeiro ao passar do teto",
        adjustment=Gtk.Adjustment(
            value=settings.get_int("cache.max-mb", 100),
            lower=10,
            upper=10000,
            step_increment=10,
            page_increment=100,
        ),
    )
    cache_row.set_digits(0)
    cache_row.set_numeric(True)
    cache_row.connect(
        "notify::value",
        lambda row, _p: settings.set("cache.max-mb", str(int(row.get_value()))),
    )
    g_cache.add(cache_row)

    usage_row = Adw.ActionRow(title="Em uso agora", subtitle="—")
    clear_button = Gtk.Button(label="Limpar")
    clear_button.set_valign(Gtk.Align.CENTER)
    clear_button.add_css_class("pill")
    usage_row.add_suffix(clear_button)
    g_cache.add(usage_row)

    def _sync_usage(*_args):
        if images is not None:
            usage_row.set_subtitle(_human(images.cache_size()))

    def _clear_cache(_btn):
        if images is None:
            return
        removed = images.clear()
        _sync_usage()
        dialog.add_toast(Adw.Toast.new(f"{removed} arquivo(s) removido do cache"))

    clear_button.connect("clicked", _clear_cache)
    _sync_usage()
    page.add(g_cache)

    # ---------------- Aparência e janela ----------------
    g_ui = Adw.PreferencesGroup(title="Aparência e janela")
    g_ui.add(
        _combo_row(
            "Tema", None,
            [("default", "Seguir o sistema"), ("light", "Claro"), ("dark", "Escuro")],
            settings.get("appearance.color-scheme"),
            lambda v: settings.set("appearance.color-scheme", v),
        )
    )
    g_ui.add(
        _switch_row(
            "Abrir maximizado", None,
            settings.get_bool("window.maximized", True),
            lambda v: settings.set("window.maximized", "true" if v else "false"),
        )
    )
    g_ui.add(
        _switch_row(
            "Buscar wallpapers ao iniciar", None,
            settings.get_bool("behavior.autoload", True),
            lambda v: settings.set("behavior.autoload", "true" if v else "false"),
        )
    )
    page.add(g_ui)

    # ---------------- Restaurar padrões ----------------
    g_reset = Adw.PreferencesGroup()
    reset_row = Adw.ActionRow(
        title="Restaurar padrões",
        subtitle="Volta todas as opções ao estado inicial",
    )
    reset_button = Gtk.Button(label="Restaurar")
    reset_button.set_valign(Gtk.Align.CENTER)
    reset_button.add_css_class("destructive-action")
    reset_button.add_css_class("pill")

    def _do_reset(_btn):
        confirm = Adw.MessageDialog(
            transient_for=dialog,
            heading="Restaurar padrões?",
            body="Todas as configurações voltarão ao valor inicial.",
        )
        confirm.add_response("cancel", "Cancelar")
        confirm.add_response("reset", "Restaurar")
        confirm.set_response_appearance("reset", Adw.ResponseAppearance.DESTRUCTIVE)
        confirm.set_default_response("cancel")

        def _confirmed(_d, response):
            if response == "reset":
                settings.reset()
                dialog.close()

        confirm.connect("response", _confirmed)
        confirm.present()

    reset_button.connect("clicked", _do_reset)
    reset_row.add_suffix(reset_button)
    reset_row.set_activatable_widget(reset_button)
    g_reset.add(reset_row)
    page.add(g_reset)

    # Um único observador por diálogo, removido quando ele fecha.
    # Antes cada abertura registrava 2 callbacks novos e NUNCA os
    # removia — eles ficavam segurando widgets já destruídos.
    def _on_settings_changed(key):
        if key.startswith("search."):
            sync_categories()
            sync_purity()
        if key == "search.apikey":
            _sync_nsfw()

    settings.connect(_on_settings_changed)

    def _release(_dialog, *_args):
        settings.disconnect(_on_settings_changed)
        return False   # False deixa o diálogo fechar normalmente

    # GTK4: Gtk.Window::destroy não dispara no fechar; close-request sim
    dialog.connect("close-request", _release)

    dialog.add(page)
    return dialog
