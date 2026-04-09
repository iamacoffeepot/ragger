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

Templates are expanded **innermost-first** in a fixed-point loop, so
deeply nested forms like ``{{mes|...{{Colour|red|word}}...}}`` are
unwound from the leaves up. The transform is idempotent: re-running on
already-normalized text is a no-op. Unrecognized templates are passed
through unchanged so we never silently damage content we don't have a
rule for.
"""
from __future__ import annotations

import re

# [[Page]] or [[Page|alias]]
_LINK_PATTERN = re.compile(r"\[\[([^\]|]+?)(?:\|([^\]]*?))?\]\]")

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

# An "innermost" template: ``{{name|args}}`` where the body contains
# no other ``{`` or ``}`` characters. Each fixed-point iteration
# strips one nesting level by matching only leaf templates.
_INNERMOST_TEMPLATE_PATTERN = re.compile(r"\{\{([^{}]+?)\}\}", re.DOTALL)


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


def _split_args(args: str) -> list[str]:
    """Split template args on top-level ``|`` only.

    The dialogue parser already brace-balances at the line level, but
    by the time the normalizer is running on a string the args may
    contain nested templates that have already been expanded into MDX
    output (which can include ``|`` inside ``[[...]]`` markdown link
    URLs — there are none, but the principle is the same). Defensive
    splitting keeps the rules robust to whatever's in the value.
    """
    parts: list[str] = []
    start = 0
    bracket_depth = 0
    i = 0
    n = len(args)
    while i < n:
        if i + 1 < n:
            pair = args[i:i + 2]
            if pair == "[[":
                bracket_depth += 1
                i += 2
                continue
            if pair == "]]":
                bracket_depth -= 1
                i += 2
                continue
        if args[i] == "|" and bracket_depth == 0:
            parts.append(args[start:i])
            start = i + 1
        i += 1
    parts.append(args[start:])
    return parts


def _expand_template(name: str, args: str) -> str | None:
    """Return the replacement for one template, or ``None`` to leave it.

    ``args`` is the raw text after the first ``|`` (or ``""`` for a
    no-arg template). The expansion rules cover the high-frequency
    templates seen in the dialogue corpus; anything else returns
    ``None`` so the template passes through unchanged.
    """
    name = name.strip().lower()

    if name == "tmissing":
        return "<missing/>"
    if name == "sic":
        return ""
    if name == "trandom":
        return ""

    if name == "mes":
        # System message popup. Strip the wrapper, keep the content;
        # the message-vs-line distinction is a UI detail and the
        # content is what downstream consumers care about. Multi-arg
        # mes templates with inline color overrides ({{mes|a|color=b|c}})
        # are joined back into one string — the color metadata is lost
        # but the text payload is preserved.
        parts = _split_args(args)
        return " ".join(p.strip() for p in parts if p.strip() and not p.strip().startswith("color="))

    if name in ("colour", "color"):
        # {{colour|red|text}} → text. Drop the color, keep the payload.
        parts = _split_args(args)
        if len(parts) >= 2:
            return parts[-1].strip()
        return args.strip()

    if name == "gender":
        parts = _split_args(args)
        male = (parts[0] if parts else "").strip().replace('"', "&quot;")
        female = (parts[1] if len(parts) > 1 else "").strip().replace('"', "&quot;")
        return f'<gender male="{male}" female="{female}"/>'

    if name == "overhead":
        return f"<overhead>{args.strip()}</overhead>"

    if name in ("plink", "plinkp"):
        parts = _split_args(args)
        item = parts[0].strip() if parts else ""
        display = item
        for arg in parts[1:]:
            arg = arg.strip()
            if arg.startswith("txt="):
                display = arg[4:].strip()
        return f"[{display}](item:{_slug(item)})"

    return None


def _innermost_replace(match: re.Match[str]) -> str:
    body = match.group(1)
    if "|" in body:
        name, args = body.split("|", 1)
    else:
        name, args = body, ""
    expanded = _expand_template(name, args)
    return expanded if expanded is not None else match.group(0)


def normalize_dialogue_wikitext(text: str) -> str:
    """Normalize raw dialogue wikitext to MDX-style markup.

    Idempotent. Pass-through for empty input. Order of operations:

    1. Strip ``nowiki`` wrappers (escape hatch).
    2. Expand templates from the innermost out, fixed-point. Each
       iteration strips one nesting level; unrecognized templates
       block further progress at their level but don't crash.
    3. Convert ``<player>``-style substitution slots.
    4. Convert ``[[wiki links]]`` to markdown links.
    5. Convert wikitext bold/italic to markdown bold/italic.
    """
    if not text:
        return text

    text = _NOWIKI_TEMPLATE_PATTERN.sub(r"\1", text)
    text = _NOWIKI_TAG_PATTERN.sub(r"\1", text)

    # Innermost-first template expansion. Each pass strips the leaves
    # of the template tree; we stop when nothing changes (either the
    # tree is fully expanded or only unrecognized templates remain).
    while True:
        new_text = _INNERMOST_TEMPLATE_PATTERN.sub(_innermost_replace, text)
        if new_text == text:
            break
        text = new_text

    text = _PLAYER_PATTERN.sub("<player/>", text)
    text = _LINK_PATTERN.sub(_link_replace, text)

    text = _BOLD_PATTERN.sub(r"**\1**", text)
    text = _ITALIC_PATTERN.sub(r"*\1*", text)

    return text
