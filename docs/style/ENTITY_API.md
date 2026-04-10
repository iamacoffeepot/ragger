# Entity API Conventions

Rules for Python dataclass APIs in `src/ragger/`. Every entity that maps to a database table should follow these patterns so that the query surface is predictable without reading each module's docs.

## Query methods

Every entity must provide these class methods where applicable:

| Method | Signature | When to include |
|--------|-----------|-----------------|
| `by_name` | `(conn, name) -> T \| None` | Every entity with a unique `name` column |
| `search` | `(conn, name) -> list[T]` | Every entity with a `name` column |
| `all` | `(conn, **filters) -> list[T]` | Every entity |

### `by_name` — exact match, single result

Always returns `T | None`. If the entity has non-unique names (e.g. NPCs with versions), return the first match or accept an optional disambiguator like `version`.

```python
@classmethod
def by_name(cls, conn, name) -> Item | None:
```

Never return a list from `by_name`. If callers need all versions, provide a separate method (e.g. `all_by_name`).

### `search` — partial match, multiple results

Always `LIKE %name%`, always returns `list[T]`, always ordered by `name`.

```python
@classmethod
def search(cls, conn, name) -> list[Item]:
```

### `all` — full listing with optional filters

Returns `list[T]`, ordered by `name` (or `level`, `sort_order` where name doesn't apply). Common filter parameters: `region`, `members`, type-specific enums.

```python
@classmethod
def all(cls, conn, region=None, shop_type=None) -> list[Shop]:
```

## Additional query methods

These are optional but should use consistent naming when present:

| Method | Signature | Purpose |
|--------|-----------|---------|
| `by_id` | `(conn, id) -> T \| None` | Lookup by primary key |
| `at_level` | `(conn, level) -> list[T]` | All entities with `level <= N` |
| `for_skill` | `(conn, skill) -> list[T]` | Bitmask match on skills field |
| `near` | `(conn, x, y, radius?) -> list[T]` | Spatial proximity |
| `nearest` | `(conn, x, y) -> T \| None` | Single closest result |
| `at_location` | `(conn, location_id) -> list[T]` | By location FK |

Prefix conventions:
- `by_` — lookup by a specific field value (exact match)
- `for_` — entities related to another entity or concept
- `at_` — spatial or positional lookup
- `near` / `nearest` — distance-based lookup

## Instance methods

Relationship accessors follow the pattern `related_thing(conn) -> list[T]` or `related_thing(conn) -> T | None`:

```python
def runes(self, conn) -> list[SpellRune]:
def locations(self, conn) -> list[MonsterLocation]:
def game_vars(self, conn) -> list[GameVariable]:
```

## Field naming

### Coordinates

Always `x`, `y`, `plane` for map coordinates. Use `dst_x`, `dst_y` for destination coordinates. Always `int | None` unless the entity is guaranteed to have coordinates (e.g. ground item spawns).

### Boolean fields

`members` is always `bool` (not `bool | None`). Default to `False` when the wiki doesn't specify. Other boolean fields (`tradeable`, `aggressive`) may be `bool | None` when the absence of data is meaningful.

### Stat prefixes

Use `attack_` and `defence_` prefixes for offensive and defensive bonuses (matching Equipment). Not `defensive_` — that's the Monster table's legacy naming and should be migrated.

### Bitmask fields

Name bitmask fields after what they contain: `skills`, `immunities`, `facilities`. Provide a `_list()` convenience method to expand them:

```python
def skill_list(self) -> list[Skill]:
def immunity_list(self) -> list[Immunity]:
def facility_list(self) -> list[Facility]:
```

### Enums over strings

Use enum types for fields with a known fixed set of values. Store the enum's `.value` in the database, construct the enum in `_from_row`.

## `_from_row` pattern

Every entity uses a private `_from_row(cls, row) -> T` classmethod to construct from a database row tuple. Keep `_COLS` as a class variable listing the SELECT columns in order.

```python
_COLS = "id, name, members, level"

@classmethod
def _from_row(cls, row: tuple) -> Spell:
    return cls(id=row[0], name=row[1], members=bool(row[2]), level=row[3])
```

## Ordering

- `all()` and `search()` results: `ORDER BY name` (or `level` for spells, `sort_order` for nodes)
- `near()` results: `ORDER BY distance`
- Relationship accessors: `ORDER BY name` or natural order

## Connection parameter

Every query method takes `conn: sqlite3.Connection` as the first parameter. This is always a positional argument, never keyword-only.
