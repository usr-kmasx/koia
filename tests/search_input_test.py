#!/usr/bin/env python3
"""Regressão: texto só pesquisa com Enter; filtros esperam 2s; requests não se perdem.

Usa GTK real sem apresentar janelas; API e relógio falsos, sem rede.
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, GLib, Gtk

from koia.config import Settings, build_preferences
from koia.window import KoiaWindow, FILTER_SEARCH_DELAY_MS

Gtk.init()
Adw.init()
app = Adw.Application(application_id="org.koia.SearchInputTest",
                      flags=Gio.ApplicationFlags.NON_UNIQUE)
app.register()
temp = tempfile.mkdtemp(prefix="koia-search-test-")
settings = Settings(path=os.path.join(temp, "settings.ini"))
win = KoiaWindow(app, settings)
calls = []


def api_search(page=1, on_done=None, on_error=None):
    calls.append({
        "page": page,
        "q": settings.get("search.q"),
        "categories": settings.get("search.categories"),
        "order": settings.get("search.order"),
        "done": on_done,
        "error": on_error,
    })


win.api.search = api_search
dialog = build_preferences(win, settings)


def walk(widget):
    seen, refs, stack = set(), [], [widget]
    while stack:
        item = stack.pop()
        if id(item) in seen:
            continue
        seen.add(id(item))
        refs.append(item)
        yield item
        children = []
        child = item.get_first_child()
        while child is not None:
            children.append(child)
            child = child.get_next_sibling()
        stack.extend(reversed(children))


term = next(w for w in walk(dialog)
            if isinstance(w, Adw.EntryRow) and w.get_title() == "Search term")
for partial in ("n", "na", "nat", "nature"):
    term.set_text(partial)
    assert not calls, "digitar disparou chamada à API"
    assert settings.get("search.q") == "", "digitando gravou termo antes do Enter"
term.emit("entry-activated")
assert len(calls) == 1 and calls[0]["q"] == "nature"
assert settings.get("search.q") == "nature"

# Relógio falso: valida o intervalo e o cancelamento dos timers anteriores.
orig_add, orig_remove = GLib.timeout_add, GLib.source_remove
timers, canceled = {}, set()
next_id = [900]


def fake_add(delay, callback, *args):
    assert delay == FILTER_SEARCH_DELAY_MS == 2000
    next_id[0] += 1
    timers[next_id[0]] = (callback, args)
    return next_id[0]


def fake_remove(source):
    canceled.add(source)
    return True


try:
    GLib.timeout_add = fake_add
    GLib.source_remove = fake_remove
    settings.set("search.categories", "101")
    first_id = win._filter_search_source
    settings.set("search.order", "asc")
    second_id = win._filter_search_source
    assert first_id != second_id and first_id in canceled
    assert len(calls) == 1, "marcar filtro pesquisou antes de 2 segundos"
    assert second_id not in canceled
    callback, args = timers[second_id]
    assert callback(*args) is False
    assert len(calls) == 1 and win._reload_queued, (
        "busca durante request ativo não foi enfileirada"
    )
finally:
    GLib.timeout_add = orig_add
    GLib.source_remove = orig_remove

# A resposta antiga não substitui o resultado; busca uma vez com filtros finais.
calls[0]["done"]({"data": [], "meta": {"current_page": 1}})
assert len(calls) == 2, "busca nova foi descartada enquanto API carregava"
assert calls[1]["categories"] == "101" and calls[1]["order"] == "asc"
assert not win._reload_queued

# Enter com outro termo durante a busca também precisa prevalecer sobre erro.
term.set_text("mountain")
assert len(calls) == 2 and settings.get("search.q") == "nature"
term.emit("entry-activated")
assert win._reload_queued and len(calls) == 2
calls[1]["error"](RuntimeError("resposta antiga"))
assert len(calls) == 3 and calls[2]["q"] == "mountain"
assert not win._reload_queued

# Ao pressionar Enter no mesmo termo, mantém a ação de pesquisar.
term.emit("entry-activated")
assert win._reload_queued
calls[2]["done"]({"data": [], "meta": {"current_page": 1}})
assert len(calls) == 4 and calls[3]["q"] == "mountain"

print("[koia-search] Enter, debounce 2s, mudança sucessiva e request em curso: ok")
