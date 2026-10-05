"""Recherche web gratuite (DuckDuckGo, sans clé) et lecture de pages."""

import html
import ipaddress
import re
from html.parser import HTMLParser
from urllib.parse import parse_qs, unquote, urlparse

import httpx

DDG_URL = "https://html.duckduckgo.com/html/"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/128.0 Safari/537.36"
    ),
    "Accept-Language": "fr-FR,fr;q=0.9",
}

# Sites d'offres privilégiés pour les recherches d'offres.
JOB_SITES = (
    "indeed.fr", "hellowork.com", "welcometothejungle.com", "francetravail.fr",
    "linkedin.com/jobs", "labonnealternance.apprentissage.beta.gouv.fr",
    "jobteaser.com", "apec.fr", "meteojob.com",
)


class WebSearchError(Exception):
    pass


def _clean(fragment: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", fragment)).strip()


def _real_url(href: str) -> str:
    """DuckDuckGo encapsule les liens : //duckduckgo.com/l/?uddg=<url>."""
    if href.startswith("//"):
        href = "https:" + href
    parsed = urlparse(href)
    if parsed.netloc.endswith("duckduckgo.com") and parsed.path.startswith("/l/"):
        target = parse_qs(parsed.query).get("uddg")
        if target:
            return unquote(target[0])
    return href


def parse_results(page: str) -> list[dict]:
    results = []
    blocks = re.split(r'<div class="result[ "]', page)[1:]
    for block in blocks:
        link = re.search(r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', block, re.S)
        if not link:
            continue
        url = _real_url(html.unescape(link.group(1)))
        if "duckduckgo.com/y.js" in url:  # publicité
            continue
        snippet = re.search(r'class="result__snippet"[^>]*>(.*?)</a>', block, re.S)
        results.append({
            "title": _clean(link.group(2)),
            "url": url,
            "snippet": _clean(snippet.group(1)) if snippet else "",
        })
    return results


async def search(query: str, max_results: int = 8) -> list[dict]:
    try:
        async with httpx.AsyncClient(timeout=20, headers=HEADERS, follow_redirects=True) as client:
            resp = await client.post(DDG_URL, data={"q": query, "kl": "fr-fr"})
    except httpx.HTTPError as exc:
        raise WebSearchError(f"Recherche web impossible : {exc}") from exc
    if resp.status_code != 200:
        raise WebSearchError(f"Le moteur de recherche a répondu {resp.status_code}.")
    return parse_results(resp.text)[:max_results]


def job_query(keywords: str, location: str = "", kind: str = "emploi") -> str:
    words = keywords.strip()
    if kind in ("stage", "alternance") and kind not in words.lower():
        words = f"{kind} {words}"
    sites = " OR ".join(f"site:{s}" for s in JOB_SITES[:5])
    return f"offre {words} {location.strip()} ({sites})".replace("  ", " ")


async def search_jobs(keywords: str, location: str = "", kind: str = "emploi", max_results: int = 10) -> list[dict]:
    return await search(job_query(keywords, location, kind), max_results)


class _TextExtractor(HTMLParser):
    SKIP = {"script", "style", "noscript", "svg", "nav", "footer", "header", "form"}

    def __init__(self):
        super().__init__()
        self.parts: list[str] = []
        self.title = ""
        self._skip = 0
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self._skip += 1
        elif tag == "title":
            self._in_title = True
        elif tag in ("p", "br", "li", "h1", "h2", "h3", "div", "tr"):
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in self.SKIP and self._skip:
            self._skip -= 1
        elif tag == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        elif not self._skip:
            self.parts.append(data)


def html_to_text(page: str) -> tuple[str, str]:
    parser = _TextExtractor()
    parser.feed(page)
    text = re.sub(r"[ \t\r\f\v]+", " ", "".join(parser.parts))
    text = re.sub(r"\n\s*\n+", "\n\n", text).strip()
    return parser.title.strip(), text


def _is_local(hostname: str) -> bool:
    """Empêche l'IA de lire des adresses de la machine ou du réseau local."""
    if hostname == "localhost" or hostname.endswith((".local", ".internal")):
        return True
    try:
        ip = ipaddress.ip_address(hostname)
    except ValueError:
        return False
    return ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved


async def fetch_page(url: str, max_chars: int = 6000) -> dict:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname or _is_local(parsed.hostname):
        raise WebSearchError("Adresse invalide.")
    try:
        async with httpx.AsyncClient(timeout=20, headers=HEADERS, follow_redirects=True) as client:
            resp = await client.get(url)
    except httpx.HTTPError as exc:
        raise WebSearchError(f"Page inaccessible : {exc}") from exc
    if resp.status_code >= 400:
        raise WebSearchError(f"Page inaccessible ({resp.status_code}).")
    if "html" not in resp.headers.get("content-type", "html"):
        raise WebSearchError("Ce lien ne pointe pas vers une page web.")
    title, text = html_to_text(resp.text)
    return {"url": str(resp.url), "title": title, "text": text[:max_chars]}
