@app.post("/api/auth/register-code")
@db_write_api
def send_register_code(payload: RegisterCodeRequest) -> dict[str, Any]:
    email = payload.email.strip().lower()
    if not email or "@" not in email:
        raise AppError(400, "VALIDATION_FAILED", "Invalid email")
    code = f"{random.randint(0, 999999):06d}"
    ttl_minutes = max(1, VERIFICATION_CODE_TTL_MINUTES)
    expires_at = (datetime.now(timezone.utc) + timedelta(minutes=ttl_minutes)).isoformat()
    with db() as con:
        con.execute(
            """
            insert into verification_codes(email, code, expires_at) values (?, ?, ?)
            on conflict(email) do update set code=excluded.code, expires_at=excluded.expires_at
            """,
            (email, code, expires_at),
        )
    mail_sent = send_verification_email(email, code, ttl_minutes)
    data = {"email": email, "expiresInMinutes": ttl_minutes, "mailSent": mail_sent}
    if ALLOW_DEV_VERIFY_CODE:
        data["debugCode"] = code
    print(f"[backend_py] register code for {email}: {code}")
    return api_ok(data)


@app.post("/api/auth/register")
@db_write_api
def register(payload: RegisterRequest, request: Request) -> dict[str, Any]:
    verify_turnstile(payload.turnstileToken, request)
    email = payload.email.strip().lower()
    if not email or "@" not in email:
        raise AppError(400, "VALIDATION_FAILED", "Invalid email")
    if not payload.password:
        raise AppError(400, "VALIDATION_FAILED", "Password is required")
    with db() as con:
        code_row = con.execute("select * from verification_codes where email = ?", (email,)).fetchone()
        if not code_row or code_row["code"] != payload.verificationCode:
            raise AppError(400, "INVALID_VERIFICATION_CODE", "Invalid or expired verification code")
        if datetime.fromisoformat(code_row["expires_at"]) <= datetime.now(timezone.utc):
            raise AppError(400, "INVALID_VERIFICATION_CODE", "Invalid or expired verification code")
        user_id = str(uuid.uuid4())
        try:
            con.execute(
                """
                insert into users(id, email, password_hash, registration_ip, balance, status, created_at)
                values (?, ?, ?, ?, ?, 'active', ?)
                """,
                (
                    user_id,
                    email,
                    payload.password,
                    client_ip(request),
                    decimal_text(DEFAULT_BALANCE),
                    now_iso(),
                ),
            )
        except sqlite3.IntegrityError as exc:
            raise AppError(409, "CONFLICT", "Email or registration IP has already been used") from exc
        con.execute("delete from verification_codes where email = ?", (email,))
        user = con.execute("select * from users where id = ?", (user_id,)).fetchone()
    return api_ok(auth_response(user))


@app.post("/api/auth/login")
@db_write_api
def login(payload: LoginRequest) -> dict[str, Any]:
    email = payload.email.strip().lower()
    with db() as con:
        user = con.execute("select * from users where email = ?", (email,)).fetchone()
    if not user or payload.password != user["password_hash"]:
        raise AppError(401, "INVALID_CREDENTIALS", "Invalid email or password")
    with db() as con:
        deduct_expired_redeem_codes(con, user["id"])
        user = con.execute("select * from users where id = ?", (user["id"],)).fetchone()
    return api_ok(auth_response(user))


def auth_response(user: sqlite3.Row) -> dict[str, Any]:
    return {"userId": user["id"], "email": user["email"], "balance": float(user["balance"]), "token": issue_jwt(user)}


@app.get("/api/balance")
@db_write_api
def balance(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    user_id = current_user_id(authorization)
    with db() as con:
        deduct_expired_redeem_codes(con, user_id)
        user = con.execute("select balance from users where id = ?", (user_id,)).fetchone()
    if not user:
        raise AppError(401, "UNAUTHORIZED", "Unauthorized")
    return api_ok({"balance": float(user["balance"])})


@app.get("/api/balance/stream")
@db_write_api
async def balance_stream(request: Request, authorization: str | None = Header(default=None)) -> StreamingResponse:
    user_id = current_user_id(authorization)

    def load_balance(*, deduct_expired: bool = False) -> str | None:
        with db() as con:
            if deduct_expired:
                deduct_expired_redeem_codes(con, user_id)
            user = con.execute("select balance from users where id = ?", (user_id,)).fetchone()
        return str(user["balance"]) if user else None

    initial_balance = await run_in_threadpool(load_balance, deduct_expired=True)
    if initial_balance is None:
        raise AppError(401, "UNAUTHORIZED", "Unauthorized")

    async def generate() -> AsyncIterable[str]:
        last_balance: str | None = None
        last_keepalive_at = time.time()
        next_balance = initial_balance
        while True:
            if await request.is_disconnected():
                break

            if next_balance is None:
                payload = json.dumps({"message": "Unauthorized", "code": "UNAUTHORIZED"}, ensure_ascii=False)
                yield f"event: error\ndata: {payload}\n\n"
                break

            if next_balance != last_balance:
                last_balance = next_balance
                payload = json.dumps({"balance": float(next_balance)}, ensure_ascii=False)
                yield f"event: balance\ndata: {payload}\n\n"
                last_keepalive_at = time.time()
            elif time.time() - last_keepalive_at >= 25:
                yield ": keepalive\n\n"
                last_keepalive_at = time.time()

            await asyncio.sleep(5)
            next_balance = await run_in_threadpool(load_balance)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/api-keys")
def list_api_keys(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    user_id = current_user_id(authorization)
    with db() as con:
        rows = con.execute(
            "select * from api_keys where user_id = ? and status = 'active' order by id desc", (user_id,)
        ).fetchall()
    return api_ok([api_key_response(row) for row in rows])


@app.post("/api/api-keys")
@db_write_api
def create_api_key(payload: CreateApiKeyRequest, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    user_id = current_user_id(authorization)
    name = payload.name.strip()
    key = issue_api_key()
    with db() as con:
        exists = con.execute(
            "select 1 from api_keys where user_id = ? and name = ? and status = 'active'", (user_id, name)
        ).fetchone()
        if exists:
            raise AppError(409, "CONFLICT", "API key name already exists")
        con.execute(
            "insert into api_keys(user_id, key_hash, key_value, name, status, created_at) values (?, ?, ?, ?, 'active', ?)",
            (user_id, sha256_key(key), key, name, now_iso()),
        )
        row = con.execute("select * from api_keys where id = last_insert_rowid()").fetchone()
    if "invalidate_proxy_context_cache" in globals():
        invalidate_proxy_context_cache()
    return api_ok(api_key_response(row))


@app.delete("/api/api-keys/{key_id}")
@db_write_api
def revoke_api_key(key_id: int, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    user_id = current_user_id(authorization)
    with db() as con:
        cur = con.execute(
            "update api_keys set status = 'revoked' where id = ? and user_id = ? and status = 'active'",
            (key_id, user_id),
        )
        if cur.rowcount == 0:
            raise AppError(404, "NOT_FOUND", "API key not found")
    if "invalidate_proxy_context_cache" in globals():
        invalidate_proxy_context_cache()
    return api_ok(None)


def api_key_response(row: sqlite3.Row) -> dict[str, Any]:
    key = row["key_value"] or display_key(row["key_hash"])
    return {"id": row["id"], "name": row["name"], "key": key, "status": row["status"], "createdAt": row["created_at"]}


@app.get("/api/request-logs")
def request_logs(
    limit: int = 100,
    cursor: str = "",
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    user_id = current_user_id(authorization)
    limit = max(1, min(int(limit), 200))
    conditions = ["user_id = ?"]
    params: list[Any] = [user_id]
    trimmed_cursor = cursor.strip()
    if trimmed_cursor:
        cursor_created_at, cursor_id = decode_request_log_cursor(trimmed_cursor)
        conditions.append("(created_at < ? or (created_at = ? and id < ?))")
        params.extend([cursor_created_at, cursor_created_at, cursor_id])
    with db() as con:
        rows = con.execute(
            f"""
            select id, created_at, token_name, group_key, request_type, model, use_time_ms,
                   first_token_ms, prompt_tokens, completion_tokens, cache_read_tokens,
                   cache_creation_tokens, cost, ip, status, upstream_service_id
            from request_logs
            where {' and '.join(conditions)}
            order by created_at desc, id desc
            limit ?
            """,
            tuple(params) + (limit + 1,),
        ).fetchall()
    page_rows = rows[:limit]
    has_more = len(rows) > limit
    return api_ok(
        {
            "items": [request_log_response(row) for row in page_rows],
            "limit": limit,
            "hasMore": has_more,
            "nextCursor": encode_request_log_cursor(page_rows[-1]) if has_more and page_rows else "",
        }
    )


def request_log_response(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "createdAt": row["created_at"],
        "token": row["token_name"],
        "group": row["group_key"],
        "type": row["request_type"],
        "model": row["model"],
        "useTimeMs": row["use_time_ms"],
        "firstTokenMs": row["first_token_ms"],
        "inputTokens": row["prompt_tokens"],
        "outputTokens": row["completion_tokens"],
        "cacheReadTokens": row["cache_read_tokens"],
        "cacheCreationTokens": row["cache_creation_tokens"],
        "cost": float(row["cost"]),
        "ip": row["ip"],
        "status": row["status"],
        "upstreamServiceId": row["upstream_service_id"],
    }
