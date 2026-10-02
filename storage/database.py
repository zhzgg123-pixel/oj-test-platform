"""Per-operation connections and explicit, short SQLite transactions."""
from contextlib import contextmanager
from pathlib import Path
import sqlite3


class Database:
    def __init__(self, path):
        self.path = Path(path).resolve()

    @contextmanager
    def connection(self, *, write=False):
        db = sqlite3.connect(self.path, timeout=5, isolation_level=None)
        db.row_factory = sqlite3.Row
        try:
            db.execute('PRAGMA foreign_keys=ON')
            db.execute('PRAGMA busy_timeout=5000')
            db.execute('BEGIN IMMEDIATE' if write else 'BEGIN')
            yield db
            db.execute('COMMIT')
        except BaseException:
            if db.in_transaction:
                db.execute('ROLLBACK')
            raise
        finally:
            db.close()

    def initialize(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # WAL cannot be enabled inside a transaction.
        db = sqlite3.connect(self.path, timeout=5, isolation_level=None)
        try:
            version = db.execute('PRAGMA user_version').fetchone()[0]
            if version not in (0, 1, 2):
                raise ValueError(f'unsupported database version: {version}')
            db.execute('PRAGMA journal_mode=WAL')
        finally:
            db.close()
        with self.connection(write=True) as db:
            version = db.execute('PRAGMA user_version').fetchone()[0]
            if version not in (0, 1, 2):
                raise ValueError(f'unsupported database version: {version}')
            migrations = ('001_initial.sql', '002_task_name.sql')
            for next_version in range(version + 1, len(migrations) + 1):
                sql = (Path(__file__).parent / 'migrations' / migrations[next_version - 1]).read_text(encoding='utf-8-sig')
                # Fixed migrations contain no procedural SQL; avoid executescript's implicit COMMIT.
                for statement in sql.split(';'):
                    if statement.strip():
                        db.execute(statement)
                db.execute(f'PRAGMA user_version={next_version}')
