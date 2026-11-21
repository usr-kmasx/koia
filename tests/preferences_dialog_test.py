#!/usr/bin/env python3
"""PreferencesDialog: apresentação integrada, foco, fechar e reset sem janela visível."""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Adw, Gio, GLib, Gtk

from koia.config import Settings
from koia.window import KoiaWindow

Gtk.init()
Adw.init()
app = Adw.Application(application_id='org.koia.PreferencesDialogTest',
                      flags=Gio.ApplicationFlags.NON_UNIQUE)
app.register()
settings = Settings(path=os.path.join(tempfile.mkdtemp(prefix='koia-prefs-'),
                                      'settings.ini'))
win = KoiaWindow(app, settings)


def preorder(root):
    yield root
    child = root.get_first_child()
    while child is not None:
        yield from preorder(child)
        child = child.get_next_sibling()


def row(dialog, title):
    return next(w for w in preorder(dialog)
                if isinstance(w, Adw.PreferencesRow)
                and w.get_title() == title)


def reset_button(dialog):
    return next(w for w in preorder(dialog)
                if isinstance(w, Gtk.Button) and w.get_label() == 'Restore')


def alert():
    return next(w for w in preorder(win) if isinstance(w, Adw.AlertDialog))


def drain_rebuild():
    for _ in range(60):
        if not win._prefs_rebuild_pending:
            break
        assert GLib.MainContext.default().pending(), 'rebuild sem callback de closed'
        GLib.MainContext.default().iteration(False)
    assert not win._prefs_rebuild_pending


original_gallery = win.toast_overlay
assert len(settings._listeners) == 1
win.open_preferences()
dialog = win.prefs_dialog
assert isinstance(dialog, Adw.PreferencesDialog)
assert dialog.get_search_enabled(), 'pesquisa das opções desapareceu'
assert dialog.get_title() == 'Settings'
assert (dialog.get_content_width(), dialog.get_content_height()) == (620, 680)
assert dialog.get_parent() is not None, 'diálogo não foi integrado à janela'
assert win.toast_overlay is original_gallery, 'o diálogo substituiu a galeria'
assert row(dialog, 'Search term')
assert row(dialog, 'Direction')
assert row(dialog, 'Restore defaults')
assert len(settings._listeners) == 2

# Acionar o botão de configuração novamente não empilha diálogos nem listeners.
win.open_preferences()
assert win.prefs_dialog is dialog and len(settings._listeners) == 2

# A ordenação não-Toplist tira o campo do percurso por Tab.
settings.set('search.sorting', 'random')
toplist = row(dialog, 'Toplist period')
assert not toplist.get_sensitive() and not toplist.get_focusable()
assert not toplist.grab_focus()

# Confirmação de reset deve ser outro Adw.Dialog, dentro da janela, e
# Cancelar não altera os ajustes nem fecha Configurações.
reset_button(dialog).emit('clicked')
confirm = alert()
assert isinstance(confirm, Adw.AlertDialog)
assert confirm.get_heading() == 'Restore defaults?'
assert confirm.get_response_label('cancel') == 'Cancel'
assert confirm.get_response_label('reset') == 'Restore'
confirm.emit('response', 'cancel')
if confirm.get_parent() is not None:
    confirm.close()
assert settings.get('search.sorting') == 'random'
assert win.prefs_dialog is dialog and len(settings._listeners) == 2

# Reset avisa a janela sobre a troca de idioma e fecha o painel anterior;
# somente depois do sinal closed cria o novo PreferencesDialog.
reset_button(dialog).emit('clicked')
confirm = alert()
confirm.emit('response', 'reset')
if confirm.get_parent() is not None:
    confirm.close()
assert settings.get('search.sorting') == 'toplist'
drain_rebuild()
new_dialog = win.prefs_dialog
assert isinstance(new_dialog, Adw.PreferencesDialog)
assert new_dialog is not dialog
assert row(new_dialog, 'Toplist period').get_sensitive()
assert row(new_dialog, 'Toplist period').get_focusable()
assert len(settings._listeners) == 2, 'o diálogo antigo deixou um listener órfão'

# A animação de fechar usa o sinal "closed", não close-request.
new_dialog.close()
assert win.prefs_dialog is None
assert len(settings._listeners) == 1
win.open_preferences()
assert len(settings._listeners) == 2
win.prefs_dialog.close()
assert len(settings._listeners) == 1

# O gesto deve existir apenas no diálogo, capturando cliques no escurecido.
# O conteúdo do PreferencesDialog é um ToastOverlay, diferente da grade
# simples de Favoritos. Validar que cliques dentro não fecham e fora fecham.
win.open_preferences()
click_dialog = win.prefs_dialog
controllers = click_dialog.observe_controllers()
gestures = [controllers.get_item(i) for i in range(controllers.get_n_items())
            if isinstance(controllers.get_item(i), Gtk.GestureClick)]
assert len(gestures) == 1, 'falta o gesto de clique fora de Configurações'
gesture = gestures[0]
assert gesture.get_propagation_phase() == Gtk.PropagationPhase.CAPTURE
from koia.favorites_view import _posicao_no_dialogo
child = click_dialog.get_child()
assert child is not None
start_x, start_y = _posicao_no_dialogo(click_dialog, child)
size = child.get_allocation()
gesture.emit('pressed', 1, start_x + size.width / 2, start_y + size.height / 2)
assert win.prefs_dialog is click_dialog, 'clicar dentro fechou Configurações'
assert len(settings._listeners) == 2
# Ponto fora de todos os limites do conteúdo, mesmo com widget sem mapear.
gesture.emit('pressed', 1, start_x + size.width + 100, start_y + size.height + 100)
assert win.prefs_dialog is None, 'clicar no fundo não fechou Configurações'
assert len(settings._listeners) == 1, 'observador vazou no fechamento por clique'
win.open_preferences()
assert win.prefs_dialog is not None and win.prefs_dialog is not click_dialog
win.prefs_dialog.close()
assert len(settings._listeners) == 1

print('[koia-prefs] Adw.PreferencesDialog, busca, alerta, reset, idioma, foco, closed e clique fora: ok')
