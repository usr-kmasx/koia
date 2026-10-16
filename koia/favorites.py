"""Armazenamento de favoritos — ligado à interface em ``window.py``.

O coração ♡ da barra flutuante (ação ``win.toggle-favorite``, sem
atalho) chama ``KoiaWindow.toggle_favorite``; o coração da HeaderBar
abre o diálogo de favoritos (``favorites_view.py``). Cada wallpaper
guarda o dado cru do wallhaven, então reabrir depois é só reexibir —
sem nova busca.
"""

import json
import os

from gi.repository import GLib


def default_path():
    return os.path.join(GLib.get_user_config_dir(), "koia", "favorites.json")


class FavoritesStore:
    """Lista de wallpapers favoritados persistida em JSON."""

    def __init__(self, path=None):
        self.path = path or default_path()
        self._items = {}
        self._load()

    # ------------------------------------------------------------------
    def _load(self):
        try:
            with open(self.path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, ValueError):
            self._items = {}
            return
        self._items = {w["id"]: w for w in data if isinstance(w, dict) and w.get("id")}

    def _save(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as handle:
            json.dump(list(self._items.values()), handle, indent=2, ensure_ascii=False)
        os.replace(tmp, self.path)

    # ------------------------------------------------------------------
    def contains(self, wallpaper_id):
        return wallpaper_id in self._items

    def all(self):
        return list(self._items.values())

    def __len__(self):
        return len(self._items)

    def add(self, wallpaper):
        self._items[wallpaper["id"]] = wallpaper
        self._save()

    def remove(self, wallpaper_id):
        if self._items.pop(wallpaper_id, None) is not None:
            self._save()

    def toggle(self, wallpaper):
        """Devolve ``True`` se passou a ser favorito."""
        if self.contains(wallpaper["id"]):
            self.remove(wallpaper["id"])
            return False
        self.add(wallpaper)
        return True
