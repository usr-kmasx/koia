"""Carregamento e cache de imagens.

Exibição em duas etapas: a *thumbnail* aparece quase que instantaneamente
e, meio segundo depois, a imagem completa a substitui quando termina de
baixar.

O que vai para onde:

* **thumbnail** (~20 KB) → disco, em ``<cache>/thumbs``. É o que torna a
  navegação instantânea e é o **único** tipo gravado em disco.
* **imagem completa** (até 20 MB) → **só em RAM**, dentro de um LRU com
  teto de bytes. Guardá-la no disco gastaria ~95% de espaço para exibir
  algo que cabe em 4096 px, e regravá-la significaria recomprimir — perda
  de qualidade. O arquivo original continua acessível pelo botão ⤓, que
  baixa direto do wallhaven para a sua pasta.

O disco tem teto próprio (LRU por data de uso). Tudo roda em thread
própria; a entrega na interface sempre passa por ``GLib.idle_add``.
"""

import hashlib
import os
import threading
from collections import OrderedDict
from urllib.parse import unquote, urlparse

import gi

gi.require_version("Gdk", "4.0")
gi.require_version("Soup", "3.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gdk, GdkPixbuf, GLib, Soup  # noqa: E402

# Lado maior máximo que vai para a textura (evita texturas gigantes)
THUMB_SCALE = 1600
FULL_SCALE = 4096

# Teto de RAM reservado às imagens completas já decodificadas. Uma textura
# de 4096x2304 ocupa ~38 MB, então isso segura 3 ou 4 imagens — o bastante
# para voltar passos curtos sem baixar tudo de novo.
RAM_BUDGET_DEFAULT = 128 * 1024 * 1024

# Quantas gravações em disco entre uma varredura de teto e outra
_ENFORCE_EVERY = 25

_CHUNK = 64 * 1024


def _extension(url):
    path = urlparse(url).path
    ext = os.path.splitext(path)[1].lower()
    if ext not in (".jpg", ".jpeg", ".png", ".webp"):
        ext = ".jpg"
    return ".jpg" if ext == ".jpeg" else ext


def _pixbuf_from_texture(texture):
    """Converte uma ``Gdk.Texture`` em ``GdkPixbuf`` só para poder escalar.

    Usa o ``Gdk.TextureDownloader`` (API atual) em vez de
    ``Gdk.pixbuf_get_from_texture``, que está deprecado desde o GTK 4.12.
    O formato pedido é RGBA sem premultiplicação e o estado de cor sRGB,
    que é o mesmo que o caminho antigo entregava — os pixels saem idênticos.
    """
    downloader = Gdk.TextureDownloader(texture)
    downloader.set_format(Gdk.MemoryFormat.R8G8B8A8)
    downloader.set_color_state(Gdk.ColorState.get_srgb())
    payload, stride = downloader.download_bytes()
    # Copia para um ``bytes`` próprio: o pixbuf abaixo referencia os dados
    # diretamente, então eles têm que sobreviver ao ``scale_simple`` que
    # acontece logo em seguida, dentro desta chamada.
    data = bytes(payload.get_data())
    return GdkPixbuf.Pixbuf.new_from_data(
        data,
        GdkPixbuf.Colorspace.RGB,
        True,
        8,
        texture.get_width(),
        texture.get_height(),
        stride,
    )


def _scaled_texture(texture, max_side):
    """Redimensiona só quando necessário; sem escala não há cópia extra."""
    width, height = texture.get_width(), texture.get_height()
    longest = max(width, height)
    if not max_side or longest <= max_side:
        return texture
    factor = max_side / longest
    pixbuf = _pixbuf_from_texture(texture)
    scaled = pixbuf.scale_simple(
        max(1, round(width * factor)),
        max(1, round(height * factor)),
        GdkPixbuf.InterpType.BILINEAR,
    )
    # ``new_for_pixbuf`` mantém o pixbuf vivo dentro da textura, então os
    # dados escalados ficam válidos enquanto a textura existir.
    return Gdk.Texture.new_for_pixbuf(scaled)


def _texture_from_bytes(data, max_side):
    """Decodifica ``data`` direto da memória (sem passar pelo disco).

    Decodifica com ``Gdk.Texture`` (carregadores do próprio GTK) em vez de
    ``GdkPixbuf``: o caminho do ``GdkPixbuf`` passa pelo glycin, que aborta
    o processo (SIGABRT, não-catchable) com certos arquivos — por exemplo,
    um JPEG com ``XResolution``/``YResolution`` RATIONAL igual a ``0/0``,
    que vira NaN e derruba uma validação de propriedade no meio de uma
    chamada C. ``Gdk.Texture`` só sinaliza erro (``GLib.Error``), que é
    capturado aqui como sempre foi.
    """
    try:
        texture = Gdk.Texture.new_from_bytes(GLib.Bytes.new(data))
    except GLib.Error:
        return None
    if texture is None:
        return None
    return _scaled_texture(texture, max_side)


def _texture_from_file(path, max_side):
    """Lê o arquivo e devolve uma ``Gdk.Texture`` (pode ser ``None``).

    Mesmo motivo do ``_texture_from_bytes``: ``Gdk.Texture`` evita o
    caminho do glycin que pode abortar o processo.
    """
    try:
        texture = Gdk.Texture.new_from_filename(path)
    except GLib.Error:
        return None
    if texture is None:
        return None
    return _scaled_texture(texture, max_side)


class ImageLoader:
    """Baixa imagens em thread, guarda em cache e entrega ``Gdk.Texture``.

    ``max_bytes`` é o teto do disco em cache; ajuste chamando
    ``enforce_limit()`` depois de mudá-lo.
    """

    def __init__(self, cache_dir=None, session=None,
                 ram_budget=RAM_BUDGET_DEFAULT, max_bytes=100 * 1024 * 1024):
        self.cache_dir = cache_dir or os.path.join(
            GLib.get_user_cache_dir(), "koia"
        )
        self.thumb_dir = os.path.join(self.cache_dir, "thumbs")
        os.makedirs(self.thumb_dir, exist_ok=True)
        self.session = session or Soup.Session.new()
        self.session.set_timeout(60)
        self.session.set_user_agent("Koia/1.0 (wallpaper viewer)")
        self.max_bytes = max_bytes

        self._threads = []
        self._lock = threading.Lock()
        # limite simples de threads simultâneas
        self._slots = threading.Semaphore(6)

        # LRU de imagens completas em RAM: url -> Gdk.Texture
        self._ram = OrderedDict()
        self._ram_bytes = 0
        self._ram_budget = ram_budget
        self._ram_lock = threading.Lock()

        self._writes = 0
        self._purge_legacy()

    # ------------------------------------------------------------------
    # Disco
    # ------------------------------------------------------------------
    def cache_path(self, url):
        digest = hashlib.sha1(url.encode("utf-8")).hexdigest()
        return os.path.join(self.thumb_dir, digest + _extension(url))

    def is_cached(self, url):
        path = self.cache_path(url)
        return os.path.exists(path) and os.path.getsize(path) > 0

    def cache_size(self):
        return _tree_size(self.cache_dir)

    def clear(self):
        """Apaga todo o cache em disco. As texturas em RAM continuam válidas."""
        removed = 0
        for root, _dirs, files in os.walk(self.cache_dir):
            for name in files:
                try:
                    os.remove(os.path.join(root, name))
                    removed += 1
                except OSError:
                    pass
        self._writes = 0
        return removed

    def enforce_limit(self, max_bytes=None):
        """Apaga os arquivos mais antigos até o cache caber no teto.

        A ordem é a data de acesso (``touch`` a cada leitura), então sai
        primeiro o que você olhou há mais tempo. Arquivos ``.part`` estão
        sendo escritos e nunca são tocados. Apagar é seguro: a textura
        exibida vive na RAM, não no arquivo.
        """
        if max_bytes is not None:
            self.max_bytes = max_bytes
        entries = []
        total = 0
        for root, _dirs, files in os.walk(self.cache_dir):
            for name in files:
                if name.endswith(".part"):
                    continue
                path = os.path.join(root, name)
                try:
                    total += os.path.getsize(path)
                    entries.append((os.path.getmtime(path), path))
                except OSError:
                    continue
        if total <= self.max_bytes:
            return 0

        # ordem decisiva: primeiro sai o arquivo de uso mais antigo
        entries.sort()

        freed = 0
        for _mtime, path in entries:
            if total - freed <= self.max_bytes:
                break
            try:
                freed += os.path.getsize(path)
                os.remove(path)
            except OSError:
                continue
        return freed

    def _purge_legacy(self):
        """Remove os arquivos do formato antigo.

        Antes, as imagens completas e as thumbs se misturavam no mesmo
        diretório (chegou a ocupar meio GB). Agora só as thumbs são
        gravadas, dentro de ``thumbs/``: qualquer arquivo solto no
        diretório raiz é resto antigo que nada mais vai ler.
        """
        try:
            names = os.listdir(self.cache_dir)
        except OSError:
            return
        for name in names:
            path = os.path.join(self.cache_dir, name)
            if not os.path.isfile(path):
                continue
            try:
                os.remove(path)
            except OSError:
                pass

    @staticmethod
    def _touch(path):
        # data de acesso = critério de ordenação do LRU em disco
        try:
            os.utime(path, None)
        except OSError:
            pass

    # ------------------------------------------------------------------
    # RAM (imagens completas)
    # ------------------------------------------------------------------
    def _ram_get(self, url):
        with self._ram_lock:
            texture = self._ram.get(url)
            if texture is not None:
                self._ram.move_to_end(url)
            return texture

    def _ram_put(self, url, texture):
        size = texture.get_width() * texture.get_height() * 4
        with self._ram_lock:
            previous = self._ram.pop(url, None)
            if previous is not None:
                self._ram_bytes -= _texture_bytes(previous)
            self._ram[url] = texture
            self._ram_bytes += size
            # sempre deixa a recém-guardada: uma textura maior que o teto
            # inteiro não pode se evaporar sozinha
            while self._ram_bytes > self._ram_budget and len(self._ram) > 1:
                _url, victim = self._ram.popitem(last=False)
                self._ram_bytes -= _texture_bytes(victim)

    # ------------------------------------------------------------------
    def prefetch(self, url, max_side=THUMB_SCALE):
        """Aquece o cache sem entregar textura (usado para a próxima imagem)."""
        if self.is_cached(url):
            return
        self._spawn(url, max_side, callback=None, persist=True)

    # ------------------------------------------------------------------
    def load(self, url, callback, max_side=THUMB_SCALE, persist=True):
        """Baixa (ou lê do cache) e chama ``callback(Gdk.Texture | None)``.

        ``persist=False`` deixa a imagem completa só em RAM: nada é gravado
        no disco e nada é recomprimido — a textura vem direto dos bytes
        originais.
        """
        self._spawn(url, max_side, callback, persist)

    def _spawn(self, url, max_side, callback, persist=True):
        def work():
            self._slots.acquire()
            try:
                texture = self._load_blocking(url, max_side, persist)
            finally:
                self._slots.release()
            if callback is not None:
                GLib.idle_add(_deliver, callback, texture)

        thread = threading.Thread(target=work, daemon=True, name="koia-image")
        thread.start()
        with self._lock:
            self._threads = [t for t in self._threads if t.is_alive()]
            self._threads.append(thread)

    def _load_blocking(self, url, max_side, persist):
        """Roda na thread. Devolve a ``Gdk.Texture`` ou ``None``."""
        if not persist:
            texture = self._ram_get(url)
            if texture is not None:
                return texture
            texture = self._download(url, None, max_side)
            if texture is not None:
                self._ram_put(url, texture)
            return texture

        path = self.cache_path(url)
        if os.path.exists(path) and os.path.getsize(path) > 0:
            self._touch(path)
            return _texture_from_file(path, max_side)

        texture = self._download(url, path, max_side)
        if texture is not None:
            self._writes += 1
            if self._writes % _ENFORCE_EVERY == 0:
                self.enforce_limit()
        return texture

    def _download(self, url, dest, max_side):
        """Baixa ``url`` e devolve a textura (ou ``None`` em falha).

        ``dest`` recebe os bytes originais, sem recompressão. Quando é
        ``None`` nada é gravado — a imagem completa só passa pela RAM.
        ``file://`` lê o arquivo do disco direto, sem rede (usado pelos
        wallpapers já baixados).
        """
        if urlparse(url).scheme == "file":
            data = _read_local_file(url)
        else:
            message = Soup.Message.new("GET", url)
            try:
                body = self.session.send_and_read(message, None)
            except GLib.Error:
                return None
            if message.get_status() != 200:
                return None
            data = bytes(body.get_data())
        if not data:
            return None

        texture = _texture_from_bytes(data, max_side)
        if dest is not None:
            try:
                tmp = dest + ".part"
                with open(tmp, "wb") as handle:
                    handle.write(data)
                os.replace(tmp, dest)
            except OSError:
                pass
        return texture


def _read_local_file(url):
    """Bytes brutos de um ``file://`` — arquivo local, sem rede."""
    path = unquote(urlparse(url).path)
    try:
        with open(path, "rb") as handle:
            return handle.read()
    except OSError:
        return b""


def _texture_bytes(texture):
    return texture.get_width() * texture.get_height() * 4


def _tree_size(root):
    """Tamanho do cache em disco.

    Arquivos ``.part`` são temporários de escrita e ficam de fora — o
    teto do LRU também os ignora, então o número mostrado no painel e o
    que o teto governa são a mesma coisa.
    """
    total = 0
    for _dirpath, _dirs, files in os.walk(root):
        for name in files:
            if name.endswith(".part"):
                continue
            try:
                total += os.path.getsize(os.path.join(_dirpath, name))
            except OSError:
                continue
    return total


def _deliver(callback, texture):
    try:
        callback(texture)
    except Exception as exc:  # pragma: no cover
        print(f"[koia] callback de imagem falhou: {exc}")
    return False
