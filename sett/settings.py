"""Settings made on Sett's /settings page, kept in <data>/settings.json and
layered over sett.toml (which still works on its own and is never rewritten).

    title, theme, search          the basics
    ui                            accent, accent_2, density ("compact"), clock ("24h")
    weather                       latitude, longitude, label, units
    bookmarks                     links added on the page (sett.toml's stay too)
    hidden                        service keys hidden for everyone
    vitals                        url, token, window, style
    caddy_file                    a Caddyfile to take card links from

Secrets (the Vitals token) go back to the browser masked; a masked value sent
back means "unchanged".
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

from .config import data_dir

MASK = "••••"
THEME_RE = re.compile(r"^[a-z0-9][a-z0-9/_-]{0,40}$")
COLOR_RE = re.compile(r"^#[0-9a-fA-F]{3,8}$")


class Invalid(ValueError):
    pass


def path() -> Path | None:
    d = data_dir()
    return d / "settings.json" if d else None


def load_doc() -> dict:
    p = path()
    if not p or not p.is_file():
        return {}
    try:
        doc = json.loads(p.read_text(encoding="utf-8"))
        return doc if isinstance(doc, dict) else {}
    except (OSError, ValueError):
        return {}


def save_doc(doc: dict) -> None:
    p = path()
    if not p:
        raise OSError("no writable data folder: mount /data to keep settings")
    tmp = p.with_suffix(".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)   # it can hold the Vitals token
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=1)
    os.replace(tmp, p)


def apply(cfg, doc: dict) -> None:
    """Layer the page's settings over what sett.toml said."""
    for k in ("title", "theme", "search"):
        if doc.get(k) is not None:
            setattr(cfg, k, doc[k])
    if doc.get("ui"):
        cfg.ui = {**cfg.ui, **doc["ui"]}
    if doc.get("weather") is not None:
        cfg.weather = doc["weather"]
    cfg.bookmarks = list(cfg.bookmarks) + [b for b in doc.get("bookmarks") or [] if isinstance(b, dict)]
    cfg.hidden_keys = set(doc.get("hidden") or [])
    if doc.get("vitals"):
        cfg.vitals = {**cfg.vitals, **doc["vitals"]}


def clean(new: dict, old: dict) -> dict:
    """Check and tidy what the page sent. Raises Invalid with a message a person can act on."""
    if not isinstance(new, dict):
        raise Invalid("expected a settings object")
    out: dict = {}
    title = str(new.get("title") or "").strip()
    if title:
        out["title"] = title[:60]
    theme = str(new.get("theme") or "").strip()
    if theme:
        if not THEME_RE.match(theme):
            raise Invalid("that isn't a theme name")
        out["theme"] = theme
    search = str(new.get("search") or "")
    if search not in ("", "google", "duckduckgo", "bing"):
        raise Invalid("web search is Google, DuckDuckGo, Bing or none")
    out["search"] = search

    ui = new.get("ui") or {}
    out["ui"] = {}
    for k in ("accent", "accent_2"):
        v = str(ui.get(k) or "").strip()
        if v:
            if not COLOR_RE.match(v):
                raise Invalid("colours look like #8b97ff")
            out["ui"][k] = v
    if ui.get("density") == "compact":
        out["ui"]["density"] = "compact"
    if ui.get("clock") == "24h":
        out["ui"]["clock"] = "24h"

    w = new.get("weather") or {}
    if w.get("latitude") not in (None, "") or w.get("longitude") not in (None, ""):
        try:
            lat, lon = float(w["latitude"]), float(w["longitude"])
        except (KeyError, TypeError, ValueError):
            raise Invalid("weather needs both a latitude and a longitude (numbers)") from None
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            raise Invalid("latitude is -90..90 and longitude -180..180")
        out["weather"] = {"latitude": lat, "longitude": lon, "label": str(w.get("label") or "")[:40],
                          "units": "imperial" if w.get("units") == "imperial" else "metric"}
    else:
        out["weather"] = {}

    out["bookmarks"] = []
    for b in new.get("bookmarks") or []:
        name, url = str(b.get("name") or "").strip(), str(b.get("url") or "").strip()
        if not name and not url:
            continue
        if not name or not url.startswith(("http://", "https://")):
            raise Invalid(f"link {name or url!r}: needs a name and an address starting with http:// or https://")
        out["bookmarks"].append({"name": name[:60], "url": url[:500], "group": str(b.get("group") or "Links")[:40],
                                 **({"abbr": str(b["abbr"])[:3]} if b.get("abbr") else {})})

    out["hidden"] = sorted({str(k)[:200] for k in new.get("hidden") or [] if str(k).strip()})

    v = new.get("vitals") or {}
    url = str(v.get("url") or "").strip().rstrip("/")
    if url:
        if not url.startswith(("http://", "https://")):
            raise Invalid("the Vitals address starts with http:// or https://")
        token = str(v.get("token") or "")
        if MASK in token:
            token = (old.get("vitals") or {}).get("token", "")
        out["vitals"] = {"url": url, "token": token}
        for k, allowed in (("window", ("24h", "7d", "30d", "90d")), ("style", ("tag", "stat", "bars"))):
            if v.get(k) in allowed:
                out["vitals"][k] = v[k]

    cf = str(new.get("caddy_file") or "").strip()
    if cf:
        if not cf.startswith("/"):
            raise Invalid("the Caddyfile path is a full path inside the container, like /config/Caddyfile")
        out["caddy_file"] = cf
    return out


def view(doc: dict) -> dict:
    """The document for the page, secrets masked."""
    d = json.loads(json.dumps(doc))
    tok = (d.get("vitals") or {}).get("token")
    if tok:
        d["vitals"]["token"] = MASK + tok[-4:] if len(tok) > 8 else MASK
    return d
