### Wiki utilities (`src/ragger/wiki.py`)

```python
from ragger.wiki import (
    WIKI_BATCH_SIZE,
    WikiCache,
    set_wiki_cache,
    get_wiki_cache,
    default_cache,
    fetch_category_members,
    fetch_page_wikitext,
    fetch_pages_wikitext_batch,
    fetch_page_wikitext_with_attribution,
    fetch_contributors_batch,
    record_attribution,
    record_attributions_batch,
    strip_markup,
    strip_refs,
    strip_wiki_links,
    strip_plinks,
    clean_name,
    detect_versions,
    extract_template,
    extract_section,
    parse_template_param,
    parse_int,
    parse_xp,
    parse_ticks,
    parse_members,
    parse_boostable,
    parse_skill_requirements,
    link_requirement,
    throttle,
)

# Constants
WIKI_BATCH_SIZE = 50                                                       # max pages per MediaWiki API batch request

# Cache
WikiCache(path, ttl=DEFAULT_WIKI_TTL)                                      # SQLite-backed wikitext cache with TTL-based freshness
cache.validate() -> None                                                   # bulk-check revids, bump fetched_at on fresh, evict stale
set_wiki_cache(path) -> None                                               # set default cache instance (or None to disable)
get_wiki_cache() -> WikiCache | None                                       # get default cache instance
default_cache: WikiCache | None                                            # module-level default (from RAGGER_WIKI_CACHE env var)

# Fetching (accept optional cache=WikiCache parameter)
fetch_category_members(category, ...) -> list[str]                         # paginated category listing
fetch_page_wikitext(page, cache?) -> str                                   # raw wikitext for one page
fetch_pages_wikitext_batch(pages, cache?) -> dict[str, str]                # batch fetch up to 50 pages
fetch_page_wikitext_with_attribution(conn, page, table_name) -> str        # wikitext + record attribution
fetch_contributors_batch(pages) -> dict[str, list[str]]                    # contributors for up to 50 pages

# Attribution (required for all data ingestion)
record_attribution(conn, table_name, wiki_page, authors)                   # single page
record_attributions_batch(conn, table_names, pages)                        # batched; table_names can be str or list[str]

# Parsing
strip_markup(text) -> str                                                  # remove wiki markup
strip_refs(val) -> str | None                                              # strip <ref> tags and {{Refn}} templates
strip_wiki_links(text) -> str                                              # [[Link|Display]] -> Display
strip_plinks(text) -> str                                                  # {{plink|Name}} -> Name
clean_name(text, page_name) -> str                                         # strip links + plinks + clean page ref
detect_versions(block) -> list[str]                                        # version1, version2, ... from template block
extract_template(wikitext, template_name) -> str | None                    # nested brace-aware
extract_section(wikitext, field_name) -> str                               # |field= section
parse_template_param(text, param) -> str | None                            # brace-aware param extraction
parse_int(val) -> int | None                                               # "1,234" / "+15" / "5%" -> int
parse_xp(val) -> float                                                     # XP string -> float, 0.0 default
parse_ticks(val) -> int | None                                             # tick count, None for N/A/varies
parse_members(val) -> int                                                  # "Yes"/"No" -> 1/0, default 1
parse_boostable(val) -> int | None                                         # "Yes"/"No" -> 1/0
parse_skill_requirements(text) -> list[tuple[int, int]]                    # {{SCP|Skill|Level}}

# DB helpers
link_requirement(conn, table, columns, junction_table, ...)                # insert-or-ignore + link
throttle()                                                                 # rate limit (default 1s)
```
