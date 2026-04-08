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
