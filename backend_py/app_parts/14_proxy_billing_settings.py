@app.api_route("/v1/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
@app.api_route("/backend-api/codex/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
@db_write_api
async def proxy(path: str, request: Request) -> Response:
    body = await request.body()
    event_stream = "text/event-stream" in (request.headers.get("accept") or "")
    raw_key = bearer_token(request.headers.get("authorization")) or request.headers.get("x-api-key")
    try:
        api_key = await run_in_threadpool(authenticate_api_key, raw_key)
    except AppError as exc:
        return local_proxy_error(exc.status, exc.message, event_stream)
    if await run_in_threadpool(user_balance, api_key["user_id"]) < Decimal("0"):
        return local_proxy_error(402, "余额不足", event_stream)
    client_type = detect_client_type(request, body)
    upstreams = await run_in_threadpool(acquire_upstreams, client_type)
    if not upstreams:
        return local_proxy_error(404, "No upstream service configured", event_stream)
    return await proxy_with_body(path, request, body, event_stream, api_key, client_type, upstreams)


async def proxy_with_body(
    path: str,
    request: Request,
    body: bytes,
    event_stream: bool,
    api_key: sqlite3.Row,
    client_type: str,
    upstreams: list[dict[str, Any]],
) -> Response:
    request_uri = request.url.path
    query_string = request.url.query
    started = time.monotonic()
    if client_type == "CODEX" and event_stream:
        return lazy_codex_streaming_response(
            request,
            body,
            api_key,
            client_type,
            upstreams,
            request_uri,
            query_string,
            started,
        )
    client: httpx.AsyncClient | None = httpx.AsyncClient(timeout=None)
    stream: httpx.Response | None = None
    upstream: dict[str, Any] | None = None
    prefetched_body: bytes | None = None
    last_error = "Unable to reach upstream service"
    for index, candidate in enumerate(upstreams):
        try:
            upstream_body = normalize_upstream_body(body, candidate, client_type, event_stream)
            upstream_url = join_upstream_url(upstream_endpoint(candidate), request_uri, query_string)
            headers = build_upstream_headers(request, candidate, client_type, upstream_body)
            upstream_request = client.build_request(request.method, upstream_url, content=upstream_body, headers=headers)
            candidate_stream = await client.send(upstream_request, stream=True)
            if should_inspect_quota_retry(client_type, candidate_stream.status_code):
                candidate_body = await candidate_stream.aread()
                await candidate_stream.aclose()
                if is_retryable_quota_error(candidate_stream.status_code, candidate_body) and index < len(upstreams) - 1:
                    last_error = f"Upstream service {candidate.get('id')} quota limited"
                    continue
                stream = candidate_stream
                upstream = candidate
                prefetched_body = candidate_body
                break
            stream = candidate_stream
            upstream = candidate
            break
        except Exception as exc:
            last_error = exception_summary(exc)
            try:
                if stream is not None:
                    await stream.aclose()
            except Exception:
                pass
            if index < len(upstreams) - 1:
                continue
    if stream is None or upstream is None:
        if client is not None:
            await client.aclose()
        return local_proxy_error(502, last_error, event_stream)
    response_headers = {
        key: value
        for key, value in stream.headers.items()
        if key.lower() not in DROP_RESPONSE_HEADERS
    }
    response_headers["cache-control"] = "no-cache"
    response_headers["x-accel-buffering"] = "no"
    media_type = stream.headers.get("content-type") or ("text/event-stream" if event_stream else "application/json")

    async def generate() -> AsyncIterable[bytes]:
        captured = bytearray()
        first_token_ms = 0
        response_bytes = 0
        saw_first = False
        status_code = stream.status_code
        try:
            async for chunk, from_upstream in async_proxy_chunks(stream, prefetched_body, client_type, media_type):
                if not chunk:
                    continue
                if from_upstream and not saw_first:
                    saw_first = True
                    first_token_ms = int((time.monotonic() - started) * 1000)
                response_bytes += len(chunk)
                if from_upstream and len(captured) < 256 * 1024:
                    captured.extend(chunk[: 256 * 1024 - len(captured)])
                yield chunk
        finally:
            try:
                if prefetched_body is None:
                    await stream.aclose()
                if client is not None:
                    await client.aclose()
            finally:
                use_time_ms = int((time.monotonic() - started) * 1000)
                await run_in_threadpool(
                    record_proxy_request_sync,
                    api_key,
                    client_type,
                    request.method,
                    request_uri,
                    query_string,
                    client_ip(request),
                    request.headers.get("user-agent"),
                    body,
                    bytes(captured),
                    upstream.get("id") if upstream else None,
                    status_code,
                    use_time_ms,
                    first_token_ms or use_time_ms,
                )

    return StreamingResponse(generate(), status_code=stream.status_code, headers=response_headers, media_type=media_type)


CODEX_SSE_KEEPALIVE = b": relay-keepalive\n\n"


def lazy_codex_streaming_response(
    request: Request,
    body: bytes,
    api_key: sqlite3.Row,
    client_type: str,
    upstreams: list[dict[str, Any]],
    request_uri: str,
    query_string: str,
    started: float,
) -> StreamingResponse:
    response_headers = {
        "cache-control": "no-cache",
        "x-accel-buffering": "no",
    }

    async def generate() -> AsyncIterable[bytes]:
        captured = bytearray()
        first_token_ms = 0
        response_bytes = 0
        saw_first = False
        status_code = 502
        upstream: dict[str, Any] | None = None
        stream: httpx.Response | None = None
        client: httpx.AsyncClient | None = httpx.AsyncClient(timeout=None)
        last_error = "Unable to reach upstream service"
        try:
            for index, candidate in enumerate(upstreams):
                send_task: asyncio.Task[httpx.Response] | None = None
                try:
                    upstream_body = normalize_upstream_body(body, candidate, client_type, True)
                    upstream_url = join_upstream_url(upstream_endpoint(candidate), request_uri, query_string)
                    headers = build_upstream_headers(request, candidate, client_type, upstream_body)
                    upstream_request = client.build_request(
                        request.method, upstream_url, content=upstream_body, headers=headers
                    )
                    send_task = asyncio.create_task(client.send(upstream_request, stream=True))
                    while True:
                        done, _ = await asyncio.wait({send_task}, timeout=2.0)
                        if done:
                            stream = send_task.result()
                            status_code = stream.status_code
                            break
                        response_bytes += len(CODEX_SSE_KEEPALIVE)
                        yield CODEX_SSE_KEEPALIVE

                    if should_inspect_quota_retry(client_type, status_code):
                        candidate_body = await stream.aread()
                        await stream.aclose()
                        if is_retryable_quota_error(status_code, candidate_body) and index < len(upstreams) - 1:
                            last_error = f"Upstream service {candidate.get('id')} quota limited"
                            stream = None
                            continue
                        upstream = candidate
                        async for chunk in codex_sse_error_chunks(status_code, candidate_body):
                            response_bytes += len(chunk)
                            if len(captured) < 256 * 1024:
                                captured.extend(chunk[: 256 * 1024 - len(captured)])
                            if not saw_first:
                                saw_first = True
                                first_token_ms = int((time.monotonic() - started) * 1000)
                            yield chunk
                        break

                    upstream = candidate
                    async for chunk, from_upstream in sse_chunks_with_keepalive(stream):
                        if not chunk:
                            continue
                        response_bytes += len(chunk)
                        if from_upstream:
                            if not saw_first:
                                saw_first = True
                                first_token_ms = int((time.monotonic() - started) * 1000)
                            if len(captured) < 256 * 1024:
                                captured.extend(chunk[: 256 * 1024 - len(captured)])
                        yield chunk
                    break
                except Exception as exc:
                    last_error = exception_summary(exc)
                    if send_task is not None and not send_task.done():
                        send_task.cancel()
                        try:
                            await send_task
                        except (asyncio.CancelledError, Exception):
                            pass
                    if stream is not None:
                        await stream.aclose()
                        stream = None
                    if index < len(upstreams) - 1:
                        continue
                    chunk = codex_sse_error_bytes(last_error)
                    response_bytes += len(chunk)
                    captured.extend(chunk[: 256 * 1024 - len(captured)])
                    yield chunk
        finally:
            try:
                if stream is not None:
                    await stream.aclose()
                if client is not None:
                    await client.aclose()
            finally:
                use_time_ms = int((time.monotonic() - started) * 1000)
                await run_in_threadpool(
                    record_proxy_request_sync,
                    api_key,
                    client_type,
                    request.method,
                    request_uri,
                    query_string,
                    client_ip(request),
                    request.headers.get("user-agent"),
                    body,
                    bytes(captured),
                    upstream.get("id") if upstream else None,
                    status_code,
                    use_time_ms,
                    first_token_ms or use_time_ms,
                )

    return StreamingResponse(generate(), status_code=200, headers=response_headers, media_type="text/event-stream")


async def codex_sse_error_chunks(status_code: int, body: bytes) -> AsyncIterable[bytes]:
    message = f"Upstream returned HTTP {status_code}"
    if body:
        message = f"{message}: {truncate(body.decode('utf-8', 'replace'), 2000)}"
    yield codex_sse_error_bytes(message)


def codex_sse_error_bytes(message: str) -> bytes:
    body = {"error": {"message": message, "type": "relay_error", "code": "relay_error"}}
    return f"event: error\ndata: {json.dumps(body, ensure_ascii=False, separators=(',', ':'))}\n\n".encode()


async def async_proxy_chunks(
    stream: httpx.Response,
    prefetched_body: bytes | None,
    client_type: str,
    media_type: str,
) -> AsyncIterable[tuple[bytes, bool]]:
    if prefetched_body is not None:
        yield prefetched_body, True
        return
    if client_type == "CODEX" and "text/event-stream" in (media_type or "").lower():
        async for item in sse_chunks_with_keepalive(stream):
            yield item
        return
    async for chunk in stream.aiter_bytes():
        yield chunk, True


async def sse_chunks_with_keepalive(stream: httpx.Response) -> AsyncIterable[tuple[bytes, bool]]:
    interval_seconds = 2.0
    iterator = stream.aiter_bytes().__aiter__()
    next_chunk = asyncio.create_task(iterator.__anext__())
    try:
        while True:
            done, _ = await asyncio.wait({next_chunk}, timeout=interval_seconds)
            if not done:
                yield CODEX_SSE_KEEPALIVE, False
                continue
            try:
                chunk = next_chunk.result()
            except StopAsyncIteration:
                break
            yield chunk, True
            next_chunk = asyncio.create_task(iterator.__anext__())
    finally:
        if not next_chunk.done():
            next_chunk.cancel()
            try:
                await next_chunk
            except (asyncio.CancelledError, StopAsyncIteration):
                pass


def authenticate_api_key(key: str | None) -> sqlite3.Row:
    if not key or not key.startswith("relay_"):
        raise AppError(401, "UNAUTHORIZED", "Invalid API key")
    with db() as con:
        row = con.execute(
            "select * from api_keys where key_hash = ? and status = 'active'", (sha256_key(key),)
        ).fetchone()
    if not row:
        raise AppError(401, "UNAUTHORIZED", "Invalid API key")
    return row


def user_balance(user_id: str) -> Decimal:
    with db() as con:
        deduct_expired_redeem_codes(con, user_id)
        row = con.execute("select balance from users where id = ?", (user_id,)).fetchone()
    return parse_decimal(row["balance"]) if row else Decimal("-1")


def detect_client_type(request: Request, body: bytes) -> str:
    path = request.url.path.lower()
    headers = " ".join([request.headers.get("user-agent", ""), request.headers.get("originator", "")]).lower()
    body_text = body[:4096].decode("utf-8", "ignore").lower()
    if path.startswith("/backend-api/codex") or "codex" in headers or "codex" in body_text:
        return "CODEX"
    if "anthropic" in path or "claude" in headers or "claude" in body_text:
        return "CLAUDE"
    return "CODEX"


def acquire_upstreams(client_type: str) -> list[dict[str, Any]]:
    with db() as con:
        if client_type == "CLAUDE":
            rows = con.execute("select * from claude_services order by id").fetchall()
            return [row_to_dict(row) for row in rows]
        mode = int(setting(con, "openai.request_mode", "2"))
        if mode == 2:
            rows = con.execute(
                """
                select s.*, p.profile_name, p.auth_mode, p.openai_api_key, p.access_token,
                       p.account_id, p.base_url as profile_base_url, p.model, p.reasoning_effort
                from openai_services s
                join openai_codex_profiles p on p.openai_service_id = s.id
                order by s.id
                """
            ).fetchall()
        else:
            rows = con.execute("select * from openai_services order by id").fetchall()
        return [row_to_dict(row) for row in rows]


def upstream_endpoint(upstream: dict[str, Any]) -> str:
    return first_non_blank(upstream.get("profile_base_url"), upstream.get("api_endpoint"), "https://chatgpt.com/backend-api/codex")


def should_inspect_quota_retry(client_type: str, status_code: int) -> bool:
    return client_type == "CODEX" and status_code in {402, 403, 429}


def is_retryable_quota_error(status_code: int, body: bytes | None) -> bool:
    if status_code not in {402, 403, 429}:
        return False
    if not body:
        return status_code == 402
    text = body.decode("utf-8", "ignore").lower()
    markers = [
        "insufficient_quota",
        "rate_limit_exceeded",
        "quota",
        "billing",
        "credit",
        "balance",
        "rate limit",
        "额度",
        "配额",
        "余额",
        "棰濆害",
        "閰嶉",
        "浣欓",
    ]
    return any(marker in text for marker in markers)


def build_upstream_headers(request: Request, upstream: dict[str, Any], client_type: str, body: bytes) -> dict[str, str]:
    if client_type == "CODEX":
        accept = request.headers.get("accept")
        headers = {
            "accept": "text/event-stream" if not accept or b'"stream":true' in body else accept,
            "content-type": "application/json",
            "originator": "codex_cli_rs",
            "user-agent": "codex_cli_rs/0.126.0 (Windows 10; x86_64)",
            "version": "0.126.0",
        }
        token = first_non_blank(upstream.get("access_token"), upstream.get("openai_api_key"), upstream.get("token"))
        if token:
            headers["authorization"] = "Bearer " + clean_bearer(token)
        if upstream.get("account_id"):
            headers["ChatGPT-Account-ID"] = upstream["account_id"]
        return headers
    headers = {k: v for k, v in request.headers.items() if k.lower() not in DROP_REQUEST_HEADERS}
    token = clean_bearer(upstream.get("token") or "")
    headers["x-api-key"] = token
    if "token-plan-cn.xiaomimimo.com" in (upstream.get("api_endpoint") or "").lower():
        headers["authorization"] = "Bearer " + token
    return headers


def normalize_upstream_body(body: bytes, upstream: dict[str, Any], client_type: str, event_stream: bool) -> bytes:
    if not body:
        return body
    try:
        root = json.loads(body)
        if not isinstance(root, dict):
            return body
        if client_type == "CODEX":
            if upstream.get("profile_name"):
                if not root.get("model") and upstream.get("model"):
                    root["model"] = upstream["model"]
                root.setdefault("store", False)
                root.setdefault("parallel_tool_calls", True)
                effort = root.pop("reasoning_effort", None) or upstream.get("reasoning_effort")
                if effort and "reasoning" not in root:
                    root["reasoning"] = {"effort": effort}
            if event_stream:
                root["stream"] = True
            if "chatgpt.com/backend-api/codex" in upstream_endpoint(upstream).lower():
                root.pop("truncation", None)
        elif client_type == "CLAUDE" and "token-plan-cn.xiaomimimo.com" in upstream_endpoint(upstream).lower():
            if isinstance(root.get("model"), str):
                root["model"] = root["model"].lower()
        return json.dumps(root, ensure_ascii=False, separators=(",", ":")).encode()
    except Exception:
        return body


def join_upstream_url(base_url: str, request_uri: str, query: str) -> str:
    base = trim_slash(base_url)
    suffix = request_uri
    if suffix.startswith("/v1"):
        suffix = suffix[len("/v1") :]
    elif suffix.startswith("/backend-api/codex"):
        suffix = suffix[len("/backend-api/codex") :]
    target = base + suffix
    return target + ("?" + query if query else "")


def local_proxy_error(status: int, message: str, event_stream: bool) -> Response:
    body = {"error": {"message": message, "type": "relay_error", "code": "relay_error"}}
    if event_stream:
        return Response(
            content=sse_event("error", body),
            status_code=status,
            media_type="text/event-stream",
            headers={"cache-control": "no-cache", "x-accel-buffering": "no"},
        )
    return JSONResponse(status_code=status, content=body)


def record_proxy_request_sync(
    api_key: sqlite3.Row,
    client_type: str,
    request_method: str,
    request_uri: str,
    query_string: str,
    ip: str | None,
    user_agent: str | None,
    request_body: bytes,
    response_body: bytes,
    upstream_service_id: int | None,
    status_code: int,
    use_time_ms: int,
    first_token_ms: int,
) -> None:
    usage = parse_usage(request_body, response_body)
    with db() as con:
        price = con.execute("select * from model_catalog where id = ? and enabled = 1", (usage["model"],)).fetchone()
        cost = calculate_cost(con, usage, price)
        con.execute(
            """
            insert into request_logs
              (user_id, api_key_id, token_name, group_key, request_type, client_type, model,
               use_time_ms, first_token_ms, prompt_tokens, completion_tokens, cache_read_tokens,
               cache_creation_tokens, cost, ip, status, upstream_service_id, detail, created_at)
            values (?, ?, ?, ?, 'usage', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                api_key["user_id"],
                api_key["id"],
                api_key["name"] or display_key(api_key["key_hash"]),
                api_key["key_value"] or display_key(api_key["key_hash"]),
                client_type,
                usage["model"],
                use_time_ms,
                first_token_ms,
                usage["input"],
                usage["output"],
                usage["cache_read"],
                usage["cache_create"],
                decimal_text(cost),
                ip,
                "success" if 200 <= status_code < 300 else "error",
                upstream_service_id,
                response_body.decode("utf-8", "replace"),
                now_iso(),
            ),
        )
        if cost > 0:
            add_balance(con, api_key["user_id"], -cost)


def parse_usage(request_body: bytes, response_body: bytes) -> dict[str, Any]:
    texts = [response_body.decode("utf-8", "ignore"), request_body.decode("utf-8", "ignore")]
    payloads = []
    for text in texts:
        payloads.extend(parse_json_payloads(text))
    model = None
    input_tokens = output_tokens = cache_read = cache_create = 0
    for payload in payloads:
        usage = usage_from_payload(payload)
        model = first_non_blank(model, usage.get("model"))
        input_tokens = input_tokens or usage.get("input", 0)
        output_tokens = output_tokens or usage.get("output", 0)
        cache_read = cache_read or usage.get("cache_read", 0)
        cache_create = cache_create or usage.get("cache_create", 0)
    for text in texts:
        model = first_non_blank(model, regex_first(text, MODEL_RE), regex_first(text, NAME_RE))
    return {"model": model, "input": input_tokens, "output": output_tokens, "cache_read": cache_read, "cache_create": cache_create}


def parse_json_payloads(text: str) -> list[Any]:
    text = text.strip()
    if not text:
        return []
    if text.startswith("{") or text.startswith("["):
        try:
            return [json.loads(text)]
        except Exception:
            return []
    payloads = []
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("data:"):
            data = line[5:].strip()
            if data and data != "[DONE]":
                try:
                    payloads.append(json.loads(data))
                except Exception:
                    pass
    return payloads


def usage_from_payload(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    response = payload.get("response") if isinstance(payload.get("response"), dict) else {}
    message = payload.get("message") if isinstance(payload.get("message"), dict) else {}
    usage = response.get("usage") or payload.get("usage") or message.get("usage") or {}
    if not isinstance(usage, dict):
        usage = {}
    return {
        "model": first_non_blank(response.get("model"), payload.get("model"), message.get("model")),
        "input": int_first(usage, ["input_tokens", "prompt_tokens", "inputTokens", "promptTokens"]),
        "output": int_first(usage, ["output_tokens", "completion_tokens", "outputTokens", "completionTokens"]),
        "cache_read": int_first_nested(usage, ["cache_read_input_tokens", "cache_read_tokens"], ["input_tokens_details", "prompt_tokens_details"], "cached_tokens"),
        "cache_create": int_first_nested(usage, ["cache_creation_input_tokens", "cache_creation_tokens"], ["input_tokens_details", "prompt_tokens_details"], "cache_creation_tokens"),
    }


def calculate_cost(con: sqlite3.Connection, usage: dict[str, Any], price: sqlite3.Row | None) -> Decimal:
    if not price:
        return Decimal("0.000000")
    regular_input = max(0, usage["input"] - usage["cache_read"] - usage["cache_create"])
    cost = (
        parse_decimal(price["input_price"]) * regular_input
        + parse_decimal(price["output_price"]) * usage["output"]
        + parse_decimal(price["cached_input_price"]) * usage["cache_read"]
        + parse_decimal(price["cache_creation_price"]) * usage["cache_create"]
    ) / Decimal(1_000_000)
    multiplier = parse_decimal(setting(con, "billing.cost_multiplier", "1.2"))
    return (cost * multiplier).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)


def add_balance(con: sqlite3.Connection, user_id: str, amount: Decimal) -> Decimal:
    row = con.execute("select balance from users where id = ?", (user_id,)).fetchone()
    if not row:
        raise AppError(401, "UNAUTHORIZED", "Unauthorized")
    next_balance = parse_decimal(row["balance"]) + amount
    con.execute("update users set balance = ? where id = ?", (decimal_text(next_balance), user_id))
    return next_balance


def deduct_expired_redeem_codes(con: sqlite3.Connection, user_id: str) -> Decimal | None:
    ts = now_iso()
    rows = con.execute(
        """
        select * from redeem_codes
        where holder_user_id = ?
          and expired_deducted_at is null
          and expires_at <= ?
        order by expires_at, id
        """,
        (user_id, ts),
    ).fetchall()
    balance_value: Decimal | None = None
    for row in rows:
        balance_value = add_balance(con, user_id, -parse_decimal(row["amount"]))
        con.execute(
            """
            update redeem_codes
            set expired_deducted_at = ?, updated_at = ?
            where id = ? and expired_deducted_at is null
            """,
            (ts, ts, row["id"]),
        )
    return balance_value


def setting(con: sqlite3.Connection, key: str, default: str) -> str:
    row = con.execute("select setting_value from app_settings where setting_key = ?", (key,)).fetchone()
    return row["setting_value"] if row else default


def bool_setting(con: sqlite3.Connection, key: str, default: bool) -> bool:
    raw = setting(con, key, "true" if default else "false")
    return str(raw).strip().lower() not in {"0", "false", "no", "off", ""}


def turnstile_enabled() -> bool:
    try:
        with db() as con:
            return bool_setting(con, "auth.turnstile_enabled", True)
    except sqlite3.Error:
        return True


def recharge_payment_settings() -> dict[str, str]:
    try:
        with db() as con:
            return {
                "alipayQrImage": setting(con, "recharge.alipay_qr_image", ""),
                "wechatQrImage": setting(con, "recharge.wechat_qr_image", ""),
            }
    except sqlite3.Error:
        return {"alipayQrImage": "", "wechatQrImage": ""}


def setting_image_dir() -> Path:
    return ROOT.parent / "frontend" / "public" / "uploads" / "settings"


def setting_image_path_from_url(value: str) -> Path | None:
    prefix = "/uploads/settings/"
    if not value.startswith(prefix):
        return None
    path = (setting_image_dir() / value[len(prefix) :]).resolve()
    upload_root = setting_image_dir().resolve()
    try:
        path.relative_to(upload_root)
    except ValueError:
        return None
    return path


def delete_setting_image(value: str) -> None:
    path = setting_image_path_from_url(value)
    if path and path.exists() and path.is_file():
        try:
            path.unlink()
        except OSError:
            pass


def save_setting_image(file_name: str, data_url: str, setting_key: str) -> str:
    match = re.match(r"^data:(image/(?:png|jpeg|jpg|webp|gif));base64,(.+)$", data_url or "", re.I | re.S)
    if not match:
        raise AppError(400, "VALIDATION_FAILED", "Image must be a PNG, JPG, WebP, or GIF data URL")
    media_type = match.group(1).lower()
    extension = {
        "image/png": "png",
        "image/jpeg": "jpg",
        "image/jpg": "jpg",
        "image/webp": "webp",
        "image/gif": "gif",
    }[media_type]
    try:
        image_bytes = base64.b64decode(match.group(2), validate=True)
    except Exception as exc:
        raise AppError(400, "VALIDATION_FAILED", "Invalid image data") from exc
    if not image_bytes:
        raise AppError(400, "VALIDATION_FAILED", "Image is empty")
    if len(image_bytes) > 5 * 1024 * 1024:
        raise AppError(400, "VALIDATION_FAILED", "Image must be 5 MB or smaller")

    safe_stem = re.sub(r"[^a-zA-Z0-9_-]+", "-", setting_key).strip("-")[:80]
    if not safe_stem:
        safe_stem = "setting-image"
    upload_dir = setting_image_dir()
    upload_dir.mkdir(parents=True, exist_ok=True)
    for old_file in upload_dir.glob(f"{safe_stem}.*"):
        if old_file.is_file():
            try:
                old_file.unlink()
            except OSError:
                pass
    target = upload_dir / f"{safe_stem}.{extension}"
    target.write_bytes(image_bytes)
    return f"/uploads/settings/{target.name}"


def verify_turnstile(token: str | None, request: Request) -> None:
    if not turnstile_enabled():
        return
    token = (token or "").strip()
    if not token or len(token) > 2048:
        raise AppError(400, "TURNSTILE_REQUIRED", "Human verification is required")
    if not TURNSTILE_SECRET.strip():
        raise AppError(500, "TURNSTILE_NOT_CONFIGURED", "Turnstile is not configured")

    body = {
        "secret": TURNSTILE_SECRET,
        "response": token,
    }
    ip = client_ip(request)
    if ip:
        body["remoteip"] = ip

    try:
        with httpx.Client(timeout=10) as client:
            response = client.post(TURNSTILE_VERIFY_URL, data=body)
            response.raise_for_status()
            payload = response.json()
    except Exception as exc:
        raise AppError(400, "TURNSTILE_FAILED", "Human verification failed") from exc

    if not payload.get("success"):
        raise AppError(400, "TURNSTILE_FAILED", "Human verification failed", payload.get("error-codes"))


def regex_first(text: str, pattern: re.Pattern[str]) -> str | None:
    match = pattern.search(text or "")
    return match.group(1) if match else None


def int_first(data: dict[str, Any], keys: list[str]) -> int:
    for key in keys:
        if key in data:
            try:
                return max(0, int(data[key]))
            except Exception:
                pass
    return 0


def int_first_nested(data: dict[str, Any], direct_keys: list[str], object_keys: list[str], nested_key: str) -> int:
    direct = int_first(data, direct_keys)
    if direct:
        return direct
    for object_key in object_keys:
        child = data.get(object_key)
        if isinstance(child, dict) and nested_key in child:
            try:
                return max(0, int(child[nested_key]))
            except Exception:
                pass
    return 0


def clean_bearer(token: str) -> str:
    token = token.strip()
    return token[7:].strip() if token.lower().startswith("bearer ") else token


def client_ip(request: Request) -> str | None:
    for header in ["cf-connecting-ip", "x-forwarded-for", "x-real-ip"]:
        value = request.headers.get(header)
        if value:
            return value.split(",")[0].strip()
    return request.client.host if request.client else None


def trim_slash(value: str) -> str:
    return value.rstrip("/")


def truncate(value: str, max_len: int) -> str:
    return value if len(value) <= max_len else value[:max_len] + "..."


def exception_summary(exc: Exception) -> str:
    message = str(exc) or exc.__class__.__name__
    return truncate(message, 180)
