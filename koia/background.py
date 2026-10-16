"""Aplicar a imagem atual como papel de parede (somente GNOME).

O ``gsettings`` do GNOME aponta para um **arquivo em disco**
(``picture-uri``), então o wallpaper precisa estar salvo antes — é o
próprio download do Koia que garante isso (ver ``window.start_apply``).

Antes de trocar o fundo, o URI vigente é empilhado em
``~/.config/koia/background.json``; assim, ao apagar o arquivo que está
como papel de parede, dá para **restaurar o anterior**. Se não houver
nada a restaurar (ou o arquivo anterior não existir mais), não se aplica
nada.

Todas as funções devolvem ``None`` em sucesso ("nada a fazer" também é
sucesso) ou uma mensagem pronta para toast; nenhuma lança exceção, para
nunca derrubar a interface.
"""

import json
import os

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib  # noqa: E402

# Esquema do papel de parede do GNOME (tema claro e escuro separados)
BACKGROUND_SCHEMA = "org.gnome.desktop.background"

# Teto da pilha de restauração. O slideshow do tray troca de wallpaper
# a cada N segundos — sem cap ela cresce ad infinitum com o decorrer dos
# dias. O topo sempre sobrevive; o excesso sai pelo fundo (mais antigo).
MAX_PREVIOUS = 50


def default_state_path():
    return os.path.join(GLib.get_user_config_dir(), "koia", "background.json")


# ------------------------------------------------------------------
# Estado: pilha de URIs anteriores (JSON, no padrão do favorites.py)
# ------------------------------------------------------------------
def _load_state(state_path=None):
    path = state_path or default_state_path()
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return []
    prev = data.get("previous") if isinstance(data, dict) else None
    if not isinstance(prev, list):
        return []
    return [u for u in prev if isinstance(u, str) and u]


def _push_previous(uri, state_path=None):
    """Guarda ``uri`` como candidato a restaurar (sem repetir o topo)."""
    path = state_path or default_state_path()
    stack = _load_state(path)
    if uri and (not stack or stack[-1] != uri):
        stack.append(uri)
    _save_state(stack[-MAX_PREVIOUS:], path)


def _save_state(stack, state_path=None):
    path = state_path or default_state_path()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as handle:
            json.dump({"previous": stack}, handle, indent=2,
                      ensure_ascii=False)
        os.replace(tmp, path)
    except OSError:
        pass  # estado é conveniência, nunca pode quebrar a aplicação


def _pop_previous(state_path=None):
    """Retira e devolve o último URI guardado (ou ``None``)."""
    path = state_path or default_state_path()
    stack = _load_state(path)
    if not stack:
        return None
    uri = stack.pop()
    _save_state(stack, path)
    return uri


# ------------------------------------------------------------------
# Leitura do fundo atual (somente leitura, sem efeito colateral)
# ------------------------------------------------------------------
def _settings():
    source = Gio.SettingsSchemaSource.get_default()
    schema = None if source is None else source.lookup(BACKGROUND_SCHEMA, True)
    if schema is None:
        return None
    return Gio.Settings.new_full(schema, None, None)


def get_current_uri():
    """URI do papel de parede vigente ou ``None`` (inacessível/ausente)."""
    settings = _settings()
    if settings is None:
        return None
    try:
        uri = settings.get_string("picture-uri")
    except GLib.Error:
        return None
    return uri or None


def is_current_background(path):
    """``True`` se ``path`` é o arquivo apontado agora pelo GNOME."""
    uri = get_current_uri()
    if not uri or not path:
        return False
    if not uri.startswith("file://"):
        return False
    try:
        current = Gio.File.new_for_uri(uri).get_path()
    except GLib.Error:
        return False
    if current is None:
        return False
    return os.path.abspath(current) == os.path.abspath(path)


# ------------------------------------------------------------------
# Aplicar / restaurar
# ------------------------------------------------------------------
def set_as_background(path, state_path=None):
    """Define ``path`` como papel de parede. Devolve ``None`` ou mensagem."""
    if not path or not os.path.exists(path):
        return "arquivo do wallpaper não encontrado"

    settings = _settings()
    if settings is None:
        return "este ambiente não suporta aplicar wallpaper (só GNOME)"

    try:
        target = GLib.filename_to_uri(os.path.abspath(path), None)
        current = get_current_uri()
        # guarda o vigente para poder voltar atrás; se já apontava para
        # o mesmo arquivo, a pilha não muda (não duplica o topo)
        if current and current != target:
            _push_previous(current, state_path)
        elif not current:
            _save_state([], state_path)
        # os dois porque o GNOME mantém um URI para cada tema
        settings.set_string("picture-uri", target)
        settings.set_string("picture-uri-dark", target)
        settings.apply()
    except GLib.Error as exc:
        return f"não foi possível aplicar: {exc.message}"

    return None


def restore_previous_background(state_path=None):
    """Volta ao fundo anterior ao último ``set_as_background``.

    Devolve ``(erro, aplicou)``: ``erro`` é ``None`` ou mensagem pronta
    para toast; ``aplicou`` diz se o fundo foi mesmo restaurado. Se não
    há anterior guardado, ou o arquivo dele não existe mais, **não
    aplica nada** — o fundo atual só é tocado quando há algo válido para
    restaurar.
    """
    previous = _pop_previous(state_path)
    if not previous:
        return None, False  # nada a restaurar: não aplica nada

    if previous.startswith("file://"):
        try:
            prev_path = Gio.File.new_for_uri(previous).get_path()
        except GLib.Error:
            prev_path = None
        if not prev_path or not os.path.exists(prev_path):
            return None, False  # anterior sumiu: não aplica nada

    settings = _settings()
    if settings is None:
        return "este ambiente não suporta aplicar wallpaper (só GNOME)", False

    try:
        settings.set_string("picture-uri", previous)
        settings.set_string("picture-uri-dark", previous)
        settings.apply()
    except GLib.Error as exc:
        return f"não foi possível restaurar: {exc.message}", False

    return None, True
