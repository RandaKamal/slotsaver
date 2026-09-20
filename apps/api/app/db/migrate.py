"""Additive column migrations for the demo DB.

There is no Alembic in this project, and `create_all` only creates missing
tables - it will not add a column to a table that already exists. Without this,
anyone with a relay.db from before a field was added gets a confusing
OperationalError instead of a working app.

Only ever ADDs nullable/defaulted columns. Never drops or rewrites data.

DDL is rendered per dialect because SQLite and PostgreSQL disagree on literals:
SQLite has no boolean type and spells false as 0, while PostgreSQL rejects a
bare string literal as the default for a JSON column without an explicit cast.
Getting this wrong is silent locally and only fails on the deployed Postgres.
"""

from dataclasses import dataclass

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

# Literals that differ between the two dialects we support.
_FALSE = {"sqlite": "0", "postgresql": "FALSE"}
_EMPTY_JSON = {"sqlite": "'{}'", "postgresql": "'{}'::json"}
_TIMESTAMPTZ = {"sqlite": "DATETIME", "postgresql": "TIMESTAMP WITH TIME ZONE"}
_TIMESTAMP = {"sqlite": "DATETIME", "postgresql": "TIMESTAMP"}


@dataclass(frozen=True)
class _Column:
    """One additive column, rendered into dialect-specific DDL on demand."""

    type_name: dict[str, str] | str
    default: dict[str, str] | str | None = None
    not_null: bool = False

    def ddl(self, dialect: str) -> str:
        if isinstance(self.type_name, dict):
            if dialect not in self.type_name:
                raise ValueError(
                    f"no {dialect} spelling for this column type; add one to "
                    "app/db/migrate.py before deploying on that database"
                )
            type_name = self.type_name[dialect]
        else:
            type_name = self.type_name
        parts = [type_name]
        if self.default is not None:
            if isinstance(self.default, dict):
                if dialect not in self.default:
                    raise ValueError(
                        f"no {dialect} spelling for this column default; add one to "
                        "app/db/migrate.py before deploying on that database"
                    )
                literal = self.default[dialect]
            else:
                literal = self.default  # same spelling everywhere
            parts.append(f"DEFAULT {literal}")
        if self.not_null:
            parts.append("NOT NULL")
        return " ".join(parts)


# table -> column -> definition
_ADDITIVE: dict[str, dict[str, _Column]] = {
    "preference_records": {
        "context": _Column("TEXT"),
        "status": _Column("VARCHAR", default="'extracted'", not_null=True),
        "notify_if_opens": _Column("BOOLEAN", default=_FALSE, not_null=True),
        "requested_time": _Column("VARCHAR"),
        "refinement_diff": _Column("JSON"),
        "phone_number": _Column("VARCHAR"),
    },
    "recovery_plans": {
        "candidate_statuses": _Column("JSON", default=_EMPTY_JSON, not_null=True),
        "current_offer_at": _Column(_TIMESTAMPTZ),
    },
    "appointments": {
        "cancelled_at": _Column(_TIMESTAMP),
        "last_cancelled_by": _Column("VARCHAR"),
    },
    "outreach_attempts": {
        "conversation_id": _Column("VARCHAR"),
    },
}


def ensure_columns(engine: Engine) -> list[str]:
    """Adds any missing columns. Returns what it added, for logging."""
    added: list[str] = []
    dialect = engine.dialect.name
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())

    with engine.begin() as conn:
        for table, columns in _ADDITIVE.items():
            if table not in existing_tables:
                continue  # create_all will build it with every column already
            present = {c["name"] for c in inspector.get_columns(table)}
            for column, spec in columns.items():
                if column not in present:
                    conn.execute(
                        text(f"ALTER TABLE {table} ADD COLUMN {column} {spec.ddl(dialect)}")
                    )
                    added.append(f"{table}.{column}")
    return added
