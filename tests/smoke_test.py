"""Lógica do KoiaTray sem criar indicador real nem tocar settings.

- Indicator.new substituído por stub (sem D-Bus, sem ícone na tela)
- _write_key/_start_slide_timer/_stop_slide_timer/set_as_background
  interceptados: só registram chamadas
Asserts de: estrutura do menu, grupos de radio, labels dinâmicos,
sensibilidade por pasta vazia, handlers de slide/pausa e o fluxo
de "Sair".
"""
import os
import sys

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("AyatanaAppIndicator3", "0.1")
from gi.repository import AyatanaAppIndicator3, Gtk  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import koia.tray as T  # noqa: E402


class StubIndicator:
    def __init__(self):
        self.status = None
        self.title = None
        self.menu = None

    def set_title(self, v):
        self.title = v

    def set_status(self, v):
        self.status = v

    def set_menu(self, m):
        self.menu = m


# --- interceptações --------------------------------------------------------
writes = []
starts = []
stops = []
applied = []
T._write_key = lambda k, v: writes.append((k, v))
T.KoiaTray._start_slide_timer = \
    lambda self, first_immediate=True: starts.append(first_immediate)
T.KoiaTray._stop_slide_timer = lambda self: stops.append(True)
T.set_as_background = lambda path: applied.append(path)

AyatanaAppIndicator3.Indicator.new = \
    staticmethod(lambda *a: StubIndicator())

# --- construção ------------------------------------------------------------
app = T.KoiaTray()
app._slide_choice = ""     # estado conhecido p/ este teste
app._paused = False
app._build_indicator_and_menu()

ind = app.indicator
assert isinstance(ind, StubIndicator), "indicator stub não aplicado"
assert ind.title == "Koia Tray"
assert ind.menu is not None, "set_menu não chamado"

menu = ind.menu
# SeparatorMenuItem É subclasse de MenuItem (aparece com label '') —
# filtra para checar só os itens de ação
labels = [c.get_label() for c in menu.get_children()
          if isinstance(c, Gtk.MenuItem)
          and not isinstance(c, Gtk.SeparatorMenuItem)]
assert labels == ["Abrir", "Próximo", "Anterior", "Slide koia",
                  "Pausar", "Sair"], labels
sep = [c for c in menu.get_children()
       if isinstance(c, Gtk.SeparatorMenuItem)]
assert len(sep) == 1, "falta o separador antes de Sair"

# submenu do slide: Desligado + Segundos + Minutos
slide_item = menu.get_children()[3]
assert slide_item.get_label() == "Slide koia"
submenu = slide_item.get_submenu()
kids = submenu.get_children()
assert [k.get_label() for k in kids] == ["Desligado", "Segundos", "Minutos"], \
    [k.get_label() for k in kids]

# grupos de radio: Segundos tem 5, Minutos tem 5, todos do MESMO grupo
off = kids[0]
assert off.get_active(), "com slide vazio, 'Desligado' deve estar ativo"
sec_radios = kids[1].get_submenu().get_children()
min_radios = kids[2].get_submenu().get_children()
assert [r.get_label() for r in sec_radios] == \
    ["5 s", "10 s", "15 s", "30 s", "60 s"]
assert [r.get_label() for r in min_radios] == \
    ["1 min", "3 min", "5 min", "30 min", "60 min"]
assert sec_radios[0].get_group() == off.get_group(), \
    "radios de segundos fora do grupo"
assert min_radios[0].get_group() == off.get_group(), \
    "radios de minutos fora do grupo"
# exclusão mútua real
sec_radios[2].set_active(True)
assert sec_radios[2].get_active() and not off.get_active()

# --- labels/sensibilidade ---------------------------------------------------
app.window_open = None
app._refresh_menu_state()
assert app.menu_items["open_close"].get_label() == "Abrir"
app.window_open = True
app._refresh_menu_state()
assert app.menu_items["open_close"].get_label() == "Fechar"

app._slide_choice = "10s"
app._paused = False
app._refresh_menu_state()
assert app.menu_items["pause"].get_label() == "Pausar"
assert app.menu_items["pause"].get_sensitive()
app._paused = True
app._refresh_menu_state()
assert app.menu_items["pause"].get_label() == "Retomar"
app._slide_choice = ""
app._refresh_menu_state()
assert not app.menu_items["pause"].get_sensitive(), \
    "Pausar deve ficar insensível com slide desligado"

# pasta inexistente → Próximo/Anterior sensíveis? devem ficar INSENSÍVEIS
app._download_folder = lambda: "/nonexistent-dir/xyz"
app._refresh_menu_state()
assert not app.menu_items["next"].get_sensitive()
assert not app.menu_items["prev"].get_sensitive()

# --- handlers de slide ------------------------------------------------------
writes.clear()
starts.clear()
stops.clear()

class FakeItem:
    def __init__(self, active):
        self._a = active

    def get_active(self):
        return self._a

# escolher 5s: grava, limpa pausa, liga timer
app._on_slide_choice(FakeItem(True), "5s")
assert app._slide_choice == "5s" and not app._paused
assert ("tray.slide-choice", "5s") in writes
assert ("tray.slide-paused", "false") in writes
assert starts == [True], starts  # 1ª troca imediata

# re-clicar no mesmo: no-op
writes.clear()
starts.clear()
app._on_slide_choice(FakeItem(True), "5s")
assert writes == [] and starts == []

# toggled vindo do item DESATIVADO (troca de grupo): no-op
app._on_slide_choice(FakeItem(False), "10s")
assert app._slide_choice == "5s"

# Desligado: para timer, zera escolha e pausa
stops.clear()
writes.clear()
app._on_slide_off(FakeItem(True))
assert app._slide_choice == "" and not app._paused
assert stops == [True]
assert ("tray.slide-choice", "") in writes

# Desligado quando já estava desligado: no-op
writes.clear()
stops.clear()
app._on_slide_off(FakeItem(True))
assert writes == [] and stops == []

# pausa/retomar
app._slide_choice = "15s"
app._paused = False
writes.clear()
stops.clear()
starts.clear()
app._on_pause_resume()
assert app._paused and stops == [True]
assert ("tray.slide-paused", "true") in writes
app._on_pause_resume()
assert not app._paused and starts == [False]  # sem troca imediata

# pausa sem slide ativo: no-op
app._slide_choice = ""
writes.clear()
app._on_pause_resume()
assert writes == [] and app._paused is False

# --- intervalo -----------------------------------------------------------
app._slide_choice = "60s"
assert app._slide_interval() == 60
app._slide_choice = "3m"
assert app._slide_interval() == 180
app._slide_choice = ""
assert app._slide_interval() == 0

# --- _jump_and_apply usa a lista de baixados e aplica --------------------
applied.clear()
app._download_folder = lambda: "/nonexistent-dir/xyz"
assert app._jump_and_apply(1) is False, "pasta vazia → nada"
assert applied == []

# --- Sair: Quit entregue, quit SÓ na resposta (ou fallback) ---------------
quits = []
calls = []
app.quit = lambda: quits.append(True)
app._stop_slide_timer = lambda: stops.append(True)


class FakeProxy:
    def call(self, method, params, flags, timeout, cancellable, cb):
        calls.append((method, cb))

    def call_finish(self, res):
        return None


app.proxy = FakeProxy()
app._on_quit()
assert calls == [("Quit", app._quit_reply)], \
    "Sair deve chamar Quit com callback"
assert quits == [], "quit ANTES da entrega do Quit()!"
# resposta chega → aí sim encerra
app._quit_reply(None, object())
assert quits == [True]

# sem proxy (app morto): sai direto
quits.clear()
app.proxy = None
app._on_quit()
assert quits == [True]

# fallback dispara quit (app não respondeu)
quits.clear()
app._quit_fallback()
assert quits == [True]

print("[koia-smoke] menu/lógica/tray ok")
