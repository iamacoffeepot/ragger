### WikiCategory (`src/ragger/category.py`)

```python
from ragger.category import WikiCategory

WikiCategory.by_name(conn, name) -> WikiCategory | None
WikiCategory.search(conn, name) -> list[WikiCategory]     # partial name match
WikiCategory.roots(conn) -> list[WikiCategory]             # categories with no parents
WikiCategory.for_page(conn, page_title) -> list[WikiCategory]  # categories a page belongs to

category.children(conn) -> list[WikiCategory]              # direct subcategories
category.parents(conn) -> list[WikiCategory]               # direct parent categories
category.ancestors(conn) -> list[WikiCategory]             # all transitive parents (recursive CTE)
category.descendants(conn) -> list[WikiCategory]           # all transitive children (recursive CTE)
category.pages(conn) -> list[str]                          # page titles in this category

category.name -> str
category.page_count -> int                                 # pages directly in this category
category.subcat_count -> int                               # number of direct subcategories
```
