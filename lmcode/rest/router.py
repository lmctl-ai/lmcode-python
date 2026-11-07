"""Route templates and matching for the opt-in `rest` std module (spec/std-rest.md). Strings are latin-1 byte strings."""
from __future__ import annotations
import re
from functools import cmp_to_key
from typing import Dict, List, Optional
from ..errors import HostError

METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"]
_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_HEX = re.compile(r"[0-9A-Fa-f]{2}")
# Whitespace is ASCII only (0x00-0x20, 0x7f); a byte such as 0xA0 is ordinary.
_BAD_PATH = re.compile(r"[\x00-\x20\x7f?#]")
_PLACEHOLDER = re.compile(r"\{(.*?)(\.\.\.)?\}")


def fail(message: str):
    raise HostError(message)


def percent_decode(text: str, plus: bool = False) -> Optional[str]:
    """Decode %XX into bytes (latin-1 chars); None on an invalid escape. `plus` turns '+' into a space."""
    out: List[str] = []
    i = 0
    while i < len(text):
        c = text[i]
        if c == "%":
            h = text[i + 1:i + 3]
            if not _HEX.fullmatch(h):
                return None
            out.append(chr(int(h, 16)))
            i += 3
            continue
        out.append(" " if plus and c == "+" else c)
        i += 1
    return "".join(out)


class Route:
    def __init__(self, method, path, segments, shape):
        self.method, self.path, self.segments, self.shape, self.annotation = method, path, segments, shape, None


def parse_route(method: str, path: str) -> Route:
    label = method + " " + path
    def invalid(reason):
        fail("rest: invalid route " + label + ": " + reason)
    if method not in METHODS:
        invalid("method must be one of " + ", ".join(METHODS))
    if not path.startswith("/"):
        invalid("path must start with '/'")
    if _BAD_PATH.search(path):
        invalid("path must not contain whitespace, control characters, ? or #")
    raw = path[1:].split("/")
    names = set()
    segments = []
    for index, text in enumerate(raw):
        last = index == len(raw) - 1
        if text == "" and not last:
            invalid("empty segment ('//')")
        m = _PLACEHOLDER.fullmatch(text)
        if not m:
            if "{" in text or "}" in text:
                invalid("malformed placeholder in segment '" + text + "'")
            segments.append(("literal", text))
            continue
        name, rest = m.group(1), m.group(2)
        if not _NAME.fullmatch(name):
            invalid("invalid parameter name '" + name + "'")
        if name in names:
            invalid("duplicate parameter '" + name + "'")
        names.add(name)
        if rest and not last:
            invalid("'{" + name + "...}' must be the last segment")
        segments.append(("rest" if rest else "param", name))
    shape = "/".join(("L" + v) if k == "literal" else "P" if k == "param" else "R" for k, v in segments)
    return Route(method, path, segments, shape)


_RANK = {"literal": 0, "param": 1, "rest": 2}


def _specificity(a: Route, b: Route) -> int:
    for (ka, _), (kb, _) in zip(a.segments, b.segments):
        d = _RANK[ka] - _RANK[kb]
        if d:
            return d
    return len(a.segments) - len(b.segments)


def _match_segments(route: Route, raw: List[str]) -> Optional[Dict[str, str]]:
    params: Dict[str, str] = {}
    segs = route.segments
    for i, (kind, value) in enumerate(segs):
        if kind == "rest":
            if len(raw) <= i:
                return None
            parts = []
            for r in raw[i:]:
                d = percent_decode(r)
                if d is None:
                    return None
                parts.append(d)
            params[value] = "/".join(parts)
            return params
        if i >= len(raw):
            return None
        d = percent_decode(raw[i])
        if d is None:
            return None
        if kind == "literal":
            if d != value:
                return None
        else:
            if d == "":
                return None
            params[value] = d
    return params if len(raw) == len(segs) else None


class Match:
    """Either a route with params (status None), or status 404 / 405 (+ allow)."""
    def __init__(self, route=None, params=None, status=None, allow=None):
        self.route, self.params, self.status, self.allow = route, params, status, allow


class RouteTable:
    def __init__(self):
        self.routes: List[Route] = []

    @property
    def size(self) -> int:
        return len(self.routes)

    def add(self, method: str, path: str, annotation: str) -> Route:
        route = parse_route(method, path)
        if any(r.method == method and r.shape == route.shape for r in self.routes):
            fail("rest: duplicate route " + method + " " + path)
        route.annotation = annotation
        self.routes.append(route)
        return route

    def match(self, method: str, raw_path: str) -> Match:
        raw = raw_path[1:].split("/")
        hits = []
        for route in self.routes:
            params = _match_segments(route, raw)
            if params is not None:
                hits.append((route, params))
        if not hits:
            return Match(status=404)
        def best(verb):
            found = [h for h in hits if h[0].method == verb]
            return min(found, key=cmp_to_key(lambda x, y: _specificity(x[0], y[0]))) if found else None
        direct = best(method) or (best("GET") if method == "HEAD" else None)
        if direct:
            return Match(route=direct[0], params=direct[1])
        allow = {h[0].method for h in hits}
        if "GET" in allow:
            allow.add("HEAD")
        return Match(status=405, allow=", ".join(sorted(allow)))
