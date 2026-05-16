import re
from typing import FrozenSet, Optional, Tuple
from urllib.parse import ParseResult, urlparse, urlunparse

from config import STRICT_ROOT_ONLY_HOSTS


_LINK_RE = re.compile(r"https?://[^\s\"'<>`]+", re.IGNORECASE)


def _basic_url_checks(url: str) -> Tuple[str, ParseResult]:

    if not isinstance(url, str):

        raise ValueError("url должен быть строкой.")

    url = url.strip()

    if not url:

        raise ValueError("Пустой url.")

    if any(c in url for c in " \t\n\r"):

        raise ValueError("В URL есть пробелы или переносы.")

    parsed = urlparse(url)

    if parsed.scheme not in ("http", "https"):

        raise ValueError("URL должен начинаться с http:// или https://.")

    if not parsed.hostname:

        raise ValueError("В URL нет домена (host).")

    if len(url) > 4096:

        raise ValueError("URL слишком длинный.")

    return url, parsed


def _host_requires_strict_root_only(hostname: str) -> bool:

    h = (hostname or "").lower()

    return h in STRICT_ROOT_ONLY_HOSTS


def _root_only_no_query(parsed) -> bool:

    path = parsed.path or ""

    if path not in ("", "/"):

        return False

    if parsed.query:

        return False

    if parsed.fragment:

        return False

    return True


def _normalize_http_url_for_match(url: str) -> str:

    p = urlparse(url.strip())

    netloc = (p.netloc or "").lower()

    if "@" in netloc:

        netloc = netloc.split("@")[-1]

    path = p.path or "/"

    if path != "/" and path.endswith("/"):

        path = path.rstrip("/")

    return urlunparse(
        (
            (p.scheme or "https").lower(),
            netloc,
            path,
            "",
            p.query,
            "",
        )
    )


def _url_matches_allowed(url: str, allowed: FrozenSet[str]) -> bool:

    if not allowed:

        return False

    nu = _normalize_http_url_for_match(url)

    for a in allowed:

        if nu == _normalize_http_url_for_match(a):

            return True

    return False


def collect_urls_from_user_task(task: str) -> FrozenSet[str]:

    if not task:

        return frozenset()

    found = []

    for m in _LINK_RE.finditer(task):

        u = m.group(0).rstrip(").,;]}'\"")

        try:

            cleaned, _parsed = _basic_url_checks(u)

        except ValueError:

            continue

        found.append(cleaned)

    return frozenset(found)


def validate_agent_url(
    url: str,
    *,
    allowed_urls: Optional[FrozenSet[str]] = None,
) -> str:

    allowed = allowed_urls if allowed_urls is not None else frozenset()

    url, parsed = _basic_url_checks(url)

    host = parsed.hostname or ""

    if STRICT_ROOT_ONLY_HOSTS and _host_requires_strict_root_only(host):

        if _url_matches_allowed(url, allowed):

            return url

        if _root_only_no_query(parsed):

            return url

        raise ValueError(
            "Для этого домена действует ограничение: нельзя открывать выдуманный глубокий URL "
            "(путь или ?параметры). Разрешены только главная страница без пути и без query, "
            "либо точный https-адрес, который пользователь целиком вставил в TASK. "
            "Дальше ищи через интерфейс страницы (поле поиска + Enter, клики по ref из снимка)."
        )

    return url


def navigation_is_redundant(current: str, target: str) -> bool:

    try:

        c = urlparse((current or "").strip())

        t = urlparse((target or "").strip())

    except Exception:

        return False

    if not getattr(c, "hostname", None) or not getattr(t, "hostname", None):

        return False

    if (c.hostname or "").lower() != (t.hostname or "").lower():

        return False

    def norm_path(path: str) -> str:

        return ((path or "").rstrip("/") or "")

    cp = norm_path(c.path or "")

    tp = norm_path(t.path or "")

    cq = c.query or ""

    tq = t.query or ""

    if cp == tp and cq == tq:

        return True

    if tp == "" and tq == "":

        return True

    return False
