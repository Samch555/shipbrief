"""Text utilities: HTML stripping, whitespace cleanup, sentence splitting, URL canonicalization."""
from __future__ import annotations

import html
import re
import unicodedata
from html.parser import HTMLParser
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


class _Stripper(HTMLParser):
    SKIP = {"script", "style", "noscript", "iframe", "svg", "head", "template"}
    BLOCK = {"p", "div", "br", "li", "ul", "ol", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "pre", "blockquote", "section"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self._skip += 1
        elif tag in self.BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in self.SKIP and self._skip:
            self._skip -= 1
        elif tag in self.BLOCK:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self._skip:
            self.parts.append(data)


_CTRL = re.compile(r"[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f​-‏‪-‮⁦-⁩]")
_WS = re.compile(r"[ \t\r\f\v]+")
_MD_NOISE = re.compile(r"(!\[[^\]]*\]\([^)]*\))|(\[([^\]]+)\]\([^)]*\))|(`{1,3})|(^#{1,6}\s*)|(\*\*|__)", re.M)


def strip_html(value: str) -> str:
    """HTML -> plain text. Also removes invisible/bidi control chars (prompt-smuggling vectors)."""
    if not value:
        return ""
    if "<" in value or "&" in value:
        p = _Stripper()
        try:
            p.feed(value)
            p.close()
            value = "".join(p.parts)
        except Exception:
            value = re.sub(r"<[^>]+>", " ", value)
        value = html.unescape(value)
    value = unicodedata.normalize("NFKC", value)
    value = _CTRL.sub("", value)
    return value


def clean_text(value: str) -> str:
    """strip_html + markdown noise removal + whitespace collapse (single line)."""
    t = strip_html(value)
    t = _MD_NOISE.sub(lambda m: m.group(3) or "", t)
    t = _WS.sub(" ", t.replace("\n", " "))
    return t.strip()


_SENT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(])")
_ABBREV = re.compile(r"\b(e\.g|i\.e|etc|vs|Dr|Mr|Ms|Inc|Ltd|U\.S|No|Fig|al)\.$")


def sentences(text: str) -> list[str]:
    raw = _SENT.split(text.strip())
    out: list[str] = []
    for s in raw:
        if out and _ABBREV.search(out[-1]):
            out[-1] = f"{out[-1]} {s}"
        else:
            out.append(s)
    return [s.strip() for s in out if s.strip()]


def truncate(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    cut = text[: max_chars - 1]
    if " " in cut:
        cut = cut.rsplit(" ", 1)[0]
    return cut.rstrip(",;:-– ") + "…"


TRACKING_PARAMS = re.compile(r"^(utm_.*|ref|ref_src|ref_url|fbclid|gclid|mc_cid|mc_eid|source|via|cmp|campaign|_hsenc|_hsmi|si)$", re.I)
_ARXIV_VER = re.compile(r"^(/(abs|pdf)/[^/]+?)(v\d+)?(\.pdf)?$")


def canonical_url(url: str) -> str:
    """Normalize a URL for deduplication (not for display)."""
    try:
        parts = urlsplit(url.strip())
    except ValueError:
        return url.strip()
    scheme = "https" if parts.scheme in ("http", "https") else parts.scheme
    host = parts.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    if host.endswith(":443") or host.endswith(":80"):
        host = host.rsplit(":", 1)[0]
    path = parts.path or "/"
    if host in ("arxiv.org", "export.arxiv.org"):
        host = "arxiv.org"
        m = _ARXIV_VER.match(path)
        if m:
            path = m.group(1).replace("/pdf/", "/abs/")
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/")
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if not TRACKING_PARAMS.match(k)]
    if host == "news.ycombinator.com":
        query = [(k, v) for k, v in query if k == "id"]
    query.sort()
    return urlunsplit((scheme, host, path, urlencode(query), ""))


_TITLE_NORM = re.compile(r"[^a-z0-9 ]+")
STOP = {"the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "with", "is", "are", "by", "at", "from",
        "its", "it", "new", "now", "how", "we", "our", "your", "you", "this", "that", "as", "be", "show", "hn", "ask"}


def title_tokens(title: str) -> frozenset[str]:
    t = _TITLE_NORM.sub(" ", title.lower())
    return frozenset(w for w in t.split() if w not in STOP and len(w) > 1)
