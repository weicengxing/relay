@app.post("/api/auth/register-code")
@db_write_api
def send_register_code(payload: RegisterCodeRequest) -> dict[str, Any]:
    if not EMAIL_REGISTER_ENABLED:
        raise AppError(403, "EMAIL_REGISTER_DISABLED", "Email registration is disabled; please use OAuth login")
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
    if not EMAIL_REGISTER_ENABLED:
        raise AppError(403, "EMAIL_REGISTER_DISABLED", "Email registration is disabled; please use OAuth login")
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


@app.get("/api/auth/dc/start")
@db_write_api
def dc_auth_start(request: Request, redirect: str = "/") -> RedirectResponse:
    if not DC_AUTH_ENABLED:
        raise AppError(404, "NOT_FOUND", "dc.hhhl.cc login is disabled")
    if not DC_AUTH_APP_SECRET:
        raise AppError(500, "INTERNAL_ERROR", "DC_AUTH_APP_SECRET is not configured")

    redirect_url = safe_frontend_redirect_url(redirect, request)
    session = dc_auth_api("auth/session/generate", {"appSecret": DC_AUTH_APP_SECRET})
    session_token = str(session.get("token") or "").strip()
    session_url = str(session.get("url") or "").strip()
    if not session_token or not session_url:
        raise AppError(502, "UPSTREAM_ERROR", "dc.hhhl.cc did not return an auth session")

    state = b64url(secrets.token_bytes(24))
    expires_at = (datetime.now(timezone.utc) + timedelta(seconds=max(60, DC_AUTH_STATE_TTL_SECONDS))).isoformat()
    with db() as con:
        cleanup_expired_dc_auth_states(con)
        con.execute(
            """
            insert into dc_oauth_states(state, session_token, redirect_url, created_at, expires_at)
            values (?, ?, ?, ?, ?)
            """,
            (state, session_token, redirect_url, now_iso(), expires_at),
        )
    return RedirectResponse(session_url, status_code=302)


@app.get("/api/auth/dc/callback")
@db_write_api
def dc_auth_callback(request: Request, token: str = "", session: str = "") -> RedirectResponse:
    session_token = (token or session or "").strip()
    if not session_token:
        raise AppError(400, "VALIDATION_FAILED", "Missing dc.hhhl.cc auth token")
    if not DC_AUTH_APP_SECRET:
        raise AppError(500, "INTERNAL_ERROR", "DC_AUTH_APP_SECRET is not configured")

    with db() as con:
        cleanup_expired_dc_auth_states(con)
        state_row = con.execute(
            "select * from dc_oauth_states where session_token = ?",
            (session_token,),
        ).fetchone()
        if not state_row:
            raise AppError(400, "INVALID_AUTH_STATE", "Login session expired, please try again")
        con.execute("delete from dc_oauth_states where session_token = ?", (session_token,))

    data = dc_auth_api("auth/session/userkey", {"appSecret": DC_AUTH_APP_SECRET, "token": session_token})
    user_payload = data.get("user") if isinstance(data.get("user"), dict) else {}
    user = login_or_create_dc_user(user_payload)
    auth = auth_response(user)
    redirect_url = append_dc_auth_fragment(state_row["redirect_url"], auth)
    return RedirectResponse(redirect_url, status_code=302)


def auth_response(user: sqlite3.Row) -> dict[str, Any]:
    plan = auth_user_plan(user["id"])
    return {
        "userId": user["id"],
        "email": user["email"],
        "balance": float(user["balance"]),
        "token": issue_jwt(user),
        "billingGroup": plan["billing_group"],
        "costMultiplier": float(parse_decimal(plan["cost_multiplier"])),
    }


def cleanup_expired_dc_auth_states(con: sqlite3.Connection) -> None:
    con.execute("delete from dc_oauth_states where expires_at <= ?", (datetime.now(timezone.utc).isoformat(),))


def dc_auth_api(endpoint: str, payload: dict[str, Any]) -> dict[str, Any]:
    try:
        with httpx.Client(timeout=20) as client:
            response = client.post(
                f"{DC_AUTH_ORIGIN}/api/{endpoint}",
                json=payload,
                headers={"Content-Type": "application/json", "User-Agent": "relay-dc-auth/1.0"},
            )
    except Exception as exc:
        raise AppError(502, "UPSTREAM_ERROR", f"Unable to reach dc.hhhl.cc: {exc}") from exc
    try:
        data = response.json()
    except Exception as exc:
        raise AppError(502, "UPSTREAM_ERROR", "dc.hhhl.cc returned a non-JSON response") from exc
    if response.status_code < 200 or response.status_code >= 300:
        raise AppError(502, "UPSTREAM_ERROR", f"dc.hhhl.cc auth failed: {truncate(json.dumps(data), 500)}")
    if not isinstance(data, dict):
        raise AppError(502, "UPSTREAM_ERROR", "dc.hhhl.cc returned an invalid response")
    return data


def safe_frontend_redirect_url(value: str, request: Request) -> str:
    frontend_base = dc_frontend_base_url(request)
    raw = str(value or "/").strip() or "/"
    parsed = urlparse(raw)
    if parsed.scheme or parsed.netloc:
        base = urlparse(frontend_base)
        if parsed.scheme != base.scheme or parsed.netloc != base.netloc:
            raw = "/"
    elif not raw.startswith("/"):
        raw = "/" + raw
    if raw.startswith("//"):
        raw = "/"
    return urljoin(frontend_base + "/", raw.lstrip("/"))


def dc_frontend_base_url(request: Request) -> str:
    if DC_AUTH_FRONTEND_BASE_URL:
        return DC_AUTH_FRONTEND_BASE_URL
    origin = request.headers.get("origin")
    if origin:
        parsed = urlparse(origin)
        if parsed.scheme in {"http", "https"} and parsed.netloc:
            return f"{parsed.scheme}://{parsed.netloc}".rstrip("/")
    referer = request.headers.get("referer")
    if referer:
        parsed = urlparse(referer)
        if parsed.scheme in {"http", "https"} and parsed.netloc:
            return f"{parsed.scheme}://{parsed.netloc}".rstrip("/")
    return "http://127.0.0.1:5173"


def append_dc_auth_fragment(redirect_url: str, auth: dict[str, Any]) -> str:
    fragment = urlencode(
        {
            "dc_status": "ok",
            "token": auth["token"],
            "userId": auth["userId"],
            "email": auth["email"],
            "balance": str(auth["balance"]),
            "billingGroup": auth["billingGroup"],
            "costMultiplier": str(auth["costMultiplier"]),
        }
    )
    return f"{redirect_url.split('#', 1)[0]}#{fragment}"


def login_or_create_dc_user(dc_user: dict[str, Any]) -> sqlite3.Row:
    provider_user_id = str(dc_user.get("id") or dc_user.get("username") or "").strip()
    if not provider_user_id:
        raise AppError(502, "UPSTREAM_ERROR", "dc.hhhl.cc user response is missing an id")
    username = str(dc_user.get("username") or dc_user.get("name") or provider_user_id).strip()
    display_name = str(dc_user.get("name") or username or provider_user_id).strip()
    avatar_url = str(dc_user.get("avatarUrl") or dc_user.get("avatar_url") or "").strip()
    synthetic_email = dc_synthetic_email(provider_user_id, username)
    ts = now_iso()

    with db() as con:
        existing = con.execute(
            """
            select u.*
            from user_oauth_bindings b
            join users u on u.id = b.user_id
            where b.provider = 'dc.hhhl.cc' and b.provider_user_id = ?
            """,
            (provider_user_id,),
        ).fetchone()
        if existing:
            con.execute(
                """
                update user_oauth_bindings
                set provider_username = ?, provider_name = ?, provider_avatar_url = ?, updated_at = ?
                where provider = 'dc.hhhl.cc' and provider_user_id = ?
                """,
                (username, display_name, avatar_url, ts, provider_user_id),
            )
            ensure_dc_oauth_user_plan(con, existing["id"], provider_user_id)
            return con.execute("select * from users where id = ?", (existing["id"],)).fetchone()

        user_id = str(uuid.uuid4())
        con.execute(
            """
            insert into users(id, email, password_hash, registration_ip, balance, status, created_at)
            values (?, ?, ?, null, ?, 'active', ?)
            """,
            (
                user_id,
                synthetic_email,
                "dc-oauth:" + b64url(secrets.token_bytes(24)),
                decimal_text(DC_AUTH_INITIAL_BALANCE),
                ts,
            ),
        )
        con.execute(
            """
            insert into user_oauth_bindings(
              provider, provider_user_id, user_id, provider_username,
              provider_name, provider_avatar_url, created_at, updated_at
            )
            values ('dc.hhhl.cc', ?, ?, ?, ?, ?, ?, ?)
            """,
            (provider_user_id, user_id, username, display_name, avatar_url, ts, ts),
        )
        ensure_dc_oauth_user_plan(con, user_id, provider_user_id)
        return con.execute("select * from users where id = ?", (user_id,)).fetchone()


def dc_synthetic_email(provider_user_id: str, username: str) -> str:
    cleaned = re.sub(r"[^a-z0-9._+-]+", "-", (username or provider_user_id).strip().lower()).strip(".-")
    cleaned = cleaned[:40] or "user"
    digest = hashlib.sha256(provider_user_id.encode("utf-8")).hexdigest()[:12]
    return f"dc-{cleaned}-{digest}@dc.hhhl.cc"


def ensure_dc_oauth_user_plan(con: sqlite3.Connection, user_id: str, provider_user_id: str | None = None) -> None:
    binding = None
    if provider_user_id:
        binding = con.execute(
            """
            select signup_bonus_applied
            from user_oauth_bindings
            where provider = 'dc.hhhl.cc' and provider_user_id = ?
            """,
            (provider_user_id,),
        ).fetchone()
    if binding and not int(binding["signup_bonus_applied"] or 0):
        user = con.execute("select balance from users where id = ?", (user_id,)).fetchone()
        if user and parse_decimal(user["balance"]) < DC_AUTH_INITIAL_BALANCE:
            con.execute(
                "update users set balance = ? where id = ?",
                (decimal_text(DC_AUTH_INITIAL_BALANCE), user_id),
            )
            if "store_cached_balance" in globals():
                store_cached_balance(user_id, DC_AUTH_INITIAL_BALANCE)
        con.execute(
            """
            update user_oauth_bindings
            set signup_bonus_applied = 1, updated_at = ?
            where provider = 'dc.hhhl.cc' and provider_user_id = ?
            """,
            (now_iso(), provider_user_id),
        )

    con.execute(
        """
        update api_keys
        set billing_group = ?, cost_multiplier = ?
        where user_id = ? and status = 'active'
        """,
        (DC_AUTH_BILLING_GROUP, decimal_text(DC_AUTH_COST_MULTIPLIER), user_id),
    )
    existing = con.execute(
        "select 1 from api_keys where user_id = ? and status = 'active' limit 1",
        (user_id,),
    ).fetchone()
    if existing:
        return
    key = issue_api_key()
    insert_with_next_integer_id(
        con,
        "api_keys",
        {
            "user_id": user_id,
            "key_hash": sha256_key(key),
            "key_value": key,
            "name": DC_AUTH_DEFAULT_KEY_NAME,
            "billing_group": DC_AUTH_BILLING_GROUP,
            "cost_multiplier": decimal_text(DC_AUTH_COST_MULTIPLIER),
            "status": "active",
            "created_at": now_iso(),
        },
    )
    if "invalidate_proxy_context_cache" in globals():
        invalidate_proxy_context_cache(user_id)


def user_api_key_plan(con: sqlite3.Connection, user_id: str) -> dict[str, str]:
    row = con.execute(
        "select 1 from user_oauth_bindings where provider = 'dc.hhhl.cc' and user_id = ?",
        (user_id,),
    ).fetchone()
    if row:
        return {
            "billing_group": DC_AUTH_BILLING_GROUP,
            "cost_multiplier": decimal_text(DC_AUTH_COST_MULTIPLIER),
        }
    return {"billing_group": "default", "cost_multiplier": "1"}


def auth_user_plan(user_id: str) -> dict[str, str]:
    with db() as con:
        return user_api_key_plan(con, user_id)


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
        plan = user_api_key_plan(con, user_id)
        exists = con.execute(
            "select 1 from api_keys where user_id = ? and name = ? and status = 'active'", (user_id, name)
        ).fetchone()
        if exists:
            raise AppError(409, "CONFLICT", "API key name already exists")
        cur = insert_with_next_integer_id(
            con,
            "api_keys",
            {
                "user_id": user_id,
                "key_hash": sha256_key(key),
                "key_value": key,
                "name": name,
                "billing_group": plan["billing_group"],
                "cost_multiplier": plan["cost_multiplier"],
                "status": "active",
                "created_at": now_iso(),
            },
        )
        row = con.execute("select * from api_keys where id = ?", (cur.lastrowid,)).fetchone()
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
    multiplier = parse_decimal(row["cost_multiplier"] if "cost_multiplier" in row.keys() else "1")
    return {
        "id": row["id"],
        "name": row["name"],
        "key": key,
        "status": row["status"],
        "billingGroup": row["billing_group"] if "billing_group" in row.keys() else "default",
        "costMultiplier": float(multiplier),
        "createdAt": row["created_at"],
    }


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
