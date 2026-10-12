"""Copy a legacy SQLite store into an empty MySQL database; source stays read-only."""

import argparse
import sqlite3
import sys
from contextlib import closing
from pathlib import Path
from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.config import settings
from app.db import initialize, engine_for, schema


def migrate(source):
    engine = engine_for(settings.database_url)
    if engine.dialect.name != "mysql":
        raise ValueError("Target DATABASE_URL must be MySQL")
    source = Path(source).resolve(strict=True)
    initialize(seed_demo=False)
    metadata = schema("mysql")
    tables = [t for t in metadata.sorted_tables if t.name != "schema_migrations"]
    counts = {}
    with (
        closing(sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)) as legacy,
        engine.begin() as target,
    ):
        legacy.row_factory = sqlite3.Row
        for table in tables:
            if target.execute(text(f"SELECT count(*) FROM {table.name}")).scalar():
                raise ValueError(
                    "Target must be empty; migration never overwrites existing data"
                )
        available = {
            r[0]
            for r in legacy.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        for table in tables:
            if table.name not in available:
                continue
            rows = [dict(r) for r in legacy.execute(f"SELECT * FROM {table.name}")]
            columns = {c.name for c in table.columns if c.computed is None}
            for row in rows:
                data = {k: v for k, v in row.items() if k in columns}
                names = list(data)
                statement = f"INSERT INTO {table.name} ({','.join(names)}) VALUES ({','.join(':' + n for n in names)})"
                target.execute(text(statement), data)
            count = target.execute(text(f"SELECT count(*) FROM {table.name}")).scalar()
            if count != len(rows):
                raise ValueError(f"Row count mismatch: {table.name}")
            counts[table.name] = count
    return counts


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source", required=True, help="Legacy SQLite file; opened read-only"
    )
    args = parser.parse_args()
    import json

    print(json.dumps(migrate(args.source), ensure_ascii=False, indent=2))
