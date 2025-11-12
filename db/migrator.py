import logging
from dataclasses import dataclass
from typing import Callable, List, Set

from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection


@dataclass(frozen=True)
class Migration:
    id: str
    description: str
    upgrade: Callable[[Connection], None]


def _ensure_migrations_table(connection: Connection) -> None:
    connection.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                id VARCHAR(255) PRIMARY KEY,
                applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
    )


def _migration_0001_add_channel_subscription_fields(connection: Connection) -> None:
    inspector = inspect(connection)
    columns: Set[str] = {col["name"] for col in inspector.get_columns("users")}
    statements: List[str] = []

    if "channel_subscription_verified" not in columns:
        statements.append(
            "ALTER TABLE users ADD COLUMN channel_subscription_verified BOOLEAN"
        )
    if "channel_subscription_checked_at" not in columns:
        statements.append(
            "ALTER TABLE users ADD COLUMN channel_subscription_checked_at TIMESTAMPTZ"
        )
    if "channel_subscription_verified_for" not in columns:
        statements.append(
            "ALTER TABLE users ADD COLUMN channel_subscription_verified_for BIGINT"
        )

    for stmt in statements:
        connection.execute(text(stmt))


def _migration_0002_add_uid_columns(connection: Connection) -> None:
    inspector = inspect(connection)
    columns: Set[str] = {col["name"] for col in inspector.get_columns("users")}

    if "uid" not in columns:
        connection.execute(text("ALTER TABLE users ADD COLUMN uid VARCHAR(14)"))

    # Add partial unique index to keep UID unique when filled.
    indexes: Set[str] = {index["name"] for index in inspector.get_indexes("users")}
    if "uq_users_uid" not in indexes:
        connection.execute(
            text(
                "CREATE UNIQUE INDEX uq_users_uid ON users (uid) WHERE uid IS NOT NULL"
            )
        )

    tables = inspector.get_table_names()
    if "uid_rotation_journal" not in tables:
        connection.execute(
            text(
                """
                CREATE TABLE uid_rotation_journal (
                    uid VARCHAR(14) PRIMARY KEY,
                    version SMALLINT NOT NULL DEFAULT 1,
                    rotated_at TIMESTAMPTZ DEFAULT NOW()
                )
                """
            )
        )


MIGRATIONS: List[Migration] = [
    Migration(
        id="0001_add_channel_subscription_fields",
        description="Add columns to track required channel subscription verification",
        upgrade=_migration_0001_add_channel_subscription_fields,
    ),
    Migration(
        id="0002_add_uid_columns",
        description="Add uid storage and rotation journal scaffolding",
        upgrade=_migration_0002_add_uid_columns,
    ),
]


def run_database_migrations(connection: Connection) -> None:
    """
    Apply pending migrations sequentially. Already applied revisions are skipped.
    """
    _ensure_migrations_table(connection)

    applied_revisions: Set[str] = {
        row[0]
        for row in connection.execute(
            text("SELECT id FROM schema_migrations")
        )
    }

    for migration in MIGRATIONS:
        if migration.id in applied_revisions:
            continue

        logging.info(
            "Migrator: applying %s – %s", migration.id, migration.description
        )
        try:
            with connection.begin_nested():
                migration.upgrade(connection)
                connection.execute(
                    text(
                        "INSERT INTO schema_migrations (id) VALUES (:revision)"
                    ),
                    {"revision": migration.id},
                )
        except Exception as exc:
            logging.error(
                "Migrator: failed to apply %s (%s)",
                migration.id,
                migration.description,
                exc_info=True,
            )
            raise exc
        else:
            logging.info("Migrator: migration %s applied successfully", migration.id)
