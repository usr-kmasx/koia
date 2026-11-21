#!/usr/bin/env python3
"""Painel no topo central: Tab/Shift+Tab, hover restrito e animação.

Testes GTK sem apresentar janela ou acessar rede.
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
gi.require_version('Gdk', '4.0')
from gi.repository import Adw, Gdk, Gio, Gtk  # noqa: E402

Gtk.init()
Adw.init()

from koia.config import Settings  # noqa: E402
from koia.window import KoiaWindow, CONTROLS_HIDE_AFTER_MS  # noqa: E402

app = Adw.Application(application_id='org.koia.KeyboardOnlyControlsTest',
                      flags=Gio.ApplicationFlags.NON_UNIQUE)
app.register()
tmp = tempfile.mkdtemp(prefix='koia-controls-')
win = KoiaWindow(app, Settings(path=os.path.join(tmp, 'settings.ini')))


def controllers(widget):
    model = widget.observe_controllers()
    return [model.get_item(i) for i in range(model.get_n_items())]


def buttons():
    return [win.btn_prev, win.btn_next, win.btn_fav,
            win.btn_dl, win.btn_fs, win.btn_apply,
            win.btn_downloads, win.btn_favorites,
            win.btn_page, win.btn_settings]


def check_layout():
    bar = win.revealer.get_child()
    expected = buttons()
    observed = []
    child = bar.get_first_child()
    while child is not None:
        observed.append(child)
        child = child.get_next_sibling()
    assert observed == expected, 'ordem dos 10 botões alterada'
    assert all(b.has_css_class('koia-control') and b.has_css_class('flat')
               for b in expected), 'CSS dos botões divergente'
    assert [b.get_action_name() for b in expected[-4:]] == [
        'win.show-downloads', 'win.show-favorites',
        'win.show-page', 'win.preferences'
    ]
    # Coração = ação de favoritar foto; marcador = abrir coleção.
    assert win.btn_fav.get_icon_name() == 'koia-heart-symbolic'
    assert win.btn_favorites.get_icon_name() == 'koia-bookmark-symbolic'
    assert win.btn_favorites.get_tooltip_text() == 'Favorites'

    panel_zone = win._panel_hover_zone
    assert win.revealer.get_parent() is panel_zone
    assert panel_zone.get_halign() == Gtk.Align.CENTER
    assert panel_zone.get_valign() == Gtk.Align.START
    assert win.revealer.get_halign() == Gtk.Align.CENTER
    assert win.revealer.get_valign() == Gtk.Align.START
    assert win.revealer.get_margin_top() == 18
    assert win.revealer.get_margin_bottom() == 0
    assert bar.get_margin_top() == 18 and bar.get_margin_bottom() == 10
    motion = [c for c in controllers(panel_zone)
              if isinstance(c, Gtk.EventControllerMotion)]
    assert motion == [win._panel_motion], 'hover não está restrito ao painel'
    assert not any(isinstance(c, Gtk.EventControllerMotion)
                   for c in controllers(bar)), 'hover duplicado nos botões'
    assert not any(isinstance(c, Gtk.EventControllerMotion)
                   for c in controllers(panel_zone.get_parent())), (
        'hover indevido na área inteira da imagem'
    )
    hitbox = panel_zone.get_child()
    assert hitbox.get_opacity() == 0
    assert hitbox.get_margin_start() == 36
    assert hitbox.get_margin_end() == 36
    assert hitbox.get_margin_top() == 36
    assert hitbox.get_margin_bottom() == 10
    placeholders = []
    child = hitbox.get_first_child()
    while child is not None:
        placeholders.append(child)
        child = child.get_next_sibling()
    assert len(placeholders) == 10
    assert all(isinstance(child, Gtk.Button)
               and child.get_icon_name() == button.get_icon_name()
               and child.has_css_class('koia-control')
               and child.has_css_class('flat')
               and not child.get_can_target()
               and not child.get_focusable()
               for child, button in zip(placeholders, expected))
    assert all(b.get_can_target() for b in expected)
    # SLIDE_DOWN revela descendo e recolhe o painel para cima.
    assert win.revealer.get_transition_type() == Gtk.RevealerTransitionType.SLIDE_DOWN
    assert win.revealer.get_transition_duration() == 250
    assert CONTROLS_HIDE_AFTER_MS == 5000


def tab(backward=False):
    key = Gdk.KEY_ISO_Left_Tab if backward else Gdk.KEY_Tab
    mods = Gdk.ModifierType.SHIFT_MASK if backward else Gdk.ModifierType(0)
    return win._controls_keyboard.emit('key-pressed', key, 0, mods)


def expire_for_test():
    # No teste manual, o GLib não remove a source como removeria quando
    # chama o callback automaticamente. Evitar temporizadores órfãos.
    win._cancel_controls_hide_timer()
    return win._hide_controls()


check_layout()
assert win.revealer.get_reveal_child(), 'painel deve nascer visível'
assert win._controls_hide_source, 'prazo inicial de 5 s não foi armado'

# Testa que foco sozinho não sustenta a barra: o prazo vence até se um
# dos botões inferiores estiver com a borda de foco do GTK.
win.set_focus(win.btn_apply)
assert win.get_focus() is win.btn_apply
assert expire_for_test() is False
assert not win.revealer.get_reveal_child(), 'foco prendeu barra aberta'
assert win.get_focus() is not win.btn_apply, 'foco ficou preso em botão oculto'

# Tab abre e começa do primeiro; Shift+Tab abre do último. O primeiro
# evento é consumido, os próximos percorrem normalmente pelo GTK.
assert tab() is True
assert win.revealer.get_reveal_child()
assert win.get_focus() is win.btn_prev
assert win._controls_hide_source
old_timer = win._controls_hide_source
assert tab() is False
assert win._controls_hide_source and win._controls_hide_source != old_timer
assert expire_for_test() is False
assert tab(backward=True) is True
assert win.get_focus() is win.btn_settings
assert tab(backward=True) is False

# Outras teclas não acionam visibilidade nem reiniciam o prazo.
expire_for_test()
assert not win.revealer.get_reveal_child()
assert win._controls_keyboard.emit('key-pressed', Gdk.KEY_a, 0,
                                   Gdk.ModifierType(0)) is False
assert not win.revealer.get_reveal_child()
assert not win._controls_hide_source

# Hover só sobre a barra superior: entra, revela, cancela contagem,
# permanece aberta mesmo após 5 s, sai e retoma a contagem.
class PointerStub:
    def __init__(self, inside=False):
        self.inside = inside

    def contains_pointer(self):
        return self.inside


real_motion = win._panel_motion
pointer = PointerStub()
win._panel_motion = pointer
try:
    # Mouse fora da barra não interfere; foco sozinho não mantém aberto.
    assert not win.revealer.get_reveal_child()
    pointer.inside = True
    win._on_panel_pointer_enter(None, 10, 10)
    assert win.revealer.get_reveal_child()
    assert not win._controls_hide_source, 'hover devia pausar contagem'
    win.set_focus(win.btn_apply)
    assert expire_for_test() is False
    assert win.revealer.get_reveal_child(), 'hover não protegeu o painel'
    assert win.get_focus() is win.btn_apply, 'hover alterou foco do Tab'

    # Mesmo Tab com o ponteiro sobre a barra não pode escondê-la.
    assert tab() is False
    assert win._controls_hide_source
    assert expire_for_test() is False
    assert win.revealer.get_reveal_child()

    # Ao sair, o prazo de 5 s volta a contar.
    pointer.inside = False
    win._on_panel_pointer_leave(None)
    assert win._controls_hide_source
    assert expire_for_test() is False
    assert not win.revealer.get_reveal_child()
finally:
    win._panel_motion = real_motion

# Reconstruir o idioma não cria outro controlador nem timers órfãos.
key_controller = win._controls_keyboard
win._build_ui()
assert win._controls_keyboard is key_controller
assert win._controls_hide_source
check_layout()
assert win.revealer.get_reveal_child()
expire_for_test()
assert tab(backward=True) is True and win.get_focus() is win.btn_settings

print('[koia-panel] 10 botoes, Tab/ShiftTab, 5s, hover local, foco independente, rebuild: ok')
