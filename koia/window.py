"""Janela principal do Koia — o layout do mockup."""

import json
import os
from collections import OrderedDict

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, GLib, Gtk  # noqa: E402

from .api import WallhavenAPI, build_query  # noqa: E402
from .background import (  # noqa: E402
    is_current_background,
    restore_previous_background,
    set_as_background,
)
from .config import build_preferences  # noqa: E402
from .downloads_view import build_downloads_dialog  # noqa: E402
from .downloader import Downloader, destination_for, filename_of  # noqa: E402
from .favorites import FavoritesStore  # noqa: E402
from .favorites_view import build_favorites_dialog  # noqa: E402
from .i18n import num, set_idioma, t  # noqa: E402
from .image import FULL_SCALE, THUMB_SCALE, ImageLoader  # noqa: E402
from .page_view import build_page_dialog  # noqa: E402

CONTROLS_HIDE_AFTER_MS = 5000
CONTROLS_ANIMATION_MS = 250
FULL_SWAP_DELAY_MS = 250
FILTER_SEARCH_DELAY_MS = 2000

# Quantas páginas já buscadas ficam guardadas em memória. Guardar é o que
# permite voltar para a página anterior **com as mesmas imagens** e entrando
# pelo último item — a API do wallhaven sorteia um conjunto novo a cada
# requisição quando o ordenador é "random", então refazer a chamada nunca
# devolveria a mesma página.
PAGE_CACHE_MAX = 60

# "índice" que significa o último item da página
LAST = -1


class KoiaWindow(Adw.ApplicationWindow):
    def __init__(self, app, settings):
        super().__init__(application=app, title="Koia",
                         default_width=1280, default_height=800)
        self.settings = settings
        self.app = app

        cache_dir = os.path.join(GLib.get_user_cache_dir(), "koia")
        self.api = WallhavenAPI(settings)
        self.images = ImageLoader(
            cache_dir,
            max_bytes=settings.get_int("cache.max-mb", 100) * 1024 * 1024,
        )
        self.downloader = Downloader(self.images.session)
        self.favorites = FavoritesStore()

        # estado da navegação
        self.items = []
        self.index = 0
        self.page = 1
        self.last_page = 1
        self.total = 0
        self._gen = 0            # invalida callbacks de imagens antigas
        self._busy = False
        self._filter_search_source = 0
        self._reload_queued = False
        self._dl_busy = False
        # arquivo aplicado como papel de parede nesta sessão (None = nenhum)
        self._applied_path = None
        # visualizando um favorito? (página de um item; as setas voltam
        # para a busca anterior, que segue em cache)
        self._fav_context = False
        self._return_to = None
        self._fullscreen = False
        # Visibilidade temporária da barra, independente do foco do GTK.
        self._controls_hide_source = 0

        # páginas já buscadas nesta sessão, na ordem em que foram pedidas
        self._pages = OrderedDict()
        self._fingerprint = None

        # última página vista no visor ▦ (não mexe na janela) e a página
        # da JANELA naquele momento; a lembrança só vale enquanto a
        # janela segue na mesma página — se ela cruzar de página (setas),
        # o ▦ reabre onde a janela parou
        self._page_view_page = None
        self._page_view_window = None

        # diálogo de preferências aberto (o rebuild de idioma fecha e
        # reabre ele, porque ele nasceu com os textos do idioma anterior)
        self.prefs_dialog = None

        self._build_ui()
        self._install_actions()

        # Tab/Shift+Tab e hover na área inferior têm controle separado;
        # o movimento fora do painel nunca influencia a visibilidade.
        keyboard = Gtk.EventControllerKey()
        keyboard.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        keyboard.connect("key-pressed", self._on_controls_key_pressed)
        self.add_controller(keyboard)
        self._controls_keyboard = keyboard
        self._arm_controls_hide_timer()

        # abre maximizada — comportamento fixo, sem opção de desligar
        self.maximize()

        settings.connect(self._on_settings_changed)

        # a janela se carrega sozinha ao ser mapeada na tela
        self.connect("map", self._on_mapped)

        # o X da janela ESCONDE (o app segue vivo — daemon/tray); quem
        # encerra de verdade é o "Sair" do tray. Esconder (e não destruir)
        # preserva a navegação: "Abrir" reabre na mesma imagem
        self.connect("close-request", self._on_close_request)

    def _on_close_request(self, *_args):
        self.hide()
        return True  # cancela o destroy padrão

    def _on_mapped(self, *_args):
        # a busca sai sozinha na largada; a guarda de itens evita
        # rebuscar toda vez que a janela volta a mapear
        if not self.items:
            self.load_page(1)

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------
    def _build_ui(self):
        # Ao reconstruir a interface por mudança de idioma, o temporizador
        # antigo não pode recolher a nova barra antecipadamente.
        self._cancel_controls_hide_timer()

        # ---- palco com a imagem -------------------------------------
        self.picture = Gtk.Picture(content_fit=Gtk.ContentFit.CONTAIN)
        self.picture.set_can_target(False)
        self.picture.add_css_class("koia-stage")

        overlay = Gtk.Overlay()
        overlay.set_child(self.picture)

        self.spinner = Adw.Spinner()
        self.spinner.set_halign(Gtk.Align.CENTER)
        self.spinner.set_valign(Gtk.Align.CENTER)
        self.spinner.set_size_request(32, 32)
        self.spinner.set_opacity(0.0)
        overlay.add_overlay(self.spinner)

        # ---- barra flutuante de controles ---------------------------
        bar = Gtk.Box(spacing=6)
        bar.set_margin_start(18)
        bar.set_margin_end(18)
        bar.set_margin_top(10)
        bar.set_margin_bottom(18)
        bar.add_css_class("koia-controls")

        self.btn_prev = self._icon_button(
            "go-previous-symbolic", t("Previous"), "win.go-prev")
        self.btn_next = self._icon_button(
            "go-next-symbolic", t("Next"), "win.go-next")
        self.btn_fav = self._icon_button(
            "koia-heart-symbolic", t("Favorite"), "win.toggle-favorite")
        self.btn_dl = self._icon_button(
            "document-save-symbolic", t("Download"), "win.download")
        self.btn_fs = self._icon_button(
            "view-fullscreen-symbolic", t("Fullscreen  ·  F"),
            "win.fullscreen")
        self.btn_apply = self._icon_button(
            "video-display-symbolic", t("Apply wallpaper"),
            "win.apply-wallpaper")

        # Os quatro antigos ícones da barra de título vêm depois dos
        # seis controles originais, na mesma ordem visual (esq. -> dir.).
        # _icon_button aplica o mesmo tamanho, formato e estilo a todos.
        self.btn_downloads = self._icon_button(
            "image-x-generic-symbolic", "Downloads", "win.show-downloads")
        self.btn_favorites = self._icon_button(
            "koia-heart-symbolic", t("Favorites"), "win.show-favorites")
        self.btn_page = self._icon_button(
            "view-grid-symbolic", t("View the page"), "win.show-page")
        self.btn_settings = self._icon_button(
            "preferences-system-symbolic", t("Settings  ·  Ctrl+,"),
            "win.preferences")

        self._control_buttons = (
            self.btn_prev, self.btn_next, self.btn_fav,
            self.btn_dl, self.btn_fs, self.btn_apply,
            self.btn_downloads, self.btn_favorites,
            self.btn_page, self.btn_settings,
        )
        for button in self._control_buttons:
            bar.append(button)

        # A mesma animação serve para revelar por Tab ou pelo mouse.
        self.revealer = Gtk.Revealer(
            transition_type=Gtk.RevealerTransitionType.SLIDE_UP,
            transition_duration=CONTROLS_ANIMATION_MS,
            halign=Gtk.Align.START,
            valign=Gtk.Align.END,
        )
        self.revealer.set_margin_start(18)
        self.revealer.set_margin_end(18)
        self.revealer.set_margin_bottom(18)
        self.revealer.set_child(bar)
        self.revealer.set_reveal_child(True)

        # Área de hover estável, exatamente na região da barra inferior.
        # O Gtk.Revealer encolhe quando oculto; um molde transparente
        # mantém essa região detectável SEM instalar motion na tela toda.
        # Como o controlador pertence ao pai, permanece ativo também
        # quando o ponteiro passa para os botões revelados.
        panel_zone = Gtk.Overlay(halign=Gtk.Align.START,
                                 valign=Gtk.Align.END)
        hit_area = Gtk.Box(spacing=6)
        hit_area.add_css_class("koia-controls")
        hit_area.set_margin_start(36)  # 18 da barra + 18 do revealer
        hit_area.set_margin_end(36)
        hit_area.set_margin_top(10)
        hit_area.set_margin_bottom(36)
        for button in self._control_buttons:
            # Cópia apenas para medição: respeita o tamanho natural
            # real de Gtk.Button no tema, sem receber clique nem Tab.
            placeholder = Gtk.Button.new_from_icon_name(button.get_icon_name())
            placeholder.add_css_class("flat")
            placeholder.add_css_class("koia-control")
            placeholder.set_can_target(False)
            placeholder.set_focusable(False)
            hit_area.append(placeholder)
        hit_area.set_opacity(0)
        panel_zone.set_child(hit_area)
        panel_zone.add_overlay(self.revealer)
        overlay.add_overlay(panel_zone)
        self._panel_hover_zone = panel_zone

        panel_motion = Gtk.EventControllerMotion()
        panel_motion.connect("enter", self._on_panel_pointer_enter)
        panel_motion.connect("leave", self._on_panel_pointer_leave)
        panel_zone.add_controller(panel_motion)
        self._panel_motion = panel_motion

        # ---- chrome Adwaita ------------------------------------------
        toolbar = Adw.ToolbarView()
        header = Adw.HeaderBar()
        header.set_title_widget(Adw.WindowTitle.new("Koia", ""))

        # Ícones utilitários agora ficam no fim da barra inferior.
        toolbar.add_top_bar(header)
        toolbar.set_content(overlay)

        self.header = header
        self.toast_overlay = Adw.ToastOverlay(child=toolbar)
        self.set_content(self.toast_overlay)
        if getattr(self, "_controls_keyboard", None) is not None:
            self._arm_controls_hide_timer()

    def _cancel_controls_hide_timer(self):
        if self._controls_hide_source:
            GLib.source_remove(self._controls_hide_source)
            self._controls_hide_source = 0

    def _arm_controls_hide_timer(self):
        self._cancel_controls_hide_timer()
        self._controls_hide_source = GLib.timeout_add(
            CONTROLS_HIDE_AFTER_MS, self._hide_controls
        )

    def _hide_controls(self):
        self._controls_hide_source = 0
        # O mouse só sustenta o painel dentro de sua região inferior.
        # O foco do teclado não entra nessa decisão.
        if self._panel_motion.contains_pointer():
            return GLib.SOURCE_REMOVE
        # O foco (borda ao redor do ícone) não sustenta a visibilidade.
        # Soltar o foco antes de recolher evita ficar preso em um botão
        # que já não pode ser alcançado visualmente pelo Tab.
        if self.get_focus() in self._control_buttons:
            self.set_focus(None)
        self.revealer.set_reveal_child(False)
        return GLib.SOURCE_REMOVE

    def _on_panel_pointer_enter(self, _controller, _x, _y):
        self.revealer.set_reveal_child(True)
        self._cancel_controls_hide_timer()

    def _on_panel_pointer_leave(self, _controller):
        self._arm_controls_hide_timer()

    def _on_controls_key_pressed(self, _controller, keyval, _keycode, mods):
        if keyval not in (Gdk.KEY_Tab, Gdk.KEY_KP_Tab, Gdk.KEY_ISO_Left_Tab):
            return False
        backward = (keyval == Gdk.KEY_ISO_Left_Tab
                    or bool(mods & Gdk.ModifierType.SHIFT_MASK))
        was_hidden = not self.revealer.get_reveal_child()
        self.revealer.set_reveal_child(True)
        self._arm_controls_hide_timer()
        if was_hidden:
            # A barra recolhida não participa da travessia normal do GTK.
            # O primeiro Tab a revela e foca o botão correto sem saltos.
            candidates = reversed(self._control_buttons) if backward else self._control_buttons
            for button in candidates:
                if button.get_sensitive() and button.get_focusable():
                    button.grab_focus()
                    break
            return True
        # Visível: deixar o GTK percorrer naturalmente os dez ícones.
        return False

    def _icon_button(self, icon_name, tooltip, action_name):
        button = Gtk.Button.new_from_icon_name(icon_name)
        button.set_tooltip_text(tooltip)
        button.set_action_name(action_name)
        button.add_css_class("flat")
        button.add_css_class("koia-control")
        return button

    def _rebuild_ui(self):
        """Troca de idioma: refaz a árvore de widgets no idioma novo.

        O GTK não troca rótulos em runtime, então a única saída limpa é
        reconstruir (``set_content`` novo, o antigo é desreferenciado).
        Depois devolve o que a árvore nova não sabe sozinha: o estado de
        tela cheia, a sensibilidade do ▦, a imagem em exibição e os
        badges — todos vivem em ``self``, não nos widgets.
        """
        fullscreen = self._fullscreen
        reabrir_prefs = self.prefs_dialog is not None
        if reabrir_prefs:
            # a janela vai nascer nova; a referência antiga morre junto
            antigo, self.prefs_dialog = self.prefs_dialog, None
            antigo.close()

        self._build_ui()

        if fullscreen:
            self._sync_fullscreen_ui()
        self._sync_page_button()
        if self.items:
            self.show_current()
        if reabrir_prefs:
            self.open_preferences()

    # ------------------------------------------------------------------
    # Ações e atalhos
    # ------------------------------------------------------------------
    def _install_actions(self):
        handlers = {
            "go-prev": lambda *_: self.go_prev(),
            "go-next": lambda *_: self.go_next(),
            "download": lambda *_: self.start_download(),
            "toggle-favorite": lambda *_: self.toggle_favorite(),
            "show-favorites": lambda *_: self.open_favorites(),
            "show-downloads": lambda *_: self.open_downloads(),
            "show-page": lambda *_: self.open_page_view(),
            "preferences": lambda *_: self.open_preferences(),
            "reload": lambda *_: self.reload(),
            "fullscreen": lambda *_: self.toggle_fullscreen(),
            # separada do toggle: Esc só SAÍ da tela cheia, nunca entra
            "leave-fullscreen": lambda *_: self.unfullscreen(),
            "apply-wallpaper": lambda *_: self.start_apply(),
        }
        for name, handler in handlers.items():
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", handler)
            self.add_action(action)

        # estado inicial do ▦ sincronizado AQUI, depois das ações: o
        # GTK ressincroniza a sensibilidade do botão com o estado da
        # ação quando ela entra no mapa — um set_sensitive(False) no
        # _build_ui seria engolido por este add_action
        self._sync_page_button()

        # mantém ícone e HeaderBar em sincronia com o estado real da janela
        self.connect("notify::fullscreened", self._on_fullscreened)

    def toggle_fullscreen(self):
        if self.is_fullscreen():
            self.unfullscreen()
        else:
            self.fullscreen()

    def _on_fullscreened(self, *_args):
        fullscreen = self.is_fullscreen()
        if fullscreen == self._fullscreen:
            return
        self._fullscreen = fullscreen
        # em tela cheia a barra da janela some — sem config e sem os
        # controles da GNOME; Esc volta
        self._sync_fullscreen_ui()

    def _sync_fullscreen_ui(self):
        """Ícone do ⛶ e HeaderBar seguem o estado de tela cheia real."""
        fullscreen = self._fullscreen
        self.header.set_visible(not fullscreen)
        self.btn_fs.set_icon_name(
            "view-restore-symbolic" if fullscreen else "view-fullscreen-symbolic")
        self.btn_fs.set_tooltip_text(
            t("Leave fullscreen  ·  F") if fullscreen
            else t("Fullscreen  ·  F"))

    def open_preferences(self):
        dialog = build_preferences(self, self.settings)
        self.prefs_dialog = dialog

        def _closed(_dialog, *_args):
            # fecha-req do GTK4 não é destroy: dá para confiar em
            # fechar a referência por aqui (o config já soltou os listeners)
            if self.prefs_dialog is dialog:
                self.prefs_dialog = None
            return False

        dialog.connect("close-request", _closed)
        dialog.present()

    # ------------------------------------------------------------------
    # Preferências
    # ------------------------------------------------------------------
    def _on_settings_changed(self, key):
        if key == "ui.language":
            # o settings já gravou; aqui só se certifica de que o
            # idioma está ativo antes de remontar (cobre o reset também)
            set_idioma(self.settings.get("ui.language"))
            self._rebuild_ui()
        elif key == "search.q":
            # O termo só muda quando o usuário confirma com Enter.
            self.reload()
        elif key.startswith("search."):
            # Marcações/filtros: espere 2 s após a última alteração.
            self._schedule_filter_reload()
        elif key == "download.folder":
            self._refresh_download_badge()
            self._refresh_apply_badge()
        elif key == "cache.max-mb":
            self.images.enforce_limit(
                self.settings.get_int("cache.max-mb", 100) * 1024 * 1024
            )

    # ------------------------------------------------------------------
    # Busca e navegação
    # ------------------------------------------------------------------
    def _cancel_filter_reload(self):
        if self._filter_search_source:
            GLib.source_remove(self._filter_search_source)
            self._filter_search_source = 0

    def _schedule_filter_reload(self):
        self._cancel_filter_reload()
        self._filter_search_source = GLib.timeout_add(
            FILTER_SEARCH_DELAY_MS, self._apply_filter_reload
        )

    def _apply_filter_reload(self):
        self._filter_search_source = 0
        self.reload()
        return GLib.SOURCE_REMOVE

    def reload(self):
        self._cancel_filter_reload()
        if self._busy:
            # Não descarte a pesquisa nova enquanto a API responde à velha.
            self._reload_queued = True
            return
        self._reload_queued = False
        self.load_page(1, index=0)

    def _query_fingerprint(self):
        """Assinatura dos filtros atuais, sem a página.

        Mudou a assinatura, mudou o resultado: vale limpar o cache de
        páginas da sessão.
        """
        query = build_query(self.settings, page=1)
        query.pop("page", None)
        return json.dumps(query, sort_keys=True)

    def _drop_page_cache(self):
        self._pages.clear()
        self._fingerprint = None

    def load_page(self, page=1, index=0):
        if self._busy:
            return

        fingerprint = self._query_fingerprint()
        if fingerprint != self._fingerprint:
            self._drop_page_cache()
            self._fingerprint = fingerprint

        cached = self._pages.get(page)
        if cached is not None:
            # já temos esta página: mesmas imagens, sem rede e sem
            # spinner — nada a esperar
            self._on_page(cached, index)
            return

        self._busy = True
        self._set_loading(True)
        self.api.search(
            page=page,
            on_done=lambda result: self._on_page(result, index),
            on_error=self._on_error,
        )

    def _on_page(self, result, index):
        self._busy = False
        if self._reload_queued:
            # A resposta antiga não deve substituir a pesquisa mais nova.
            self.reload()
            return
        meta = result.get("meta", {}) or {}
        self.items = result.get("data", []) or []
        self.page = int(meta.get("current_page", 1) or 1)
        self.last_page = int(meta.get("last_page", 1) or 1)
        self.total = int(meta.get("total", 0) or 0)
        self.index = self._clamp_index(index)
        self._sync_page_button()

        self._remember_page()

        if not self.items:
            self._set_loading(False)
            self.picture.set_paintable(None)
            self.toast(t("No wallpapers found with these filters"))
            return
        self.show_current()

    def _clamp_index(self, index):
        if not self.items:
            return 0
        if index == LAST:
            return len(self.items) - 1
        return max(0, min(index, len(self.items) - 1))

    def _remember_page(self):
        if not self.items:
            return
        self._pages.pop(self.page, None)
        self._pages[self.page] = {
            "data": self.items,
            "meta": {
                "current_page": self.page,
                "last_page": self.last_page,
                "total": self.total,
            },
        }
        while len(self._pages) > PAGE_CACHE_MAX:
            self._pages.popitem(last=False)

    def _on_error(self, error):
        self._busy = False
        if self._reload_queued:
            self.reload()
            return
        self._set_loading(False)
        self.picture.set_paintable(None)
        self.toast(getattr(error, "message", str(error)))

    # -- navegação ------------------------------------------------------
    def go_next(self):
        if self._fav_context:
            self._leave_favorites()
            return
        if not self.items:
            self.load_page(1)
            return
        if self.index + 1 < len(self.items):
            self.index += 1
            self.show_current()
        elif self.page < self.last_page:
            self.load_page(self.page + 1, index=0)
        else:
            self.toast(t("End of results — %s wallpapers") % num(self.total))

    def go_prev(self):
        if self._fav_context:
            self._leave_favorites()
            return
        if not self.items:
            return
        if self.index > 0:
            self.index -= 1
            self.show_current()
        elif self.page > 1:
            # entra pelo último item da página anterior — a navegação não
            # tem fronteira: passar do primeiro item de uma página te
            # devolve no fim da anterior, com as mesmas imagens
            self.load_page(self.page - 1, index=LAST)

    def current(self):
        if 0 <= self.index < len(self.items):
            return self.items[self.index]
        return None

    # ------------------------------------------------------------------
    # Exibição
    # ------------------------------------------------------------------
    def show_current(self):
        wallpaper = self.current()
        if wallpaper is None:
            return

        self._gen += 1
        gen = self._gen

        # thumbnail aparece na hora
        self._set_loading(True)
        self.images.load(
            wallpaper["thumbs"]["large"],
            lambda tex: self._apply_thumb(tex, gen),
            max_side=THUMB_SCALE,
        )

        # imagem completa troca depois, quando estabilizar
        GLib.timeout_add(
            FULL_SWAP_DELAY_MS, self._schedule_full, wallpaper["path"], gen
        )

        self._refresh_download_badge()
        self._refresh_apply_badge()
        self._refresh_fav_badge()
        self._prefetch_next()

    def _schedule_full(self, url, gen):
        if gen != self._gen:
            return False
        self.images.load(
            url,
            lambda tex: self._apply_full(tex, gen),
            max_side=FULL_SCALE,
            persist=False,   # só em RAM: nada gravado, nada recomprimido
        )
        return False

    def _apply_thumb(self, texture, gen):
        if gen != self._gen or texture is None:
            return
        self.picture.set_paintable(texture)
        self._set_loading(False)

    def _apply_full(self, texture, gen):
        if gen != self._gen or texture is None:
            return
        self.picture.set_paintable(texture)

    def _prefetch_next(self):
        nxt = self.index + 1
        if nxt < len(self.items):
            self.images.prefetch(self.items[nxt]["thumbs"]["large"])

    def _set_loading(self, loading):
        # Adw.Spinner anima sozinho enquanto visível (libadwaita >= 1.6)
        self.spinner.set_opacity(1.0 if loading else 0.0)
        self.spinner.set_visible(loading)

    # ------------------------------------------------------------------
    # Download
    # ------------------------------------------------------------------
    def start_download(self):
        """Baixa o wallpaper atual — ou, se já está em disco, oferece
        para apagar (sempre com confirmação: é apagamento permanente)."""
        wallpaper = self.current()
        if wallpaper is None or self._dl_busy:
            return

        folder = self.settings.get("download.folder")
        dest = destination_for(wallpaper, folder)
        name = filename_of(wallpaper)

        # já existe: vira lixeira — pede confirmação antes de apagar
        if os.path.exists(dest):
            self._confirm_delete(dest, name)
            return

        try:
            os.makedirs(folder, exist_ok=True)
        except OSError as exc:
            self.toast(t("Folder unreachable: %s") % exc)
            return

        self._dl_busy = True
        self.btn_dl.add_css_class("spinning")
        self.downloader.download(
            wallpaper["path"],
            dest,
            on_done=lambda ok, info: self._on_downloaded(ok, name, info),
        )

    def _on_downloaded(self, ok, name, info):
        self._dl_busy = False
        self.btn_dl.remove_css_class("spinning")
        if ok:
            self._refresh_download_badge()
            self.toast(t("Downloaded: %s") % name)
        else:
            self.toast(t("Download failed: %s") % info)

    # ------------------------------------------------------------------
    # Apagar download (com confirmação)
    # ------------------------------------------------------------------
    def _confirm_delete(self, dest, name):
        dialog = Adw.AlertDialog.new(
            t("Delete the wallpaper?"),
            t("“%s” will be permanently deleted from disk.") % name,
        )
        dialog.add_response("cancel", t("Cancel"))
        dialog.add_response("delete", t("Delete"))
        dialog.set_response_appearance("delete", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_default_response("cancel")
        dialog.set_close_response("cancel")
        dialog.connect(
            "response",
            lambda _dlg, response: self._on_delete_response(response, dest, name),
        )
        dialog.present(self)

    def _on_delete_response(self, response, dest, name):
        if response != "delete":
            return
        # era o fundo do sistema? precisa saber ANTES de o arquivo sumir
        era_fundo = is_current_background(dest)
        era_aplicado = self._applied_path == dest
        try:
            os.remove(dest)
        except OSError as exc:
            self.toast(t("Could not delete: %s") % exc)
            return
        if era_aplicado:
            self._applied_path = None
        # volta ao fundo anterior; se não há (ou sumiu), não aplica nada
        msg = t("Deleted: %s") % name
        if era_fundo:
            erro_restore, restaurou = restore_previous_background()
            if restaurou:
                msg = t("Deleted — system background restored")
            elif erro_restore:
                msg = t("%s · file deleted") % erro_restore
            else:
                msg = t("Deleted — no previous background to restore")
        self._refresh_download_badge()
        self._refresh_apply_badge()
        self.toast(msg)

    def _refresh_download_badge(self):
        """⤓ vira lixeira vermelha quando o arquivo já está em disco."""
        wallpaper = self.current()
        if wallpaper is None:
            return False
        dest = destination_for(wallpaper, self.settings.get("download.folder"))
        baixado = os.path.exists(dest)
        if baixado:
            self.btn_dl.set_icon_name("user-trash-symbolic")
            self.btn_dl.add_css_class("koia-trash")
            self.btn_dl.set_tooltip_text(t("Delete from disk"))
        else:
            self.btn_dl.set_icon_name("document-save-symbolic")
            self.btn_dl.remove_css_class("koia-trash")
            self.btn_dl.set_tooltip_text(t("Download"))
        return baixado

    # ------------------------------------------------------------------
    # Aplicar como papel de parede
    # ------------------------------------------------------------------
    def start_apply(self):
        """Aplica o wallpaper atual no desktop (GNOME).

        O ``gsettings`` precisa de um arquivo em disco, então se o
        wallpaper ainda não foi baixado ele baixa primeiro — reaproveita
        o mesmo ``Downloader`` do botão ⤓, com a mesma pasta configurada.
        """
        wallpaper = self.current()
        if wallpaper is None or self._dl_busy:
            return

        folder = self.settings.get("download.folder")
        dest = destination_for(wallpaper, folder)

        if os.path.exists(dest):
            self._set_background(dest)
            return

        try:
            os.makedirs(folder, exist_ok=True)
        except OSError as exc:
            self.toast(t("Folder unreachable: %s") % exc)
            return

        self._apply_pending = dest
        self._dl_busy = True
        self.btn_apply.add_css_class("spinning")
        self.toast(t("Downloading to apply…"))
        self.downloader.download(
            wallpaper["path"],
            dest,
            on_done=self._on_applied,
        )

    def _on_applied(self, ok, info):
        self._dl_busy = False
        self.btn_apply.remove_css_class("spinning")
        dest = getattr(self, "_apply_pending", None)
        if not ok:
            self.toast(t("Download failed: %s") % info)
            return
        if dest:
            self._refresh_download_badge()
            self._set_background(dest)

    def _set_background(self, path):
        error = set_as_background(path)
        if error is None:
            self._applied_path = path
            self._refresh_apply_badge()
            self.toast(t("Wallpaper applied"))
        else:
            self.toast(error)

    def _refresh_apply_badge(self):
        """Monitor verde só quando o wallpaper DA TELA é o aplicado."""
        wallpaper = self.current()
        aplicado = False
        if wallpaper is not None and self._applied_path:
            dest = destination_for(
                wallpaper, self.settings.get("download.folder"))
            # o arquivo precisa ainda existir: apagaram por fora?
            aplicado = (self._applied_path == dest and os.path.exists(dest))
        if aplicado:
            self.btn_apply.add_css_class("koia-downloaded")
        else:
            self.btn_apply.remove_css_class("koia-downloaded")

    # ------------------------------------------------------------------
    # Favoritos
    # ------------------------------------------------------------------
    def toggle_favorite(self):
        """Alterna o wallpaper atual nos favoritos (só pelo ♡ flutuante)."""
        wallpaper = self.current()
        if wallpaper is None:
            return
        favorited = self.favorites.toggle(wallpaper)
        self._refresh_fav_badge()
        self.toast(t("Added to favorites") if favorited
                   else t("Removed from favorites"))

    def _refresh_fav_badge(self):
        """Contorno branco quando não é favorito; preenchido e VERMELHO
        (mesmo tom da lixeira) quando é."""
        wallpaper = self.current()
        favorited = (wallpaper is not None
                     and self.favorites.contains(wallpaper["id"]))
        if favorited:
            self.btn_fav.set_icon_name("koia-heart-filled-symbolic")
            self.btn_fav.add_css_class("koia-fav")
            self.btn_fav.set_tooltip_text(t("Remove from favorites"))
        else:
            self.btn_fav.set_icon_name("koia-heart-symbolic")
            self.btn_fav.remove_css_class("koia-fav")
            self.btn_fav.set_tooltip_text(t("Favorite"))
        return favorited

    def open_favorites(self):
        """Abre o diálogo de favoritos (botão na barra inferior)."""
        dialog = build_favorites_dialog(
            self, self.favorites, self.images, self.show_wallpaper,
            on_remove=self._refresh_fav_badge)
        dialog.present(self)

    def open_downloads(self):
        """Abre o diálogo de arquivos baixados (barra inferior)."""
        dialog = build_downloads_dialog(
            self, self.settings.get("download.folder"), self.show_wallpaper)
        dialog.present(self)

    def open_page_view(self):
        """Abre o visor de página (▦ da barra inferior)."""
        # página inteira só existe na navegação normal — favorito e
        # download são "página" de um item só (o botão já nasce
        # apagado nesses casos; a guarda aqui é dupla)
        if not self.items or self._fav_context:
            return
        # o ▦ reabre onde você parou (não a página da janela) — enquanto
        # a janela não sair da página em que você estava; a página
        # lembrada é buscada pelo próprio diálogo e a janela só se move
        # ao clicar numa foto
        guardada = self._page_view_page \
            if self._page_view_window == self.page else None
        page = max(1, min(int(guardada or self.page),
                          self.last_page or 1))
        dialog = build_page_dialog(
            self, page, self.items, self.index,
            self.images, self.jump_to,
            self.fetch_page, self.last_page,
            window_page=self.page,
            on_page=self._remember_page_view,
        )
        dialog.present(self)

    def _remember_page_view(self, page):
        """Guarda a página exibida no ▦ — sem tocar na janela."""
        self._page_view_page = page
        # a página da janela daquele momento: mudando ela, a lembrança
        # vira papel e o ▦ passa a abrir onde a janela está
        self._page_view_window = self.page

    def jump_to(self, page, index):
        """Salta direto pra uma foto — da página atual ou de outra.

        Página atual: troca o índice na hora (setas/dl/favoritar seguem
        normais). Outra página: carrega ela no lugar — cache é
        instantâneo, senão a janela mostra o spinner de sempre.
        """
        if page == self.page and self.items and not self._fav_context:
            self.index = max(0, min(index, len(self.items) - 1))
            self.show_current()
        else:
            self.load_page(page, index=index)

    def fetch_page(self, page, on_done, on_error):
        """Busca uma página SEM trocar o que a janela mostra.

        Cache primeiro (as páginas navegadas ficam guardadas); rede só
        quando não está lá. Responde no MESMO formato da API.
        """
        cached = self._pages.get(page)
        if cached is not None:
            on_done(cached)
            return
        self.api.search(page=page, on_done=on_done, on_error=on_error)

    def _sync_page_button(self):
        """O ▦ só faz sentido com página inteira carregada."""
        self.btn_page.set_sensitive(
            bool(self.items) and not self._fav_context
        )

    def show_wallpaper(self, wallpaper):
        """Mostra um wallpaper direto (vindo do diálogo de favoritos).

        Ele vira uma "página de um item"; as setas voltam para a busca
        anterior — as páginas ficam em cache, então a volta é instantânea
        e com as MESMAS imagens.
        """
        if not self._fav_context:
            self._return_to = (self.page, self.index) if self.items else None
        self._fav_context = True
        self.items = [wallpaper]
        self.index = 0
        self.page = 1
        self.last_page = 1
        self.total = 1
        self._sync_page_button()   # item único: ▦ apaga
        self.show_current()

    def _leave_favorites(self):
        self._fav_context = False
        saved = self._return_to
        self._return_to = None
        if saved:
            self.items = []
            self.load_page(saved[0], index=saved[1])
        else:
            self.reload()

    # ------------------------------------------------------------------
    def toast(self, message):
        toast = Adw.Toast.new(message)
        toast.set_timeout(3)
        self.toast_overlay.add_toast(toast)
