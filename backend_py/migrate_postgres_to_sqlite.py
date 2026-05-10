from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import uuid
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

try:
    import psycopg
    from psycopg.rows import dict_row
except ImportError as exc:
    raise SystemExit(
        "Missing dependency: psycopg. Run `pip install -r backend_py/requirements.txt` first."
    ) from exc

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend_py import app as appmod  # noqa: E402


DEFAULT_SKIP_TABLES = {"verification_codes"}

SQLITE_TYPE_BY_PG = {
    "bool": "integer",
    "boolean": "integer",
    "int2": "integer",
    "int4": "integer",
    "int8": "integer",
    "serial": "integer",
    "bigserial": "integer",
    "float4": "real",
    "float8": "real",
    "numeric": "text",
    "decimal": "text",
    "uuid": "text",
    "json": "text",
    "jsonb": "text",
    "bytea": "blob",
    "date": "text",
    "timestamp": "text",
    "timestamptz": "text",
    "time": "text",
}


def quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def normalize(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, bool):
        return 1 if value else 0
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, datetime):
        text = value.isoformat()
        return text.replace("+00:00", "Z")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, memoryview):
        return bytes(value)
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return value


def comparable(value: Any) -> Any:
    value = normalize(value)
    if isinstance(value, bytes):
        return value
    if value is None:
        return None
    return str(value)


def pg_tables(pg: psycopg.Connection, schema: str, selected: set[str] | None, skip: set[str]) -> list[str]:
    rows = pg.execute(
        """
        select table_name
        from information_schema.tables
        where table_schema = %s and table_type = 'BASE TABLE'
        order by table_name
        """,
        (schema,),
    ).fetchall()
    names = [row["table_name"] for row in rows]
    return [name for name in names if name not in skip and (selected is None or name in selected)]


def pg_columns(pg: psycopg.Connection, schema: str, table: str) -> list[dict[str, Any]]:
    return pg.execute(
        """
        select column_name, udt_name, data_type, is_nullable, column_default, ordinal_position
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


def sqlite_tables(con: sqlite3.Connection) -> set[str]:
    rows = con.execute(
        "select name from sqlite_master where type = 'table' and name not like 'sqlite_%'"
    ).fetchall()
    return {row["name"] for row in rows}


def sqlite_columns(con: sqlite3.Connection, table: str) -> list[dict[str, Any]]:
    rows = con.execute(f"pragma table_info({quote_ident(table)})").fetchall()
    return [
        {
            "name": row["name"],
            "type": row["type"] or "",
            "notnull": bool(row["notnull"]),
            "default": row["dflt_value"],
            "pk": int(row["pk"] or 0),
        }
        for row in rows
    ]


def sqlite_pk(columns: list[dict[str, Any]]) -> list[str]:
    return [column["name"] for column in sorted(columns, key=lambda item: item["pk"]) if column["pk"]]


def map_type(column: dict[str, Any]) -> str:
    udt = str(column["udt_name"] or "").lower()
    data_type = str(column["data_type"] or "").lower()
    return SQLITE_TYPE_BY_PG.get(udt) or SQLITE_TYPE_BY_PG.get(data_type) or "text"


def create_sqlite_table(
    con: sqlite3.Connection,
    table: str,
    columns: list[dict[str, Any]],
    pk_columns: list[str],
    dry_run: bool,
) -> None:
    parts = []
    for column in columns:
        parts.append(f"{quote_ident(column['column_name'])} {map_type(column)}")
    if pk_columns:
        parts.append("primary key (" + ", ".join(quote_ident(column) for column in pk_columns) + ")")
    sql = f"create table {quote_ident(table)} ({', '.join(parts)})"
    if dry_run:
        print(f"[dry-run] {sql}")
    else:
        con.execute(sql)


def add_missing_columns(
    con: sqlite3.Connection,
    table: str,
    pg_cols: list[dict[str, Any]],
    sqlite_col_names: set[str],
    dry_run: bool,
) -> int:
    added = 0
    for column in pg_cols:
        name = column["column_name"]
        if name in sqlite_col_names:
            continue
        sql = f"alter table {quote_ident(table)} add column {quote_ident(name)} {map_type(column)}"
        if dry_run:
            print(f"[dry-run] {sql}")
        else:
            con.execute(sql)
        added += 1
    return added


def row_exists_without_pk(con: sqlite3.Connection, table: str, values: dict[str, Any]) -> bool:
    if not values:
        return False
    where = " and ".join(f"{quote_ident(key)} is ?" for key in values)
    row = con.execute(f"select 1 from {quote_ident(table)} where {where} limit 1", list(values.values())).fetchone()
    return row is not None


def fetch_existing_by_pk(
    con: sqlite3.Connection,
    table: str,
    columns: list[str],
    pk_columns: list[str],
    values: dict[str, Any],
) -> sqlite3.Row | None:
    select_cols = ", ".join(quote_ident(column) for column in columns)
    where = " and ".join(f"{quote_ident(column)} = ?" for column in pk_columns)
    params = [values[column] for column in pk_columns]
    return con.execute(f"select {select_cols} from {quote_ident(table)} where {where}", params).fetchone()


def insert_row(con: sqlite3.Connection, table: str, values: dict[str, Any]) -> None:
    names = list(values)
    sql = (
        f"insert into {quote_ident(table)} ({', '.join(quote_ident(name) for name in names)}) "
        f"values ({', '.join('?' for _ in names)})"
    )
    con.execute(sql, [values[name] for name in names])


def update_row(
    con: sqlite3.Connection,
    table: str,
    values: dict[str, Any],
    pk_columns: list[str],
    update_columns: list[str],
) -> None:
    assignments = ", ".join(f"{quote_ident(column)} = ?" for column in update_columns)
    where = " and ".join(f"{quote_ident(column)} = ?" for column in pk_columns)
    params = [values[column] for column in update_columns] + [values[column] for column in pk_columns]
    con.execute(f"update {quote_ident(table)} set {assignments} where {where}", params)


def sqlite_unique_indexes(con: sqlite3.Connection, table: str, pk_columns: list[str]) -> list[list[str]]:
    indexes = []
    for index in con.execute(f"pragma index_list({quote_ident(table)})").fetchall():
        if not index["unique"]:
            continue
        columns = [
            row["name"]
            for row in con.execute(f"pragma index_info({quote_ident(index['name'])})").fetchall()
            if row["name"]
        ]
        if columns and columns != pk_columns:
            indexes.append(columns)
    return indexes


def delete_unique_conflicts(
    con: sqlite3.Connection,
    table: str,
    pk_columns: list[str],
    unique_indexes: list[list[str]],
    values: dict[str, Any],
    dry_run: bool,
) -> int:
    deleted = 0
    pk_where = " and ".join(f"{quote_ident(column)} = ?" for column in pk_columns)
    pk_params = [values[column] for column in pk_columns]
    for unique_columns in unique_indexes:
        if any(values.get(column) is None for column in unique_columns):
            continue
        conflict_where = " and ".join(f"{quote_ident(column)} = ?" for column in unique_columns)
        params = [values[column] for column in unique_columns]
        rows = con.execute(
            f"select {', '.join(quote_ident(column) for column in pk_columns)} from {quote_ident(table)} "
            f"where {conflict_where}",
            params,
        ).fetchall()
        for row in rows:
            same_pk = all(comparable(row[column]) == comparable(values[column]) for column in pk_columns)
            if same_pk:
                continue
            if not dry_run:
                con.execute(f"delete from {quote_ident(table)} where {pk_where}", [row[column] for column in pk_columns])
            deleted += 1
    return deleted


def sqlite_insert_defaults(sqlite_cols: list[dict[str, Any]], values: dict[str, Any]) -> dict[str, Any]:
    filled = dict(values)
    for column in sqlite_cols:
        name = column["name"]
        if name in filled or column["pk"] or not column["notnull"] or column["default"] is not None:
            continue
        type_name = str(column["type"] or "").lower()
        if "int" in type_name:
            filled[name] = 0
        elif "real" in type_name or "floa" in type_name or "doub" in type_name:
            filled[name] = 0.0
        elif "blob" in type_name:
            filled[name] = b""
        else:
            filled[name] = ""
    return filled


def delete_extra_rows(
    con: sqlite3.Connection,
    table: str,
    pk_columns: list[str],
    source_keys: set[tuple[Any, ...]],
    dry_run: bool,
) -> int:
    if not pk_columns:
        return 0
    rows = con.execute(
        f"select {', '.join(quote_ident(column) for column in pk_columns)} from {quote_ident(table)}"
    ).fetchall()
    deleted = 0
    where = " and ".join(f"{quote_ident(column)} = ?" for column in pk_columns)
    for row in rows:
        key = tuple(comparable(row[column]) for column in pk_columns)
        if key in source_keys:
            continue
        if not dry_run:
            con.execute(f"delete from {quote_ident(table)} where {where}", [row[column] for column in pk_columns])
        deleted += 1
    return deleted


def pg_source_keys(
    pg: psycopg.Connection,
    schema: str,
    table: str,
    pk_columns: list[str],
) -> set[tuple[Any, ...]]:
    if not pk_columns:
        return set()
    col_sql = ", ".join(quote_ident(column) for column in pk_columns)
    rows = pg.execute(f"select {col_sql} from {quote_ident(schema)}.{quote_ident(table)}").fetchall()
    return {tuple(comparable(row[column]) for column in pk_columns) for row in rows}


def sync_table(
    pg: psycopg.Connection,
    con: sqlite3.Connection,
    schema: str,
    table: str,
    batch_size: int,
    dry_run: bool,
) -> dict[str, int | str]:
    pg_cols = pg_columns(pg, schema, table)
    pg_col_names = [column["column_name"] for column in pg_cols]
    pk_columns = pg_primary_key(pg, schema, table)

    created = 0
    added_columns = 0
    table_exists = table in sqlite_tables(con)
    if not table_exists:
        create_sqlite_table(con, table, pg_cols, pk_columns, dry_run)
        created = 1
    else:
        sqlite_col_names = {column["name"] for column in sqlite_columns(con, table)}
        added_columns = add_missing_columns(con, table, pg_cols, sqlite_col_names, dry_run)

    sqlite_cols = sqlite_columns(con, table) if table_exists or not dry_run else [
        {"name": column["column_name"], "pk": 1 if column["column_name"] in pk_columns else 0} for column in pg_cols
    ]
    sqlite_col_names = {column["name"] for column in sqlite_cols}
    common_cols = [name for name in pg_col_names if name in sqlite_col_names]
    if not common_cols:
        return {
            "table": table,
            "created": created,
            "addedColumns": added_columns,
            "inserted": 0,
            "updated": 0,
            "deleted": 0,
            "skipped": 0,
        }

    sqlite_pk_cols = sqlite_pk(sqlite_cols)
    key_cols = [column for column in pk_columns if column in common_cols] or [column for column in sqlite_pk_cols if column in common_cols]
    update_cols = [column for column in common_cols if column not in key_cols]

    inserted = 0
    updated = 0
    deleted = 0
    skipped = 0
    source_keys = pg_source_keys(pg, schema, table, key_cols) if key_cols else set()
    if key_cols and table_exists:
        deleted = delete_extra_rows(con, table, key_cols, source_keys, dry_run)
    unique_indexes = sqlite_unique_indexes(con, table, key_cols) if key_cols and table_exists else []
    col_sql = ", ".join(quote_ident(column) for column in common_cols)
    with pg.cursor(name=f"migrate_{table}", row_factory=dict_row) as cur:
        cur.itersize = batch_size
        cur.execute(f"select {col_sql} from {quote_ident(schema)}.{quote_ident(table)}")
        for source in cur:
            values = {column: normalize(source[column]) for column in common_cols}
            if key_cols:
                if dry_run and not table_exists:
                    inserted += 1
                    continue
                existing = fetch_existing_by_pk(con, table, common_cols, key_cols, values)
                if existing is None:
                    if unique_indexes:
                        deleted += delete_unique_conflicts(con, table, key_cols, unique_indexes, values, dry_run)
                    if not dry_run:
                        insert_row(con, table, sqlite_insert_defaults(sqlite_cols, values))
                    inserted += 1
                    continue
                changed = any(comparable(existing[column]) != comparable(values[column]) for column in update_cols)
                if changed and update_cols:
                    if unique_indexes:
                        deleted += delete_unique_conflicts(con, table, key_cols, unique_indexes, values, dry_run)
                    if not dry_run:
                        update_row(con, table, values, key_cols, update_cols)
                    updated += 1
                else:
                    skipped += 1
            elif dry_run and not table_exists:
                inserted += 1
                continue
            elif row_exists_without_pk(con, table, values):
                skipped += 1
            else:
                if not dry_run:
                    insert_row(con, table, sqlite_insert_defaults(sqlite_cols, values))
                inserted += 1

    return {
        "table": table,
        "created": created,
        "addedColumns": added_columns,
        "inserted": inserted,
        "updated": updated,
        "deleted": deleted,
        "skipped": skipped,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sync Supabase/Postgres tables into backend_py SQLite.")
    parser.add_argument("--postgres-url", default=os.getenv("SUPABASE_DB_URL") or os.getenv("POSTGRES_URL") or os.getenv("DATABASE_URL"))
    parser.add_argument("--sqlite", default=str(appmod.DB_PATH))
    parser.add_argument("--schema", default="public")
    parser.add_argument("--tables", default="", help="Comma-separated table names. Empty means all public tables.")
    parser.add_argument("--skip-tables", default=",".join(sorted(DEFAULT_SKIP_TABLES)))
    parser.add_argument("--batch-size", type=int, default=500)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not args.postgres_url:
        raise SystemExit("Set SUPABASE_DB_URL or pass --postgres-url.")

    selected = {name.strip() for name in args.tables.split(",") if name.strip()} or None
    skip = {name.strip() for name in args.skip_tables.split(",") if name.strip()}
    sqlite_path = Path(args.sqlite)
    appmod.DB_PATH = sqlite_path
    appmod.init_db()

    sqlite_path.parent.mkdir(parents=True, exist_ok=True)
    with psycopg.connect(args.postgres_url, row_factory=dict_row) as pg, sqlite3.connect(sqlite_path) as con:
        con.row_factory = sqlite3.Row
        con.execute("pragma foreign_keys = off")
        tables = pg_tables(pg, args.schema, selected, skip)
        totals = {"created": 0, "addedColumns": 0, "inserted": 0, "updated": 0, "deleted": 0, "skipped": 0}
        for table in tables:
            result = sync_table(pg, con, args.schema, table, max(1, args.batch_size), args.dry_run)
            for key in totals:
                totals[key] += int(result[key])
            print(
                f"{table}: created={result['created']} added_columns={result['addedColumns']} "
                f"inserted={result['inserted']} updated={result['updated']} "
                f"deleted={result['deleted']} skipped={result['skipped']}"
            )
        if args.dry_run:
            con.rollback()
        else:
            con.commit()
    print(
        f"total: created={totals['created']} added_columns={totals['addedColumns']} "
        f"inserted={totals['inserted']} updated={totals['updated']} "
        f"deleted={totals['deleted']} skipped={totals['skipped']}"
    )


if __name__ == "__main__":
    main()
