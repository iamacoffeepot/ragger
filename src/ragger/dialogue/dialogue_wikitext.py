"""Normalize raw wikitext into MDX-style markup for dialogue text.

Pure string-in, string-out transformer. ``fetch_dialogues.py`` calls
this on every parsed node's text so downstream consumers (the IR, the
plugin renderer, the LLM) see one normalized representation rather
than raw wikitext.

Output format:

- **Markdown links with typed prefixes** for entity references —
  ``[Cook](wiki:Cook)``, ``[cabbage](item:cabbage)``. The prefix tells
  consumers how to resolve the link; ``wiki:`` is the catch-all when
  the entity type isn't known at parse time.
- **XML self-closing tags** for substitution slots and conditionals —
  ``<player/>``, ``<gender male="he" female="she"/>``, ``<missing/>``.
- **XML element tags** for content with semantic styling —
  ``<overhead>...</overhead>``.
- **Markdown bold/italic** — ``**X**`` and ``*X*``.

The transform is idempotent: re-running on already-normalized text is
a no-op. Unrecognized templates are passed through unchanged so we
never silently damage content we don't have a rule for.
"""
from __future__ import annotations

import re

# [[Page]] or [[Page|alias]]
_LINK_PATTERN = re.compile(r"\[\[([^\]|]+?)(?:\|([^\]]*?))?\]\]")

# {{plink|item}} / {{plink|item|txt=alias}} / {{plinkp|item}} (picture variant).
# Both are normalized to a typed item link — the picture-vs-link distinction
# is presentation, not semantics.
_PLINK_PATTERN = re.compile(r"\{\{[Pp]link[Pp]?\|([^}|]+)(?:\|([^}]*))?\}\}")

# {{Gender|male|female}}
_GENDER_PATTERN = re.compile(r"\{\{[Gg]ender\|([^}|]*)\|([^}]*)\}\}")

# <player>, <Player>, <player name>, <Player name>
_PLAYER_PATTERN = re.compile(r"<[Pp]layer(?:\s+name)?>")

# '''bold''' must come before italic so the inner '' doesn't mismatch
_BOLD_PATTERN = re.compile(r"'''(.+?)'''")
_ITALIC_PATTERN = re.compile(r"''(.+?)''")

# {{nowiki}}...{{/nowiki}} and <nowiki>...</nowiki>
_NOWIKI_TEMPLATE_PATTERN = re.compile(
    r"\{\{nowiki\}\}(.*?)\{\{/nowiki\}\}", re.DOTALL | re.IGNORECASE
)
_NOWIKI_TAG_PATTERN = re.compile(
    r"<nowiki>(.*?)</nowiki>", re.DOTALL | re.IGNORECASE
)

# {{tmissing}} or {{tmissing|note}}
_TMISSING_PATTERN = re.compile(r"\{\{tmissing(?:\|[^}]*)?\}\}", re.IGNORECASE)

# {{overhead|text}}
_OVERHEAD_PATTERN = re.compile(r"\{\{overhead\|([^}]*)\}\}", re.IGNORECASE)

# {{mes|text}} — system message popup. Strip the wrapper, keep the content;
# the message-vs-line distinction is a UI detail and the content is the
# payload downstream consumers care about.
_MES_PATTERN = re.compile(r"\{\{mes\|([^}]*)\}\}", re.IGNORECASE)

# {{colour|red|text}} / {{color|red|text}} — keep just the text, drop colour.
_COLOUR_PATTERN = re.compile(
    r"\{\{colou?r\|[^}|]*\|([^}]*)\}\}", re.IGNORECASE
)

# {{sic}} or {{sic|note}} — "sic erat scriptum" marker. The optional note
# is an editorial comment ("Missing period", etc.), not user-visible
# content. Drop entirely.
_SIC_PATTERN = re.compile(r"\{\{sic(?:\|[^}]*)?\}\}", re.IGNORECASE)

# {{trandom}} — "random pick follows" wiki marker. Drop; the IR's instruction
# stream already preserves the alternatives as separate top-level branches.
_TRANDOM_PATTERN = re.compile(r"\{\{trandom\}\}", re.IGNORECASE)


def _slug(name: str) -> str:
    """Convert a wiki page name into a URL-safe slug.

    Spaces become underscores; other characters are left as-is. The
    goal is reversibility, not strict URL validity — downstream
    consumers can re-encode if they need to.
    """
    return name.strip().replace(" ", "_")


def _link_replace(match: re.Match[str]) -> str:
    target = match.group(1).strip()
    alias = (match.group(2) or "").strip()
    display = alias or target
    return f"[{display}](wiki:{_slug(target)})"


def _plink_replace(match: re.Match[str]) -> str:
    item = match.group(1).strip()
    args = match.group(2) or ""
    display = item
    for arg in args.split("|"):
        arg = arg.strip()
        if arg.startswith("txt="):
            display = arg[4:].strip()
    return f"[{display}](item:{_slug(item)})"


def _gender_replace(match: re.Match[str]) -> str:
    male = match.group(1).strip().replace('"', "&quot;")
    female = match.group(2).strip().replace('"', "&quot;")
    return f'<gender male="{male}" female="{female}"/>'


def _overhead_replace(match: re.Match[str]) -> str:
    return f"<overhead>{match.group(1).strip()}</overhead>"


def normalize_dialogue_wikitext(text: str) -> str:
    """Normalize raw dialogue wikitext to MDX-style markup.

    Idempotent. Pass-through for empty input. Order of operations is
    intentional: nowiki strips first (so escaped content survives),
    templates expand next, and markdown formatting runs last (so the
    ``'''`` and ``''`` markers from wikitext aren't already inside
    expanded templates).
    """
    if not text:
        return text

    text = _NOWIKI_TEMPLATE_PATTERN.sub(r"\1", text)
    text = _NOWIKI_TAG_PATTERN.sub(r"\1", text)

    text = _SIC_PATTERN.sub("", text)
    text = _TRANDOM_PATTERN.sub("", text)
    text = _TMISSING_PATTERN.sub("<missing/>", text)
    text = _PLAYER_PATTERN.sub("<player/>", text)
    text = _GENDER_PATTERN.sub(_gender_replace, text)
    text = _OVERHEAD_PATTERN.sub(_overhead_replace, text)
    text = _MES_PATTERN.sub(lambda m: m.group(1).strip(), text)
    text = _COLOUR_PATTERN.sub(lambda m: m.group(1).strip(), text)

    text = _PLINK_PATTERN.sub(_plink_replace, text)
    text = _LINK_PATTERN.sub(_link_replace, text)

    text = _BOLD_PATTERN.sub(r"**\1**", text)
    text = _ITALIC_PATTERN.sub(r"*\1*", text)

    return text
