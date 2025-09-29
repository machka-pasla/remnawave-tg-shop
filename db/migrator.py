import logging
from typing import Set

from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection

from .models import Base


def _add_missing_columns(connection: Connection) -> None:
    inspector = inspect(connection)
    metadata = Base.metadata

    existing_tables: Set[str] = set(inspector.get_table_names())

    for table in metadata.tables.values():
        table_name = table.name
        if table_name not in existing_tables:
            # Tables are created elsewhere via create_all; skip here.
            continue

        existing_columns = {col_info["name"] for col_info in inspector.get_columns(table_name)}

        for desired_column in table.columns:
            if desired_column.name in existing_columns:
                continue

            # Build ADD COLUMN DDL
            preparer = connection.dialect.identifier_preparer
            table_quoted = preparer.format_table(table)
            column_name_quoted = preparer.quote(desired_column.name)
            column_type_sql = desired_column.type.compile(dialect=connection.dialect)

            default_clause = ""
            server_default = getattr(desired_column, "server_default", None)
            if server_default is not None and getattr(server_default, "arg", None) is not None:
                try:
                    compiled_default = str(
                        server_default.arg.compile(dialect=connection.dialect)
                    )
                    default_clause = f" DEFAULT {compiled_default}"
                except Exception:  # best-effort
                    pass

            # For safety, add new columns as NULLable to avoid failures on existing rows
            # If strict NOT NULL is needed, it can be enforced manually later.
            ddl = f"ALTER TABLE {table_quoted} ADD COLUMN {column_name_quoted} {column_type_sql}{default_clause}"

            logging.info(
                f"Migrator: adding missing column {desired_column.name} to table {table_name}"
            )
            connection.execute(text(ddl))


def run_simple_migrations(connection: Connection) -> None:
    """
    Run lightweight, idempotent migrations:
    - Ensure missing columns are added to existing tables to match models in db/models.py
    Note: Table creation is handled separately via Base.metadata.create_all.
    """
    try:
        _add_missing_columns(connection)
        logging.info("Migrator: schema synchronized (columns added as needed).")
    except Exception as e:
        logging.error(f"Migrator: failed to run simple migrations: {e}", exc_info=True)
        raise
