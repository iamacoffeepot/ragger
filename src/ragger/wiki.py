"""Shared utilities for fetching and parsing OSRS wiki data."""

from __future__ import annotations

import os
import re
import sqlite3
import time
from pathlib import Path

import requests

DEFAULT_THROTTLE = 1.0
THROTTLE_DELAY = float(os.environ.get("RAGGER_THROTTLE", DEFAULT_THROTTLE))

from ragger.enums import Region, Skill

class WikiCache:
    """SQLite-backed cache for wiki page wikitext.

    Stores wikitext alongside the MediaWiki revision ID. On cache hit,
    a cheap rev-ID-only API call checks whether the cached revision is
    still current. Only stale or missing pages are re-fetched with full
    content.
    """

    def __init__(self, path: Path | str) -> None:
        self.conn = sqlite3.connect(str(path))
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS wiki_pages (
                title TEXT PRIMARY KEY,
                wikitext TEXT NOT NULL,
                revid INTEGER NOT NULL,
                fetched_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def get(self, title: str) -> tuple[str, int] | None:
        """Return (wikitext, revid) for a cached page, or None."""
        row = self.conn.execute(
            "SELECT wikitext, revid FROM wiki_pages WHERE title = ?", (title,),
        ).fetchone()
        return (row[0], row[1]) if row else None

    def get_batch(self, titles: list[str]) -> dict[str, tuple[str, int]]:
        """Return {title: (wikitext, revid)} for all cached pages in the list."""
        if not titles:
            return {}
        placeholders = ",".join("?" * len(titles))
        rows = self.conn.execute(
            f"SELECT title, wikitext, revid FROM wiki_pages WHERE title IN ({placeholders})",
            titles,
        ).fetchall()
        return {title: (wikitext, revid) for title, wikitext, revid in rows}

    def put(self, title: str, wikitext: str, revid: int) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO wiki_pages (title, wikitext, revid, fetched_at) VALUES (?, ?, ?, datetime('now'))",
            (title, wikitext, revid),
        )
        self.conn.commit()

    def put_batch(self, pages: dict[str, tuple[str, int]]) -> None:
        """Store multiple pages. pages: {title: (wikitext, revid)}."""
        if not pages:
            return
        self.conn.executemany(
            "INSERT OR REPLACE INTO wiki_pages (title, wikitext, revid, fetched_at) VALUES (?, ?, ?, datetime('now'))",
            [(title, wikitext, revid) for title, (wikitext, revid) in pages.items()],
        )
        self.conn.commit()


# Default cache instance, initialized from RAGGER_WIKI_CACHE env var.
default_cache: WikiCache | None = None


def set_wiki_cache(path: Path | str | None) -> None:
    """Set the default wiki cache instance."""
    global default_cache
    if default_cache is not None:
        default_cache.close()
        default_cache = None
    if path is not None:
        default_cache = WikiCache(path)


def get_wiki_cache() -> WikiCache | None:
    """Return the default wiki cache instance, or None if not configured."""
    return default_cache


if os.environ.get("RAGGER_WIKI_CACHE"):
    set_wiki_cache(os.environ["RAGGER_WIKI_CACHE"])

# Maximum pages per MediaWiki API batch request (action=query limit).
WIKI_BATCH_SIZE = 50
API_URL = "https://oldschool.runescape.wiki/api.php"
USER_AGENT = "ragger/0.2 (https://github.com/iamacoffeepot/ragger) OSRS Leagues planner"
HEADERS = {"User-Agent": USER_AGENT}

SKILL_NAME_MAP: dict[str, Skill] = {s.label.lower(): s for s in Skill}

SKILL_REQ_PATTERN = re.compile(r"\{\{SCP\|(\w+)\|(\d+)")
WIKI_LINK_PATTERN = re.compile(r"\[\[([^\]|]*?)(?:\|[^\]]*?)?\]\]")
_PLINK_PATTERN = re.compile(r"\{\{[Pp]link\|([^}|]+)(?:\|[^}]*)?\}\}")

_COORD_X_PARAM = re.compile(r"\|x\s*=\s*(\d+)")
_COORD_Y_PARAM = re.compile(r"\|y\s*=\s*(\d+)")
_COORD_XY_COLON = re.compile(r"x:(\d+),y:(\d+)")
_COORD_POSITIONAL = re.compile(r"\|(\d{3,5}),(\d{3,5})")


def extract_coords(text: str) -> list[tuple[int, int]]:
    """Extract all (x, y) coordinate pairs from wiki template text.

    Handles three formats:
    - |x=N|y=N (or |x = N|y = N)
    - x:N,y:N
    - |N,N (positional 3-5 digit pairs)
    """
    coords: list[tuple[int, int]] = []

    # x=N|y=N format (single pair)
    x_match = _COORD_X_PARAM.search(text)
    y_match = _COORD_Y_PARAM.search(text)
    if x_match and y_match:
        coords.append((int(x_match.group(1)), int(y_match.group(1))))
        return coords

    # x:N,y:N format (may have multiple)
    for match in _COORD_XY_COLON.finditer(text):
        coords.append((int(match.group(1)), int(match.group(2))))
    if coords:
        return coords

    # Positional |N,N format
    for match in _COORD_POSITIONAL.finditer(text):
        coords.append((int(match.group(1)), int(match.group(2))))

    return coords


def resolve_region(label: str | None) -> int | None:
    """Map a leagueRegion label to a Region enum value.

    Handles complex formats like 'Misthalin&Morytania, Misthalin&Fremennik'
    by extracting the first region. Returns None for 'no', 'n/a', 'none', etc.
    """
    if not label:
        return None
    cleaned = re.sub(r"<!--.*?-->", "", label).strip().lower()
    if cleaned in ("no", "n/a", "none", ""):
        return None
    first_group = label.split(",")[0].strip()
    first_region = first_group.split("&")[0].strip()
    try:
        return Region.from_label(first_region).value
    except KeyError:
        return None


def fetch_category_members(
    category: str,
    namespace: int = 0,
    exclude_prefixes: tuple[str, ...] = (),
    exclude_suffixes: tuple[str, ...] = (),
    exclude_titles: set[str] | None = None,
    exclude_namespaces: set[int] | None = None,
) -> list[str]:
    """Fetch all page titles in a wiki category with pagination."""
    pages: list[str] = []
    excluded = exclude_titles or set()
    excluded_ns = exclude_namespaces or set()
    params = {
        "action": "query",
        "list": "categorymembers",
        "cmtitle": f"Category:{category}",
        "cmlimit": "500",
        "cmtype": "page",
        "cmnamespace": str(namespace),
        "format": "json",
    }

    while True:
        resp = requests.get(API_URL, params=params, headers=HEADERS)
        resp.raise_for_status()
        data = resp.json()

        for member in data["query"]["categorymembers"]:
            title = member["title"]
            ns = member["ns"]

            if ns in excluded_ns:
                continue
            if title in excluded:
                continue
            if exclude_prefixes and title.startswith(exclude_prefixes):
                continue
            if exclude_suffixes and title.endswith(exclude_suffixes):
                continue

            pages.append(title)

        if "continue" in data:
            params["cmcontinue"] = data["continue"]["cmcontinue"]
        else:
            break

    return sorted(pages)


def fetch_page_wikitext(page: str, cache: WikiCache | None = ...) -> str:
    """Fetch the raw wikitext for a wiki page.

    Uses the provided cache (or the default if not specified) to avoid
    redundant API calls. Validates cached pages against the current
    revision ID.
    """
    if cache is ...:
        cache = default_cache

    if cache is not None:
        cached = cache.get(page)
        if cached is not None:
            cached_text, cached_revid = cached
            # Check if cached revision is still current
            current_revid = _fetch_revid(page)
            if current_revid is not None and current_revid == cached_revid:
                return cached_text

    resp = requests.get(
        API_URL,
        params={"action": "parse", "page": page, "prop": "wikitext", "format": "json"},
        headers=HEADERS,
    )
    resp.raise_for_status()
    parse_data = resp.json().get("parse", {})
    wikitext = parse_data.get("wikitext", {}).get("*", "")
    revid = parse_data.get("revid", 0)

    if cache is not None and revid:
        cache.put(page, wikitext, revid)

    return wikitext


def _fetch_revid(page: str) -> int | None:
    """Fetch the latest revision ID for a page (cheap, no content)."""
    resp = requests.get(
        API_URL,
        params={
            "action": "query",
            "titles": page,
            "prop": "revisions",
            "rvprop": "ids",
            "format": "json",
        },
        headers=HEADERS,
    )
    resp.raise_for_status()
    for _, page_data in resp.json().get("query", {}).get("pages", {}).items():
        revisions = page_data.get("revisions", [])
        if revisions:
            return revisions[0].get("revid")
    return None


def _fetch_revids_batch(pages: list[str]) -> dict[str, int]:
    """Fetch latest revision IDs for up to WIKI_BATCH_SIZE pages (no content)."""
    result: dict[str, int] = {}
    for i in range(0, len(pages), WIKI_BATCH_SIZE):
        batch = pages[i:i + WIKI_BATCH_SIZE]
        resp = requests.get(
            API_URL,
            params={
                "action": "query",
                "titles": "|".join(batch),
                "prop": "revisions",
                "rvprop": "ids",
                "format": "json",
            },
            headers=HEADERS,
        )
        resp.raise_for_status()
        for _, page_data in resp.json().get("query", {}).get("pages", {}).items():
            title = page_data.get("title", "")
            revisions = page_data.get("revisions", [])
            if revisions:
                result[title] = revisions[0]["revid"]
        throttle()
    return result


def fetch_pages_wikitext_batch(
    pages: list[str], cache: WikiCache | None = ...,
) -> dict[str, str]:
    """Fetch raw wikitext for multiple pages, batched in groups of 50.

    Returns a dict mapping page title to wikitext.
    Uses action=query with revisions prop (supports batching).

    When a cache is available, fetches current revision IDs first (cheap,
    no content) and only re-fetches pages whose cached revid is stale or
    missing.
    """
    if cache is ...:
        cache = default_cache

    result: dict[str, str] = {}
    need_fetch: list[str] = list(pages)

    if cache is not None:
        cached = cache.get_batch(pages)
        if cached:
            # Check which cached pages are still current
            current_revids = _fetch_revids_batch(list(cached.keys()))
            fresh = 0
            stale = 0
            for title, (wikitext, cached_revid) in cached.items():
                current = current_revids.get(title)
                if current is not None and current == cached_revid:
                    result[title] = wikitext
                    fresh += 1
                else:
                    stale += 1
            need_fetch = [p for p in pages if p not in result]
            print(f"  Cache: {fresh} fresh, {stale} stale, {len(need_fetch) - stale} new")

    for i in range(0, len(need_fetch), WIKI_BATCH_SIZE):
        batch = need_fetch[i:i + WIKI_BATCH_SIZE]
        params = {
            "action": "query",
            "titles": "|".join(batch),
            "prop": "revisions",
            "rvprop": "content|ids",
            "rvslots": "main",
            "format": "json",
        }
        resp = requests.get(API_URL, params=params, headers=HEADERS)
        resp.raise_for_status()
        data = resp.json()

        to_cache: dict[str, tuple[str, int]] = {}
        for _, page_data in data.get("query", {}).get("pages", {}).items():
            title = page_data.get("title", "")
            revisions = page_data.get("revisions", [])
            if revisions:
                rev = revisions[0]
                content = rev.get("slots", {}).get("main", {}).get("*", "")
                revid = rev.get("revid", 0)
                result[title] = content
                if revid:
                    to_cache[title] = (content, revid)

        if cache is not None:
            cache.put_batch(to_cache)

        throttle()

    return result


def strip_markup(text: str) -> str:
    """Remove wiki markup (links, templates, bold/italic) from text."""
    text = re.sub(r"\[\[([^]|]*\|)?([^]]*)\]\]", r"\2", text)
    text = re.sub(r"\{\{[^}]*\}\}", "", text)
    text = re.sub(r"'{2,3}", "", text)
    return text.strip()


_REF_TAG = re.compile(r"<ref[^>]*>.*?</ref>|<ref[^>]*/>|\{\{Refn\|[^}]*\}\}", re.DOTALL)


def strip_refs(val: str | None) -> str | None:
    """Strip <ref> tags and {{Refn}} templates from a value."""
    if not val:
        return val
    return _REF_TAG.sub("", val).strip()


_FRAGMENT_SUFFIX = re.compile(r"#.*$")
_TEMPLATE_ARTIFACT = re.compile(r"\{\{[^}]*\}\}?")


def clean_page_reference(text: str, page_name: str | None = None) -> str:
    """Clean wiki artifacts from a page/item reference.

    - Substitutes {{PAGENAME}} with the actual page name (if provided)
    - Strips #fragment suffixes (e.g. "Teapot#Clay" -> "Teapot")
    - Strips residual template artifacts (e.g. "{{!}}")
    """
    if page_name:
        text = text.replace("{{PAGENAME}}", page_name).replace("{{PAGENAME", page_name)
    text = _FRAGMENT_SUFFIX.sub("", text)
    text = _TEMPLATE_ARTIFACT.sub("", text)
    return text.strip()


def strip_wiki_links(text: str) -> str:
    """Replace [[Link|Display]] or [[Link]] with just the display text."""
    return WIKI_LINK_PATTERN.sub(r"\1", text)


def strip_plinks(text: str) -> str:
    """Replace {{plink|Name}} or {{Plink|Name}} with just the name."""
    return _PLINK_PATTERN.sub(r"\1", text)


def clean_name(text: str, page_name: str) -> str:
    """Strip wiki links, plinks, and clean page references."""
    return clean_page_reference(strip_wiki_links(strip_plinks(text.strip())), page_name)


def detect_versions(block: str) -> list[str]:
    """Detect version names from version1, version2, ... params in a template block."""
    versions = []
    i = 1
    while True:
        v = parse_template_param(block, f"version{i}")
        if not v:
            break
        versions.append(v.strip())
        i += 1
    return versions


def extract_template(wikitext: str, template_name: str) -> str | None:
    """Extract a template block handling nested braces.

    Returns the content between {{TemplateName ... }} excluding
    the opening {{TemplateName and closing }}.
    """
    start = wikitext.find("{{" + template_name)
    if start == -1:
        return None
    depth = 0
    i = start
    while i < len(wikitext):
        if wikitext[i:i + 2] == "{{":
            depth += 1
            i += 2
        elif wikitext[i:i + 2] == "}}":
            depth -= 1
            if depth == 0:
                return wikitext[start + len("{{" + template_name):i]
            i += 2
        else:
            i += 1
    return None


def extract_all_templates(wikitext: str, template_name: str) -> list[str]:
    """Extract all occurrences of a template from wikitext.

    Like extract_template but returns every match, not just the first.
    Useful for pages with multiple {{Recipe}} blocks, etc.
    """
    results: list[str] = []
    search_from = 0
    prefix = "{{" + template_name
    while True:
        start = wikitext.find(prefix, search_from)
        if start == -1:
            break
        depth = 0
        i = start
        while i < len(wikitext):
            if wikitext[i:i + 2] == "{{":
                depth += 1
                i += 2
            elif wikitext[i:i + 2] == "}}":
                depth -= 1
                if depth == 0:
                    results.append(wikitext[start + len(prefix):i])
                    search_from = i + 2
                    break
                i += 2
            else:
                i += 1
        else:
            break
    return results


def fetch_template_users(template_name: str) -> list[str]:
    """Fetch all mainspace pages that transclude a given template.

    Uses the embeddedin API with pagination (500 per request).
    """
    pages: list[str] = []
    params = {
        "action": "query",
        "list": "embeddedin",
        "eititle": f"Template:{template_name}",
        "eilimit": "500",
        "einamespace": "0",
        "format": "json",
    }

    while True:
        resp = requests.get(API_URL, params=params, headers=HEADERS)
        resp.raise_for_status()
        data = resp.json()

        for item in data["query"]["embeddedin"]:
            pages.append(item["title"])

        if "continue" in data:
            params["eicontinue"] = data["continue"]["eicontinue"]
        else:
            break

    return sorted(pages)


def extract_section(wikitext: str, field_name: str) -> str:
    """Extract a |field= section from a template, handling nested braces.

    Stops at the next top-level | or }}.
    """
    start = re.search(rf"\|{field_name}\s*=\s*", wikitext)
    if not start:
        return ""
    pos = start.end()
    depth = 0
    result: list[str] = []
    while pos < len(wikitext):
        if wikitext[pos:pos + 2] == "{{":
            depth += 1
            result.append("{{")
            pos += 2
        elif wikitext[pos:pos + 2] == "}}":
            if depth == 0:
                break
            depth -= 1
            result.append("}}")
            pos += 2
        elif wikitext[pos] == "|" and depth == 0:
            break
        else:
            result.append(wikitext[pos])
            pos += 1
    return "".join(result)


def parse_template_param(text: str, param: str) -> str | None:
    """Extract a single |param=value from template text.

    Brace-aware: correctly handles nested templates like {{plink|Name}}
    inside parameter values.
    """
    pattern = re.compile(rf"\|\s*{re.escape(param)}\s*=\s*")
    m = pattern.search(text)
    if not m:
        return None
    start = m.end()
    brace_depth = 0
    bracket_depth = 0
    i = start
    while i < len(text):
        ch = text[i]
        if ch == '{' and i + 1 < len(text) and text[i + 1] == '{':
            brace_depth += 1
            i += 2
            continue
        if ch == '}' and i + 1 < len(text) and text[i + 1] == '}':
            if brace_depth == 0:
                break
            brace_depth -= 1
            i += 2
            continue
        if ch == '[' and i + 1 < len(text) and text[i + 1] == '[':
            bracket_depth += 1
            i += 2
            continue
        if ch == ']' and i + 1 < len(text) and text[i + 1] == ']':
            bracket_depth = max(0, bracket_depth - 1)
            i += 2
            continue
        if ch == '|' and brace_depth == 0 and bracket_depth == 0:
            break
        if ch == '\n' and brace_depth == 0 and bracket_depth == 0:
            break
        i += 1
    val = text[start:i].strip()
    return val if val else None


def parse_int(val: str | None) -> int | None:
    """Parse an optional integer string, stripping commas, +, and %."""
    if not val:
        return None
    val = val.strip().replace(",", "").replace("+", "").replace("%", "")
    try:
        return int(val)
    except ValueError:
        return None


def parse_xp(val: str | None) -> float:
    """Parse an XP value, returning 0.0 for missing/invalid. Treats -1 as 0 (wiki hides cell)."""
    if not val:
        return 0.0
    val = val.strip().replace(",", "")
    if val == "-1":
        return 0.0
    try:
        return float(val)
    except ValueError:
        return 0.0


def parse_ticks(val: str | None) -> int | None:
    """Parse a tick count, returning None for missing/varies/N/A."""
    if not val:
        return None
    cleaned = val.strip().lower()
    if cleaned in ("na", "n/a", "?", "varies", ""):
        return None
    cleaned = cleaned.replace(",", "")
    try:
        return int(cleaned)
    except ValueError:
        return None


def parse_members(val: str | None) -> int:
    """Parse a members field, defaulting to 1 (members) if missing."""
    if not val:
        return 1
    return 0 if val.strip().lower() == "no" else 1


def parse_boostable(val: str | None) -> int | None:
    """Parse a boostable yes/no field."""
    if not val:
        return None
    lower = val.strip().lower()
    if lower == "yes":
        return 1
    if lower == "no":
        return 0
    return None


def parse_skill_requirements(text: str) -> list[tuple[int, int]]:
    """Parse {{SCP|Skill|Level}} patterns into (skill_id, level) tuples."""
    reqs: list[tuple[int, int]] = []
    for match in SKILL_REQ_PATTERN.finditer(text):
        skill_name = match.group(1).lower()
        level = int(match.group(2))
        skill = SKILL_NAME_MAP.get(skill_name)
        if skill is not None and 1 <= level <= 99:
            reqs.append((skill.value, level))
    return reqs


def link_requirement(
    conn: sqlite3.Connection,
    table: str,
    columns: dict[str, object],
    junction_table: str,
    entity_column: str,
    entity_id: int,
    requirement_column: str,
) -> int:
    """Insert-or-ignore a requirement row, then link it to an entity via a junction table.

    Returns the requirement row id.
    """
    cols = ", ".join(columns.keys())
    placeholders = ", ".join("?" * len(columns))
    values = list(columns.values())
    where = " AND ".join(f"{k} = ?" for k in columns.keys())

    conn.execute(f"INSERT OR IGNORE INTO {table} ({cols}) VALUES ({placeholders})", values)
    req_id = conn.execute(f"SELECT id FROM {table} WHERE {where}", values).fetchone()[0]
    conn.execute(
        f"INSERT OR IGNORE INTO {junction_table} ({entity_column}, {requirement_column}) VALUES (?, ?)",
        (entity_id, req_id),
    )
    return req_id


# ---------------------------------------------------------------------------
# Generic requirement group utilities
# ---------------------------------------------------------------------------


def create_requirement_group(conn: sqlite3.Connection) -> int:
    """Create a new requirement group and return its id."""
    conn.execute("INSERT INTO requirement_groups DEFAULT VALUES")
    return conn.execute("SELECT last_insert_rowid()").fetchone()[0]


def add_group_requirement(
    conn: sqlite3.Connection,
    group_id: int,
    table: str,
    columns: dict[str, object],
) -> int:
    """Add a typed requirement to a group. Returns the requirement row id."""
    all_cols = {"group_id": group_id, **columns}
    col_names = ", ".join(all_cols.keys())
    placeholders = ", ".join("?" * len(all_cols))
    values = list(all_cols.values())
    conn.execute(f"INSERT INTO {table} ({col_names}) VALUES ({placeholders})", values)
    return conn.execute("SELECT last_insert_rowid()").fetchone()[0]


def link_requirement_group(
    conn: sqlite3.Connection,
    junction_table: str,
    entity_column: str,
    entity_id: int,
    group_id: int,
) -> None:
    """Link an entity to a requirement group via a junction table."""
    conn.execute(
        f"INSERT OR IGNORE INTO {junction_table} ({entity_column}, group_id) VALUES (?, ?)",
        (entity_id, group_id),
    )


def link_group_requirement(
    conn: sqlite3.Connection,
    table: str,
    columns: dict[str, object],
    junction_table: str,
    entity_column: str,
    entity_id: int,
) -> int:
    """Convenience: create a group with a single requirement and link it to an entity.

    This is the common AND case — one requirement per group. Returns the group id.
    """
    group_id = create_requirement_group(conn)
    add_group_requirement(conn, group_id, table, columns)
    link_requirement_group(conn, junction_table, entity_column, entity_id, group_id)
    return group_id


def fetch_contributors_batch(pages: list[str]) -> dict[str, list[str]]:
    """Fetch contributors for up to WIKI_BATCH_SIZE pages in a single API call.

    Returns a dict mapping page title to list of contributor names.
    """
    result: dict[str, list[str]] = {p: [] for p in pages}

    params = {
        "action": "query",
        "titles": "|".join(pages),
        "prop": "contributors",
        "pclimit": "500",
        "format": "json",
    }

    while True:
        resp = requests.get(API_URL, params=params, headers=HEADERS)
        resp.raise_for_status()
        data = resp.json()

        for _, page_data in data["query"]["pages"].items():
            title = page_data.get("title", "")
            for c in page_data.get("contributors", []):
                if title in result:
                    result[title].append(c["name"])

        if "continue" in data:
            params["pccontinue"] = data["continue"]["pccontinue"]
        else:
            break

    return result


def fetch_page_contributors(page: str) -> list[str]:
    """Fetch the list of contributors for a single wiki page."""
    return fetch_contributors_batch([page]).get(page, [])


def record_attribution(
    conn: sqlite3.Connection,
    table_name: str,
    wiki_page: str,
    authors: list[str],
) -> None:
    """Record an attribution entry for a wiki page that was used to populate a table."""
    conn.execute(
        "INSERT INTO attributions (table_name, wiki_page, authors, fetched_at) VALUES (?, ?, ?, datetime('now'))",
        (table_name, wiki_page, ", ".join(authors)),
    )


def record_attributions_batch(
    conn: sqlite3.Connection,
    table_names: str | list[str],
    pages: list[str],
) -> None:
    """Fetch contributors for a batch of pages and record attributions.

    table_names can be a single string or a list of table names to attribute.
    Pages are processed in batches of WIKI_BATCH_SIZE (API limit).
    """
    if isinstance(table_names, str):
        table_names = [table_names]
    for i in range(0, len(pages), WIKI_BATCH_SIZE):
        batch = pages[i:i + WIKI_BATCH_SIZE]
        contributors = fetch_contributors_batch(batch)
        for page, authors in contributors.items():
            for table_name in table_names:
                record_attribution(conn, table_name, page, authors)
        throttle()


def fetch_page_wikitext_with_attribution(
    conn: sqlite3.Connection,
    page: str,
    table_name: str,
) -> str:
    """Fetch wikitext and record attribution in one call."""
    wikitext = fetch_page_wikitext(page)
    contributors = fetch_page_contributors(page)
    record_attribution(conn, table_name, page, contributors)
    return wikitext


def throttle() -> None:
    """Sleep to avoid hammering the wiki API.

    Default 1 second. Override with RAGGER_THROTTLE env var.
    """
    time.sleep(THROTTLE_DELAY)
