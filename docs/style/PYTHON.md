# Python Style Guide

## Type hints

Use modern syntax (`str | None`, `list[int]`) with `from __future__ import annotations`. Annotate function signatures and class fields. Don't annotate obvious locals.

```python
# WRONG
from typing import Optional, List

def search(conn: sqlite3.Connection, title: str) -> Optional[List[str]]:

# RIGHT
from __future__ import annotations

def search(conn: sqlite3.Connection, title: str) -> list[str] | None:
```

## Dataclasses for data models

Use `@dataclass` for plain data containers. Put classmethods for database queries on the dataclass itself.

```python
@dataclass
class DialoguePage:
    id: int
    title: str
    page_type: str | None

    @classmethod
    def by_title(cls, conn: sqlite3.Connection, title: str) -> DialoguePage | None:
        row = conn.execute(
            "SELECT id, title, page_type FROM dialogue_pages WHERE title = ?", (title,)
        ).fetchone()
        return cls(*row) if row else None
```

## SQL formatting

Short queries on one line. Multi-line queries use triple-quoted strings with consistent indentation.

```python
# short — one line is fine
rows = conn.execute("SELECT id, name FROM items WHERE name = ?", (name,)).fetchall()

# long — triple-quoted, indented
rows = conn.execute(
    """SELECT id, page_id, parent_id, sort_order, depth, node_type, speaker, text, section
       FROM dialogue_nodes WHERE page_id = ? AND parent_id IS NULL
       ORDER BY sort_order""",
    (page_id,),
).fetchall()
```

## Comprehensions over loops for simple transforms

```python
# WRONG
result = []
for r in rows:
    result.append(cls(*r))
return result

# RIGHT
return [cls(*r) for r in rows]
```

## Blank lines — group by purpose

Same principle as Java. Separate guards, setup, and return with blank lines.

## Comments — only when non-obvious

Docstrings on public API methods. Inline comments only when the why isn't clear.

```python
# WRONG
# Return None if no row
return cls(*row) if row else None

# RIGHT — explains a non-obvious design choice
"""Return only the top-level nodes (no parent)."""
```

## Enums for well-defined values

Use `str, Enum` or `int, Enum` instead of bare strings or integers when the set of values is known and fixed. Define enums in `enums.py` and reference them in dataclass fields, comparisons, and DB inserts.

```python
# WRONG
node_type: str  # "line", "option", "condition", ...

if node.node_type == "condition":
    ...

# RIGHT
node_type: DialogueNodeType

if node.node_type == DialogueNodeType.CONDITION:
    ...
```

## Verbose module names inside subpackages

Inside subpackages, repeat the package prefix on filenames rather than dropping it. `dialogue/dialogue_flatten.py`, not `dialogue/flatten.py`. The visual redundancy is worth it — `rg dialogue_flatten` finds the file unambiguously, imports read clearly at the call site, and filename collisions across unrelated subpackages stop being possible.

```python
# WRONG
# src/ragger/dialogue/flatten.py
# src/ragger/dialogue/passes.py

# RIGHT
# src/ragger/dialogue/dialogue_flatten.py
# src/ragger/dialogue/dialogue_passes.py
```

## No section headers

Never use comments as section dividers. Let blank lines and logical grouping speak for themselves.

```python
# WRONG
# --- Database queries ---
def get_items(): ...
def get_quests(): ...

# --- Helpers ---
def parse_name(): ...

# WRONG
##############################
# Initialization
##############################

# RIGHT — just group with blank lines, no headers
def get_items(): ...
def get_quests(): ...

def parse_name(): ...
```
