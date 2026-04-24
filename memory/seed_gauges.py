"""Seed ky_gauges.db by fetching each KY gauge individually from NWPS."""

import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from gauges import _connect, init_db, upsert_gauge, refresh_reading
from ingestion.NWPS import fetch_gauge

DB_PATH = Path(__file__).resolve().parent.parent / "database" / "ky_gauges.db"
WORKERS = 10

KY_LIDS = [
    "ABPK2", "ALVK2", "AMOK2", "APXK2", "ASHK2", "BAHK2", "BARK2", "BBVK2",
    "BDCK2", "BLCK2", "BLSK2", "BLWK2", "BNWK2", "BOOK2", "BRCK2", "BRKK2",
    "BRRK2", "BSNK2", "BTDK2", "BTLK2", "BUCK2", "BVCK2", "BVLK2", "BVUK2",
    "BWGK2", "BXTK2", "CALK2", "CATK2", "CDZK2", "CFAK2", "CFLK2", "CFTK2",
    "CHLK2", "CLBK2", "CLVK2", "CMBK2", "CORK2", "CPNK2", "CREK2", "CRLK2",
    "CRMK2", "CRRK2", "CYCK2", "CYNK2", "DIXK2", "DLPK2", "DNVK2", "DOTK2",
    "DUNK2", "DWYK2", "EDGK2", "EHMK2", "ELJK2", "ELKK2", "ELPK2", "ERLK2",
    "FCVK2", "FDLK2", "FFTK2", "FLMK2", "FLRK2", "FMCK2", "FNCK2", "FODK2",
    "FRLK2", "FRMK2", "FSVK2", "FTLK2", "FTSK2", "GEOK2", "GNBK2", "GNCK2",
    "GNSK2", "GNUK2", "GPCK2", "GRAK2", "GRLK2", "GSTK2", "GYLK2", "GYNK2",
    "HAZK2", "HENK2", "HGRK2", "HGVK2", "HIBK2", "HKMK2", "HLBK2", "HLDK2",
    "HLHK2", "HLSK2", "HLWK2", "HPKK2", "HSBK2", "HTFK2", "HYDK2", "HYSK2",
    "JKNK2", "KYDK2", "KYTK2", "LBJK2", "LEOK2", "LPTK2", "LVMK2", "LYDK2",
    "LYLK2", "MCHK2", "MCKK2", "MCPK2", "MDLK2", "MDOK2", "MDWK2", "MDYK2",
    "MFVK2", "MKBK2", "MKLK2", "MLPK2", "MLUK2", "MLWK2", "MLXK2", "MMCK2",
    "MNFK2", "MSGK2", "MTCK2", "MTGK2", "MTOK2", "MUDK2", "MWTK2", "MYRK2",
    "MYVK2", "NHVK2", "NOLK2", "ODAK2", "OKLK2", "ONYK2", "OVHK2", "OWBK2",
    "PAHK2", "PANK2", "PCRK2", "PCVK2", "PHYK2", "PKMK2", "PKYK2", "PLPK2",
    "PNTK2", "PRDK2", "PRPK2", "PRSK2", "PSTK2", "PSWK2", "PTVK2", "PVLK2",
    "PVYK2", "RAVK2", "RCHK2", "RCPK2", "RRLK2", "RVPK2", "SAYK2", "SDVK2",
    "SHPK2", "SHVK2", "SLVK2", "SPTK2", "SRKK2", "STMK2", "STRK2", "SXTK2",
    "TLLK2", "TMCK2", "TVLK2", "TWPK2", "TYGK2", "TYRK2", "VLIK2", "VLVK2",
    "VTPK2", "VYWK2", "WDHK2", "WHMK2", "WHTK2", "WKLK2", "WLBK2", "WLCK2",
    "WLWK2", "WPCK2", "WPTK2", "WTNK2", "YATK2", "YNTK2", "YTUK2", "ZTNK2",
]

_local = threading.local()

def _get_con() -> object:
    """Return a per-thread SQLite connection, creating it if needed."""
    if not hasattr(_local, "con"):
        _local.con = _connect(DB_PATH)
    return _local.con


def _fetch_and_upsert(lid: str) -> tuple[str, str]:
    """Fetch one gauge and write it to the DB. Returns (lid, status)."""
    data = fetch_gauge(lid)
    if data is None:
        return lid, "skipped"
    con = _get_con()
    upsert_gauge(con, data)
    observed = (data.get("status") or {}).get("observed") or {}
    stage = observed.get("primary")
    if stage is not None and stage != -999:
        refresh_reading(
            con, lid, float(stage),
            observed.get("validTime"),
            observed.get("floodCategory"),
        )
    return lid, "ok"


def main():
    init_db(DB_PATH)
    print(f"database → {DB_PATH}")
    print(f"fetching {len(KY_LIDS)} gauges with {WORKERS} workers...\n")

    ok = skipped = failed = 0
    total = len(KY_LIDS)

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = {pool.submit(_fetch_and_upsert, lid): lid for lid in KY_LIDS}
        for i, future in enumerate(as_completed(futures), 1):
            lid = futures[future]
            try:
                _, status = future.result()
                if status == "skipped":
                    print(f"  [{i:3}/{total}] {lid} — 404 skipped")
                    skipped += 1
                else:
                    print(f"  [{i:3}/{total}] {lid} — ok")
                    ok += 1
            except Exception as e:
                print(f"  [{i:3}/{total}] {lid} — ERROR: {e}")
                failed += 1

    print(f"\ndone: {ok} upserted, {skipped} skipped, {failed} failed")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
