"""Download dos wallpapers para a pasta escolhida pelo usuário."""

import os
import threading
from urllib.parse import urlparse

import gi

gi.require_version("Soup", "3.0")
from gi.repository import GLib, Soup  # noqa: E402

_CHUNK = 64 * 1024


def filename_of(wallpaper):
    """Nome original do arquivo, como o site serve (``wallhaven-<id>.jpg``)."""
    return os.path.basename(urlparse(wallpaper["path"]).path)


def destination_for(wallpaper, folder):
    return os.path.join(folder, filename_of(wallpaper))


class Downloader:
    """Baixa um arquivo por vez, com progresso e escrita atômica."""

    def __init__(self, session=None):
        self.session = session or Soup.Session.new()
        self.session.set_timeout(120)
        self.session.set_user_agent("Koia/1.0 (wallpaper viewer)")
        self._active = set()
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    def is_downloaded(self, wallpaper, folder):
        return os.path.exists(destination_for(wallpaper, folder))

    def cancel_all(self):
        with self._lock:
            self._active.clear()

    # ------------------------------------------------------------------
    def download(self, url, dest, on_progress=None, on_done=None):
        """Roda em thread. ``on_done(ok: bool, info: str)`` na thread principal."""
        with self._lock:
            if dest in self._active:
                return False  # já em andamento
            self._active.add(dest)

        def work():
            ok, info = self._run(url, dest, on_progress)
            with self._lock:
                self._active.discard(dest)
            if on_done is not None:
                GLib.idle_add(_deliver, on_done, ok, info)

        threading.Thread(target=work, daemon=True, name="koia-download").start()
        return True

    # ------------------------------------------------------------------
    def _run(self, url, dest, on_progress):
        message = Soup.Message.new("GET", url)
        tmp = dest + ".part"
        try:
            os.makedirs(os.path.dirname(dest), exist_ok=True)
        except OSError as exc:
            return False, f"pasta inacessível: {exc}"
        try:
            stream = self.session.send(message, None)
        except GLib.Error as exc:
            return False, f"falha de rede: {exc.message}"

        if message.get_status() != 200:
            return False, f"HTTP {message.get_status()}"

        total = message.get_response_headers().get_content_length()
        received = 0
        try:
            with open(tmp, "wb") as handle:
                while True:
                    chunk = stream.read_bytes(_CHUNK, None)
                    size = chunk.get_size()
                    if size == 0:
                        break
                    handle.write(chunk.get_data())
                    received += size
                    if on_progress is not None and total > 0:
                        GLib.idle_add(_progress, on_progress, received, total)
        except GLib.Error as exc:
            _cleanup(tmp)
            return False, f"transferência interrompida: {exc.message}"
        except OSError as exc:
            _cleanup(tmp)
            return False, f"não foi possível gravar: {exc}"
        finally:
            try:
                stream.close(None)
            except (GLib.Error, AttributeError):
                pass

        if received == 0:
            _cleanup(tmp)
            return False, "arquivo vazio"

        try:
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            os.replace(tmp, dest)
        except OSError as exc:
            _cleanup(tmp)
            return False, f"não foi possível salvar: {exc}"

        return True, dest


def _cleanup(path):
    try:
        if os.path.exists(path):
            os.remove(path)
    except OSError:
        pass


def _progress(callback, received, total):
    try:
        callback(received, total)
    except Exception:  # pragma: no cover
        pass
    return False


def _deliver(callback, ok, info):
    try:
        callback(ok, info)
    except Exception as exc:  # pragma: no cover
        print(f"[koia] callback de download falhou: {exc}")
    return False
