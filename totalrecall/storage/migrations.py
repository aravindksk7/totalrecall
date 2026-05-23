import asyncio
from pathlib import Path

from totalrecall.config.settings import Settings
from totalrecall.storage.database import connect


async def apply_migrations(settings: Settings | None = None) -> list[str]:
    resolved_settings = settings or Settings()
    migrations_path = Path(resolved_settings.migrations_path)
    connection = await connect(resolved_settings)
    applied: list[str] = []

    try:
        await connection.execute(
            """
            create table if not exists schema_migrations (
                version text primary key,
                applied_at timestamptz not null default now()
            )
            """
        )

        existing_rows = await connection.fetch("select version from schema_migrations")
        existing = {row["version"] for row in existing_rows}

        for migration_file in sorted(migrations_path.glob("*.sql")):
            version = migration_file.name
            if version in existing:
                continue
            sql = migration_file.read_text(encoding="utf-8")
            async with connection.transaction():
                await connection.execute(sql)
                await connection.execute(
                    "insert into schema_migrations(version) values($1)",
                    version,
                )
            applied.append(version)
    finally:
        await connection.close()

    return applied


def main() -> None:
    applied = asyncio.run(apply_migrations())
    if applied:
        print(f"Applied migrations: {', '.join(applied)}")
    else:
        print("No migrations to apply.")


if __name__ == "__main__":
    main()
