"""Item possession, currency, and coin frames."""
from __future__ import annotations

from ragger.dialogue.condition_types import (
    CONTAINER,
    CUR_CMP,
    CUR_COUNT,
    COUNT,
    FrameRule,
    HAS_VERB,
    ITEM_NOUN,
    ITEM_NOUN_NC,
    NEG,
    make_atom,
    parse_count,
    pre_rule,
    rule,
)


def _has_item(m) -> "Atom":  # noqa: F821
    gd = m.groupdict()
    return make_atom(
        "has_item",
        count=parse_count(gd.get("count")),
        qual=gd.get("qual") or "any",
        neg=bool(gd.get("neg")),
    )


def _has_coins(m) -> "Atom":  # noqa: F821
    gd = m.groupdict()
    return make_atom(
        "has_coins",
        amount=parse_count(gd.get("count")) if gd.get("count") else None,
        cmp=(gd.get("cmp") or "ge").strip(),
        neg=bool(gd.get("neg")),
    )


RULES: list[FrameRule] = [
    # --- has_item core ---
    rule("has_item",
         rf"^{NEG}{HAS_VERB}\s+"
         rf"(?:at least |at most |more than |less than |only |fewer than |enough )?"
         rf"{COUNT}?\s*"
         rf"(?:piece of |bit of )?(?:their )?{ITEM_NOUN}"
         rf"(?:\s+in (?:their |the )?(?P<qual>inventory|bank|possession))?"
         rf"(?:\s+.*)?$",
         _has_item),
    rule("has_item",
         rf"^(?:has|have)\s+(?:lost|lost/banked) (?:the |a |an |both |one |their )?{ITEM_NOUN}(?:\s+.*)?$",
         lambda m: make_atom("has_item", count=1, qual="any", neg=True)),
    rule("has_item",
         rf"^lost (?:the |a |an |their )?{ITEM_NOUN}(?:\s+.*)?$",
         lambda m: make_atom("has_item", count=1, qual="any", neg=True)),
    rule("has_item",
         rf"^(?:gets?|receives?|finds?|takes?)\s+(?:a |an |the )?{ITEM_NOUN}(?:\s+.*)?$",
         lambda m: make_atom("has_item", count=1, qual="any", neg=False)),
    rule("has_item",
         rf"^(?:a |an |the )?{ITEM_NOUN}\s+in (?:their |the )?(?P<qual>inventory|bank)(?:\s+.*)?$",
         _has_item),
    rule("has_item",
         rf"^(?:has|have)\s+(?:not\s+)?claimed (?:their |the )?{ITEM_NOUN}(?:\s+.*)?$",
         lambda m: make_atom("has_item", count=1, qual="any", neg="not " in m.string[:m.end()])),
    rule("has_item",
         rf"^claimed (?:their |the )?{ITEM_NOUN}(?:\s+.*)?$",
         lambda m: make_atom("has_item", count=1, qual="any", neg=False)),
    rule("has_item",
         rf"^needs to (?:repair|fix|replace) (?:the |a |an )?{ITEM_NOUN}(?:\s+.*)?$",
         lambda m: make_atom("has_item", count=1, qual="any", neg=True)),
    rule("has_item",
         rf"^(?:is\s+)?missing\s+(?:only\s+)?(?:a |an |the |some )?{ITEM_NOUN}(?:\s+.*)?$",
         lambda m: make_atom("has_item", count=1, qual="any", neg=True)),
    rule("has_item",
         rf"^{NEG}(?:have|has)\s+no\s+{ITEM_NOUN}"
         rf"(?:\s+in (?:their |the )?(?:player's )?(?P<qual>inventory|bank|possession))?"
         rf"(?:\s+.*)?$",
         lambda m: make_atom("has_item", count=0, qual=m.groupdict().get("qual") or "any", neg=True)),
    rule("has_item",
         rf"^{NEG}{HAS_VERB}\s+both\s+(?:a |an |the )?{ITEM_NOUN}\s+and\s+(?:a |an |the )?{ITEM_NOUN_NC}(?:\s+.*)?$",
         lambda m: make_atom("has_item", count=2, qual="any", neg=bool(m.groupdict().get("neg")))),
    rule("has_item",
         rf"^(?:the |a )?{ITEM_NOUN}\s+is\s+(?:not\s+)?in\s+(?:the\s+)?(?:player's\s+)?(?P<qual>inventory|bank)(?:\s+.*)?$",
         lambda m: make_atom("has_item", count=1, qual=m.groupdict().get("qual") or "inventory", neg="not " in m.string)),
    rule("has_item",
         rf"^(?:is\s+)?(?P<neg>not\s+)?(?:holding|carrying)\s+(?:a |an |the )?{ITEM_NOUN}"
         rf"(?:\s+in (?:their |the )?(?P<qual>inventory|bank|possession))?"
         rf"(?:\s+.*)?$",
         _has_item),
    rule("has_item",
         rf"^(?:has\s+|have\s+)?brought\s+(?:a |an |the |their )?{ITEM_NOUN}(?:\s+.*)?$",
         lambda m: make_atom("has_item", count=1, qual="any", neg=False)),
    rule("has_item",
         rf"^(?:the |a )?{ITEM_NOUN}\s+is\s+(?P<neg>not\s+)?with\s+(?:the\s+)?player(?:\s+.*)?$",
         lambda m: make_atom("has_item", count=1, qual="any", neg=bool(m.groupdict().get("neg")))),
    rule("has_item",
         rf"^(?:has|have)\s+(?:not\s+)?(?:a |an |the )"
         rf"(?:enchanted|completed|charged|correct|repaired|fixed|restored|full|empty|broken|assembled|combined|finished)\s+"
         rf"{ITEM_NOUN}(?:\s+.*)?$",
         lambda m: make_atom("has_item", count=1, qual="any", neg="not " in m.string[:20])),
    rule("has_item",
         rf"^(?:has|have)\s+(?:not\s+)?their\s+{ITEM_NOUN}\s+with\s+them(?:\s+.*)?$",
         lambda m: make_atom("has_item", count=1, qual="any", neg="not " in m.string[:20])),
    rule("has_item",
         rf"^(?:has|have)\s+(?:not\s+)?acquired\s+(?:a |an |the )?{ITEM_NOUN}(?:\s+.*)?$",
         lambda m: make_atom("has_item", count=1, qual="any", neg="not " in m.string[:20])),
    rule("has_item",
         rf"^still\s+(?:has|have)\s+(?:a |an |the )?{ITEM_NOUN}(?:\s+.*)?$",
         lambda m: make_atom("has_item", count=1, qual="any", neg=False)),
    rule("has_item",
         rf"^there is at least (?P<count>\d+|one|two|three|four|five|six|seven|eight|nine|ten)\s+{ITEM_NOUN}(?:\s+.*)?$",
         lambda m: make_atom("has_item", count=parse_count(m.group("count")), qual="any", neg=False)),
    rule("has_item",
         rf"^there are no \w+ in the (?:bank|inventory)(?:\s+.*)?$",
         lambda m: make_atom("has_item", count=1, qual="any", neg=True)),

    # --- has_item pre-strip (container-qualified, prepositional) ---
    pre_rule("has_item",
             rf"^(?:if\s+)?(?:there\s+(?:are|is)\s+){CUR_CMP}(?P<count>\d+|a|an|the|one|two|three|four|five)?\s*(?:\(or more\)\s*)?{ITEM_NOUN}\s+in\s+{CONTAINER}(?:\s+.*)?$",
             lambda m: make_atom("has_item", count=parse_count(m.groupdict().get("count")), qual=m.groupdict().get("qual") or "inventory", neg=False)),
    pre_rule("has_item",
             rf"^with\s+{CUR_CMP}(?P<count>\d+|a|an|the|one|two|three|four|five)?\s*{ITEM_NOUN}\s+in\s+{CONTAINER}(?:\s+.*)?$",
             lambda m: make_atom("has_item", count=parse_count(m.groupdict().get("count")), qual=m.groupdict().get("qual") or "inventory", neg=False)),
    pre_rule("has_item",
             rf"^with\s+(?P<count>\d+|a|an|the|one|two|three|four|five)?\s*(?:a |an |the )?{ITEM_NOUN}(?:\s+(?:only|with them))?$",
             lambda m: make_atom("has_item", count=parse_count(m.groupdict().get("count")), qual="any", neg=False)),
    pre_rule("has_item",
             rf"^without\s+(?:having\s+)?(?:a |an |the )?{ITEM_NOUN}(?:\s+.*)?$",
             lambda m: make_atom("has_item", count=1, qual="any", neg=True)),
    pre_rule("has_item",
             rf"^(?:if\s+)?while\s+(?:already\s+)?having\s+(?:a |an |the )?{ITEM_NOUN}(?:\s+.*)?$",
             lambda m: make_atom("has_item", count=1, qual="any", neg=False)),

    # --- has_all_items ---
    rule("has_all_items",
         rf"^(?:has|have)\s+(?:not\s+)?all\s+(?:the\s+)?(?:required\s+)?(?:items|materials|components|ingredients|parts|pieces)(?:\s+.*)?$",
         lambda m: make_atom("has_all_items", neg="not " in m.string[:20])),
    rule("has_all_items",
         rf"^(?:does not |do not )?have\s+all\s+(?:the\s+)?(?:required\s+)?(?:items|materials|components|ingredients|parts|pieces)(?:\s+.*)?$",
         lambda m: make_atom("has_all_items", neg="does not" in m.string[:15] or "do not" in m.string[:10])),

    # --- showing_item ---
    rule("showing_item",
         rf"^{NEG}(?:is\s+)?showing\s+(?:the |a |an )?{ITEM_NOUN}(?:\s+.*)?$",
         lambda m: make_atom("showing_item", neg=bool(m.groupdict().get("neg")))),

    # --- has_read ---
    rule("has_read",
         rf"^(?:has|have)\s+(?:not\s+)?read\s+(?:the\s+)?{ITEM_NOUN}(?:\s+.*)?$",
         lambda m: make_atom("has_read", neg="not " in m.string[:m.end()])),

    # --- has_coins ---
    rule("has_coins",
         rf"^{NEG}{HAS_VERB}\s+(?P<cmp>at least |at most |more than |less than |enough )?"
         rf"(?P<count>\d{{1,3}}(?:,\d{{3}})+|\d+)?\s*(?:coins?|gp|gold|money)(?:\s+.*)?$",
         _has_coins),
    rule("has_coins",
         rf"^{NEG}{HAS_VERB}\s+enough (?:coins?|money|gold|gp)(?:\s+.*)?$",
         lambda m: make_atom("has_coins", amount=None, cmp="enough", neg=bool(m.groupdict().get("neg")))),

    # --- has_currency ---
    rule("has_currency",
         rf"^{NEG}{HAS_VERB}\s+(?P<cmp>at least |at most |more than |less than |fewer than |enough )?"
         rf"(?P<count>\d{{1,3}}(?:,\d{{3}})+|\d+|no)?\s*(?:or more |or fewer )?"
         rf"\{{currency\}}(?:\s+.*)?$",
         lambda m: make_atom(
             "has_currency",
             amount=parse_count(m.groupdict().get("count")) if m.groupdict().get("count") and m.groupdict().get("count") != "no" else None,
             cmp=(m.groupdict().get("cmp") or "ge").strip(),
             neg=bool(m.groupdict().get("neg")) or m.groupdict().get("count") == "no")),
    # "less/fewer than N {currency} in inventory" — must be before general
    pre_rule("has_currency",
             rf"^(?:if\s+)?(?:there\s+(?:are|is)\s+)?(?:less|fewer)\s+than\s+{CUR_COUNT}\s*\{{currency\}}\s+in\s+{CONTAINER}(?:\s+.*)?$",
             lambda m: make_atom("has_currency", amount=parse_count(m.groupdict().get("count")) if m.groupdict().get("count") else None, cmp="lt", qual=m.groupdict().get("qual") or "inventory", neg=False)),
    pre_rule("has_currency",
             rf"^(?:if\s+)?(?:there\s+(?:are|is)\s+){CUR_CMP}{CUR_COUNT}?\s*(?:\(or more\)\s*)?\{{currency\}}\s+in\s+{CONTAINER}(?:\s+.*)?$",
             lambda m: make_atom("has_currency", amount=parse_count(m.groupdict().get("count")) if m.groupdict().get("count") else None, cmp="ge", qual=m.groupdict().get("qual") or "inventory", neg=False)),
    pre_rule("has_currency",
             rf"^with\s+{CUR_CMP}{CUR_COUNT}\s*\{{currency\}}\s+in\s+{CONTAINER}(?:\s+.*)?$",
             lambda m: make_atom("has_currency", amount=parse_count(m.groupdict().get("count")) if m.groupdict().get("count") else None, cmp="ge", qual=m.groupdict().get("qual") or "inventory", neg=False)),

    # --- currency_cap ---
    pre_rule("currency_cap",
             rf"^if the value of the item puts the player over the maximum amount of \{{currency\}}.*$",
             lambda m: make_atom("currency_cap")),

    # --- received_reward ---
    pre_rule("received_reward",
             rf"^(?:if\s+)?(?:when\s+)?given (?:a |the |another )?reward(?:\s+.*)?$",
             lambda m: make_atom("received_reward")),
    pre_rule("received_reward",
             rf"^(?:if\s+)?(?:when\s+)?given\s+(?:a |an |the |another )?{ITEM_NOUN}(?:\s+.*)?$",
             lambda m: make_atom("received_reward")),
    pre_rule("received_reward",
             rf"^(?:if\s+)?(?:the\s+)?result is (?:a |an |the |another )?{ITEM_NOUN}(?:\s+.*)?$",
             lambda m: make_atom("received_reward")),
    pre_rule("received_reward",
             rf"^(?:if\s+)?(?:the\s+)?result is (?:nothing|empty)$",
             lambda m: make_atom("received_reward")),
    rule("received_reward",
         rf"^(?:has|have)\s+(?:not\s+)?(?:received|gotten)\s+(?:a |an |the |another )?{ITEM_NOUN}(?:\s+.*)?$",
         lambda m: make_atom("received_reward")),

    # --- reward_is ---
    rule("reward_is",
         rf"^(?:the\s+)?reward\s+.*$",
         lambda m: make_atom("reward_is")),
]
