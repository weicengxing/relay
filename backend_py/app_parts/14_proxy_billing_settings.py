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
    if client_type == "CODEX" and is_codex_responses_request(path):
        allowed = cached_codex_responses_allowed_for_user(context.api_key["user_id"])
        if allowed is None:
            allowed = await run_in_threadpool(codex_responses_allowed_for_user_sync, context.api_key["user_id"])
        if not allowed:
            return local_proxy_error(403, "目前无法使用", event_stream)
    if client_type == "CODEX":
        submit_codex_user_message_log(
            context.api_key,
            request.url.path,
            {
                "x-client-request-id": request.headers.get("x-client-request-id"),
                "session_id": request.headers.get("session_id"),
                "x-codex-turn-metadata": request.headers.get("x-codex-turn-metadata"),
            },
            body,
        )
    return await proxy_with_body(path, request, body, event_stream, context.api_key, client_type, context.upstreams)


CODEX_CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
CODEX_REFRESH_TOKEN_URL = "https://auth.openai.com/oauth/token"
CODEX_RESPONSES_NON_ADMIN_ENABLED_SETTING = "codex.responses_non_admin_enabled"
codex_proxy_logger = logging.getLogger("relay.codex_proxy")
_codex_refresh_lock = threading.Lock()
_codex_instructions_lock = threading.Lock()
_codex_default_instructions_cache: tuple[float | None, str | None] = (None, None)
_codex_instructions_stop = threading.Event()
_codex_instructions_thread_lock = threading.Lock()
_codex_instructions_thread: threading.Thread | None = None
_codex_profile_refresh_stop = threading.Event()
_codex_profile_refresh_thread_lock = threading.Lock()
_codex_profile_refresh_thread: threading.Thread | None = None
PROXY_API_KEY_CACHE_TTL = float(os.getenv("RELAY_PY_PROXY_API_KEY_CACHE_TTL", "600"))
PROXY_UPSTREAM_CACHE_TTL = float(os.getenv("RELAY_PY_PROXY_UPSTREAM_CACHE_TTL", "30"))
PROXY_BALANCE_CACHE_TTL = float(os.getenv("RELAY_PY_PROXY_BALANCE_CACHE_TTL", "1"))
PROXY_BILLING_CACHE_TTL = float(os.getenv("RELAY_PY_PROXY_BILLING_CACHE_TTL", "inf"))
PROXY_EXPIRED_REDEEM_CHECK_TTL = float(os.getenv("RELAY_PY_PROXY_EXPIRED_REDEEM_CHECK_TTL", "30"))
PROXY_LOG_BATCH_SIZE = int(os.getenv("RELAY_PY_PROXY_LOG_BATCH_SIZE", "100"))
PROXY_LOG_FLUSH_INTERVAL = float(os.getenv("RELAY_PY_PROXY_LOG_FLUSH_INTERVAL", "0.05"))
CODEX_USER_MESSAGE_MAX_CHARS = max(1, int(os.getenv("RELAY_PY_CODEX_USER_MESSAGE_MAX_CHARS", "20000")))
CODEX_INSTRUCTIONS_REFRESH_INTERVAL = max(1.0, float(os.getenv("RELAY_PY_CODEX_INSTRUCTIONS_REFRESH_INTERVAL", "5")))
CODEX_PROFILE_REFRESH_ENABLED_SETTING = "codex.refresh_enabled"
CODEX_PROFILE_REFRESH_INTERVAL_DAYS = max(1, int(os.getenv("RELAY_PY_CODEX_REFRESH_INTERVAL_DAYS", "6")))
CODEX_PROFILE_REFRESH_SCAN_INTERVAL_SECONDS = max(
    60.0, float(os.getenv("RELAY_PY_CODEX_REFRESH_SCAN_INTERVAL_SECONDS", "300"))
)
CODEX_PROFILE_REFRESH_INITIAL_DELAY_SECONDS = max(
    0.0, float(os.getenv("RELAY_PY_CODEX_REFRESH_INITIAL_DELAY_SECONDS", "60"))
)
CODEX_PROFILE_REFRESH_LOG_PATH = Path(
    os.getenv(
        "RELAY_PY_CODEX_REFRESH_LOG",
        str(DB_PATH.parent / "logs" / "codex-token-refresh.log"),
    )
)
RELAY_CODEX_SYNC_SECRET = os.getenv("RELAY_PY_CODEX_SYNC_SECRET", "")
CODEX_USER_MESSAGE_WORKERS = max(1, int(os.getenv("RELAY_PY_CODEX_USER_MESSAGE_WORKERS", "2")))
PROXY_LOG_CAPTURE_LIMIT = 256 * 1024
PROXY_LOG_IMPORTANT_SSE_LIMIT = 256 * 1024
PROXY_LOG_SSE_PENDING_LIMIT = 1024 * 1024

_proxy_cache_lock = threading.Lock()
_api_key_cache: dict[str, tuple[float, dict[str, Any]]] = {}
_upstream_cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}
_balance_cache: dict[str, tuple[float, Decimal]] = {}
_expired_redeem_check_cache: dict[str, float] = {}
_codex_responses_enabled_cache: bool | None = None
_owner_user_cache: dict[str, bool] = {}
_billing_catalog_cache: tuple[float, dict[str, dict[str, Any]], Decimal, Decimal] | None = None
_upstream_limiter_lock = threading.Lock()
_upstream_limiters: dict[tuple[str, int, int], "UpstreamLimiter"] = {}
_upstream_client_lock = threading.Lock()
_shared_upstream_clients: dict[tuple[str, int], httpx.AsyncClient] = {}
_shared_upstream_client_ids: set[int] = set()
_mode2_rotation_lock = threading.Lock()
_mode2_rotation_state: dict[str, dict[str, Any]] = {}
_mode3_rotation_lock = threading.Lock()
_mode3_rotation_state: dict[str, dict[str, Any]] = {}
_codex_user_message_executor = concurrent.futures.ThreadPoolExecutor(
    max_workers=CODEX_USER_MESSAGE_WORKERS,
    thread_name_prefix="relay-codex-user-log",
)


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


def is_codex_responses_request(path: str) -> bool:
    clean_path = "/" + str(path or "").strip("/").lower()
    return (
        clean_path == "/responses"
        or clean_path.startswith("/responses/")
        or clean_path == "/v1/responses"
        or clean_path.startswith("/v1/responses/")
    )


def cached_codex_responses_allowed_for_user(user_id: str) -> bool | None:
    with _proxy_cache_lock:
        enabled = _codex_responses_enabled_cache
        owner = _owner_user_cache.get(user_id)
    if enabled is None:
        return None
    if enabled:
        return True
    if owner is None:
        return None
    return owner


def codex_responses_allowed_for_user_sync(user_id: str) -> bool:
    enabled = codex_responses_enabled_sync()
    if enabled:
        return True
    with _proxy_cache_lock:
        cached_owner = _owner_user_cache.get(user_id)
    if cached_owner is not None:
        return cached_owner
    with db() as con:
        row = con.execute("select email from users where id = ?", (user_id,)).fetchone()
        owner = is_owner_email(row["email"] if row else None)
    with _proxy_cache_lock:
        _owner_user_cache[user_id] = owner
    return owner


def codex_responses_enabled_sync() -> bool:
    global _codex_responses_enabled_cache
    with _proxy_cache_lock:
        cached = _codex_responses_enabled_cache
    if cached is not None:
        return cached
    with db() as con:
        enabled = bool_setting(con, CODEX_RESPONSES_NON_ADMIN_ENABLED_SETTING, True)
    with _proxy_cache_lock:
        _codex_responses_enabled_cache = enabled
    return enabled


class ProxyResponseCapture:
    def __init__(self) -> None:
        self.prefix = bytearray()
        self.important_sse = bytearray()
        self.pending_line = bytearray()

    def feed(self, chunk: bytes) -> None:
        if not chunk:
            return
        if len(self.prefix) < PROXY_LOG_CAPTURE_LIMIT:
            self.prefix.extend(chunk[: PROXY_LOG_CAPTURE_LIMIT - len(self.prefix)])
        if len(self.important_sse) < PROXY_LOG_IMPORTANT_SSE_LIMIT:
            self._feed_sse_bytes(chunk)

    def body(self) -> bytes:
        if self.pending_line:
            self._capture_important_sse_line(bytes(self.pending_line))
            self.pending_line.clear()
        if not self.important_sse:
            return bytes(self.prefix)
        return bytes(self.prefix) + b"\n" + bytes(self.important_sse)

    def _feed_sse_bytes(self, data: bytes) -> None:
        if not data:
            return
        if self.pending_line:
            data = bytes(self.pending_line) + data
            self.pending_line.clear()

        start = 0
        while start < len(data):
            newline = data.find(b"\n", start)
            if newline < 0:
                tail = data[start:]
                if len(tail) > PROXY_LOG_SSE_PENDING_LIMIT:
                    tail = tail[-4096:]
                self.pending_line.extend(tail)
                return
            self._capture_important_sse_line(data[start : newline + 1])
            if len(self.important_sse) >= PROXY_LOG_IMPORTANT_SSE_LIMIT:
                self.pending_line.clear()
                return
            start = newline + 1

    def _capture_important_sse_line(self, line: bytes) -> None:
        if len(self.important_sse) >= PROXY_LOG_IMPORTANT_SSE_LIMIT:
            return
        stripped = line.strip()
        if not stripped.startswith(b"data:"):
            return
        payload = stripped[5:].strip()
        if not payload or payload == b"[DONE]":
            return
        if not (
            b'"usage"' in payload
            or b'"type":"response.completed"' in payload
            or b'"type": "response.completed"' in payload
            or b'"type":"response.failed"' in payload
            or b'"type": "response.failed"' in payload
            or b'"error"' in payload
        ):
            return
        encoded = b"data: " + payload + b"\n"
        self.important_sse.extend(encoded[: PROXY_LOG_IMPORTANT_SSE_LIMIT - len(self.important_sse)])


def is_important_sse_log_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped.startswith("data:"):
        return False
    payload = stripped[5:].strip()
    if not payload or payload == "[DONE]":
        return False
    return (
        '"usage"' in payload
        or '"type":"response.completed"' in payload
        or '"type": "response.completed"' in payload
        or '"type":"response.failed"' in payload
        or '"type": "response.failed"' in payload
        or '"error"' in payload
    )


def compact_important_sse_log_line(line: str) -> str:
    stripped = line.strip()
    if not stripped.startswith("data:"):
        return line
    payload = stripped[5:].strip()
    try:
        root = json.loads(payload)
    except Exception:
        return line
    if not isinstance(root, dict):
        return line

    compact: dict[str, Any] = {}
    event_type = root.get("type")
    if event_type is not None:
        compact["type"] = event_type
    response = root.get("response") if isinstance(root.get("response"), dict) else None
    if response is not None:
        compact_response = {
            key: response.get(key)
            for key in ["id", "status", "model", "usage"]
            if response.get(key) is not None
        }
        if compact_response:
            compact["response"] = compact_response
    message = root.get("message") if isinstance(root.get("message"), dict) else None
    if message is not None:
        compact_message = {
            key: message.get(key)
            for key in ["id", "status", "model", "usage"]
            if message.get(key) is not None
        }
        if compact_message:
            compact["message"] = compact_message
    for key in ["model", "usage", "error"]:
        if root.get(key) is not None:
            compact[key] = root.get(key)
    if not compact:
        return line
    return "data: " + json.dumps(compact, ensure_ascii=False, separators=(",", ":")) + "\n"


def codex_text_blocks(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            parts.extend(codex_text_blocks(item))
        return parts
    if not isinstance(value, dict):
        return []
    block_type = value.get("type")
    if block_type in {"input_text", "text", "output_text"} and isinstance(value.get("text"), str):
        return [value["text"]]
    if isinstance(value.get("text"), str) and block_type is None:
        return [value["text"]]
    return codex_text_blocks(value.get("content"))


def extract_latest_codex_user_message(body: bytes) -> dict[str, Any] | None:
    try:
        root = json.loads(body)
    except Exception:
        return None
    if not isinstance(root, dict):
        return None
    raw_input = root.get("input")
    input_index: int | None = None
    text = ""
    if isinstance(raw_input, str):
        text = raw_input.strip()
    elif isinstance(raw_input, list):
        for idx in range(len(raw_input) - 1, -1, -1):
            item = raw_input[idx]
            if not isinstance(item, dict) or item.get("role") != "user":
                continue
            parts = [part.strip() for part in codex_text_blocks(item.get("content")) if part.strip()]
            text = "\n\n".join(parts).strip()
            input_index = idx
            break
    if not text:
        return None
    if len(text) > CODEX_USER_MESSAGE_MAX_CHARS:
        text = text[:CODEX_USER_MESSAGE_MAX_CHARS]
    return {
        "message_text": text,
        "message_hash": b64url(hashlib.sha256(text.encode("utf-8")).digest()),
        "input_index": input_index,
        "model": root.get("model") if isinstance(root.get("model"), str) else None,
        "previous_response_id": root.get("previous_response_id")
        if isinstance(root.get("previous_response_id"), str)
        else None,
    }


def parse_codex_turn_metadata(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except Exception:
        return {}
    return value if isinstance(value, dict) else {}


def record_codex_user_message_sync(
    api_key: dict[str, Any],
    request_uri: str,
    headers: dict[str, str | None],
    body: bytes,
) -> None:
    extracted = extract_latest_codex_user_message(body)
    if not extracted:
        return
    metadata = parse_codex_turn_metadata(headers.get("x-codex-turn-metadata"))
    request_id = first_non_blank(headers.get("x-client-request-id"), metadata.get("request_id"))
    session_id = first_non_blank(headers.get("session_id"), metadata.get("session_id"))
    turn_id = first_non_blank(metadata.get("turn_id"))
    dedupe_material = "|".join(
        str(value or "")
        for value in [
            api_key.get("id"),
            api_key.get("user_id"),
            request_uri,
            request_id,
            session_id,
            turn_id,
            extracted.get("previous_response_id"),
            extracted["message_hash"],
        ]
    )
    dedupe_key = b64url(hashlib.sha256(dedupe_material.encode("utf-8")).digest())
    try:
        with db() as con:
            insert_with_next_integer_id(
                con,
                "codex_user_messages",
                {
                    "user_id": api_key["user_id"],
                    "api_key_id": api_key["id"],
                    "request_uri": request_uri,
                    "request_id": request_id,
                    "session_id": session_id,
                    "turn_id": turn_id,
                    "previous_response_id": extracted.get("previous_response_id"),
                    "model": extracted.get("model"),
                    "message_text": extracted["message_text"],
                    "message_hash": extracted["message_hash"],
                    "dedupe_key": dedupe_key,
                    "created_at": now_iso(),
                },
                """
                on conflict(dedupe_key) do nothing
                """,
            )
    except Exception:
        codex_proxy_logger.exception("failed to record Codex user message")


def submit_codex_user_message_log(
    api_key: Any,
    request_uri: str,
    headers: dict[str, str | None],
    body: bytes,
) -> None:
    try:
        api_key_snapshot = {"id": api_key["id"], "user_id": api_key["user_id"]}
    except Exception:
        codex_proxy_logger.exception("failed to snapshot api key for Codex user message log")
        return
    try:
        future = _codex_user_message_executor.submit(
            record_codex_user_message_sync,
            api_key_snapshot,
            request_uri,
            dict(headers),
            body,
        )
        future.add_done_callback(log_codex_user_message_task_failure)
    except RuntimeError:
        codex_proxy_logger.exception("failed to submit Codex user message log task")


def log_codex_user_message_task_failure(future: concurrent.futures.Future[Any]) -> None:
    try:
        future.result()
    except Exception:
        codex_proxy_logger.exception("Codex user message log task failed")


def stop_codex_user_message_executor() -> None:
    _codex_user_message_executor.shutdown(wait=True, cancel_futures=False)


def mode3_batch_size_from_upstreams(upstreams: list[dict[str, Any]]) -> int:
    for upstream in upstreams:
        try:
            return max(1, int(upstream.get("_mode3_batch_size") or 8))
        except Exception:
            return 8
    return 8


def mode3_reordered_upstreams(client_type: str, upstreams: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if client_type != "CODEX" or not upstreams or not upstreams[0].get("_mode3_rotation"):
        return upstreams
    signature = tuple(int(upstream.get("id") or 0) for upstream in upstreams)
    if not signature:
        return upstreams
    batch_size = mode3_batch_size_from_upstreams(upstreams)
    with _mode3_rotation_lock:
        state = _mode3_rotation_state.get(client_type)
        if state is None or state.get("signature") != signature or state.get("batch_size") != batch_size:
            state = {"signature": signature, "batch_size": batch_size, "index": 0, "remaining": batch_size}
            _mode3_rotation_state[client_type] = state
        index = int(state.get("index") or 0) % len(upstreams)
        remaining = max(1, int(state.get("remaining") or batch_size)) - 1
        if remaining <= 0:
            state["index"] = (index + 1) % len(upstreams)
            state["remaining"] = batch_size
        else:
            state["index"] = index
            state["remaining"] = remaining
    return [dict(item) for item in (upstreams[index:] + upstreams[:index])]


def mode2_start_index(client_type: str, upstreams: list[dict[str, Any]]) -> int:
    if client_type != "CODEX" or not upstreams or not upstreams[0].get("_mode2_round_robin"):
        return 0
    signature = tuple(int(upstream.get("id") or 0) for upstream in upstreams)
    if not signature:
        return 0
    with _mode2_rotation_lock:
        state = _mode2_rotation_state.get(client_type)
        if state is None or state.get("signature") != signature:
            state = {"signature": signature, "index": 0}
            _mode2_rotation_state[client_type] = state
        index = int(state.get("index") or 0) % len(upstreams)
        state["index"] = (index + 1) % len(upstreams)
    return index


def upstream_attempts(client_type: str, upstreams: list[dict[str, Any]]) -> Iterable[tuple[int, dict[str, Any], int]]:
    upstreams = mode3_reordered_upstreams(client_type, upstreams)
    total = len(upstreams)
    if total <= 0:
        return
    start = mode2_start_index(client_type, upstreams)
    for offset in range(total):
        yield offset, upstreams[(start + offset) % total], total


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
    for index, candidate, upstream_count in upstream_attempts(client_type, upstreams):
        candidate_limiter: UpstreamLimiter | None = None
        try:
            upstream_body = await normalize_upstream_body_async(body, candidate, client_type, event_stream)
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
                if is_retryable_quota_error(candidate_stream.status_code, candidate_body) and index < upstream_count - 1:
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
            if index < upstream_count - 1:
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
        capture = ProxyResponseCapture()
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
                if from_upstream:
                    capture.feed(chunk)
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
                        response_body=capture.body(),
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
        capture = ProxyResponseCapture()
        first_token_ms = 0
        response_bytes = 0
        saw_first = False
        status_code = 502
        upstream: dict[str, Any] | None = None
        assigned_upstream: dict[str, Any] | None = None
        stream: httpx.Response | None = None
        upstream_limiter: UpstreamLimiter | None = None
        client: httpx.AsyncClient | None = open_upstream_client(client_type)
        last_error = "Unable to reach upstream service"
        send_task: asyncio.Task[httpx.Response] | None = None
        try:
            for index, candidate, upstream_count in upstream_attempts(client_type, upstreams):
                candidate_limiter: UpstreamLimiter | None = None
                try:
                    upstream_body = await normalize_upstream_body_async(body, candidate, client_type, True)
                    upstream_url = join_upstream_url(upstream_endpoint(candidate), request_uri, query_string)
                    headers = build_upstream_headers(request, candidate, client_type, upstream_body)
                    upstream_request = client.build_request(
                        request.method, upstream_url, content=upstream_body, headers=headers
                    )
                    candidate_limiter = acquire_upstream_slot(client_type, candidate)
                    if candidate_limiter is None:
                        last_error = f"Upstream service {candidate.get('id')} is busy"
                        continue
                    assigned_upstream = candidate
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
                        if is_retryable_quota_error(status_code, candidate_body) and index < upstream_count - 1:
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
                            capture.feed(chunk)
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
                        capture.feed(chunk)
                        yield chunk
                    break
                except asyncio.CancelledError:
                    await discard_task_exception(send_task)
                    send_task = None
                    try:
                        if stream is not None:
                            await stream.aclose()
                            stream = None
                    finally:
                        release_upstream_slot(candidate_limiter)
                    raise
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
                    if index < upstream_count - 1:
                        continue
                    chunk = codex_sse_error_bytes(last_error)
                    response_bytes += len(chunk)
                    capture.feed(chunk)
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
                        response_body=capture.body(),
                        upstream_service_id=(upstream or assigned_upstream).get("id")
                        if upstream or assigned_upstream
                        else None,
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
    global _billing_catalog_cache, _codex_responses_enabled_cache
    with _proxy_cache_lock:
        if user_id is None:
            _api_key_cache.clear()
            _upstream_cache.clear()
            _balance_cache.clear()
            _expired_redeem_check_cache.clear()
            _owner_user_cache.clear()
            _codex_responses_enabled_cache = None
            _billing_catalog_cache = None
        else:
            _balance_cache.pop(user_id, None)
            _expired_redeem_check_cache.pop(user_id, None)
            _owner_user_cache.pop(user_id, None)


def invalidate_codex_responses_setting_cache() -> None:
    global _codex_responses_enabled_cache
    with _proxy_cache_lock:
        _codex_responses_enabled_cache = None
        _owner_user_cache.clear()


def sync_codex_profile_refresh_payload_sync(payload: dict[str, Any]) -> dict[str, Any]:
    profile = payload.get("profile") if isinstance(payload.get("profile"), dict) else payload
    if not isinstance(profile, dict):
        raise AppError(400, "VALIDATION_FAILED", "Missing Codex profile payload")

    tokens = profile.get("tokens") if isinstance(profile.get("tokens"), dict) else {}
    profile_name = first_non_blank(profile.get("name"), profile.get("profile_name"))
    if not profile_name:
        raise AppError(400, "VALIDATION_FAILED", "Missing Codex profile name")

    access_token = first_non_blank(tokens.get("access_token"), profile.get("access_token"), profile.get("OPENAI_API_KEY"))
    openai_key = first_non_blank(profile.get("OPENAI_API_KEY"), profile.get("openai_api_key"))
    if not access_token and not openai_key:
        raise AppError(400, "VALIDATION_FAILED", "Missing refreshed access token")

    ts = now_iso()
    last_refresh = first_non_blank(profile.get("last_refresh"), payload.get("timestamp"), ts)
    with db() as con:
        existing = con.execute(
            """
            select s.id, s.concurrent_limit, p.base_url, p.model, p.reasoning_effort
            from openai_services s
            join openai_codex_profiles p on p.openai_service_id = s.id
            where p.profile_name = ?
            order by s.id
            limit 1
            """,
            (profile_name,),
        ).fetchone()

        base_url = first_non_blank(
            profile.get("base_url"),
            existing["base_url"] if existing else None,
            "https://chatgpt.com/backend-api/codex",
        )
        model = first_non_blank(profile.get("model"), existing["model"] if existing else None, "gpt-5.5")
        reasoning_effort = first_non_blank(
            profile.get("reasoning_effort"),
            existing["reasoning_effort"] if existing else None,
            "high",
        )
        service_token = access_token or openai_key or ""

        if existing:
            service_id = existing["id"]
            con.execute(
                "update openai_services set api_endpoint = ?, token = ?, updated_at = ? where id = ?",
                (base_url, service_token, ts, service_id),
            )
        else:
            cur = insert_with_next_integer_id(
                con,
                "openai_services",
                {
                    "api_endpoint": base_url,
                    "token": service_token,
                    "concurrent_limit": 20,
                    "enabled": 1,
                    "created_at": ts,
                    "updated_at": ts,
                },
            )
            service_id = cur.lastrowid

        insert_with_next_integer_id(
            con,
            "openai_codex_profiles",
            {
                "openai_service_id": service_id,
                "profile_name": profile_name,
                "auth_mode": first_non_blank(profile.get("auth_mode"), "chatgpt"),
                "openai_api_key": openai_key,
                "access_token": access_token,
                "account_id": first_non_blank(tokens.get("account_id"), profile.get("account_id")),
                "id_token": first_non_blank(tokens.get("id_token"), profile.get("id_token")),
                "refresh_token": first_non_blank(tokens.get("refresh_token"), profile.get("refresh_token")),
                "client_id": first_non_blank(profile.get("client_id")),
                "base_url": base_url,
                "model": model,
                "reasoning_effort": reasoning_effort,
                "last_refresh": last_refresh,
                "created_at": ts,
                "updated_at": ts,
            },
            """
            on conflict(openai_service_id) do update set
              profile_name=excluded.profile_name, auth_mode=excluded.auth_mode,
              openai_api_key=excluded.openai_api_key, access_token=excluded.access_token,
              account_id=excluded.account_id, id_token=excluded.id_token,
              refresh_token=excluded.refresh_token, client_id=excluded.client_id, base_url=excluded.base_url,
              model=excluded.model, reasoning_effort=excluded.reasoning_effort,
              last_refresh=excluded.last_refresh, updated_at=excluded.updated_at
            """,
        )

    invalidate_proxy_context_cache()
    codex_proxy_logger.info("synced Codex profile %s from refresh notification", profile_name)
    return {"profileName": profile_name, "openAiServiceId": service_id, "cacheInvalidated": True}


@app.post("/api/internal/codex-profile-refresh")
@db_write_api
async def internal_codex_profile_refresh_sync(
    request: Request,
    x_codex_sync_secret: str | None = Header(default=None),
) -> dict[str, Any]:
    if RELAY_CODEX_SYNC_SECRET and not hmac.compare_digest(x_codex_sync_secret or "", RELAY_CODEX_SYNC_SECRET):
        raise AppError(403, "FORBIDDEN", "Invalid Codex sync secret")
    payload = await request.json()
    if not isinstance(payload, dict):
        raise AppError(400, "VALIDATION_FAILED", "Invalid Codex profile payload")
    result = await run_in_threadpool(sync_codex_profile_refresh_payload_sync, payload)
    return api_ok(result)


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
            where s.enabled = 1
            order by s.id
            """
        ).fetchall()
        upstreams = [row_to_dict(row) for row in rows]
        for upstream in upstreams:
            upstream["_mode2_round_robin"] = True
        return upstreams
    elif mode == 3:
        batch_size = positive_int(setting(con, "openai.mode3_batch_size", "8"), 8)
        rows = con.execute(
            """
            select s.*, p.profile_name, p.auth_mode, p.openai_api_key, p.access_token,
                   p.account_id, p.id_token, p.refresh_token, p.client_id,
                   p.base_url as profile_base_url, p.model, p.reasoning_effort,
                   r.sort_order as mode3_sort_order
            from openai_mode3_services r
            join openai_services s on s.id = r.openai_service_id
            left join openai_codex_profiles p on p.openai_service_id = s.id
            where r.enabled = 1
              and s.enabled = 1
            order by r.sort_order, r.id, s.id
            """
        ).fetchall()
        upstreams = [row_to_dict(row) for row in rows]
        for upstream in upstreams:
            upstream["_mode3_rotation"] = True
            upstream["_mode3_batch_size"] = batch_size
        return upstreams
    elif mode == 4:
        rows = con.execute(
            """
            select s.*, p.profile_name, p.auth_mode, p.openai_api_key, p.access_token,
                   p.account_id, p.id_token, p.refresh_token, p.client_id,
                   p.base_url as profile_base_url, p.model, p.reasoning_effort,
                   r.model as mode4_model
            from openai_mode4_services r
            join openai_services s on s.id = r.openai_service_id
            left join openai_codex_profiles p on p.openai_service_id = s.id
            where s.enabled = 1
              and trim(r.model) <> ''
            order by r.openai_service_id
            """
        ).fetchall()
        upstreams = [row_to_dict(row) for row in rows]
        for upstream in upstreams:
            upstream["_mode2_round_robin"] = True
        return upstreams
    else:
        rows = con.execute(
            """
            select s.*
            from openai_services s
            where s.enabled = 1
              and not exists (
                select 1
                from openai_codex_profiles p
                where p.openai_service_id = s.id
              )
            order by s.id
            """
        ).fetchall()
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
    return client_type == "CODEX" and status_code in {401, 402, 403, 429}


def is_retryable_quota_error(status_code: int, body: bytes | None) -> bool:
    if status_code not in {401, 402, 403, 429}:
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
            mode4_model = str(upstream.get("mode4_model") or "").strip()
            if mode4_model:
                root["model"] = mode4_model
        elif client_type == "CLAUDE" and "token-plan-cn.xiaomimimo.com" in upstream_endpoint(upstream).lower():
            if isinstance(root.get("model"), str):
                root["model"] = root["model"].lower()
        return json.dumps(root, ensure_ascii=False, separators=(",", ":")).encode()
    except Exception:
        return body


async def normalize_upstream_body_async(
    body: bytes, upstream: dict[str, Any], client_type: str, event_stream: bool
) -> bytes:
    if not body:
        return body
    if client_type == "CODEX":
        return await run_in_threadpool(normalize_upstream_body, body, upstream, client_type, event_stream)
    return normalize_upstream_body(body, upstream, client_type, event_stream)


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
    await run_in_threadpool(stop_codex_instructions_watcher)
    await run_in_threadpool(stop_codex_profile_refresh_worker)
    stop_codex_user_message_executor()


def codex_default_instructions() -> str | None:
    with _codex_instructions_lock:
        return _codex_default_instructions_cache[1]


def refresh_codex_default_instructions_cache(force: bool = False) -> str | None:
    global _codex_default_instructions_cache
    with _codex_instructions_lock:
        cached_mtime, cached_value = _codex_default_instructions_cache
    try:
        mtime = CODEX_PROFILES_PATH.stat().st_mtime
    except OSError:
        with _codex_instructions_lock:
            _codex_default_instructions_cache = (None, None)
        return None
    if not force and cached_mtime == mtime:
        return cached_value
    try:
        data = json.loads(CODEX_PROFILES_PATH.read_text(encoding="utf-8-sig"))
        defaults = data.get("request_defaults") if isinstance(data, dict) else None
        instructions = defaults.get("instructions") if isinstance(defaults, dict) else None
        value = instructions.strip() if isinstance(instructions, str) and instructions.strip() else None
    except Exception:
        value = None
    with _codex_instructions_lock:
        _codex_default_instructions_cache = (mtime, value)
    return value


def codex_instructions_watch_loop() -> None:
    refresh_codex_default_instructions_cache(force=True)
    while not _codex_instructions_stop.wait(CODEX_INSTRUCTIONS_REFRESH_INTERVAL):
        refresh_codex_default_instructions_cache()


def start_codex_instructions_watcher() -> None:
    with _codex_instructions_thread_lock:
        global _codex_instructions_thread
        if _codex_instructions_thread and _codex_instructions_thread.is_alive():
            return
        _codex_instructions_stop.clear()
        _codex_instructions_thread = threading.Thread(
            target=codex_instructions_watch_loop,
            name="relay-codex-instructions",
            daemon=True,
        )
        _codex_instructions_thread.start()


def stop_codex_instructions_watcher() -> None:
    with _codex_instructions_thread_lock:
        thread = _codex_instructions_thread
        _codex_instructions_stop.set()
    if thread and thread.is_alive():
        thread.join(timeout=5)


def parse_codex_refresh_time(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def codex_profile_refresh_due(last_refresh: Any, now: datetime | None = None) -> bool:
    refreshed_at = parse_codex_refresh_time(last_refresh)
    if refreshed_at is None:
        return True
    current = now or datetime.now(timezone.utc)
    return refreshed_at <= current - timedelta(days=CODEX_PROFILE_REFRESH_INTERVAL_DAYS)


def codex_profile_refresh_enabled() -> bool:
    try:
        with db() as con:
            return bool_setting(con, CODEX_PROFILE_REFRESH_ENABLED_SETTING, False)
    except sqlite3.Error:
        return False


def load_due_codex_profiles_sync() -> list[dict[str, Any]]:
    now = datetime.now(timezone.utc)
    with db() as con:
        rows = con.execute(
            """
            select s.*, p.profile_name, p.auth_mode, p.openai_api_key, p.access_token,
                   p.account_id, p.id_token, p.refresh_token, p.client_id,
                   p.base_url as profile_base_url, p.model, p.reasoning_effort,
                   p.last_refresh
            from openai_services s
            join openai_codex_profiles p on p.openai_service_id = s.id
            where s.enabled = 1
            order by s.id
            """
        ).fetchall()
    return [row_to_dict(row) for row in rows if codex_profile_refresh_due(row["last_refresh"], now)]


def append_codex_profile_refresh_log(event: dict[str, Any]) -> None:
    try:
        CODEX_PROFILE_REFRESH_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with CODEX_PROFILE_REFRESH_LOG_PATH.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n")
    except Exception:
        codex_proxy_logger.exception("failed to write Codex profile refresh log")


def refresh_codex_profile_with_log_sync(upstream: dict[str, Any], reason: str) -> bool:
    status_code: int | None = None
    message = "refreshed"
    success = False
    try:
        success = refresh_codex_profile_sync(upstream, reason=reason)
        if success:
            status_code = 200
        if not success:
            message = "refresh returned no access_token or missing required fields"
    except Exception as exc:
        status_code = getattr(exc, "code", None)
        message = f"{exc.__class__.__name__}: {truncate(str(exc), 500)}"
        codex_proxy_logger.warning(
            "failed to refresh Codex profile %s during %s: %s",
            upstream.get("profile_name") or upstream.get("id"),
            reason,
            exc,
        )
    append_codex_profile_refresh_log(
        {
            "timestamp": now_iso(),
            "event": "codex_profile_refresh",
            "reason": reason,
            "profileName": upstream.get("profile_name"),
            "openAiServiceId": upstream.get("id"),
            "previousLastRefresh": upstream.get("last_refresh"),
            "success": success,
            "statusCode": status_code,
            "message": message,
            "logFile": str(CODEX_PROFILE_REFRESH_LOG_PATH),
        }
    )
    return success


def codex_profile_refresh_loop() -> None:
    if _codex_profile_refresh_stop.wait(CODEX_PROFILE_REFRESH_INITIAL_DELAY_SECONDS):
        return
    while not _codex_profile_refresh_stop.is_set():
        try:
            if not codex_profile_refresh_enabled():
                codex_proxy_logger.debug("scheduled Codex profile refresh is disabled")
                if _codex_profile_refresh_stop.wait(CODEX_PROFILE_REFRESH_SCAN_INTERVAL_SECONDS):
                    break
                continue
            profiles = load_due_codex_profiles_sync()
            success_count = 0
            for upstream in profiles:
                if _codex_profile_refresh_stop.is_set():
                    break
                if refresh_codex_profile_with_log_sync(upstream, "scheduled 6-day refresh"):
                    success_count += 1
            if profiles:
                codex_proxy_logger.info(
                    "scheduled Codex profile refresh complete due=%s success=%s failure=%s log=%s",
                    len(profiles),
                    success_count,
                    len(profiles) - success_count,
                    CODEX_PROFILE_REFRESH_LOG_PATH,
                )
        except Exception:
            codex_proxy_logger.exception("scheduled Codex profile refresh scan failed")
        if _codex_profile_refresh_stop.wait(CODEX_PROFILE_REFRESH_SCAN_INTERVAL_SECONDS):
            break


def start_codex_profile_refresh_worker() -> None:
    with _codex_profile_refresh_thread_lock:
        global _codex_profile_refresh_thread
        if _codex_profile_refresh_thread and _codex_profile_refresh_thread.is_alive():
            return
        _codex_profile_refresh_stop.clear()
        _codex_profile_refresh_thread = threading.Thread(
            target=codex_profile_refresh_loop,
            name="relay-codex-profile-refresh",
            daemon=True,
        )
        _codex_profile_refresh_thread.start()


def stop_codex_profile_refresh_worker() -> None:
    with _codex_profile_refresh_thread_lock:
        thread = _codex_profile_refresh_thread
        _codex_profile_refresh_stop.set()
    if thread and thread.is_alive():
        thread.join(timeout=5)


def refresh_codex_profile_sync(upstream: dict[str, Any], reason: str = "upstream 401") -> bool:
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
        codex_proxy_logger.info("refreshed Codex profile %s after %s", profile_name or service_id, reason)
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
    refreshed = await run_in_threadpool(refresh_codex_profile_with_log_sync, upstream, "upstream 401")
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
atexit.register(stop_codex_user_message_executor)


@app.on_event("startup")
async def start_proxy_log_writer() -> None:
    proxy_log_writer.start()
    await run_in_threadpool(start_codex_instructions_watcher)
    await run_in_threadpool(start_codex_profile_refresh_worker)


def enqueue_proxy_log_event(event: ProxyLogEvent) -> None:
    proxy_log_writer.submit(event)


def billing_catalog(con: sqlite3.Connection) -> tuple[dict[str, dict[str, Any]], Decimal, Decimal]:
    global _billing_catalog_cache
    now = time.monotonic()
    if _billing_catalog_cache and _billing_catalog_cache[0] > now:
        return _billing_catalog_cache[1], _billing_catalog_cache[2], _billing_catalog_cache[3]
    rows = con.execute("select * from model_catalog where enabled = 1").fetchall()
    prices = {row["id"]: row_to_dict(row) for row in rows}
    multiplier = parse_decimal(setting(con, "billing.cost_multiplier", "1.2"))
    cache_read_factor = positive_decimal(setting(con, "billing.cache_read_token_factor", "0.8"), Decimal("0.8"))
    _billing_catalog_cache = (now + PROXY_BILLING_CACHE_TTL, prices, multiplier, cache_read_factor)
    return prices, multiplier, cache_read_factor


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


def apply_cache_read_token_factor(usage: dict[str, Any], factor: Decimal) -> dict[str, Any]:
    adjusted = int((Decimal(usage["cache_read"]) * factor).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    adjusted = max(0, adjusted)
    return {**usage, "cache_read": adjusted}


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
    prices, multiplier, cache_read_factor = billing_catalog(con)
    rows: list[tuple[Any, ...]] = []
    balance_deltas: dict[str, Decimal] = {}
    next_balances: dict[str, Decimal] = {}
    for event in events:
        usage = apply_cache_read_token_factor(parse_usage(event.request_body, event.response_body), cache_read_factor)
        key_multiplier = api_key_cost_multiplier(event.api_key)
        cost = calculate_cost_value(usage, price_for_model(prices, usage.get("model")), multiplier * key_multiplier)
        detail = compact_proxy_log_detail(event, usage)
        rows.append(
            (
                event.api_key["user_id"],
                event.api_key["id"],
                event.api_key["name"] or display_key(event.api_key["key_hash"]),
                event.api_key.get("billing_group") or event.api_key["key_value"] or display_key(event.api_key["key_hash"]),
                "usage",
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

    columns = [
        "user_id",
        "api_key_id",
        "token_name",
        "group_key",
        "request_type",
        "client_type",
        "model",
        "use_time_ms",
        "first_token_ms",
        "prompt_tokens",
        "completion_tokens",
        "cache_read_tokens",
        "cache_creation_tokens",
        "cost",
        "ip",
        "status",
        "upstream_service_id",
        "detail",
        "created_at",
    ]
    columns, rows = with_next_integer_ids(con, "request_logs", columns, rows)
    con.executemany(
        f"""
        insert into request_logs
          ({', '.join(quote_ident(column) for column in columns)})
        values ({', '.join('?' for _ in columns)})
        """,
        rows,
    )
    for user_id, delta in balance_deltas.items():
        next_balances[user_id] = add_balance(con, user_id, delta, update_cache=False)
    con.commit()
    for user_id, balance in next_balances.items():
        store_cached_balance(user_id, balance)


def api_key_cost_multiplier(api_key: dict[str, Any]) -> Decimal:
    try:
        multiplier = parse_decimal(api_key.get("cost_multiplier") or "1")
    except Exception:
        return Decimal("1")
    return multiplier if multiplier > 0 else Decimal("1")


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
    _prices, multiplier, cache_read_factor = billing_catalog(con)
    usage = apply_cache_read_token_factor(usage, cache_read_factor)
    return calculate_cost_value(usage, price, multiplier)


MODEL_DATE_SUFFIX_RE = re.compile(r"-20\d{2}-\d{1,2}-\d{1,2}$")


def price_for_model(prices: dict[str, dict[str, Any]], model: Any) -> dict[str, Any] | None:
    model_id = str(model or "").strip()
    if not model_id:
        return None
    if model_id in prices:
        return prices[model_id]
    normalized = MODEL_DATE_SUFFIX_RE.sub("", model_id)
    if normalized != model_id:
        return prices.get(normalized)
    return None


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


def positive_decimal(value: str | None, fallback: Decimal) -> Decimal:
    try:
        parsed = parse_decimal(value)
        return parsed if parsed > 0 else fallback
    except Exception:
        return fallback


def positive_int(value: Any, fallback: int) -> int:
    try:
        parsed = int(value)
        return parsed if parsed > 0 else fallback
    except Exception:
        return fallback


def bool_setting(con: sqlite3.Connection, key: str, default: bool) -> bool:
    raw = setting(con, key, "true" if default else "false")
    return str(raw).strip().lower() not in {"0", "false", "no", "off", ""}


def boolish(value: Any) -> bool:
    return str(value or "").strip().lower() not in {"", "0", "false", "no", "off", "none", "null"}


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
