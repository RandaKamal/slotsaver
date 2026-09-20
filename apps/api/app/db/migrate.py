"""Additive column migrations for the demo SQLite DB.

There is no Alembic in this project, and `create_all` only creates missing
tables - it will not add a column to a table that already exists. Without this,
anyone with a relay.db from before a field was added gets a confusing
OperationalError instead of a working app.

Only ever ADDs nullable/defaulted columns. Never drops or rewrites data.
"""

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

# table -> column -> SQLite column definition
_ADDITIVE: dict[str, dict[str, str]] = {
    "preference_records": {
        "context": "TEXT",
        "status": "VARCHAR DEFAULT 'extracted' NOT NULL",
        "notify_if_opens": "BOOLEAN DEFAULT 0 NOT NULL",
        "requested_time": "VARCHAR",
        "refinement_diff": "JSON",
    },
}


def ensure_columns(engine: Engine) -> list[str]:
    """Adds any missing columns. Returns what it added, for logging."""
    added: list[str] = []
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())

    with engine.begin() as conn:
        for table, columns in _ADDITIVE.items():
            if table not in existing_tables:
                continue  # create_all will build it with every column already
            present = {c["name"] for c in inspector.get_columns(table)}
            for column, ddl in columns.items():
                if column not in present:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}"))
                    added.append(f"{table}.{column}")
    return added
