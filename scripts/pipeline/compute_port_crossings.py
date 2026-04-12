"""Compute ridge-crossing edges between paired ports.

Ports emitted by `compute_ports.py` come in segment pairs — for each
contiguous run of samples sharing a `(blob_a, blob_b)` pair, one port row
lands on the A side and one on the B side, both carrying the same
`(ridge_location_a_id, ridge_location_b_id, sample_start, sample_end)`.

This pass finds those pairs via self-join and stores directed crossing edges
in the `port_crossings` table with Chebyshev distance between the two
representative tiles as the cost. The cost is small (usually a handful of
tiles) but keeping it as the real distance rather than 0 preserves Chebyshev
heuristic admissibility in the upcoming port-graph A*.
"""

import argparse
from pathlib import Path

from ragger.db import create_tables, get_connection


def ingest(db_path: Path) -> None:
    create_tables(db_path)
    conn = get_connection(db_path)

    conn.execute("DELETE FROM port_crossings")

    pairs = conn.execute(
        """
        SELECT pa.id, pa.rep_x, pa.rep_y, pb.id, pb.rep_x, pb.rep_y
        FROM ports pa
        JOIN ports pb ON
            pa.ridge_location_a_id = pb.ridge_location_a_id
            AND pa.ridge_location_b_id = pb.ridge_location_b_id
            AND pa.sample_start = pb.sample_start
            AND pa.sample_end = pb.sample_end
            AND pa.side_location_id != pb.side_location_id
        """
    ).fetchall()

    rows: list[tuple[int, int, int]] = []
    for a_id, ax, ay, b_id, bx, by in pairs:
        dist = max(abs(ax - bx), abs(ay - by))
        rows.append((a_id, b_id, dist))

    conn.executemany(
        "INSERT INTO port_crossings (src_port_id, dst_port_id, distance) VALUES (?, ?, ?)",
        rows,
    )
    print(f"Inserted {len(rows)} port-crossing edges")

    conn.commit()
    conn.close()
    print("Done")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Compute ridge-crossing edges between paired ports")
    parser.add_argument("--db", type=Path, default=Path("data/ragger.db"))
    args = parser.parse_args()
    ingest(args.db)
