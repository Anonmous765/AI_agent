"""SQLite schema and CRUD layer for Kentucky flood gauges."""

import json
import sqlite3
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

from ingestion.NWPS import fetch_gauge

DB_PATH = Path(__file__).resolve().parent.parent / "database" / "ky_gauges.db"
STALE_READING_THRESHOLD = timedelta(minutes=15)
REFRESH_WORKERS = 10


# Private helpers


def _normalize_stage(val) -> float | None:
    """Return None for NWPS sentinel -9999 or Python None; otherwise float."""
    if val is None or val == -9999:
        return None
    return float(val)


def _connect(db_path: str | Path) -> sqlite3.Connection:
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


# DDL

_DDL = """
CREATE TABLE IF NOT EXISTS gauges (
    lid                  TEXT PRIMARY KEY,
    usgs_id              TEXT,
    reach_id             TEXT,
    name                 TEXT,
    county               TEXT,
    state                TEXT DEFAULT 'KY',
    time_zone            TEXT,
    rfc                  TEXT,
    wfo                  TEXT,
    latitude             REAL,
    longitude            REAL,
    stage_action         REAL,
    stage_minor          REAL,
    stage_moderate       REAL,
    stage_major          REAL,
    stage_units          TEXT    DEFAULT 'ft',
    has_categories       INTEGER DEFAULT 0,
    upstream_lid         TEXT,
    downstream_lid       TEXT,
    url_hydrograph       TEXT,
    url_hydrograph_full  TEXT,
    impacts              TEXT,
    last_observed_stage  REAL,
    last_observed_time   TEXT,
    last_flood_category  TEXT,
    raw                  TEXT
);

CREATE TABLE IF NOT EXISTS gauge_crests (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    lid           TEXT    NOT NULL,
    occurred_time TEXT,
    stage         REAL,
    flow          REAL,
    preliminary   TEXT,
    old_datum     INTEGER DEFAULT 0,
    crest_type    TEXT,
    FOREIGN KEY (lid) REFERENCES gauges(lid) ON DELETE CASCADE,
    UNIQUE (lid, occurred_time, crest_type)
);

CREATE VIEW IF NOT EXISTS gauge_status AS
SELECT
    *,
    CASE
        WHEN has_categories = 0
          OR last_observed_stage IS NULL
          OR stage_action IS NULL
        THEN NULL
        ELSE ROUND(last_observed_stage / stage_action, 3)
    END AS danger_ratio,
    CASE
        WHEN last_observed_stage IS NULL
            THEN 'unknown'
        WHEN has_categories = 0
            THEN 'no_threshold'
        WHEN stage_major IS NOT NULL
         AND last_observed_stage >= stage_major
            THEN 'major_flood'
        WHEN stage_moderate IS NOT NULL
         AND last_observed_stage >= stage_moderate
            THEN 'moderate_flood'
        WHEN stage_minor IS NOT NULL
         AND last_observed_stage >= stage_minor
            THEN 'minor_flood'
        WHEN stage_action IS NOT NULL
         AND last_observed_stage >= stage_action
            THEN 'action_stage'
        WHEN stage_action IS NOT NULL
         AND last_observed_stage >= stage_action * 0.75
            THEN 'approaching_action'
        ELSE 'normal'
    END AS computed_status
FROM gauges;

CREATE INDEX IF NOT EXISTS idx_gauges_wfo    ON gauges(wfo);
CREATE INDEX IF NOT EXISTS idx_gauges_county ON gauges(county);
CREATE INDEX IF NOT EXISTS idx_crests_lid    ON gauge_crests(lid);
CREATE INDEX IF NOT EXISTS idx_crests_stage  ON gauge_crests(lid, stage DESC);
"""


# Public API


def init_db(db_path: str | Path) -> None:
    """Create all tables, view, and indexes. Safe to call on an existing database."""
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = _connect(db_path)
    con.executescript(_DDL)
    con.close()


def upsert_gauge(con: sqlite3.Connection, g: dict) -> None:
    """Insert or update one gauge record, preserving live reading columns."""
    rfc = (g.get("rfc") or {}).get("abbreviation")
    state = (g.get("state") or {}).get("abbreviation") or "KY"

    flood = g.get("flood") or {}
    categories = flood.get("categories") or {}
    hydrograph = ((g.get("images") or {}).get("hydrograph") or {})
    wfo = (g.get("wfo") or {}).get("abbreviation")

    stage_action = _normalize_stage((categories.get("action") or {}).get("stage"))
    stage_minor = _normalize_stage((categories.get("minor") or {}).get("stage"))
    stage_moderate = _normalize_stage((categories.get("moderate") or {}).get("stage"))
    stage_major = _normalize_stage((categories.get("major") or {}).get("stage"))
    has_categories = 1 if any(
        s is not None for s in (stage_action, stage_minor, stage_moderate, stage_major)
    ) else 0

    impacts = json.dumps(flood.get("impacts") or [])

    with con:
        con.execute(
            """
            INSERT INTO gauges (
                lid, usgs_id, reach_id, name, county, state, time_zone, rfc, wfo,
                latitude, longitude,
                stage_action, stage_minor, stage_moderate, stage_major,
                stage_units, has_categories,
                upstream_lid, downstream_lid,
                url_hydrograph, url_hydrograph_full,
                impacts, raw
            ) VALUES (
                :lid, :usgs_id, :reach_id, :name, :county, :state, :time_zone, :rfc, :wfo,
                :latitude, :longitude,
                :stage_action, :stage_minor, :stage_moderate, :stage_major,
                :stage_units, :has_categories,
                :upstream_lid, :downstream_lid,
                :url_hydrograph, :url_hydrograph_full,
                :impacts, :raw
            )
            ON CONFLICT(lid) DO UPDATE SET
                usgs_id             = excluded.usgs_id,
                reach_id            = excluded.reach_id,
                name                = excluded.name,
                county              = excluded.county,
                state               = excluded.state,
                time_zone           = excluded.time_zone,
                rfc                 = excluded.rfc,
                wfo                 = excluded.wfo,
                latitude            = excluded.latitude,
                longitude           = excluded.longitude,
                stage_action        = excluded.stage_action,
                stage_minor         = excluded.stage_minor,
                stage_moderate      = excluded.stage_moderate,
                stage_major         = excluded.stage_major,
                stage_units         = excluded.stage_units,
                has_categories      = excluded.has_categories,
                upstream_lid        = excluded.upstream_lid,
                downstream_lid      = excluded.downstream_lid,
                url_hydrograph      = excluded.url_hydrograph,
                url_hydrograph_full = excluded.url_hydrograph_full,
                impacts             = excluded.impacts,
                raw                 = excluded.raw
            """,
            {
                "lid": g.get("lid"),
                "usgs_id": g.get("usgsId"),
                "reach_id": g.get("reachId"),
                "name": g.get("name"),
                "county": g.get("county"),
                "state": state,
                "time_zone": g.get("timeZone"),
                "rfc": rfc,
                "wfo": wfo,
                "latitude": g.get("latitude"),
                "longitude": g.get("longitude"),
                "stage_action": stage_action,
                "stage_minor": stage_minor,
                "stage_moderate": stage_moderate,
                "stage_major": stage_major,
                "stage_units": flood.get("stageUnits", "ft"),
                "has_categories": has_categories,
                "upstream_lid": g.get("upstreamLid"),
                "downstream_lid": g.get("downstreamLid"),
                "url_hydrograph": hydrograph.get("default"),
                "url_hydrograph_full": hydrograph.get("floodcat"),
                "impacts": impacts,
                "raw": json.dumps(g),
            },
        )
        _insert_crests_unsafe(con, g["lid"], flood)


def _insert_crests_unsafe(con: sqlite3.Connection, lid: str, flood: dict) -> None:
    """Insert crests. Must be called within an active transaction."""
    crests = flood.get("crests") or {}
    rows: list[dict] = []

    for crest_type in ("historic", "recent"):
        for crest in crests.get(crest_type) or []:
            rows.append(
                {
                    "lid": lid,
                    "occurred_time": crest.get("occurredTime"),
                    "stage": crest.get("stage"),
                    "flow": crest.get("flow"),
                    "preliminary": crest.get("preliminary"),
                    "old_datum": int(crest.get("olddatum", False)),
                    "crest_type": crest_type,
                }
            )

    if rows:
        con.executemany(
            """
            INSERT OR IGNORE INTO gauge_crests
                (lid, occurred_time, stage, flow, preliminary, old_datum, crest_type)
            VALUES
                (:lid, :occurred_time, :stage, :flow, :preliminary, :old_datum, :crest_type)
            """,
            rows,
        )


def upsert_crests(con: sqlite3.Connection, lid: str, flood: dict) -> None:
    """Bulk-insert historic and recent crests, ignoring duplicates."""
    with con:
        _insert_crests_unsafe(con, lid, flood)


def refresh_reading(
    con: sqlite3.Connection,
    lid: str,
    stage: float,
    valid_time: str,
    flood_category: str,
) -> None:
    """Update the three live-reading columns on a gauge row."""
    with con:
        con.execute(
            """
            UPDATE gauges
            SET last_observed_stage    = :stage,
                last_observed_time     = :valid_time,
                last_flood_category    = :flood_category
            WHERE lid = :lid
            """,
            {
                "stage": stage,
                "valid_time": valid_time,
                "flood_category": flood_category,
                "lid": lid,
            },
        )


def _is_stale(
    last_observed_time: str | None,
    stale_threshold: timedelta = STALE_READING_THRESHOLD,
) -> bool:
    """Return True if the timestamp is missing or older than the threshold."""
    if not last_observed_time:
        return True

    try:
        last = datetime.fromisoformat(last_observed_time.replace("Z", "+00:00"))
        return datetime.now(timezone.utc) - last > stale_threshold
    except Exception:
        return True


def _refresh_lids(con: sqlite3.Connection, lids: list[str]) -> int:
    """Fetch live readings for stale gauges in parallel. Returns count refreshed."""
    success_count = 0
    lock = threading.Lock()

    def _fetch_one(lid: str) -> None:
        nonlocal success_count

        try:
            data = fetch_gauge(lid)
            if data is None:
                return

            observed = (data.get("status") or {}).get("observed") or {}
            stage = observed.get("primary")
            if stage is not None and stage != -999:
                refresh_reading(
                    con,
                    lid,
                    float(stage),
                    observed.get("validTime"),
                    observed.get("floodCategory"),
                )
                with lock:
                    success_count += 1
        except Exception as exc:
            print(f"  warning: failed to refresh {lid}: {exc}")

    with ThreadPoolExecutor(max_workers=REFRESH_WORKERS) as pool:
        pool.map(_fetch_one, lids)

    print(f"  refreshed {success_count}/{len(lids)} gauge(s) successfully")
    return success_count


def _refresh_if_stale(con: sqlite3.Connection) -> int:
    """Refresh all gauge readings when the cache is stale."""
    probe = con.execute(
        "SELECT last_observed_time FROM gauges WHERE last_observed_time IS NOT NULL LIMIT 1"
    ).fetchone()
    data_is_stale = _is_stale(probe["last_observed_time"] if probe else None)

    if not data_is_stale:
        return 0

    all_lids = [
        row["lid"] for row in con.execute("SELECT lid FROM gauges").fetchall()
    ]
    print(f"  data is stale, refreshing all {len(all_lids)} gauge(s)...")
    return _refresh_lids(con, all_lids)


def get_gauge(con: sqlite3.Connection, lid: str) -> dict | None:
    """Return a single row from gauge_status as a plain dict, or None."""
    row = con.execute(
        "SELECT * FROM gauge_status WHERE lid = ?",
        (lid,),
    ).fetchone()
    return dict(row) if row is not None else None


def query_gauges(
    county: str | None = None,
    status_filter: str | None = None,
    limit: int = 20,
) -> dict:
    """Query Kentucky flood gauges by county and/or current flood status.

    Use this tool to answer questions about current river and creek water
    levels, flood stages, and gauge conditions across Kentucky. Call it when
    the user asks about:
    - River or water levels in a specific county or statewide
    - Which gauges are currently at or above flood stage
    - How close a gauge is to flood stage (danger_ratio)
    - Gauge status categories: normal, approaching_action, action_stage,
      minor_flood, moderate_flood, or major_flood

    Always run this at least once before answering any questions about
    water levels. Data is automatically refreshed if older than 15 minutes.

    Args:
        county: Filter by county name (e.g. ``"Pike"``, ``"Jefferson"``).
                Case-insensitive partial match. ``None`` returns all counties.
        status_filter: Filter by flood status. One of: ``"normal"``,
                       ``"approaching_action"``, ``"action_stage"``,
                       ``"minor_flood"``, ``"moderate_flood"``,
                       ``"major_flood"``, ``"no_threshold"``, ``"unknown"``.
                       ``None`` returns all statuses.
        limit: Maximum number of gauges to return (default 20).

    Returns:
        A dict with:
        - ``"count"``: number of gauges returned.
        - ``"refreshed"``: number of gauges whose readings were updated.
        - ``"gauges"``: list of gauge dicts, each with ``lid``, ``name``,
          ``county``, ``last_observed_stage``, ``stage_units``,
          ``computed_status``, ``danger_ratio``, ``last_observed_time``,
          and ``url_hydrograph``.
    """
    print("[TOOL CALLED] query_gauges()")
    con = _connect(DB_PATH)
    refreshed = _refresh_if_stale(con)

    def _run(extra_clause: str | None) -> list[sqlite3.Row]:
        clauses: list[str] = []
        params: list[object] = []

        if extra_clause:
            clauses.append(extra_clause)
        if county:
            clauses.append("LOWER(county) LIKE LOWER(?)")
            params.append(f"%{county}%")
        if status_filter:
            clauses.append("computed_status = ?")
            params.append(status_filter)

        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        params.append(limit)

        return con.execute(
            f"""
            SELECT
                lid,
                name,
                county,
                last_observed_stage,
                stage_units,
                computed_status,
                danger_ratio,
                last_observed_time,
                url_hydrograph
            FROM gauge_status
            {where}
            ORDER BY danger_ratio DESC NULLS LAST
            LIMIT ?
            """,
            params,
        ).fetchall()

    rows = _run("last_observed_stage IS NOT NULL")
    if not rows:
        rows = _run(None)

    con.close()
    return {
        "count": len(rows),
        "refreshed": refreshed,
        "gauges": [dict(r) for r in rows],
    }


if __name__ == "__main__":
    db_connection = _connect(DB_PATH)
    init_db(DB_PATH)
    print(f"database initialised -> {DB_PATH}")

    BASE = "https://api.water.noaa.gov"
    HEADERS = {"User-Agent": "ky-disaster-graphrag/1.0 your@email.com"}

    # Pull entire gauge list. This is a large payload, so give it 120s.
    r = requests.get(
        f"{BASE}/nwps/v1/gauges",
        params={"state": "KY"},
        headers=HEADERS,
        timeout=120,
    )
    print(r.status_code, len(r.content), "bytes")

    try:
        r.raise_for_status()
    except requests.HTTPError:
        print("Request failed.")
        print("Content-Type:", r.headers.get("Content-Type"))
        print("Body preview:", r.text[:500] or "<empty>")
        sys.exit(1)

    if not r.content.strip():
        print("API returned an empty response body.")
        sys.exit(1)

    content_type = r.headers.get("Content-Type", "")
    if "json" not in content_type.lower():
        print("API did not return JSON.")
        print("Content-Type:", content_type or "<missing>")
        print("Body preview:", r.text[:500])
        sys.exit(1)

    try:
        data = r.json()
    except requests.exceptions.JSONDecodeError:
        print("Response body was not valid JSON.")
        print("Content-Type:", content_type or "<missing>")
        print("Body preview:", r.text[:500] or "<empty>")
        sys.exit(1)

    all_gauges = data.get("gauges", [])
    print(f"Total KY gauges: {len(all_gauges)}")

    for g in all_gauges:
        upsert_gauge(db_connection, g)
