from __future__ import annotations

import sqlite3
from dataclasses import dataclass


@dataclass
class WikiCategory:
    id: int
    name: str
    page_count: int
    subcat_count: int

    _COLS = "id, name, page_count, subcat_count"

    @classmethod
    def by_name(cls, conn: sqlite3.Connection, name: str) -> WikiCategory | None:
        row = conn.execute(
            f"SELECT {cls._COLS} FROM wiki_categories WHERE name = ?", (name,)
        ).fetchone()
        return cls._from_row(row) if row else None

    @classmethod
    def search(cls, conn: sqlite3.Connection, name: str) -> list[WikiCategory]:
        rows = conn.execute(
            f"SELECT {cls._COLS} FROM wiki_categories WHERE name LIKE ? ORDER BY name",
            (f"%{name}%",),
        ).fetchall()
        return [cls._from_row(r) for r in rows]

    @classmethod
    def roots(cls, conn: sqlite3.Connection) -> list[WikiCategory]:
        """Categories with no parents."""
        rows = conn.execute(
            f"""SELECT {cls._COLS} FROM wiki_categories
                WHERE id NOT IN (SELECT category_id FROM wiki_category_parents)
                ORDER BY name"""
        ).fetchall()
        return [cls._from_row(r) for r in rows]

    def children(self, conn: sqlite3.Connection) -> list[WikiCategory]:
        rows = conn.execute(
            f"""SELECT {self._COLS} FROM wiki_categories
                JOIN wiki_category_parents ON wiki_categories.id = wiki_category_parents.category_id
                WHERE wiki_category_parents.parent_id = ?
                ORDER BY name""",
            (self.id,),
        ).fetchall()
        return [self._from_row(r) for r in rows]

    def parents(self, conn: sqlite3.Connection) -> list[WikiCategory]:
        rows = conn.execute(
            f"""SELECT {self._COLS} FROM wiki_categories
                JOIN wiki_category_parents ON wiki_categories.id = wiki_category_parents.parent_id
                WHERE wiki_category_parents.category_id = ?
                ORDER BY name""",
            (self.id,),
        ).fetchall()
        return [self._from_row(r) for r in rows]

    def ancestors(self, conn: sqlite3.Connection) -> list[WikiCategory]:
        """All transitive ancestors via recursive CTE."""
        rows = conn.execute(
            f"""WITH RECURSIVE anc(id) AS (
                    SELECT parent_id FROM wiki_category_parents WHERE category_id = ?
                    UNION
                    SELECT cp.parent_id FROM wiki_category_parents cp
                    JOIN anc ON cp.category_id = anc.id
                )
                SELECT {self._COLS} FROM wiki_categories
                WHERE id IN (SELECT id FROM anc)
                ORDER BY name""",
            (self.id,),
        ).fetchall()
        return [self._from_row(r) for r in rows]

    def descendants(self, conn: sqlite3.Connection) -> list[WikiCategory]:
        """All transitive descendants via recursive CTE."""
        rows = conn.execute(
            f"""WITH RECURSIVE desc(id) AS (
                    SELECT category_id FROM wiki_category_parents WHERE parent_id = ?
                    UNION
                    SELECT cp.category_id FROM wiki_category_parents cp
                    JOIN desc ON cp.parent_id = desc.id
                )
                SELECT {self._COLS} FROM wiki_categories
                WHERE id IN (SELECT id FROM desc)
                ORDER BY name""",
            (self.id,),
        ).fetchall()
        return [self._from_row(r) for r in rows]

    @classmethod
    def for_page(cls, conn: sqlite3.Connection, page_title: str) -> list[WikiCategory]:
        """All categories a wiki page belongs to."""
        rows = conn.execute(
            f"""SELECT {cls._COLS} FROM wiki_categories
                JOIN page_categories ON wiki_categories.id = page_categories.category_id
                WHERE page_categories.page_title = ?
                ORDER BY name""",
            (page_title,),
        ).fetchall()
        return [cls._from_row(r) for r in rows]

    def pages(self, conn: sqlite3.Connection) -> list[str]:
        """All page titles in this category."""
        rows = conn.execute(
            "SELECT page_title FROM page_categories WHERE category_id = ? ORDER BY page_title",
            (self.id,),
        ).fetchall()
        return [r[0] for r in rows]

    @classmethod
    def _from_row(cls, row: tuple) -> WikiCategory:
        return cls(
            id=row[0],
            name=row[1],
            page_count=row[2],
            subcat_count=row[3],
        )
