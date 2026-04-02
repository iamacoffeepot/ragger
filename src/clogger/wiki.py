"""Shared utilities for fetching and parsing OSRS wiki data."""

import os
import re
import sqlite3
import time

import requests

DEFAULT_THROTTLE = 1.0
THROTTLE_DELAY = float(os.environ.get("CLOGGER_THROTTLE", DEFAULT_THROTTLE))

from clogger.enums import Skill

API_URL = "https://oldschool.runescape.wiki/api.php"
USER_AGENT = "clogger/0.2 (https://github.com/iamacoffeepot/clogger) OSRS Leagues planner"
HEADERS = {"User-Agent": USER_AGENT}

SKILL_NAME_MAP: dict[str, Skill] = {s.label.lower(): s for s in Skill}

SKILL_REQ_PATTERN = re.compile(r"\{\{SCP\|(\w+)\|(\d+)")
WIKI_LINK_PATTERN = re.compile(r"\[\[([^\]|]*?)(?:\|[^\]]*?)?\]\]")


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


def fetch_page_wikitext(page: str) -> str:
    """Fetch the raw wikitext for a wiki page."""
    resp = requests.get(
        API_URL,
        params={"action": "parse", "page": page, "prop": "wikitext", "format": "json"},
        headers=HEADERS,
    )
    resp.raise_for_status()
    return resp.json().get("parse", {}).get("wikitext", {}).get("*", "")


def strip_markup(text: str) -> str:
    """Remove wiki markup (links, templates, bold/italic) from text."""
    text = re.sub(r"\[\[([^]|]*\|)?([^]]*)\]\]", r"\2", text)
    text = re.sub(r"\{\{[^}]*\}\}", "", text)
    text = re.sub(r"'{2,3}", "", text)
    return text.strip()


def strip_wiki_links(text: str) -> str:
    """Replace [[Link|Display]] or [[Link]] with just the display text."""
    return WIKI_LINK_PATTERN.sub(r"\1", text)


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
    """Extract a single |param=value from template text."""
    match = re.search(rf"\|\s*{param}\s*=\s*([^\n|}}]*)", text)
    return match.group(1).strip() if match else None


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


def fetch_page_contributors(page: str) -> list[str]:
    """Fetch the list of contributors for a wiki page."""
    contributors: list[str] = []
    params = {
        "action": "query",
        "titles": page,
        "prop": "contributors",
        "pclimit": "500",
        "format": "json",
    }

    while True:
        resp = requests.get(API_URL, params=params, headers=HEADERS)
        resp.raise_for_status()
        data = resp.json()

        for _, page_data in data["query"]["pages"].items():
            for c in page_data.get("contributors", []):
                contributors.append(c["name"])

        if "continue" in data:
            params["pccontinue"] = data["continue"]["pccontinue"]
        else:
            break

    return contributors


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

    Default 1 second. Override with CLOGGER_THROTTLE env var.
    """
    time.sleep(THROTTLE_DELAY)
