"""Centralized filesystem paths, resolved relative to this file rather than the CWD."""

from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = PACKAGE_ROOT.parent.parent

DATA_DIR = PROJECT_ROOT / "data"
DATABASE_DIR = DATA_DIR / "database"
CHROMA_DIR = DATA_DIR / "chroma_db"
OSM_FILE = DATA_DIR / "kentucky-260404.osm.pbf"

CHAT_STORE_DB = DATABASE_DIR / "chat_store.sqlite3"
GAUGES_DB = DATABASE_DIR / "ky_gauges.db"

ENV_FILE = PROJECT_ROOT / ".env"
