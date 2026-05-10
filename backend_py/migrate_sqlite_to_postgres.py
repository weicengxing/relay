from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import uuid
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

try:
    import psycopg
    from psycopg.rows import dict_row
    from psycopg.types.json import Json, Jsonb
except ImportError as exc:
    raise SystemExit(
        "Missing dependency: psycopg. Run `pip install -r backend_py/requirements.txt` first."
    ) from exc

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend_py import app as appmod  # noqa: E402


DEFAULT_SKIP_TABLES = {"verification_codes"}
NUMERIC_TYPES = {"numeric", "decimal", "money"}
INTEGER_TYPES = {"int2", "int4", "int8", "smallint", "integer", "bigint", "serial", "bigserial"}
FLOAT_TYPES = {"float4", "float8", "real", "double precision"}
BOOL_TYPES = {"bool", "boolean"}
JSON_TYPES = {"json", "jsonb"}


def quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def pg_table_name(schema: str, table: str) -> str:
    return f"{quote_ident(schema)}.{quote_ident(table)}"


def sqlite_tables(con: sqlite3.Connection, selected: set[str] | None, skip: set[str]) -> list[str]:
    rows = con.execute(
        "select name from sqlite_master where type = 'table' and name not like 'sqlite_%' order by name"
    ).fetchall()
    return [row["name"] for row in rows if row["name"] not in skip and (selected is None or row["name"] in selected)]


def pg_tables(pg: psycopg.Connection, schema: str, selected: set[str] | None, skip: set[str]) -> set[str]:
    rows = pg.execute(
        """
        select table_name
        from information_schema.tables
        where table_schema = %s and table_type = 'BASE TABLE'
        """,
        (schema,),
    ).fetchall()
    return {row["table_name"] for row in rows if row["table_name"] not in skip and (selected is None or row["table_name"] in selected)}


def pg_columns(pg: psycopg.Connection, schema: str, table: str) -> list[dict[str, Any]]:
    return pg.execute(
        """
        select column_name, udt_name, data_type, is_nullable, column_default, ordinal_position,
               is_identity, identity_generation
        from information_schema.columns
        where table_schema = %s and table_name = %s
        order by ordinal_position
        """,
        (schema, table),
    ).fetchall()


def pg_primary_key(pg: psycopg.Connection, schema: str, table: str) -> list[str]:
    rows = pg.execute(
        """
        select a.attname as column_name
        from pg_index i
        join pg_class c on c.oid = i.indrelid
        join pg_namespace n on n.oid = c.relnamespace
        join pg_attribute a on a.attrelid = c.oid and a.attnum = any(i.indkey)
        where n.nspname = %s and c.relname = %s and i.indisprimary
        order by array_position(i.indkey, a.attnum)
        """,
        (schema, table),
    ).fetchall()
    return [row["column_name"] for row in rows]


def pg_foreign_key_order(pg: psycopg.Connection, schema: str, tables: list[str]) -> list[str]:
    selected = set(tables)
    edges: dict[str, set[str]] = {table: set() for table in tables}
    rows = pg.execute(
        """
        select child.relname as child_table, parent.relname as parent_table
        from pg_constraint c
        join pg_class child on child.oid = c.conrelid
        join pg_namespace child_ns on child_ns.oid = child.relnamespace
        join pg_class parent on parent.oid = c.confrelid
        join pg_namespace parent_ns on parent_ns.oid = parent.relnamespace
        where c.contype = 'f'
          and child_ns.nspname = %s
          and parent_ns.nspname = %s
        """,
        (schema, schema),
    ).fetchall()
    for row in rows:
        child = row["child_table"]
        parent = row["parent_table"]
        if child in selected and parent in selected and child != parent:
            edges[child].add(parent)

    ordered: list[str] = []
    pending = dict(edges)
    while pending:
        ready = sorted(table for table, parents in pending.items() if not parents.intersection(pending))
        if not ready:
            ordered.extend(sorted(pending))
            break
        ordered.extend(ready)
        for table in ready:
            pending.pop(table, None)
    return ordered


def comparable(value: Any) -> Any:
    value = normalize_for_compare(value)
    if isinstance(value, bytes):
        return value
    if value is None:
        return None
    return str(value)


def normalize_for_compare(value: Any) -> Any:
    if value.__class__.__name__ in {"Json", "Jsonb"} and hasattr(value, "obj"):
        value = value.obj
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat().replace("+00:00", "Z")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, memoryview):
        return bytes(value)
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return value


def convert_value(value: Any, column: dict[str, Any]) -> Any:
    if value is None:
        return None
    udt = str(column["udt_name"] or "").lower()
    data_type = str(column["data_type"] or "").lower()
    type_name = udt or data_type

    if type_name in BOOL_TYPES:
        return bool(value)
    if type_name in INTEGER_TYPES:
        return int(value)
    if type_name in FLOAT_TYPES:
        return float(value)
    if type_name in NUMERIC_TYPES:
        try:
            return Decimal(str(value))
        except InvalidOperation:
            return value
    if udt == "uuid":
        return uuid.UUID(str(value))
    if type_name == "jsonb":
        return Jsonb(json.loads(value) if isinstance(value, str) else value)
    if type_name == "json":
        return Json(json.loads(value) if isinstance(value, str) else value)
    if udt == "bytea" and isinstance(value, memoryview):
        return bytes(value)
    return value


def sqlite_row_values(row: sqlite3.Row, columns: list[dict[str, Any]]) -> dict[str, Any]:
    return {column["column_name"]: convert_value(row[column["column_name"]], column) for column in columns}


def pg_fetch_existing(
    pg: psycopg.Connection,
    schema: str,
    table: str,
    columns: list[str],
    pk_columns: list[str],
    values: dict[str, Any],
) -> dict[str, Any] | None:
    select_cols = ", ".join(quote_ident(column) for column in columns)
    where = " and ".join(f"{quote_ident(column)} = %s" for column in pk_columns)
    params = [values[column] for column in pk_columns]
    return pg.execute(f"select {select_cols} from {pg_table_name(schema, table)} where {where}", params).fetchone()


def pg_insert(pg: psycopg.Connection, schema: str, table: str, values: dict[str, Any]) -> None:
    names = list(values)
    sql = (
        f"insert into {pg_table_name(schema, table)} ({', '.join(quote_ident(name) for name in names)}) "
        f"values ({', '.join('%s' for _ in names)})"
    )
    pg.execute(sql, [values[name] for name in names])


def pg_update(
    pg: psycopg.Connection,
    schema: str,
    table: str,
    values: dict[str, Any],
    pk_columns: list[str],
    update_columns: list[str],
) -> None:
    assignments = ", ".join(f"{quote_ident(column)} = %s" for column in update_columns)
    where = " and ".join(f"{quote_ident(column)} = %s" for column in pk_columns)
    params = [values[column] for column in update_columns] + [values[column] for column in pk_columns]
    pg.execute(f"update {pg_table_name(schema, table)} set {assignments} where {where}", params)


def delete_extra_rows(
    pg: psycopg.Connection,
    schema: str,
    table: str,
    pk_columns: list[str],
    source_keys: set[tuple[Any, ...]],
    dry_run: bool,
) -> int:
    if not pk_columns:
        return 0
    key_cols = ", ".join(quote_ident(column) for column in pk_columns)
    rows = pg.execute(f"select {key_cols} from {pg_table_name(schema, table)}").fetchall()
    deleted = 0
    where = " and ".join(f"{quote_ident(column)} = %s" for column in pk_columns)
    for row in rows:
        key = tuple(comparable(row[column]) for column in pk_columns)
        if key in source_keys:
            continue
        if not dry_run:
            pg.execute(f"delete from {pg_table_name(schema, table)} where {where}", [row[column] for column in pk_columns])
        deleted += 1
    return deleted


def sync_table_rows(
    sqlite: sqlite3.Connection,
    pg: psycopg.Connection,
    schema: str,
    table: str,
    dry_run: bool,
) -> dict[str, int | str]:
    pg_cols = pg_columns(pg, schema, table)
    pg_col_names = [column["column_name"] for column in pg_cols]
    sqlite_cols = {row["name"] for row in sqlite.execute(f"pragma table_info({quote_ident(table)})").fetchall()}
    common_cols = [column for column in pg_cols if column["column_name"] in sqlite_cols]
    common_names = [column["column_name"] for column in common_cols]
    pk_columns = [column for column in pg_primary_key(pg, schema, table) if column in common_names]
    if not common_cols or not pk_columns:
        return {"table": table, "inserted": 0, "updated": 0, "skipped": 0}

    inserted = 0
    updated = 0
    skipped = 0
    source_keys: set[tuple[Any, ...]] = set()
    select_cols = ", ".join(quote_ident(name) for name in common_names)
    rows = sqlite.execute(f"select {select_cols} from {quote_ident(table)}").fetchall()
    update_columns = [name for name in common_names if name not in pk_columns]

    for row in rows:
        values = sqlite_row_values(row, common_cols)
        source_keys.add(tuple(comparable(values[column]) for column in pk_columns))
        existing = pg_fetch_existing(pg, schema, table, common_names, pk_columns, values)
        if existing is None:
            if not dry_run:
                pg_insert(pg, schema, table, values)
            inserted += 1
            continue
        changed = any(comparable(existing[column]) != comparable(values[column]) for column in update_columns)
        if changed and update_columns:
            if not dry_run:
                pg_update(pg, schema, table, values, pk_columns, update_columns)
            updated += 1
        else:
            skipped += 1

    return {"table": table, "inserted": inserted, "updated": updated, "skipped": skipped}


def sqlite_source_keys(
    sqlite: sqlite3.Connection,
    table: str,
    pk_columns: list[str],
) -> set[tuple[Any, ...]]:
    if not pk_columns:
        return set()
    rows = sqlite.execute(
        f"select {', '.join(quote_ident(column) for column in pk_columns)} from {quote_ident(table)}"
    ).fetchall()
    return {tuple(comparable(row[column]) for column in pk_columns) for row in rows}


def reset_sequences(pg: psycopg.Connection, schema: str, table: str) -> None:
    rows = pg.execute(
        """
        select column_name
        from information_schema.columns
        where table_schema = %s
          and table_name = %s
          and (column_default like 'nextval%%' or is_identity = 'YES')
        """,
        (schema, table),
    ).fetchall()
    for row in rows:
        column = row["column_name"]
        seq = pg.execute("select pg_get_serial_sequence(%s, %s)", (f"{schema}.{table}", column)).fetchone()
        if not seq or not seq["pg_get_serial_sequence"]:
            continue
        max_row = pg.execute(
            f"select max({quote_ident(column)}) as max_value from {pg_table_name(schema, table)}"
        ).fetchone()
        max_value = max_row["max_value"] if max_row else None
        if max_value is None:
            pg.execute("select setval(%s, 1, false)", (seq["pg_get_serial_sequence"],))
        else:
            pg.execute("select setval(%s, %s, true)", (seq["pg_get_serial_sequence"], max_value))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sync backend_py SQLite tables into Supabase/Postgres.")
    parser.add_argument("--postgres-url", default=os.getenv("SUPABASE_DB_URL") or os.getenv("POSTGRES_URL") or os.getenv("DATABASE_URL"))
    parser.add_argument("--sqlite", default=str(appmod.DB_PATH))
    parser.add_argument("--schema", default="public")
    parser.add_argument("--tables", default="", help="Comma-separated table names. Empty means all shared tables.")
    parser.add_argument("--skip-tables", default=",".join(sorted(DEFAULT_SKIP_TABLES)))
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not args.postgres_url:
        raise SystemExit("Set SUPABASE_DB_URL or pass --postgres-url.")

    selected = {name.strip() for name in args.tables.split(",") if name.strip()} or None
    skip = {name.strip() for name in args.skip_tables.split(",") if name.strip()}
    sqlite_path = Path(args.sqlite)
    if not sqlite_path.exists():
        raise SystemExit(f"SQLite database not found: {sqlite_path}")
    appmod.DB_PATH = sqlite_path
    appmod.init_db()

    with sqlite3.connect(sqlite_path) as sqlite, psycopg.connect(args.postgres_url, row_factory=dict_row) as pg:
        sqlite.row_factory = sqlite3.Row
        sqlite_names = sqlite_tables(sqlite, selected, skip)
        pg_names = pg_tables(pg, args.schema, selected, skip)
        shared = [name for name in sqlite_names if name in pg_names]
        missing = [name for name in sqlite_names if name not in pg_names]
        for name in missing:
            print(f"{name}: skipped target table missing in Postgres")

        ordered = pg_foreign_key_order(pg, args.schema, shared)
        totals = {"inserted": 0, "updated": 0, "deleted": 0, "skipped": 0}
        for table in ordered:
            result = sync_table_rows(sqlite, pg, args.schema, table, args.dry_run)
            for key in ("inserted", "updated", "skipped"):
                totals[key] += int(result[key])
            print(
                f"{table}: inserted={result['inserted']} updated={result['updated']} "
                f"skipped={result['skipped']}"
            )

        for table in reversed(ordered):
            pk_columns = pg_primary_key(pg, args.schema, table)
            source_keys = sqlite_source_keys(sqlite, table, pk_columns)
            deleted = delete_extra_rows(pg, args.schema, table, pk_columns, source_keys, args.dry_run)
            totals["deleted"] += deleted
            if deleted:
                print(f"{table}: deleted={deleted}")

        if not args.dry_run:
            for table in ordered:
                reset_sequences(pg, args.schema, table)
            pg.commit()
        else:
            pg.rollback()

    print(
        f"total: inserted={totals['inserted']} updated={totals['updated']} "
        f"deleted={totals['deleted']} skipped={totals['skipped']}"
    )


if __name__ == "__main__":
    main()
