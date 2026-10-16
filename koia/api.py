"""Cliente da API pública do wallhaven.cc (https://wallhaven.cc/api/v1).

Toda requisição roda numa thread e o resultado é entregue na thread principal
via ``GLib.idle_add`` — a interface nunca trava.
"""

import json
import threading
import urllib.parse

import gi

gi.require_version("Soup", "3.0")
from gi.repository import GLib, Soup  # noqa: E402

SEARCH_URL = "https://wallhaven.cc/api/v1/search"
USER_AGENT = "Koia/1.0 (wallpaper viewer; +https://wallhaven.cc)"


class APIError(Exception):
    """Erro de rede ou de resposta da API."""


def mask3(raw, default="100"):
    """Valida um bitmask de 3 dígitos (categories / purity)."""
    raw = (raw or "").strip()
    if len(raw) != 3 or any(c not in "01" for c in raw) or raw == "000":
        return default
    return raw


def build_query(settings, page=1):
    """Traduz as preferências salvas nos parâmetros aceitos pela API."""
    query = {
        "page": str(page),
        "categories": mask3(settings.get("search.categories"), "111"),
        "purity": mask3(settings.get("search.purity"), "100"),
        "sorting": settings.get("search.sorting") or "toplist",
        "order": settings.get("search.order") or "desc",
    }

    q = settings.get("search.q").strip()
    if q:
        query["q"] = q

    if query["sorting"] == "toplist":
        query["topRange"] = settings.get("search.toprange") or "1w"

    atleast = settings.get("search.atleast").strip()
    if atleast:
        query["atleast"] = atleast

    resolutions = settings.get("search.resolutions").strip()
    if resolutions:
        query["resolutions"] = resolutions

    ratios = settings.get("search.ratios").strip()
    if ratios:
        query["ratios"] = ratios

    colors = settings.get("search.colors").strip()
    if colors:
        query["colors"] = colors

    apikey = settings.get("search.apikey").strip()
    if apikey:
        query["apikey"] = apikey

    return query


def query_string(settings, page=1):
    return urllib.parse.urlencode(build_query(settings, page))


class WallhavenAPI:
    """Cliente stateless: cada chamada monta a URL a partir das preferências."""

    def __init__(self, settings, session=None):
        self.settings = settings
        self.session = session or Soup.Session.new()
        self.session.set_user_agent(USER_AGENT)
        self.session.set_timeout(45)
        self.last_query = None

    # ------------------------------------------------------------------
    def search(self, page=1, on_done=None, on_error=None):
        """Busca assíncrona. ``on_done(dict)`` / ``on_error(APIError)``."""
        query = build_query(self.settings, page)
        self.last_query = query
        url = SEARCH_URL + "?" + urllib.parse.urlencode(query)

        def work():
            try:
                result = self._request(url)
            except Exception as exc:  # rede, JSON inválido, HTTP de erro
                GLib.idle_add(_emit_error, on_error, exc)
                return
            GLib.idle_add(_emit_done, on_done, result)

        threading.Thread(target=work, daemon=True, name="koia-api").start()

    def _request(self, url):
        message = Soup.Message.new("GET", url)
        try:
            body = self.session.send_and_read(message, None)
        except GLib.Error as exc:
            raise APIError(f"Falha de rede: {exc.message}") from exc

        status = message.get_status()
        if status == 429:
            raise APIError("Limite de requisições atingido (45/min). Aguarde um instante.")
        if status == 401:
            raise APIError("A chave de API foi recusada pelo wallhaven.cc.")
        if status == 404:
            raise APIError("Página não encontrada.")
        if status != 200:
            raise APIError(f"O wallhaven.cc respondeu HTTP {status}.")

        try:
            return json.loads(bytes(body.get_data()).decode("utf-8"))
        except (ValueError, TypeError) as exc:
            raise APIError("Resposta inválida do servidor.") from exc


def _emit_done(callback, result):
    if callback:
        try:
            callback(result)
        except Exception as exc:  # pragma: no cover
            print(f"[koia] callback de sucesso falhou: {exc}")
    return False


def _emit_error(callback, error):
    if not isinstance(error, APIError):
        error = APIError(str(error))
    if callback:
        try:
            callback(error)
        except Exception as exc:  # pragma: no cover
            print(f"[koia] callback de erro falhou: {exc}")
    return False
