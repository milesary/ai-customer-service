import os
import tempfile
import unittest
from pathlib import Path
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from app.config import settings
from app.db import initialize, engine_for
from scripts.migrate_sqlite import migrate


@unittest.skipUnless(
    os.environ.get("MYSQL_TEST_URL"),
    "Set MYSQL_TEST_URL to verify migration against MySQL",
)
class MigrationTests(unittest.TestCase):
    def test_copy_preserves_source_and_refuses_nonempty_target(self):
        original = (settings.database_url, settings.seed_demo)
        database = "shiwu_test_" + os.urandom(6).hex()
        server = create_engine(
            make_url(os.environ["MYSQL_TEST_URL"])._replace(database=None),
            hide_parameters=True,
        )
        try:
            with server.begin() as conn:
                conn.execute(text(f"CREATE DATABASE {database} CHARACTER SET utf8mb4"))
            with tempfile.TemporaryDirectory() as temp:
                source = Path(temp) / "legacy.db"
                settings.database_url = "sqlite:///" + source.as_posix()
                initialize(seed_demo=True)
                engine_for(settings.database_url).dispose()
                before = source.read_bytes()
                settings.database_url = (
                    make_url(os.environ["MYSQL_TEST_URL"])
                    .set(database=database)
                    .render_as_string(hide_password=False)
                )
                counts = migrate(source)
                self.assertEqual(counts["users"], 2)
                self.assertEqual(counts["orders"], 1)
                self.assertEqual(source.read_bytes(), before)
                with self.assertRaisesRegex(ValueError, "empty"):
                    migrate(source)
                self.assertEqual(source.read_bytes(), before)
        finally:
            engine_for(settings.database_url).dispose()
            settings.database_url, settings.seed_demo = original
            assert database.startswith("shiwu_test_") and database[11:].isalnum()
            with server.begin() as conn:
                conn.execute(text(f"DROP DATABASE {database}"))
            server.dispose()
