from __future__ import annotations

import heapq
import sqlite3
from collections import defaultdict
from dataclasses import dataclass

from ragger.enums import MAP_LINK_ANYWHERE, MapLinkType, MapSquareType
from ragger.location import DistanceMetric

GAME_TILES_PER_REGION = 64
PIXELS_PER_REGION = 256


@dataclass
class MapSquare:
    id: int
    plane: int
    region_x: int
    region_y: int
    type: MapSquareType
    image: bytes

    @property
    def game_x(self) -> int:
        return self.region_x * GAME_TILES_PER_REGION

    @property
    def game_y(self) -> int:
        return self.region_y * GAME_TILES_PER_REGION

    @classmethod
    def _from_row(cls, row: tuple) -> MapSquare:
        return cls(
            id=row[0],
            plane=row[1],
            region_x=row[2],
            region_y=row[3],
            type=MapSquareType(row[4]),
            image=row[5],
        )

    @classmethod
    def get(
        cls, conn: sqlite3.Connection, plane: int, region_x: int, region_y: int,
        type: MapSquareType = MapSquareType.COLOR,
    ) -> MapSquare | None:
        row = conn.execute(
            "SELECT id, plane, region_x, region_y, type, image FROM map_squares WHERE plane = ? AND region_x = ? AND region_y = ? AND type = ?",
            (plane, region_x, region_y, type.value),
        ).fetchone()
        return cls._from_row(row) if row else None

    @classmethod
    def all(
        cls, conn: sqlite3.Connection, plane: int = 0,
        type: MapSquareType = MapSquareType.COLOR,
    ) -> list[MapSquare]:
        rows = conn.execute(
            "SELECT id, plane, region_x, region_y, type, image FROM map_squares WHERE plane = ? AND type = ? ORDER BY region_x, region_y",
            (plane, type.value),
        ).fetchall()
        return [cls._from_row(row) for row in rows]

    @classmethod
    def at_game_coord(
        cls, conn: sqlite3.Connection, x: int, y: int, plane: int = 0,
        type: MapSquareType = MapSquareType.COLOR,
    ) -> MapSquare | None:
        rx = x // GAME_TILES_PER_REGION
        ry = y // GAME_TILES_PER_REGION
        return cls.get(conn, plane, rx, ry, type)

    @classmethod
    def count(cls, conn: sqlite3.Connection, plane: int = 0, type: MapSquareType | None = None) -> int:
        if type is not None:
            return conn.execute("SELECT COUNT(*) FROM map_squares WHERE plane = ? AND type = ?", (plane, type.value)).fetchone()[0]
        return conn.execute("SELECT COUNT(*) FROM map_squares WHERE plane = ?", (plane,)).fetchone()[0]

    @classmethod
    def stitch(
        cls, conn: sqlite3.Connection,
        x_min: int, x_max: int, y_min: int, y_max: int,
        plane: int = 0,
        type: MapSquareType = MapSquareType.COLOR,
        region_padding: int = 1,
    ) -> tuple:
        """Stitch map tiles for a game coordinate bounding box.

        Returns (numpy.ndarray, extent) where extent is [x_min, x_max, y_min, y_max]
        in game coordinates, suitable for matplotlib imshow.

        region_padding adds extra regions around the bounding box (default 1).
        """
        import io

        import numpy as np
        from PIL import Image

        rx_min = max(0, x_min // GAME_TILES_PER_REGION - region_padding)
        rx_max = (x_max - 1) // GAME_TILES_PER_REGION + region_padding
        ry_min = max(0, y_min // GAME_TILES_PER_REGION - region_padding)
        ry_max = (y_max - 1) // GAME_TILES_PER_REGION + region_padding

        pixels_per = PIXELS_PER_REGION if type == MapSquareType.COLOR else GAME_TILES_PER_REGION
        canvas_w = (rx_max - rx_min + 1) * pixels_per
        canvas_h = (ry_max - ry_min + 1) * pixels_per
        canvas = np.zeros((canvas_h, canvas_w, 3), dtype=np.uint8)

        rows = conn.execute(
            "SELECT region_x, region_y, image FROM map_squares WHERE plane = ? AND type = ? "
            "AND region_x >= ? AND region_x <= ? AND region_y >= ? AND region_y <= ?",
            (plane, type.value, rx_min, rx_max, ry_min, ry_max),
        ).fetchall()
        for rx, ry, img_data in rows:
            try:
                tile = np.array(Image.open(io.BytesIO(img_data)).convert("RGB"))
                px = (rx - rx_min) * pixels_per
                py = (ry_max - ry) * pixels_per
                canvas[py:py + pixels_per, px:px + pixels_per] = tile
            except Exception:
                pass

        extent = [
            rx_min * GAME_TILES_PER_REGION,
            (rx_max + 1) * GAME_TILES_PER_REGION,
            ry_min * GAME_TILES_PER_REGION,
            (ry_max + 1) * GAME_TILES_PER_REGION,
        ]
        return canvas, extent


@dataclass
class MapLink:
    id: int
    src_location: str
    dst_location: str
    src_x: int
    src_y: int
    dst_x: int
    dst_y: int
    link_type: MapLinkType
    description: str | None

    @classmethod
    def all(cls, conn: sqlite3.Connection, link_type: MapLinkType | None = None) -> list[MapLink]:
        query = "SELECT id, src_location, dst_location, src_x, src_y, dst_x, dst_y, type, description FROM map_links"
        params: list = []
        if link_type is not None:
            query += " WHERE type = ?"
            params.append(link_type.value)
        query += " ORDER BY src_location, dst_location"
        return [cls._from_row(r) for r in conn.execute(query, params).fetchall()]

    @classmethod
    def departing(cls, conn: sqlite3.Connection, location: str, link_type: MapLinkType | None = None) -> list[MapLink]:
        query = "SELECT id, src_location, dst_location, src_x, src_y, dst_x, dst_y, type, description FROM map_links WHERE src_location = ?"
        params: list = [location]
        if link_type is not None:
            query += " AND type = ?"
            params.append(link_type.value)
        query += " ORDER BY type, dst_location"
        return [cls._from_row(r) for r in conn.execute(query, params).fetchall()]

    @classmethod
    def arriving(cls, conn: sqlite3.Connection, location: str, link_type: MapLinkType | None = None) -> list[MapLink]:
        query = "SELECT id, src_location, dst_location, src_x, src_y, dst_x, dst_y, type, description FROM map_links WHERE dst_location = ?"
        params: list = [location]
        if link_type is not None:
            query += " AND type = ?"
            params.append(link_type.value)
        query += " ORDER BY type, src_location"
        return [cls._from_row(r) for r in conn.execute(query, params).fetchall()]

    @classmethod
    def between(cls, conn: sqlite3.Connection, location_a: str, location_b: str, link_type: MapLinkType | None = None) -> list[MapLink]:
        if link_type is not None:
            query = """SELECT id, src_location, dst_location, src_x, src_y, dst_x, dst_y, type, description FROM map_links
                        WHERE ((src_location = ? AND dst_location = ?)
                            OR (src_location = ? AND dst_location = ?))
                          AND type = ?
                        ORDER BY type"""
            params = [location_a, location_b, location_b, location_a, link_type.value]
        else:
            query = """SELECT id, src_location, dst_location, src_x, src_y, dst_x, dst_y, type, description FROM map_links
                        WHERE (src_location = ? AND dst_location = ?)
                           OR (src_location = ? AND dst_location = ?)
                        ORDER BY type"""
            params = [location_a, location_b, location_b, location_a]
        return [cls._from_row(r) for r in conn.execute(query, params).fetchall()]

    @classmethod
    def reachable_from(cls, conn: sqlite3.Connection, location: str) -> dict[str, list[MapLink]]:
        links = cls.departing(conn, location)
        result = {}
        for link in links:
            result.setdefault(link.dst_location, []).append(link)
        return result

    @classmethod
    def _from_row(cls, row: tuple):
        return cls(
            id=row[0],
            src_location=row[1],
            dst_location=row[2],
            src_x=row[3],
            src_y=row[4],
            dst_x=row[5],
            dst_y=row[6],
            link_type=MapLinkType(row[7]),
            description=row[8],
        )


# Zero-cost link types (instant transitions)
_ZERO_COST_TYPES = {
    MapLinkType.ENTRANCE,
    MapLinkType.EXIT,
    MapLinkType.FAIRY_RING,
    MapLinkType.CHARTER_SHIP,
    MapLinkType.SPIRIT_TREE,
    MapLinkType.GNOME_GLIDER,
    MapLinkType.CANOE,
    MapLinkType.TELEPORT,
    MapLinkType.MINECART,
    MapLinkType.SHIP,
    MapLinkType.QUETZAL,
    MapLinkType.NPC_TRANSPORT,
}


def _build_adjacency(conn: sqlite3.Connection, allowed_types: set[MapLinkType] | None = None) -> dict[str, list[MapLink]]:
    """Build adjacency dict from all non-ANYWHERE map links."""
    adj: dict[str, list[MapLink]] = defaultdict(list)
    rows = conn.execute(
        "SELECT id, src_location, dst_location, src_x, src_y, dst_x, dst_y, type, description "
        "FROM map_links WHERE src_location != ?",
        (MAP_LINK_ANYWHERE,),
    ).fetchall()
    for row in rows:
        link = MapLink._from_row(row)
        if allowed_types is not None and link.link_type not in allowed_types:
            continue
        adj[link.src_location].append(link)
    return adj


def _edge_cost(link: MapLink) -> float:
    """Compute traversal cost for a map link."""
    if link.link_type in _ZERO_COST_TYPES:
        return 0
    # Walkable: Chebyshev distance between endpoints
    dx = abs(link.src_x - link.dst_x)
    dy = abs(link.src_y - link.dst_y)
    return DistanceMetric.CHEBYSHEV.compute(dx, dy)


def _heuristic(
    loc_coords: dict[str, tuple[int, int]], current: str, goal: str,
    admissible: bool = False,
) -> float:
    """A* heuristic. When zero-cost links are present (admissible=False),
    returns 0 (Dijkstra's). When walking only (admissible=True), uses
    Chebyshev distance."""
    if not admissible:
        return 0
    c = loc_coords.get(current)
    g = loc_coords.get(goal)
    if c is None or g is None:
        return 0
    if c[1] > 5000 or g[1] > 5000:
        return 0
    dx = abs(c[0] - g[0])
    dy = abs(c[1] - g[1])
    return DistanceMetric.CHEBYSHEV.compute(dx, dy)


def _has_zero_cost_links(adj: dict[str, list[MapLink]]) -> bool:
    """Check if the adjacency graph contains any zero-cost link types."""
    for links in adj.values():
        for link in links:
            if link.link_type in _ZERO_COST_TYPES:
                return True
    return False


def _astar(
    adj: dict[str, list[MapLink]],
    loc_coords: dict[str, tuple[int, int]],
    start: str,
    goal: str,
) -> list[MapLink] | None:
    """Run A* from start to goal. Falls back to Dijkstra's when zero-cost
    links are present (Chebyshev heuristic is inadmissible with instant travel)."""
    if start == goal:
        return []

    admissible = not _has_zero_cost_links(adj)

    # Priority queue: (f_score, counter, node, path)
    counter = 0
    open_set: list[tuple[float, int, str, list[MapLink]]] = []
    heapq.heappush(open_set, (0, counter, start, []))
    g_scores: dict[str, float] = {start: 0}

    while open_set:
        f, _, current, path = heapq.heappop(open_set)

        if current == goal:
            return path

        current_g = g_scores.get(current, float("inf"))

        for link in adj.get(current, []):
            cost = _edge_cost(link)
            new_g = current_g + cost

            if new_g < g_scores.get(link.dst_location, float("inf")):
                g_scores[link.dst_location] = new_g
                h = _heuristic(loc_coords, link.dst_location, goal, admissible)
                counter += 1
                heapq.heappush(open_set, (new_g + h, counter, link.dst_location, path + [link]))

    return None


def find_path(
    conn: sqlite3.Connection,
    src: str,
    dst: str,
    allowed_types: set[MapLinkType] | None = None,
) -> list[MapLink] | None:
    """Find the shortest path between two locations.

    Considers all ANYWHERE teleports as potential starting points and
    picks the overall shortest path. Returns a list of MapLinks to
    traverse in order, or None if no path exists.

    allowed_types: if set, only use these link types. Teleports from
    ANYWHERE are only considered if MapLinkType.TELEPORT is allowed.
    """
    adj = _build_adjacency(conn, allowed_types)

    # Build location coordinate lookup
    loc_coords: dict[str, tuple[int, int]] = {}
    for row in conn.execute("SELECT name, x, y FROM locations WHERE x IS NOT NULL").fetchall():
        loc_coords[row[0]] = (row[1], row[2])

    # Candidate starts: always include actual source
    candidates: list[tuple[list[MapLink], str]] = [([], src)]

    # Collect ANYWHERE teleport links if teleports are allowed
    if allowed_types is None or MapLinkType.TELEPORT in allowed_types:
        anywhere_links = conn.execute(
            "SELECT id, src_location, dst_location, src_x, src_y, dst_x, dst_y, type, description "
            "FROM map_links WHERE src_location = ?",
            (MAP_LINK_ANYWHERE,),
        ).fetchall()
        for row in anywhere_links:
            link = MapLink._from_row(row)
            candidates.append(([link], link.dst_location))

    best_path: list[MapLink] | None = None
    best_cost = float("inf")

    for prefix, start in candidates:
        prefix_cost = sum(_edge_cost(l) for l in prefix)
        if prefix_cost >= best_cost:
            continue

        result = _astar(adj, loc_coords, start, dst)
        if result is not None:
            total_cost = prefix_cost + sum(_edge_cost(l) for l in result)
            if total_cost < best_cost:
                best_cost = total_cost
                best_path = prefix + result

    return best_path


def _stitch_canvas(conn: sqlite3.Connection, x_min: int, x_max: int, y_min: int, y_max: int):
    """Stitch color map tiles for a game coordinate region. Returns (canvas, extent)."""
    return MapSquare.stitch(conn, x_min, x_max, y_min, y_max)


def render_path(
    conn: sqlite3.Connection,
    path: list[MapLink],
    output_path: str,
    padding: int = 200,
    dpi: int = 200,
) -> None:
    """Render a path on the map with colored arrows for each edge type.

    Solid arrows for walking, dashed for teleports/transport.
    Surface and underground are rendered as stacked subplots.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    if not path:
        return

    UNDERGROUND_THRESHOLD = 5000

    edge_styles = {
        MapLinkType.WALKABLE: {"color": "lime", "linestyle": "-", "label": "Walk"},
        MapLinkType.ENTRANCE: {"color": "cyan", "linestyle": "-", "label": "Entrance"},
        MapLinkType.EXIT: {"color": "cyan", "linestyle": "-", "label": "Exit"},
        MapLinkType.FAIRY_RING: {"color": "magenta", "linestyle": "--", "label": "Fairy ring"},
        MapLinkType.CHARTER_SHIP: {"color": "orange", "linestyle": "--", "label": "Charter ship"},
        MapLinkType.QUETZAL: {"color": "yellow", "linestyle": "--", "label": "Quetzal"},
        MapLinkType.TELEPORT: {"color": "white", "linestyle": ":", "label": "Teleport"},
    }
    default_style = {"color": "white", "linestyle": "--", "label": "Other"}

    # Chain links for visual continuity: each link starts where the previous ended.
    # Insert implicit walk segments when there's a gap between links.
    chained: list[MapLink] = []
    for i, link in enumerate(path):
        if i > 0:
            prev = chained[-1]
            # If there's a gap between consecutive links
            if prev.dst_x != link.src_x or prev.dst_y != link.src_y:
                if prev.dst_location == link.src_location:
                    # Same location, different coords — snap the previous link's
                    # destination to the next link's source (walk directly to it)
                    chained[-1] = MapLink(
                        id=prev.id,
                        src_location=prev.src_location,
                        dst_location=prev.dst_location,
                        src_x=prev.src_x,
                        src_y=prev.src_y,
                        dst_x=link.src_x,
                        dst_y=link.src_y,
                        link_type=prev.link_type,
                        description=prev.description,
                    )
                else:
                    # Different locations — insert an implicit walk to bridge
                    chained.append(MapLink(
                        id=-1,
                        src_location=prev.dst_location,
                        dst_location=link.src_location,
                        src_x=prev.dst_x,
                        src_y=prev.dst_y,
                        dst_x=link.src_x,
                        dst_y=link.src_y,
                        link_type=MapLinkType.WALKABLE,
                        description=f"Walk to {link.src_location}",
                    ))
        chained.append(link)
    path = chained

    # Cluster path into panels based on coordinate jumps
    # A jump > PANEL_BREAK_THRESHOLD tiles triggers a new panel
    PANEL_BREAK_THRESHOLD = 6 * GAME_TILES_PER_REGION  # 384 tiles

    # Collect ordered coordinates with their link index
    panels: list[list[tuple[int, int]]] = [[]]
    link_panel: dict[int, int] = {}  # link index -> panel index

    for li, link in enumerate(path):
        if link.src_location == MAP_LINK_ANYWHERE:
            link_panel[li] = 0
            panels[0].append((link.dst_x, link.dst_y))
            continue

        src = (link.src_x, link.src_y)
        dst = (link.dst_x, link.dst_y)

        # Check if this link's src is far from the current panel
        if panels[-1]:
            last = panels[-1][-1]
            dx = abs(src[0] - last[0])
            dy = abs(src[1] - last[1])
            if max(dx, dy) > PANEL_BREAK_THRESHOLD:
                panels.append([])

        panels[-1].append(src)

        # Check if dst jumps far from src (the link itself spans a long distance)
        jump = max(abs(dst[0] - src[0]), abs(dst[1] - src[1]))
        if jump > PANEL_BREAK_THRESHOLD:
            link_panel[li] = len(panels) - 1
            panels.append([])
            panels[-1].append(dst)
        else:
            panels[-1].append(dst)
            link_panel[li] = len(panels) - 1

    # Remove empty panels
    panels = [p for p in panels if p]

    n_panels = len(panels)
    fig, axes = plt.subplots(n_panels, 1, figsize=(16, max(4, 8 * n_panels)))
    if n_panels == 1:
        axes = [axes]

    panel_axes = []
    for pi, panel_coords in enumerate(panels):
        ax = axes[pi]
        px = [c[0] for c in panel_coords]
        py = [c[1] for c in panel_coords]
        p_xmin, p_xmax = min(px) - padding, max(px) + padding
        p_ymin, p_ymax = min(py) - padding, max(py) + padding

        canvas_img, extent = _stitch_canvas(conn, p_xmin, p_xmax, p_ymin, p_ymax)
        ax.imshow(canvas_img, extent=extent, aspect="equal")
        ax.set_xlim(p_xmin, p_xmax)
        ax.set_ylim(p_ymin, p_ymax)
        ax.axis("off")
        panel_axes.append(ax)

    def get_ax_for_link(link_idx: int):
        return panel_axes[link_panel.get(link_idx, 0)]

    # Draw edges
    seen_labels: set[str] = set()
    for li, link in enumerate(path):
        style = edge_styles.get(link.link_type, default_style)
        ax = get_ax_for_link(li)

        if link.src_location == MAP_LINK_ANYWHERE:
            ax.plot(link.dst_x, link.dst_y, "*", color=style["color"], markersize=15, zorder=15,
                    label=style["label"] if style["label"] not in seen_labels else None)
            seen_labels.add(style["label"])
            continue

        src_panel_idx = link_panel.get(li, 0)
        # Check if dst is in the same panel by seeing if the next link is on a different panel
        # or if this link itself spans a large jump
        jump = max(abs(link.src_x - link.dst_x), abs(link.src_y - link.dst_y))
        dst_in_same = jump <= PANEL_BREAK_THRESHOLD

        if dst_in_same:
            ax.annotate("",
                         xy=(link.dst_x, link.dst_y),
                         xytext=(link.src_x, link.src_y),
                         arrowprops=dict(arrowstyle="->", color=style["color"],
                                         linestyle=style["linestyle"], lw=2),
                         zorder=10)
        else:
            # Cross-panel: departure marker on src panel, arrival marker on dst panel
            ax.plot(link.src_x, link.src_y, "v", color=style["color"], markersize=12,
                    markeredgecolor="black", markeredgewidth=1, zorder=15)
            ax.text(link.src_x, link.src_y - 15, f"→ {link.dst_location}",
                    fontsize=8, color=style["color"], ha="center", va="top",
                    fontweight="bold",
                    bbox=dict(boxstyle="round,pad=0.3", facecolor="black", alpha=0.8))
            # Arrival marker on the destination panel
            dst_panel_idx = src_panel_idx + 1 if src_panel_idx + 1 < n_panels else src_panel_idx
            dst_ax = panel_axes[dst_panel_idx]
            dst_ax.plot(link.dst_x, link.dst_y, "^", color=style["color"], markersize=12,
                        markeredgecolor="black", markeredgewidth=1, zorder=15)
            dst_ax.text(link.dst_x, link.dst_y + 15, f"← {link.src_location}",
                        fontsize=8, color=style["color"], ha="center", va="bottom",
                        fontweight="bold",
                        bbox=dict(boxstyle="round,pad=0.3", facecolor="black", alpha=0.8))

        label = style["label"] if style["label"] not in seen_labels else None
        if label:
            panel_axes[0].plot([], [], color=style["color"], linestyle=style["linestyle"], lw=2, label=label)
            seen_labels.add(style["label"])

    # Mark locations
    locations_on_path = []
    for link in path:
        if link.src_location != MAP_LINK_ANYWHERE:
            locations_on_path.append((link.src_location, link.src_x, link.src_y))
        locations_on_path.append((link.dst_location, link.dst_x, link.dst_y))

    seen_locs: set[str] = set()
    unique_locs = []
    for name, x, y in locations_on_path:
        if name not in seen_locs:
            seen_locs.add(name)
            unique_locs.append((name, x, y))

    for name, x, y in unique_locs:
        # Find which panel this coord belongs to
        best_ax = panel_axes[0]
        for pi, panel_coords in enumerate(panels):
            px = [c[0] for c in panel_coords]
            py = [c[1] for c in panel_coords]
            if px and py and min(px) - padding <= x <= max(px) + padding and min(py) - padding <= y <= max(py) + padding:
                best_ax = panel_axes[pi]
                break
        best_ax.plot(x, y, "o", color="white", markersize=8, markeredgecolor="black",
                     markeredgewidth=1, zorder=20)
        best_ax.text(x, y + 12, name, fontsize=8, color="white", ha="center", va="bottom",
                     zorder=21, fontweight="bold",
                     bbox=dict(boxstyle="round,pad=0.2", facecolor="black", alpha=0.7))

    panel_axes[0].legend(loc="upper left", fontsize=10, framealpha=0.8)
    fig.suptitle(f"{unique_locs[0][0]} → {unique_locs[-1][0]}", fontsize=14)
    plt.tight_layout()
    plt.savefig(output_path, dpi=dpi, bbox_inches="tight")
    plt.close()
