def quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def admin_table_names(con: sqlite3.Connection) -> set[str]:
    rows = con.execute(
        """
        select name from sqlite_master
        where type = 'table' and name not like 'sqlite_%'
        order by name
        """
    ).fetchall()
    return {row["name"] for row in rows}


def admin_require_table(con: sqlite3.Connection, table: str) -> str:
    names = admin_table_names(con)
    if table not in names:
        raise AppError(404, "NOT_FOUND", "SQLite table not found")
    return table


def admin_columns(con: sqlite3.Connection, table: str) -> list[dict[str, Any]]:
    rows = con.execute(f"pragma table_info({quote_ident(table)})").fetchall()
    return [
        {
            "name": row["name"],
            "type": row["type"] or "",
            "notNull": bool(row["notnull"]),
            "defaultValue": row["dflt_value"],
            "primaryKey": int(row["pk"] or 0),
        }
        for row in rows
    ]


def admin_json_value(value: Any) -> Any:
    if isinstance(value, bytes):
        return {"type": "blob", "base64": base64.b64encode(value).decode("ascii")}
    return value


def admin_row_response(row: sqlite3.Row) -> dict[str, Any]:
    return {key: admin_json_value(row[key]) for key in row.keys()}


def admin_sql_result_rows(rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
    return [admin_row_response(row) for row in rows]


def admin_clean_values(columns: list[dict[str, Any]], values: dict[str, Any]) -> dict[str, Any]:
    allowed = {column["name"] for column in columns}
    cleaned: dict[str, Any] = {}
    rejected = []
    for key, value in values.items():
        if key in {"rowid", "_rowid"}:
            continue
        if key not in allowed:
            rejected.append(key)
            continue
        if isinstance(value, (dict, list)):
            cleaned[key] = json.dumps(value, ensure_ascii=False)
        else:
            cleaned[key] = value
    if rejected:
        raise AppError(400, "VALIDATION_FAILED", "Unknown SQLite column", {"columns": rejected})
    return cleaned


def admin_invalidate_proxy_cache(table: str | None = None) -> None:
    proxy_tables = {
        "api_keys",
        "app_settings",
        "claude_services",
        "model_catalog",
        "openai_codex_profiles",
        "openai_services",
        "redeem_codes",
        "users",
    }
    if table is None or table in proxy_tables:
        if "invalidate_proxy_context_cache" in globals():
            invalidate_proxy_context_cache()


@app.get("/api/admin/sqlite/tables")
def admin_sqlite_tables(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    current_owner_user_id(authorization)
    with db() as con:
        tables = []
        for name in sorted(admin_table_names(con)):
            qname = quote_ident(name)
            row_count = con.execute(f"select count(*) as count from {qname}").fetchone()["count"]
            columns = admin_columns(con, name)
            tables.append(
                {
                    "name": name,
                    "rowCount": row_count,
                    "columnCount": len(columns),
                    "primaryKey": [column["name"] for column in columns if column["primaryKey"]],
                }
            )
    return api_ok({"tables": tables, "ownerEmail": OWNER_EMAIL})


@app.get("/api/admin/maintenance")
def admin_maintenance(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    current_owner_user_id(authorization)
    return api_ok({"writeDisabled": maintenance_write_disabled()})


@app.put("/api/admin/maintenance")
@db_write_api
@maintenance_control_api
def admin_set_maintenance(
    payload: AdminMaintenanceRequest,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    current_owner_user_id(authorization)
    value = "true" if payload.writeDisabled else "false"
    with db() as con:
        con.execute(
            """
            insert into app_settings(setting_key, setting_value, description, updated_at)
            values (?, ?, ?, ?)
            on conflict(setting_key) do update set
              setting_value=excluded.setting_value,
              description=excluded.description,
              updated_at=excluded.updated_at
            """,
            ("maintenance.write_disabled", value, "Disable database write APIs during migration", now_iso()),
        )
    set_maintenance_write_disabled_cache(payload.writeDisabled)
    return api_ok({"writeDisabled": payload.writeDisabled})


@app.post("/api/admin/settings/image")
@db_write_api
def admin_upload_setting_image(
    payload: AdminSettingImageRequest,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    current_owner_user_id(authorization)
    setting_key = payload.settingKey.strip()
    if not setting_key:
        raise AppError(400, "VALIDATION_FAILED", "Setting key is required")
    with db() as con:
        row = con.execute("select setting_value from app_settings where setting_key = ?", (setting_key,)).fetchone()
        if not row:
            raise AppError(404, "NOT_FOUND", "Setting not found")
        old_value = str(row["setting_value"] or "")
        relative_url = save_setting_image(payload.fileName, payload.dataUrl, setting_key)
        if old_value != relative_url:
            delete_setting_image(old_value)
        con.execute(
            """
            update app_settings
            set setting_value = ?, updated_at = ?
            where setting_key = ?
            """,
            (relative_url, now_iso(), setting_key),
        )
    admin_invalidate_proxy_cache("app_settings")
    return api_ok({"settingKey": setting_key, "settingValue": relative_url})


@app.post("/api/admin/settings/image/delete")
@db_write_api
def admin_delete_setting_image(
    payload: AdminSettingImageDeleteRequest,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    current_owner_user_id(authorization)
    setting_key = payload.settingKey.strip()
    if not setting_key:
        raise AppError(400, "VALIDATION_FAILED", "Setting key is required")
    with db() as con:
        row = con.execute("select setting_value from app_settings where setting_key = ?", (setting_key,)).fetchone()
        if not row:
            raise AppError(404, "NOT_FOUND", "Setting not found")
        delete_setting_image(str(row["setting_value"] or ""))
        con.execute(
            """
            update app_settings
            set setting_value = '', updated_at = ?
            where setting_key = ?
            """,
            (now_iso(), setting_key),
        )
    admin_invalidate_proxy_cache("app_settings")
    return api_ok({"settingKey": setting_key, "settingValue": ""})


@app.post("/api/admin/users/balance-credit")
@db_write_api
def admin_credit_user_balance(
    payload: AdminBalanceCreditRequest,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    current_owner_user_id(authorization)
    email = payload.email.strip().lower()
    if not email or "@" not in email:
        raise AppError(400, "VALIDATION_FAILED", "Invalid email")
    if payload.amount <= 0:
        raise AppError(400, "VALIDATION_FAILED", "Amount must be greater than 0")
    credit = parse_decimal(payload.amount) * Decimal("10")
    with db() as con:
        user = con.execute("select * from users where email = ?", (email,)).fetchone()
        if not user:
            raise AppError(404, "NOT_FOUND", "User not found")
        next_balance = add_balance(con, user["id"], credit)
    return api_ok(
        {
            "email": email,
            "inputAmount": float(payload.amount),
            "creditedAmount": float(credit),
            "balance": float(next_balance),
        }
    )


@app.get("/api/admin/sqlite/tables/{table}/rows")
def admin_sqlite_rows(
    table: str,
    limit: int = 100,
    offset: int = 0,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    current_owner_user_id(authorization)
    limit = max(1, min(int(limit), 500))
    offset = max(0, int(offset))
    with db() as con:
        admin_require_table(con, table)
        qname = quote_ident(table)
        columns = admin_columns(con, table)
        total = con.execute(f"select count(*) as count from {qname}").fetchone()["count"]
        rows = con.execute(f"select rowid as _rowid, * from {qname} order by rowid desc limit ? offset ?", (limit, offset)).fetchall()
    return api_ok(
        {
            "table": table,
            "columns": columns,
            "rows": [admin_row_response(row) for row in rows],
            "limit": limit,
            "offset": offset,
            "total": total,
        }
    )


@app.post("/api/admin/sqlite/tables/{table}/rows")
@db_write_api
def admin_sqlite_create_row(
    table: str,
    payload: AdminRowRequest,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    current_owner_user_id(authorization)
    with db() as con:
        admin_require_table(con, table)
        qname = quote_ident(table)
        columns = admin_columns(con, table)
        values = admin_clean_values(columns, payload.values or {})
        try:
            if values:
                names = list(values.keys())
                sql = f"insert into {qname} ({', '.join(quote_ident(name) for name in names)}) values ({', '.join('?' for _ in names)})"
                cur = con.execute(sql, [values[name] for name in names])
            else:
                cur = con.execute(f"insert into {qname} default values")
            row = con.execute(f"select rowid as _rowid, * from {qname} where rowid = ?", (cur.lastrowid,)).fetchone()
        except sqlite3.IntegrityError as exc:
            raise AppError(400, "SQLITE_CONSTRAINT", str(exc)) from exc
        except sqlite3.OperationalError as exc:
            raise AppError(400, "SQLITE_ERROR", str(exc)) from exc
    admin_invalidate_proxy_cache(table)
    return api_ok({"row": admin_row_response(row) if row else None})


@app.put("/api/admin/sqlite/tables/{table}/rows/{rowid}")
@db_write_api
def admin_sqlite_update_row(
    table: str,
    rowid: int,
    payload: AdminRowRequest,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    current_owner_user_id(authorization)
    with db() as con:
        admin_require_table(con, table)
        qname = quote_ident(table)
        exists = con.execute(f"select 1 from {qname} where rowid = ?", (rowid,)).fetchone()
        if not exists:
            raise AppError(404, "NOT_FOUND", "SQLite row not found")
        columns = admin_columns(con, table)
        values = admin_clean_values(columns, payload.values or {})
        try:
            if values:
                names = list(values.keys())
                assignments = ", ".join(f"{quote_ident(name)} = ?" for name in names)
                con.execute(f"update {qname} set {assignments} where rowid = ?", [values[name] for name in names] + [rowid])
            row = con.execute(f"select rowid as _rowid, * from {qname} where rowid = ?", (rowid,)).fetchone()
        except sqlite3.IntegrityError as exc:
            raise AppError(400, "SQLITE_CONSTRAINT", str(exc)) from exc
        except sqlite3.OperationalError as exc:
            raise AppError(400, "SQLITE_ERROR", str(exc)) from exc
    admin_invalidate_proxy_cache(table)
    return api_ok({"row": admin_row_response(row) if row else None})


@app.delete("/api/admin/sqlite/tables/{table}/rows/{rowid}")
@db_write_api
def admin_sqlite_delete_row(
    table: str,
    rowid: int,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    current_owner_user_id(authorization)
    with db() as con:
        admin_require_table(con, table)
        qname = quote_ident(table)
        exists = con.execute(f"select 1 from {qname} where rowid = ?", (rowid,)).fetchone()
        if not exists:
            raise AppError(404, "NOT_FOUND", "SQLite row not found")
        try:
            con.execute(f"delete from {qname} where rowid = ?", (rowid,))
        except sqlite3.IntegrityError as exc:
            raise AppError(400, "SQLITE_CONSTRAINT", str(exc)) from exc
    admin_invalidate_proxy_cache(table)
    return api_ok(None)


@app.post("/api/admin/sqlite/sql")
@db_write_api
def admin_sqlite_execute_sql(
    payload: AdminSqlRequest,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    current_owner_user_id(authorization)
    sql = (payload.sql or "").strip()
    if not sql:
        raise AppError(400, "VALIDATION_FAILED", "SQL is required")
    if "\x00" in sql:
        raise AppError(400, "VALIDATION_FAILED", "SQL contains invalid characters")
    with db() as con:
        before = con.total_changes
        try:
            try:
                cur = con.execute(sql)
                columns = [item[0] for item in cur.description] if cur.description else []
                rows = cur.fetchmany(500) if cur.description else []
                truncated = bool(cur.fetchone()) if cur.description else False
                statement_count = 1
            except sqlite3.ProgrammingError as exc:
                if "one statement at a time" not in str(exc).lower():
                    raise
                con.executescript(sql)
                columns = []
                rows = []
                truncated = False
                statement_count = len([part for part in sql.split(";") if part.strip()])
        except sqlite3.IntegrityError as exc:
            raise AppError(400, "SQLITE_CONSTRAINT", str(exc)) from exc
        except sqlite3.Error as exc:
            raise AppError(400, "SQLITE_ERROR", str(exc)) from exc
        changed = con.total_changes - before
    if changed:
        admin_invalidate_proxy_cache()
    return api_ok(
        {
            "columns": columns,
            "rows": admin_sql_result_rows(rows),
            "rowCount": len(rows),
            "truncated": truncated,
            "changes": changed,
            "statementCount": statement_count,
        }
    )
