@app.api_route("/v1/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
@app.api_route("/backend-api/codex/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
@db_write_api
async def proxy(path: str, request: Request) -> Response:
    body = await request.body()
    event_stream = "text/event-stream" in (request.headers.get("accept") or "")
    raw_key = bearer_token(request.headers.get("authorization")) or request.headers.get("x-api-key")
    client_type = detect_client_type(request, body)
    try:
        context = load_cached_proxy_context(raw_key, client_type)
        if context is None:
            context = await run_in_threadpool(load_proxy_context_sync, raw_key, client_type)
    except AppError as exc:
        return local_proxy_error(exc.status, exc.message, event_stream)
    if context.balance < Decimal("0"):
        return local_proxy_error(402, "余额不足", event_stream)
    if not context.upstreams:
        return local_proxy_error(404, "No upstream service configured", event_stream)
    return await proxy_with_body(path, request, body, event_stream, context.api_key, client_type, context.upstreams)


CODEX_CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
CODEX_REFRESH_TOKEN_URL = "https://auth.openai.com/oauth/token"
codex_proxy_logger = logging.getLogger("relay.codex_proxy")
_codex_refresh_lock = threading.Lock()
_codex_default_instructions_cache: tuple[float, str | None] | None = None
PROXY_API_KEY_CACHE_TTL = float(os.getenv("RELAY_PY_PROXY_API_KEY_CACHE_TTL", "3"))
PROXY_UPSTREAM_CACHE_TTL = float(os.getenv("RELAY_PY_PROXY_UPSTREAM_CACHE_TTL", "5"))
PROXY_BALANCE_CACHE_TTL = float(os.getenv("RELAY_PY_PROXY_BALANCE_CACHE_TTL", "1"))
PROXY_BILLING_CACHE_TTL = float(os.getenv("RELAY_PY_PROXY_BILLING_CACHE_TTL", "30"))
PROXY_EXPIRED_REDEEM_CHECK_TTL = float(os.getenv("RELAY_PY_PROXY_EXPIRED_REDEEM_CHECK_TTL", "30"))
PROXY_LOG_BATCH_SIZE = int(os.getenv("RELAY_PY_PROXY_LOG_BATCH_SIZE", "100"))
PROXY_LOG_FLUSH_INTERVAL = float(os.getenv("RELAY_PY_PROXY_LOG_FLUSH_INTERVAL", "0.05"))

_proxy_cache_lock = threading.Lock()
_api_key_cache: dict[str, tuple[float, dict[str, Any]]] = {}
_upstream_cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}
_balance_cache: dict[str, tuple[float, Decimal]] = {}
_expired_redeem_check_cache: dict[str, float] = {}
_billing_catalog_cache: tuple[float, dict[str, dict[str, Any]], Decimal] | None = None
_upstream_limiter_lock = threading.Lock()
_upstream_limiters: dict[tuple[str, int, int], "UpstreamLimiter"] = {}
_upstream_client_lock = threading.Lock()
_shared_upstream_clients: dict[tuple[str, int], httpx.AsyncClient] = {}
_shared_upstream_client_ids: set[int] = set()


@dataclass
class ProxyContext:
    api_key: dict[str, Any]
    balance: Decimal
    upstreams: list[dict[str, Any]]


@dataclass
class ProxyLogEvent:
    api_key: dict[str, Any]
    client_type: str
    request_method: str
    request_uri: str
    query_string: str
    ip: str | None
    user_agent: str | None
    request_body: bytes
    response_body: bytes
    upstream_service_id: int | None
    status_code: int
    use_time_ms: int
    first_token_ms: int
    created_at: str


@dataclass
class UpstreamLimiter:
    limit: int
    active: int = 0


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
    client: httpx.AsyncClient | None = open_upstream_client(client_type)
    stream: httpx.Response | None = None
    upstream: dict[str, Any] | None = None
    upstream_limiter: UpstreamLimiter | None = None
    prefetched_body: bytes | None = None
    last_error = "Unable to reach upstream service"
    for index, candidate in enumerate(upstreams):
        candidate_limiter: UpstreamLimiter | None = None
        try:
            upstream_body = normalize_upstream_body(body, candidate, client_type, event_stream)
            upstream_url = join_upstream_url(upstream_endpoint(candidate), request_uri, query_string)
            headers = build_upstream_headers(request, candidate, client_type, upstream_body)
            upstream_request = client.build_request(request.method, upstream_url, content=upstream_body, headers=headers)
            candidate_limiter = acquire_upstream_slot(client_type, candidate)
            if candidate_limiter is None:
                last_error = f"Upstream service {candidate.get('id')} is busy"
                continue
            candidate_stream = await client.send(upstream_request, stream=True)
            refreshed_stream = await retry_codex_after_refresh(
                client, request.method, upstream_url, upstream_body, candidate, client_type, candidate_stream
            )
            if refreshed_stream is not candidate_stream:
                candidate_stream = refreshed_stream
            if should_inspect_quota_retry(client_type, candidate_stream.status_code):
                candidate_body = await candidate_stream.aread()
                await candidate_stream.aclose()
                if is_retryable_quota_error(candidate_stream.status_code, candidate_body) and index < len(upstreams) - 1:
                    last_error = f"Upstream service {candidate.get('id')} quota limited"
                    release_upstream_slot(candidate_limiter)
                    candidate_limiter = None
                    continue
                stream = candidate_stream
                upstream = candidate
                upstream_limiter = candidate_limiter
                candidate_limiter = None
                prefetched_body = candidate_body
                break
            stream = candidate_stream
            upstream = candidate
            upstream_limiter = candidate_limiter
            candidate_limiter = None
            break
        except Exception as exc:
            last_error = exception_summary(exc)
            try:
                if stream is not None:
                    await stream.aclose()
            except Exception:
                pass
            release_upstream_slot(candidate_limiter)
            if index < len(upstreams) - 1:
                continue
    if stream is None or upstream is None:
        await close_upstream_client(client)
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
                try:
                    if prefetched_body is None:
                        await stream.aclose()
                    await close_upstream_client(client)
                finally:
                    release_upstream_slot(upstream_limiter)
            finally:
                use_time_ms = int((time.monotonic() - started) * 1000)
                enqueue_proxy_log_event(
                    ProxyLogEvent(
                        api_key=dict(api_key),
                        client_type=client_type,
                        request_method=request.method,
                        request_uri=request_uri,
                        query_string=query_string,
                        ip=client_ip(request),
                        user_agent=request.headers.get("user-agent"),
                        request_body=body,
                        response_body=bytes(captured),
                        upstream_service_id=upstream.get("id") if upstream else None,
                        status_code=status_code,
                        use_time_ms=use_time_ms,
                        first_token_ms=first_token_ms or use_time_ms,
                        created_at=now_iso(),
                    )
                )

    return StreamingResponse(generate(), status_code=stream.status_code, headers=response_headers, media_type=media_type)


CODEX_SSE_KEEPALIVE = b": relay-keepalive\n\n"


async def discard_task_exception(task: asyncio.Task[Any] | None) -> None:
    if task is None:
        return
    if not task.done():
        task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    except Exception:
        pass


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
        upstream_limiter: UpstreamLimiter | None = None
        client: httpx.AsyncClient | None = open_upstream_client(client_type)
        last_error = "Unable to reach upstream service"
        send_task: asyncio.Task[httpx.Response] | None = None
        try:
            for index, candidate in enumerate(upstreams):
                candidate_limiter: UpstreamLimiter | None = None
                try:
                    upstream_body = normalize_upstream_body(body, candidate, client_type, True)
                    upstream_url = join_upstream_url(upstream_endpoint(candidate), request_uri, query_string)
                    headers = build_upstream_headers(request, candidate, client_type, upstream_body)
                    upstream_request = client.build_request(
                        request.method, upstream_url, content=upstream_body, headers=headers
                    )
                    candidate_limiter = acquire_upstream_slot(client_type, candidate)
                    if candidate_limiter is None:
                        last_error = f"Upstream service {candidate.get('id')} is busy"
                        continue
                    send_task = asyncio.create_task(client.send(upstream_request, stream=True))
                    stream = await send_task
                    send_task = None
                    refreshed_stream = await retry_codex_after_refresh(
                        client, request.method, upstream_url, upstream_body, candidate, client_type, stream
                    )
                    if refreshed_stream is not stream:
                        stream = refreshed_stream
                    status_code = stream.status_code

                    if should_inspect_quota_retry(client_type, status_code):
                        candidate_body = await stream.aread()
                        await stream.aclose()
                        if is_retryable_quota_error(status_code, candidate_body) and index < len(upstreams) - 1:
                            last_error = f"Upstream service {candidate.get('id')} quota limited"
                            stream = None
                            release_upstream_slot(candidate_limiter)
                            candidate_limiter = None
                            continue
                        upstream = candidate
                        upstream_limiter = candidate_limiter
                        candidate_limiter = None
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
                    upstream_limiter = candidate_limiter
                    candidate_limiter = None
                    async for chunk in stream.aiter_bytes():
                        if not chunk:
                            continue
                        response_bytes += len(chunk)
                        if not saw_first:
                            saw_first = True
                            first_token_ms = int((time.monotonic() - started) * 1000)
                        if len(captured) < 256 * 1024:
                            captured.extend(chunk[: 256 * 1024 - len(captured)])
                        yield chunk
                    break
                except Exception as exc:
                    last_error = exception_summary(exc)
                    await discard_task_exception(send_task)
                    send_task = None
                    try:
                        if stream is not None:
                            await stream.aclose()
                            stream = None
                    finally:
                        release_upstream_slot(candidate_limiter)
                    if index < len(upstreams) - 1:
                        continue
                    chunk = codex_sse_error_bytes(last_error)
                    response_bytes += len(chunk)
                    captured.extend(chunk[: 256 * 1024 - len(captured)])
                    yield chunk
        finally:
            try:
                try:
                    await discard_task_exception(send_task)
                    if stream is not None:
                        await stream.aclose()
                    await close_upstream_client(client)
                finally:
                    release_upstream_slot(upstream_limiter)
            finally:
                use_time_ms = int((time.monotonic() - started) * 1000)
                enqueue_proxy_log_event(
                    ProxyLogEvent(
                        api_key=dict(api_key),
                        client_type=client_type,
                        request_method=request.method,
                        request_uri=request_uri,
                        query_string=query_string,
                        ip=client_ip(request),
                        user_agent=request.headers.get("user-agent"),
                        request_body=body,
                        response_body=bytes(captured),
                        upstream_service_id=upstream.get("id") if upstream else None,
                        status_code=status_code,
                        use_time_ms=use_time_ms,
                        first_token_ms=first_token_ms or use_time_ms,
                        created_at=now_iso(),
                    )
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
            except (asyncio.CancelledError, StopAsyncIteration, Exception):
                pass


def invalidate_proxy_context_cache(user_id: str | None = None) -> None:
    global _billing_catalog_cache
    with _proxy_cache_lock:
        if user_id is None:
            _api_key_cache.clear()
            _upstream_cache.clear()
            _balance_cache.clear()
            _expired_redeem_check_cache.clear()
            _billing_catalog_cache = None
        else:
            _balance_cache.pop(user_id, None)
            _expired_redeem_check_cache.pop(user_id, None)


def cached_api_key(key_hash: str, now: float) -> dict[str, Any] | None:
    with _proxy_cache_lock:
        cached = _api_key_cache.get(key_hash)
        if cached and cached[0] > now:
            return dict(cached[1])
    return None


def store_cached_api_key(key_hash: str, api_key: dict[str, Any], now: float) -> None:
    with _proxy_cache_lock:
        _api_key_cache[key_hash] = (now + PROXY_API_KEY_CACHE_TTL, dict(api_key))


def cached_upstreams(client_type: str, now: float) -> list[dict[str, Any]] | None:
    with _proxy_cache_lock:
        cached = _upstream_cache.get(client_type)
        if cached and cached[0] > now:
            return [dict(item) for item in cached[1]]
    return None


def store_cached_upstreams(client_type: str, upstreams: list[dict[str, Any]], now: float) -> None:
    with _proxy_cache_lock:
        _upstream_cache[client_type] = (now + PROXY_UPSTREAM_CACHE_TTL, [dict(item) for item in upstreams])


def cached_balance(user_id: str, now: float) -> Decimal | None:
    with _proxy_cache_lock:
        cached = _balance_cache.get(user_id)
        if cached and cached[0] > now:
            return cached[1]
    return None


def store_cached_balance(user_id: str, balance: Decimal, now: float | None = None) -> None:
    with _proxy_cache_lock:
        _balance_cache[user_id] = ((now or time.monotonic()) + PROXY_BALANCE_CACHE_TTL, balance)


def expired_redeem_check_due(user_id: str, now: float) -> bool:
    with _proxy_cache_lock:
        return _expired_redeem_check_cache.get(user_id, 0) <= now


def should_check_expired_redeems(user_id: str, now: float) -> bool:
    with _proxy_cache_lock:
        next_check = _expired_redeem_check_cache.get(user_id, 0)
        if next_check > now:
            return False
        _expired_redeem_check_cache[user_id] = now + PROXY_EXPIRED_REDEEM_CHECK_TTL
        return True


def load_upstreams_from_connection(con: sqlite3.Connection, client_type: str) -> list[dict[str, Any]]:
    if client_type == "CLAUDE":
        rows = con.execute("select * from claude_services order by id").fetchall()
        return [row_to_dict(row) for row in rows]
    mode = int(setting(con, "openai.request_mode", "2"))
    if mode == 2:
        rows = con.execute(
            """
            select s.*, p.profile_name, p.auth_mode, p.openai_api_key, p.access_token,
                   p.account_id, p.id_token, p.refresh_token, p.client_id,
                   p.base_url as profile_base_url, p.model, p.reasoning_effort
            from openai_services s
            join openai_codex_profiles p on p.openai_service_id = s.id
            order by s.id
            """
        ).fetchall()
    else:
        rows = con.execute("select * from openai_services order by id").fetchall()
    return [row_to_dict(row) for row in rows]


def load_cached_proxy_context(key: str | None, client_type: str) -> ProxyContext | None:
    if not key or not key.startswith("relay_"):
        raise AppError(401, "UNAUTHORIZED", "Invalid API key")
    key_hash = sha256_key(key)
    now = time.monotonic()
    api_key = cached_api_key(key_hash, now)
    if api_key is None:
        return None
    if expired_redeem_check_due(api_key["user_id"], now):
        return None
    balance = cached_balance(api_key["user_id"], now)
    if balance is None:
        return None
    upstreams = cached_upstreams(client_type, now)
    if upstreams is None:
        return None
    return ProxyContext(api_key=api_key, balance=balance, upstreams=upstreams)


def load_cached_api_key_balance(key: str | None) -> tuple[dict[str, Any], Decimal] | None:
    if not key or not key.startswith("relay_"):
        raise AppError(401, "UNAUTHORIZED", "Invalid API key")
    now = time.monotonic()
    api_key = cached_api_key(sha256_key(key), now)
    if api_key is None:
        return None
    if expired_redeem_check_due(api_key["user_id"], now):
        return None
    balance = cached_balance(api_key["user_id"], now)
    if balance is None:
        return None
    return api_key, balance


def load_api_key_balance_sync(key: str | None) -> tuple[dict[str, Any], Decimal]:
    if not key or not key.startswith("relay_"):
        raise AppError(401, "UNAUTHORIZED", "Invalid API key")
    key_hash = sha256_key(key)
    now = time.monotonic()
    api_key = cached_api_key(key_hash, now)
    check_expired = False
    balance: Decimal | None = None
    if api_key is not None:
        check_expired = should_check_expired_redeems(api_key["user_id"], now)
        if not check_expired:
            balance = cached_balance(api_key["user_id"], now)

    with db() as con:
        if api_key is None:
            row = con.execute(
                "select * from api_keys where key_hash = ? and status = 'active'",
                (key_hash,),
            ).fetchone()
            if not row:
                raise AppError(401, "UNAUTHORIZED", "Invalid API key")
            api_key = row_to_dict(row)
            store_cached_api_key(key_hash, api_key, now)
            check_expired = should_check_expired_redeems(api_key["user_id"], now)

        if check_expired:
            deduct_expired_redeem_codes(con, api_key["user_id"])
        if balance is None or check_expired:
            balance_row = con.execute("select balance from users where id = ?", (api_key["user_id"],)).fetchone()
            balance = parse_decimal(balance_row["balance"]) if balance_row else Decimal("-1")
            store_cached_balance(api_key["user_id"], balance, now)

    return dict(api_key), balance


def load_proxy_context_sync(key: str | None, client_type: str) -> ProxyContext:
    if not key or not key.startswith("relay_"):
        raise AppError(401, "UNAUTHORIZED", "Invalid API key")
    key_hash = sha256_key(key)
    now = time.monotonic()
    api_key = cached_api_key(key_hash, now)
    upstreams = cached_upstreams(client_type, now)
    balance: Decimal | None = None
    check_expired = False
    if api_key is not None:
        check_expired = should_check_expired_redeems(api_key["user_id"], now)
        if not check_expired:
            balance = cached_balance(api_key["user_id"], now)

    with db() as con:
        if api_key is None:
            row = con.execute(
                "select * from api_keys where key_hash = ? and status = 'active'",
                (key_hash,),
            ).fetchone()
            if not row:
                raise AppError(401, "UNAUTHORIZED", "Invalid API key")
            api_key = row_to_dict(row)
            store_cached_api_key(key_hash, api_key, now)
            check_expired = should_check_expired_redeems(api_key["user_id"], now)

        if check_expired:
            deduct_expired_redeem_codes(con, api_key["user_id"])
        if balance is None or check_expired:
            balance_row = con.execute("select balance from users where id = ?", (api_key["user_id"],)).fetchone()
            balance = parse_decimal(balance_row["balance"]) if balance_row else Decimal("-1")
            store_cached_balance(api_key["user_id"], balance, now)

        if upstreams is None:
            upstreams = load_upstreams_from_connection(con, client_type)
            store_cached_upstreams(client_type, upstreams, now)

    return ProxyContext(api_key=dict(api_key), balance=balance, upstreams=[dict(item) for item in upstreams])


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
    now = time.monotonic()
    check_expired = should_check_expired_redeems(user_id, now)
    if not check_expired:
        cached = cached_balance(user_id, now)
        if cached is not None:
            return cached
    with db() as con:
        if check_expired:
            deduct_expired_redeem_codes(con, user_id)
        row = con.execute("select balance from users where id = ?", (user_id,)).fetchone()
    balance = parse_decimal(row["balance"]) if row else Decimal("-1")
    store_cached_balance(user_id, balance, now)
    return balance


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
        return load_upstreams_from_connection(con, client_type)


def upstream_endpoint(upstream: dict[str, Any]) -> str:
    return first_non_blank(upstream.get("profile_base_url"), upstream.get("api_endpoint"), "https://chatgpt.com/backend-api/codex")


def upstream_limit(upstream: dict[str, Any]) -> int:
    try:
        return max(1, int(upstream.get("concurrent_limit") or 1))
    except Exception:
        return 1


def acquire_upstream_slot(client_type: str, upstream: dict[str, Any]) -> UpstreamLimiter | None:
    service_id = int(upstream.get("id") or 0)
    limit = upstream_limit(upstream)
    key = (client_type, service_id, limit)
    with _upstream_limiter_lock:
        limiter = _upstream_limiters.get(key)
        if limiter is None:
            limiter = UpstreamLimiter(limit=limit)
            _upstream_limiters[key] = limiter
        if limiter.active >= limiter.limit:
            return None
        limiter.active += 1
        return limiter


def release_upstream_slot(limiter: UpstreamLimiter | None) -> None:
    if limiter is not None:
        with _upstream_limiter_lock:
            limiter.active = max(0, limiter.active - 1)


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
        "usage_limit_reached",
        "usage limit has been reached",
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
        request_id = request.headers.get("x-client-request-id")
        if request_id:
            headers["x-client-request-id"] = request_id
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
                if not root.get("instructions"):
                    instructions = codex_default_instructions()
                    if instructions:
                        root["instructions"] = instructions
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


def open_upstream_client(client_type: str) -> httpx.AsyncClient:
    timeout = httpx.Timeout(connect=10, read=None, write=30, pool=30)
    if client_type == "CODEX":
        loop_key = id(asyncio.get_running_loop())
        key = (client_type, loop_key)
        with _upstream_client_lock:
            client = _shared_upstream_clients.get(key)
            if client is None or client.is_closed:
                max_connections = int(os.getenv("RELAY_PY_CODEX_MAX_CONNECTIONS", "200"))
                max_keepalive = int(os.getenv("RELAY_PY_CODEX_MAX_KEEPALIVE", "100"))
                client = httpx.AsyncClient(
                    timeout=timeout,
                    limits=httpx.Limits(
                        max_connections=max_connections,
                        max_keepalive_connections=max_keepalive,
                    ),
                )
                _shared_upstream_clients[key] = client
                _shared_upstream_client_ids.add(id(client))
            return client
    return httpx.AsyncClient(timeout=timeout)


async def close_upstream_client(client: httpx.AsyncClient | None) -> None:
    if client is None:
        return
    with _upstream_client_lock:
        is_shared = id(client) in _shared_upstream_client_ids
    if not is_shared:
        await client.aclose()


@app.on_event("shutdown")
async def close_shared_upstream_clients() -> None:
    with _upstream_client_lock:
        clients = list(_shared_upstream_clients.values())
        _shared_upstream_clients.clear()
        _shared_upstream_client_ids.clear()
    for client in clients:
        await client.aclose()


def codex_default_instructions() -> str | None:
    global _codex_default_instructions_cache
    try:
        mtime = CODEX_PROFILES_PATH.stat().st_mtime
    except OSError:
        return None
    if _codex_default_instructions_cache and _codex_default_instructions_cache[0] == mtime:
        return _codex_default_instructions_cache[1]
    try:
        data = json.loads(CODEX_PROFILES_PATH.read_text(encoding="utf-8-sig"))
        defaults = data.get("request_defaults") if isinstance(data, dict) else None
        instructions = defaults.get("instructions") if isinstance(defaults, dict) else None
        value = instructions.strip() if isinstance(instructions, str) and instructions.strip() else None
    except Exception:
        value = None
    _codex_default_instructions_cache = (mtime, value)
    return value


def refresh_codex_profile_sync(upstream: dict[str, Any]) -> bool:
    refresh_token = first_non_blank(upstream.get("refresh_token"))
    profile_name = upstream.get("profile_name")
    service_id = upstream.get("id")
    if not refresh_token or not service_id:
        return False
    payload = {
        "client_id": first_non_blank(upstream.get("client_id"), CODEX_CLIENT_ID),
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
    }
    req = urllib_request.Request(
        CODEX_REFRESH_TOKEN_URL,
        data=json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
        headers={
            "accept": "application/json",
            "content-type": "application/json",
            "originator": "codex_cli_rs",
            "user-agent": "codex_cli_rs/0.126.0 (Windows 10; x86_64)",
            "version": "0.126.0",
        },
        method="POST",
    )
    with _codex_refresh_lock:
        with urllib_request.urlopen(req, timeout=60) as res:
            data = json.loads(res.read().decode("utf-8", errors="replace"))
        access_token = data.get("access_token")
        if not isinstance(access_token, str) or not access_token.strip():
            return False
        id_token = data.get("id_token") if isinstance(data.get("id_token"), str) else upstream.get("id_token")
        new_refresh = data.get("refresh_token") if isinstance(data.get("refresh_token"), str) else refresh_token
        ts = now_iso()
        with db() as con:
            con.execute(
                """
                update openai_codex_profiles
                set access_token = ?, id_token = ?, refresh_token = ?, last_refresh = ?, updated_at = ?
                where openai_service_id = ?
                """,
                (access_token, id_token, new_refresh, ts, ts, service_id),
            )
            con.execute(
                "update openai_services set token = ?, updated_at = ? where id = ?",
                (access_token, ts, service_id),
            )
        upstream["access_token"] = access_token
        upstream["id_token"] = id_token
        upstream["refresh_token"] = new_refresh
        upstream["token"] = access_token
        invalidate_proxy_context_cache()
        codex_proxy_logger.info("refreshed Codex profile %s after upstream 401", profile_name or service_id)
        return True


async def retry_codex_after_refresh(
    client: httpx.AsyncClient,
    method: str,
    upstream_url: str,
    upstream_body: bytes,
    upstream: dict[str, Any],
    client_type: str,
    response: httpx.Response,
) -> httpx.Response:
    if client_type != "CODEX" or response.status_code != 401 or not upstream.get("profile_name"):
        return response
    if not upstream.get("refresh_token"):
        return response
    try:
        refreshed = await run_in_threadpool(refresh_codex_profile_sync, upstream)
    except Exception as exc:
        codex_proxy_logger.warning("failed to refresh Codex profile %s after 401: %s", upstream.get("profile_name"), exc)
        return response
    if not refreshed:
        return response
    await response.aread()
    await response.aclose()
    retry_headers = build_upstream_headers_for_retry(upstream, upstream_body)
    retry_request = client.build_request(method, upstream_url, content=upstream_body, headers=retry_headers)
    return await client.send(retry_request, stream=True)


def build_upstream_headers_for_retry(upstream: dict[str, Any], body: bytes) -> dict[str, str]:
    headers = {
        "accept": "text/event-stream" if b'"stream":true' in body else "application/json",
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


class ProxyLogWriter:
    def __init__(self) -> None:
        self.queue: queue_lib.Queue[ProxyLogEvent | None] = queue_lib.Queue()
        self.stop_event = threading.Event()
        self.start_lock = threading.Lock()
        self.started = False
        self.thread = threading.Thread(target=self.run, name="relay-proxy-log-writer", daemon=True)

    def start(self) -> None:
        with self.start_lock:
            if self.started:
                return
            self.started = True
            self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        if self.started:
            self.queue.put_nowait(None)
        if self.thread.is_alive():
            self.thread.join(timeout=5)

    def submit(self, event: ProxyLogEvent) -> None:
        self.start()
        self.queue.put_nowait(event)

    def run(self) -> None:
        con = self.open_connection()
        if con is None:
            return
        try:
            while not self.stop_event.is_set():
                batch = self.read_batch()
                if batch:
                    self.write_batch(con, batch)
            while True:
                try:
                    event = self.queue.get_nowait()
                except queue_lib.Empty:
                    break
                if event is not None:
                    self.write_batch(con, [event])
        finally:
            con.close()

    def open_connection(self) -> sqlite3.Connection | None:
        while not self.stop_event.is_set():
            try:
                con = sqlite3.connect(DB_PATH, timeout=30)
                con.row_factory = sqlite3.Row
                con.execute("PRAGMA foreign_keys = ON")
                con.execute("PRAGMA busy_timeout = 30000")
                con.execute("PRAGMA journal_mode = WAL")
                con.execute("PRAGMA synchronous = NORMAL")
                return con
            except sqlite3.Error:
                codex_proxy_logger.exception("failed to open proxy log writer database connection; retrying")
                time.sleep(0.5)
        return None

    def read_batch(self) -> list[ProxyLogEvent]:
        try:
            first = self.queue.get(timeout=max(0.001, PROXY_LOG_FLUSH_INTERVAL))
        except queue_lib.Empty:
            return []
        if first is None:
            self.stop_event.set()
            return []

        batch = [first]
        deadline = time.monotonic() + max(0.001, PROXY_LOG_FLUSH_INTERVAL)
        while len(batch) < max(1, PROXY_LOG_BATCH_SIZE):
            timeout = max(0.0, deadline - time.monotonic())
            try:
                event = self.queue.get(timeout=timeout)
            except queue_lib.Empty:
                break
            if event is None:
                self.stop_event.set()
                break
            batch.append(event)
        return batch

    def write_batch(self, con: sqlite3.Connection, events: list[ProxyLogEvent]) -> None:
        try:
            write_proxy_log_events_sync(con, events)
        except Exception:
            con.rollback()
            codex_proxy_logger.exception("failed to write proxy request log batch; retrying individually")
            time.sleep(0.2)
            for event in events:
                try:
                    write_proxy_log_events_sync(con, [event])
                except Exception:
                    con.rollback()
                    codex_proxy_logger.exception("failed to write proxy request log event")


proxy_log_writer = ProxyLogWriter()
atexit.register(proxy_log_writer.stop)


@app.on_event("startup")
async def start_proxy_log_writer() -> None:
    proxy_log_writer.start()


def enqueue_proxy_log_event(event: ProxyLogEvent) -> None:
    proxy_log_writer.submit(event)


def billing_catalog(con: sqlite3.Connection) -> tuple[dict[str, dict[str, Any]], Decimal]:
    global _billing_catalog_cache
    now = time.monotonic()
    if _billing_catalog_cache and _billing_catalog_cache[0] > now:
        return _billing_catalog_cache[1], _billing_catalog_cache[2]
    rows = con.execute("select * from model_catalog where enabled = 1").fetchall()
    prices = {row["id"]: row_to_dict(row) for row in rows}
    multiplier = parse_decimal(setting(con, "billing.cost_multiplier", "1.2"))
    _billing_catalog_cache = (now + PROXY_BILLING_CACHE_TTL, prices, multiplier)
    return prices, multiplier


def calculate_cost_value(usage: dict[str, Any], price: dict[str, Any] | sqlite3.Row | None, multiplier: Decimal) -> Decimal:
    if not price:
        return Decimal("0.000000")
    regular_input = max(0, usage["input"] - usage["cache_read"] - usage["cache_create"])
    cost = (
        parse_decimal(price["input_price"]) * regular_input
        + parse_decimal(price["output_price"]) * usage["output"]
        + parse_decimal(price["cached_input_price"]) * usage["cache_read"]
        + parse_decimal(price["cache_creation_price"]) * usage["cache_create"]
    ) / Decimal(1_000_000)
    return (cost * multiplier).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)


def compact_proxy_log_detail(event: ProxyLogEvent, usage: dict[str, Any]) -> str:
    detail: dict[str, Any] = {
        "status_code": event.status_code,
        "upstream_service_id": event.upstream_service_id,
        "method": event.request_method,
        "uri": event.request_uri,
        "use_time_ms": event.use_time_ms,
        "first_token_ms": event.first_token_ms,
        "model": usage.get("model"),
        "input_tokens": usage.get("input", 0),
        "output_tokens": usage.get("output", 0),
        "cache_read_tokens": usage.get("cache_read", 0),
        "cache_creation_tokens": usage.get("cache_create", 0),
    }
    if event.query_string:
        detail["query"] = event.query_string[:256]
    response_summary = proxy_response_summary(event.response_body)
    if response_summary:
        detail.update(response_summary)
    return json.dumps(detail, ensure_ascii=False, separators=(",", ":"))


def proxy_response_summary(response_body: bytes) -> dict[str, Any]:
    if not response_body:
        return {}
    text = response_body.decode("utf-8", "replace")
    payloads = parse_json_payloads(text)
    response_summary: dict[str, Any] = {}
    for payload in payloads:
        if not isinstance(payload, dict):
            continue
        response = payload.get("response") if isinstance(payload.get("response"), dict) else None
        if response and response.get("id"):
            response_summary = {
                "response_id": response.get("id"),
                "response_status": response.get("status"),
            }
            if response.get("status") == "completed":
                return response_summary
        error = payload.get("error")
        if isinstance(error, dict):
            return {
                "error_type": error.get("type") or error.get("code"),
                "error_message": str(error.get("message") or "")[:500],
            }
        if error:
            return {"error_message": str(error)[:500]}
    if response_summary:
        return response_summary
    stripped = " ".join(text.split())
    if stripped and not stripped.startswith("event: response."):
        return {"response_excerpt": stripped[:500]}
    return {}


def write_proxy_log_events_sync(con: sqlite3.Connection, events: list[ProxyLogEvent]) -> None:
    prices, multiplier = billing_catalog(con)
    rows: list[tuple[Any, ...]] = []
    balance_deltas: dict[str, Decimal] = {}
    next_balances: dict[str, Decimal] = {}
    for event in events:
        usage = parse_usage(event.request_body, event.response_body)
        cost = calculate_cost_value(usage, prices.get(usage["model"]), multiplier)
        detail = compact_proxy_log_detail(event, usage)
        rows.append(
            (
                event.api_key["user_id"],
                event.api_key["id"],
                event.api_key["name"] or display_key(event.api_key["key_hash"]),
                event.api_key["key_value"] or display_key(event.api_key["key_hash"]),
                event.client_type,
                usage["model"],
                event.use_time_ms,
                event.first_token_ms,
                usage["input"],
                usage["output"],
                usage["cache_read"],
                usage["cache_create"],
                decimal_text(cost),
                event.ip,
                "success" if 200 <= event.status_code < 300 else "error",
                event.upstream_service_id,
                detail,
                event.created_at,
            )
        )
        if cost > 0:
            user_id = event.api_key["user_id"]
            balance_deltas[user_id] = balance_deltas.get(user_id, Decimal("0")) - cost

    con.executemany(
        """
        insert into request_logs
          (user_id, api_key_id, token_name, group_key, request_type, client_type, model,
           use_time_ms, first_token_ms, prompt_tokens, completion_tokens, cache_read_tokens,
           cache_creation_tokens, cost, ip, status, upstream_service_id, detail, created_at)
        values (?, ?, ?, ?, 'usage', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    for user_id, delta in balance_deltas.items():
        next_balances[user_id] = add_balance(con, user_id, delta, update_cache=False)
    con.commit()
    for user_id, balance in next_balances.items():
        store_cached_balance(user_id, balance)


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
    event = ProxyLogEvent(
        api_key=row_to_dict(api_key) if isinstance(api_key, sqlite3.Row) else dict(api_key),
        client_type=client_type,
        request_method=request_method,
        request_uri=request_uri,
        query_string=query_string,
        ip=ip,
        user_agent=user_agent,
        request_body=request_body,
        response_body=response_body,
        upstream_service_id=upstream_service_id,
        status_code=status_code,
        use_time_ms=use_time_ms,
        first_token_ms=first_token_ms,
        created_at=now_iso(),
    )
    with db() as con:
        write_proxy_log_events_sync(con, [event])


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
    multiplier = parse_decimal(setting(con, "billing.cost_multiplier", "1.2"))
    return calculate_cost_value(usage, price, multiplier)


def add_balance(con: sqlite3.Connection, user_id: str, amount: Decimal, *, update_cache: bool = True) -> Decimal:
    row = con.execute("select balance from users where id = ?", (user_id,)).fetchone()
    if not row:
        raise AppError(401, "UNAUTHORIZED", "Unauthorized")
    next_balance = parse_decimal(row["balance"]) + amount
    con.execute("update users set balance = ? where id = ?", (decimal_text(next_balance), user_id))
    if update_cache:
        store_cached_balance(user_id, next_balance)
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
