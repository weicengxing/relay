@app.get("/api/models")
def models() -> dict[str, Any]:
    with db() as con:
        rows = con.execute(
            """
            select * from model_catalog
            where enabled = 1
            order by sort_order, id
            """
        ).fetchall()
    return api_ok([model_to_response(row) for row in rows])


@app.get("/v1/models")
def openai_models() -> dict[str, Any]:
    with db() as con:
        rows = con.execute(
            """
            select * from model_catalog
            where enabled = 1
              and provider = 'OpenAI'
            order by sort_order, id
            """
        ).fetchall()
    return {
        "object": "list",
        "data": [
            {
                "id": row["id"],
                "object": "model",
                "created": 0,
                "owned_by": "relay",
            }
            for row in rows
        ],
    }


@app.post("/v1/chat/completions")
@db_write_api
async def openai_chat_completions(request: Request) -> Response:
    body = await request.body()
    raw_key = bearer_token(request.headers.get("authorization")) or request.headers.get("x-api-key")
    try:
        auth_context = load_cached_api_key_balance(raw_key)
        if auth_context is None:
            auth_context = await run_in_threadpool(load_api_key_balance_sync, raw_key)
        api_key, balance = auth_context
    except AppError as exc:
        return openai_error(exc.status, exc.message)
    if balance < Decimal("0"):
        return openai_error(402, "余额不足")

    try:
        payload = json.loads(body.decode("utf-8") or "{}")
    except Exception:
        return openai_error(400, "Request body must be valid JSON")
    if not isinstance(payload, dict):
        return openai_error(400, "Request body must be a JSON object")

    message = openai_messages_to_text(payload.get("messages"))
    if not message:
        return openai_error(400, "messages is required")
    model = str(payload.get("model") or DEFAULT_WEB_MODEL)
    web_payload = WebChatMessageRequest(
        message=message,
        newConversation=bool(payload.get("new_conversation", True)),
        model=model,
        images=openai_messages_to_images(payload.get("messages")),
    )
    stream = bool(payload.get("stream"))
    if stream:
        return StreamingResponse(
            stream_in_dedicated_thread(
                lambda: openai_chat_completion_stream(api_key["user_id"], web_payload, model),
                name="openai-chat-completion-stream",
            ),
            media_type="text/event-stream",
            headers={"cache-control": "no-cache", "x-accel-buffering": "no"},
        )

    try:
        result = send_web_chat_turn(api_key["user_id"], web_payload, None)
    except Exception as exc:
        message = exc.message if isinstance(exc, AppError) else exception_summary(exc)
        return openai_error(502, message)
    return JSONResponse(openai_chat_completion_response(model, result.get("answer") or ""))


@app.get("/api/announcements")
async def announcements(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    user_id = current_user_id(authorization)
    with db() as con:
        rows = con.execute(
            "select * from announcements where active = 1 order by published_at desc, id desc"
        ).fetchall()
        state = con.execute("select * from announcement_user_state where user_id = ?", (user_id,)).fetchone()
        last_seen = state["last_seen_at"] if state else "1970-01-01T00:00:00Z"
        badge_default = int(setting(con, "announcements.badge_default", "0"))
    items = [announcement_response(row) for row in rows]
    unread = sum(1 for row in rows if row["published_at"] > last_seen)
    return api_ok({"announcements": items, "unreadCount": unread, "badgeCount": max(unread, badge_default)})


@app.post("/api/announcements/read")
@db_write_api
async def mark_announcements_read(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    user_id = current_user_id(authorization)
    ts = now_iso()
    with db() as con:
        con.execute(
            """
            insert into announcement_user_state(user_id, last_seen_at, updated_at) values (?, ?, ?)
            on conflict(user_id) do update set last_seen_at=excluded.last_seen_at, updated_at=excluded.updated_at
            """,
            (user_id, ts, ts),
        )
    return await announcements(authorization)


def announcement_response(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "title": row["title"],
        "content": row["content"],
        "publishedAt": row["published_at"],
    }


@app.post("/api/redeem-codes/redeem")
@db_write_api
def redeem_code(payload: RedeemCodeRequest, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    user_id = current_user_id(authorization)
    code = payload.code.strip()
    with db() as con:
        deduct_expired_redeem_codes(con, user_id)
        row = con.execute("select * from redeem_codes where code = ?", (code,)).fetchone()
        if not row:
            raise AppError(404, "NOT_FOUND", "Redeem code does not exist")
        if row["holder_user_id"]:
            raise AppError(409, "CONFLICT", "Redeem code has already been used")
        if row["expires_at"] <= now_iso():
            raise AppError(400, "VALIDATION_FAILED", "Redeem code has expired")
        amount = parse_decimal(row["amount"])
        balance_value = add_balance(con, user_id, amount)
        con.execute(
            "update redeem_codes set holder_user_id = ?, redeemed_at = ?, updated_at = ? where id = ?",
            (user_id, now_iso(), now_iso(), row["id"]),
        )
    return api_ok({"amount": float(amount), "balance": float(balance_value), "expiresAt": row["expires_at"]})
