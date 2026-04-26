"""SQLite schema and CRUD layer for Kentucky flood gauges."""

import json
import sqlite3
import sys
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

from ingestion.NWPS import fetch_gauge

DB_PATH = Path(__file__).resolve().parent.parent / "database" / "ky_gauges.db"
STALE_READING_THRESHOLD = timedelta(hours=2)
REFRESH_WORKERS = 10
REFRESH_STATE_KEY = "last_successful_refresh_at"


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

CREATE TABLE IF NOT EXISTS gauge_refresh_state (
    key       TEXT PRIMARY KEY,
    value     TEXT NOT NULL
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


def _ensure_refresh_state_table(con: sqlite3.Connection) -> None:
    """Create refresh metadata table for existing DBs that predate it."""
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS gauge_refresh_state (
            key       TEXT PRIMARY KEY,
            value     TEXT NOT NULL
        )
        """
    )


def _get_last_successful_refresh(con: sqlite3.Connection) -> str | None:
    _ensure_refresh_state_table(con)
    row = con.execute(
        "SELECT value FROM gauge_refresh_state WHERE key = ?",
        (REFRESH_STATE_KEY,),
    ).fetchone()
    return row["value"] if row else None


def _record_successful_refresh(con: sqlite3.Connection) -> None:
    _ensure_refresh_state_table(con)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with con:
        con.execute(
            """
            INSERT INTO gauge_refresh_state (key, value)
            VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (REFRESH_STATE_KEY, now),
        )


def _fetch_live_reading(
    lid: str,
) -> tuple[str, float | None, str | None, str | None, str | None]:
    """Fetch one live gauge reading without touching SQLite."""
    try:
        data = fetch_gauge(lid)
        if data is None:
            return (lid, None, None, None, "not_found")

        observed = (data.get("status") or {}).get("observed") or {}
        stage = observed.get("primary")
        flood_category = observed.get("floodCategory")
        if stage is None:
            return (lid, None, None, None, flood_category or "missing_stage")

        try:
            numeric_stage = float(stage)
        except (TypeError, ValueError):
            return (lid, None, None, None, flood_category or "invalid_stage")

        if numeric_stage in (-999, -9999):
            return (lid, None, None, None, flood_category or "not_current")

        return (
            lid,
            numeric_stage,
            observed.get("validTime"),
            flood_category,
            None,
        )
    except Exception as exc:
        print(f"  warning: failed to fetch {lid}: {exc}")
        return (lid, None, None, None, "fetch_failed")


def _refresh_lids(con: sqlite3.Connection, lids: list[str]) -> int:
    """Fetch live readings in parallel, then write updates on this thread."""
    success_count = 0
    skip_reasons: Counter[str] = Counter()
    skip_examples: defaultdict[str, list[str]] = defaultdict(list)

    with ThreadPoolExecutor(max_workers=REFRESH_WORKERS) as pool:
        readings = pool.map(_fetch_live_reading, lids)

    for reading in readings:
        lid, stage, valid_time, flood_category, skip_reason = reading
        if stage is None:
            reason = skip_reason or "unusable_reading"
            skip_reasons[reason] += 1
            if len(skip_examples[reason]) < 5:
                skip_examples[reason].append(lid)
            continue

        try:
            refresh_reading(con, lid, stage, valid_time, flood_category)
            success_count += 1
        except Exception as exc:
            print(f"  warning: failed to write refresh for {lid}: {exc}")

    print(f"  refreshed {success_count}/{len(lids)} gauge(s) successfully")
    if skip_reasons:
        reason_counts = ", ".join(
            f"{count} {reason}" for reason, count in skip_reasons.most_common()
        )
        examples = "; ".join(
            f"{reason}: {', '.join(example_lids)}"
            for reason, example_lids in sorted(skip_examples.items())
        )
        print(f"  skipped {sum(skip_reasons.values())} gauge(s): {reason_counts}")
        print(f"  skipped examples: {examples}")
    return success_count


def _refresh_if_stale(con: sqlite3.Connection) -> int:
    """Refresh all gauge readings when the local NOAA fetch cache is stale."""
    last_refresh = _get_last_successful_refresh(con)
    data_is_stale = _is_stale(last_refresh)

    if not data_is_stale:
        return 0

    all_lids = [
        row["lid"] for row in con.execute("SELECT lid FROM gauges").fetchall()
    ]
    print(f"  data is stale, refreshing all {len(all_lids)} gauge(s)...")
    refreshed = _refresh_lids(con, all_lids)
    if refreshed > 0:
        _record_successful_refresh(con)
    return refreshed


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
    - How close a waterway is to flooding
    - General flood risk or water level conditions

    Always run this at least once before answering any questions about
    water levels. Data is automatically refreshed if the local NOAA fetch cache
    is older than 2 hours.

    **Output instructions — these are mandatory:**
    - NEVER show raw numeric values for ``danger_ratio`` to the user.
      Use it internally to assess risk, then describe the situation in plain
      English (e.g. "approaching flood stage", "well within normal range").
    - NEVER use technical field names like ``computed_status``, ``lid``,
      ``danger_ratio``, or ``stage_units`` in your response.
    - Translate ``computed_status`` values into plain language:
        - ``normal``              → "within normal range"
        - ``approaching_action``  → "approaching flood stage — worth monitoring"
        - ``action_stage``        → "at action stage — elevated concern"
        - ``minor_flood``         → "in minor flood stage"
        - ``moderate_flood``      → "in moderate flood stage"
        - ``major_flood``         → "in major flood stage — serious threat"
        - ``no_threshold``        → report the raw ft reading only, no classification
        - ``unknown``             → "no current reading available"
    - Always include the actual water level in feet so locals have a
      concrete reference (e.g. "currently at 13.3 ft").
    - For ``no_threshold`` gauges, say something like: "currently at X ft
      — no official flood threshold is defined for this location."
    - Lead with the most elevated gauges first when listing multiple results.
    - For reservoir gauges with very high ft readings (e.g. 700+ ft), clarify
      these are elevation readings above sea level, not depth, to avoid alarm.

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


def query_crests(
    lid: str | None = None,
    county: str | None = None,
    crest_type: str | None = None,
    limit: int = 20,
) -> dict:
    """Query historical flood crest records for Kentucky gauges.

    Use this tool to answer questions about historical flood patterns, records,
    and averages. Call it when the user asks about:
    - The highest ever recorded flood stage at a gauge or river
    - Historical flood averages or typical crest levels
    - How severe past flooding was compared to current levels
    - Flood frequency or recurrence at a location
    - Whether current levels are near or above historical records

    Always prefer ``query_gauges`` for *current* conditions. Use this tool
    to add historical context — e.g. "the river is at 18 ft; historically it
    has crested as high as 32 ft."

    **Output instructions — mandatory:**
    - NEVER show ``lid``, ``preliminary``, or ``old_datum`` to the user.
    - Describe crests in plain English: "crested at X ft on [date]."
    - When ``old_datum`` is 1, the measurement used an older vertical reference
      — note that older records may not be directly comparable to modern readings.
    - Use ``record_high_ft`` vs ``stage_action`` / ``stage_minor`` / etc. to
      contextualise severity: e.g. "the record crest of 32 ft far exceeded the
      major flood threshold of 26 ft."
    - Use ``avg_stage_ft`` to describe typical flood levels.
    - Lead with the most severe (highest stage) gauges when listing multiple.
    - For reservoir gauges with 700+ ft readings, clarify these are elevation
      above sea level, not water depth.

    Args:
        lid: Filter to a specific gauge by location ID (e.g. ``"PKYK2"``).
             Use ``query_gauges`` first to find the LID for a named location.
        county: Filter by county name (e.g. ``"Pike"``). Case-insensitive
                partial match. ``None`` returns all counties.
        crest_type: ``"historic"`` for all-time records, ``"recent"`` for
                    the most recent events, or ``None`` for both.
        limit: Maximum number of individual crest records to return (default 20).
               The summary stats are always computed over all matching crests,
               regardless of this limit.

    Returns:
        A dict with:
        - ``"count"``: number of crest records in ``crests``.
        - ``"crests"``: top-N crests sorted by stage descending, each with
          ``lid``, ``name``, ``county``, ``occurred_time``, ``stage``,
          ``flow``, ``crest_type``, ``stage_action``, ``stage_minor``,
          ``stage_moderate``, ``stage_major``.
        - ``"summary"``: per-gauge aggregate stats (all matching crests, no
          limit) with ``lid``, ``name``, ``county``, ``total_crests``,
          ``record_high_ft``, ``avg_stage_ft``, ``min_stage_ft``,
          ``stage_action``, ``stage_minor``, ``stage_moderate``, ``stage_major``.
    """
    print("[TOOL CALLED] query_crests()")
    con = _connect(DB_PATH)

    def _build_clauses() -> tuple[list[str], list[object]]:
        clauses: list[str] = []
        params: list[object] = []
        if lid:
            clauses.append("gc.lid = ?")
            params.append(lid)
        if county:
            clauses.append("LOWER(g.county) LIKE LOWER(?)")
            params.append(f"%{county}%")
        if crest_type:
            clauses.append("gc.crest_type = ?")
            params.append(crest_type)
        return clauses, params

    clauses, base_params = _build_clauses()
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""

    crest_rows = con.execute(
        f"""
        SELECT
            gc.lid,
            gc.occurred_time,
            gc.stage,
            gc.flow,
            gc.crest_type,
            gc.old_datum,
            g.name,
            g.county,
            g.stage_action,
            g.stage_minor,
            g.stage_moderate,
            g.stage_major
        FROM gauge_crests gc
        JOIN gauges g ON gc.lid = g.lid
        {where}
        ORDER BY gc.stage DESC NULLS LAST
        LIMIT ?
        """,
        [*base_params, limit],
    ).fetchall()

    summary_rows = con.execute(
        f"""
        SELECT
            gc.lid,
            g.name,
            g.county,
            COUNT(*)                    AS total_crests,
            MAX(gc.stage)               AS record_high_ft,
            ROUND(AVG(gc.stage), 2)     AS avg_stage_ft,
            MIN(gc.stage)               AS min_stage_ft,
            g.stage_action,
            g.stage_minor,
            g.stage_moderate,
            g.stage_major
        FROM gauge_crests gc
        JOIN gauges g ON gc.lid = g.lid
        {where}
        GROUP BY gc.lid
        ORDER BY record_high_ft DESC NULLS LAST
        """,
        base_params,
    ).fetchall()

    con.close()
    return {
        "count": len(crest_rows),
        "crests": [dict(r) for r in crest_rows],
        "summary": [dict(r) for r in summary_rows],
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
