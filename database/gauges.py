"""SQLite schema and CRUD layer for Kentucky flood gauges."""

from __future__ import annotations

import json
import sqlite3
import sys
import requests
from pathlib import Path


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# DDL
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def init_db(db_path: str | Path) -> None:
    """Create all tables, view, and indexes. Safe to call on an existing database."""
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = _connect(db_path)
    con.executescript(_DDL)
    con.close()


def upsert_gauge(con: sqlite3.Connection, g: dict) -> None:
    """Insert or update one gauge record, preserving live reading columns."""
    rfc   = (g.get("rfc")   or {}).get("abbreviation")
    state = (g.get("state") or {}).get("abbreviation") or "KY"

    flood      = g.get("flood") or {}
    categories = flood.get("categories") or {}
    hydrograph = ((g.get("images") or {}).get("hydrograph") or {})
    wfo        = (g.get("wfo") or {}).get("abbreviation")

    stage_action   = _normalize_stage((categories.get("action")   or {}).get("stage"))
    stage_minor    = _normalize_stage((categories.get("minor")    or {}).get("stage"))
    stage_moderate = _normalize_stage((categories.get("moderate") or {}).get("stage"))
    stage_major    = _normalize_stage((categories.get("major")    or {}).get("stage"))
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
                "lid":                g.get("lid"),
                "usgs_id":            g.get("usgsId"),
                "reach_id":           g.get("reachId"),
                "name":               g.get("name"),
                "county":             g.get("county"),
                "state":              state,
                "time_zone":          g.get("timeZone"),
                "rfc":                rfc,
                "wfo":                wfo,
                "latitude":           g.get("latitude"),
                "longitude":          g.get("longitude"),
                "stage_action":       stage_action,
                "stage_minor":        stage_minor,
                "stage_moderate":     stage_moderate,
                "stage_major":        stage_major,
                "stage_units":        flood.get("stageUnits", "ft"),
                "has_categories":     has_categories,
                "upstream_lid":       g.get("upstreamLid"),
                "downstream_lid":     g.get("downstreamLid"),
                "url_hydrograph":     hydrograph.get("default"),
                "url_hydrograph_full": hydrograph.get("floodcat"),
                "impacts":            impacts,
                "raw":                json.dumps(g),
            },
        )
        _insert_crests_unsafe(con, g["lid"], flood)


def _insert_crests_unsafe(con: sqlite3.Connection, lid: str, flood: dict) -> None:
    """Insert crests — must be called within an active transaction."""
    crests = flood.get("crests") or {}
    rows: list[dict] = []

    for crest_type in ("historic", "recent"):
        for crest in crests.get(crest_type) or []:
            rows.append({
                "lid":           lid,
                "occurred_time": crest.get("occurredTime"),
                "stage":         crest.get("stage"),
                "flow":          crest.get("flow"),
                "preliminary":   crest.get("preliminary"),
                "old_datum":     int(crest.get("olddatum", False)),
                "crest_type":    crest_type,
            })

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
                "stage":          stage,
                "valid_time":     valid_time,
                "flood_category": flood_category,
                "lid":            lid,
            },
        )


def get_gauge(con: sqlite3.Connection, lid: str) -> dict | None:
    """Return a single row from gauge_status as a plain dict, or None."""
    row = con.execute(
        "SELECT * FROM gauge_status WHERE lid = ?",
        (lid,),
    ).fetchone()
    return dict(row) if row is not None else None


# ---------------------------------------------------------------------------

if __name__ == "__main__":
    _default_path = Path(__file__).resolve().parent / "ky_gauges.db"
    db_connection = _connect(_default_path)
    init_db(_default_path)
    print(f"database initialised → {_default_path}")

    BASE = "https://api.water.noaa.gov"
    HEADERS = {"User-Agent": "ky-disaster-graphrag/1.0 your@email.com"}

    # Pull entire gauge list — this is a large payload, give it 120s
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


