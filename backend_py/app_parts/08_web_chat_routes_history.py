@app.get("/api/web-chat/session")
@db_write_api
def web_chat_session(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    return api_ok(session_response(find_or_create_web_session(current_user_id(authorization))))


@app.post("/api/web-chat/conversation/reset")
@db_write_api
def reset_web_chat(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    user_id = current_user_id(authorization)
    session = find_or_create_web_session(user_id)
    with db() as con:
        con.execute(
            """
            update web_chat_user_sessions
            set conversation_id = null, parent_message_id = ?, updated_at = ?
            where user_id = ?
            """,
            (ROOT_PARENT_MESSAGE_ID, now_iso(), user_id),
        )
    session["conversation_id"] = None
    session["parent_message_id"] = ROOT_PARENT_MESSAGE_ID
    return api_ok(session_response(session))


@app.post("/api/web-chat/messages")
@db_write_api
def web_chat_message(payload: WebChatMessageRequest, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    user_id = current_user_id(authorization)
    result = send_web_chat_turn(user_id, payload, None)
    return api_ok(result)


@app.post("/api/web-chat/messages/stream")
@db_write_api
async def web_chat_message_stream(
    payload: WebChatMessageRequest,
    authorization: str | None = Header(default=None),
) -> StreamingResponse:
    user_id = current_user_id(authorization)

    def generate() -> Iterable[str]:
        try:
            stream = stream_web_chat_turn(user_id, payload)
            result = None
            for item in stream:
                if isinstance(item, str):
                    yield item
                else:
                    result = item
            if result is None:
                raise AppError(502, "INTERNAL_ERROR", "Web chat stream ended without a response")
            yield sse_event("done", result)
        except Exception as exc:
            message = exc.message if isinstance(exc, AppError) else str(exc)
            yield sse_event("error", {"message": message})

    return StreamingResponse(
        stream_in_dedicated_thread(generate, name="web-chat-stream"),
        media_type="text/event-stream",
    )


@app.get("/api/web-chat/images/{config_id}/{file_id}")
def web_chat_generated_image(config_id: int, file_id: str, token: str) -> Response:
    verify_web_chat_image_token(config_id, file_id, token)
    with db() as con:
        config = con.execute("select * from web_chat_model_configs where id = ?", (config_id,)).fetchone()
    if not config:
        raise AppError(404, "NOT_FOUND", "Web chat image config not found")
    content, media_type = download_generated_web_image(row_to_dict(config), file_id)
    return Response(content=content, media_type=media_type)


@app.get("/api/web-chat/history")
def chat_history(page: int = 1, size: int = 20, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    user_id = current_user_id(authorization)
    page = max(1, page)
    size = max(1, min(size, 50))
    offset = (page - 1) * size
    with db() as con:
        total = con.execute("select count(*) from web_chat_history_files where user_id = ?", (user_id,)).fetchone()[0]
        rows = con.execute(
            """
            select * from web_chat_history_files
            where user_id = ?
            order by updated_at desc, sequence desc
            limit ? offset ?
            """,
            (user_id, size, offset),
        ).fetchall()
    return api_ok(
        {
            "items": [chat_history_file_response(row) for row in rows],
            "page": page,
            "size": size,
            "total": total,
            "hasMore": offset + len(rows) < total,
        }
    )


@app.get("/api/web-chat/history/{turn_id}")
def chat_history_detail(turn_id: int, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    user_id = current_user_id(authorization)
    with db() as con:
        row = con.execute(
            "select * from web_chat_history_files where id = ? and user_id = ?", (turn_id, user_id)
        ).fetchone()
    if not row:
        raise AppError(404, "NOT_FOUND", "Chat history not found")
    content = github_read_file_content(
        GITHUB_CHAT_HISTORY_REPOSITORY,
        GITHUB_CHAT_HISTORY_BRANCH,
        GITHUB_CHAT_HISTORY_TOKEN,
        row["object_key"],
        "chat history",
        row["content_url"],
    )
    return api_ok({"file": chat_history_file_response(row), "turns": parse_chat_history_turns(content)})


def chat_history_file_response(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "sequence": row["sequence"],
        "objectKey": row["object_key"],
        "contentUrl": row["content_url"],
        "sizeBytes": row["size_bytes"],
        "turnCount": row["turn_count"],
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
    }


def chat_history_object_key(user_id: str, sequence: int) -> str:
    base_path = trim_slashes(GITHUB_CHAT_HISTORY_BASE_PATH)
    prefix = f"{base_path}/" if base_path else ""
    return f"{prefix}{user_id}/{user_id}-{sequence:06d}.jsonl"


def image_history_documents(images: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for image in images or []:
        if not isinstance(image, dict):
            continue
        result.append(
            {
                "id": image.get("id"),
                "name": image.get("name"),
                "media_type": image.get("mediaType") or image.get("media_type"),
                "size": image.get("size"),
                "width": image.get("width"),
                "height": image.get("height"),
                "data": image.get("data"),
                "url": image.get("url"),
                "page_url": image.get("pageUrl") or image.get("page_url"),
                "source": image.get("source"),
            }
        )
    return result


def source_history_documents(sources: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for source in sources or []:
        if not isinstance(source, dict):
            continue
        result.append(
            {
                "title": source.get("title"),
                "url": source.get("url"),
                "attribution": source.get("attribution"),
                "snippet": source.get("snippet"),
                "pub_date": source.get("pubDate") or source.get("pub_date"),
            }
        )
    return result


def chat_history_turn_document(user_id: str, request_payload: WebChatMessageRequest, response: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(uuid.uuid4()),
        "created_at": now_iso(),
        "user_id": user_id,
        "conversation_id": response.get("conversationId"),
        "parent_message_id": response.get("parentMessageId"),
        "model": response.get("model"),
        "config_id": response.get("configId"),
        "config_name": response.get("configName"),
        "user": {
            "message": request_payload.message or "",
            "images": image_history_documents(request_payload.images),
        },
        "assistant": {
            "answer": response.get("answer") or "",
            "images": image_history_documents(response.get("images")),
            "sources": source_history_documents(response.get("sources")),
        },
    }


def parse_chat_history_turns(content: str) -> list[dict[str, Any]]:
    turns: list[dict[str, Any]] = []
    for line in (content or "").splitlines():
        if not line.strip():
            continue
        try:
            node = json.loads(line)
        except Exception:
            continue
        user = node.get("user") if isinstance(node.get("user"), dict) else {}
        assistant = node.get("assistant") if isinstance(node.get("assistant"), dict) else {}
        images = [history_image_response(image) for image in user.get("images") or [] if isinstance(image, dict)]
        assistant_images = [
            history_image_response(image)
            for image in assistant.get("images") or []
            if isinstance(image, dict)
        ]
        assistant_sources = [
            history_source_response(source)
            for source in assistant.get("sources") or []
            if isinstance(source, dict)
        ]
        turns.append(
            {
                "createdAt": node.get("created_at"),
                "conversationId": node.get("conversation_id"),
                "parentMessageId": node.get("parent_message_id"),
                "model": node.get("model"),
                "configName": node.get("config_name"),
                "userMessage": user.get("message"),
                "images": images,
                "assistantImages": assistant_images,
                "assistantSources": assistant_sources,
                "assistantAnswer": clean_web_answer(assistant.get("answer") or ""),
            }
        )
    turns.reverse()
    return turns


def history_image_response(image: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": image.get("id"),
        "name": image.get("name"),
        "mediaType": image.get("media_type") or image.get("mediaType"),
        "size": image.get("size"),
        "width": image.get("width"),
        "height": image.get("height"),
        "data": image.get("data"),
        "url": image.get("url"),
        "pageUrl": image.get("page_url") or image.get("pageUrl"),
        "source": image.get("source"),
    }


def history_source_response(source: dict[str, Any]) -> dict[str, Any]:
    return {
        "title": source.get("title"),
        "url": source.get("url"),
        "attribution": source.get("attribution"),
        "snippet": source.get("snippet"),
        "pubDate": source.get("pub_date") or source.get("pubDate"),
    }


def create_chat_history_file(con: sqlite3.Connection, user_id: str, sequence: int) -> sqlite3.Row:
    ts = now_iso()
    con.execute(
        """
        insert into web_chat_history_files
          (user_id, sequence, object_key, content_url, size_bytes, turn_count, created_at, updated_at)
        values (?, ?, ?, '', 0, 0, ?, ?)
        """,
        (user_id, sequence, chat_history_object_key(user_id, sequence), ts, ts),
    )
    return con.execute(
        "select * from web_chat_history_files where user_id = ? and sequence = ?", (user_id, sequence)
    ).fetchone()


def append_web_chat_history(
    con: sqlite3.Connection,
    user_id: str,
    request_payload: WebChatMessageRequest,
    response: dict[str, Any],
) -> None:
    if not CHAT_HISTORY_ENABLED:
        return
    line = json.dumps(chat_history_turn_document(user_id, request_payload, response), ensure_ascii=False) + "\n"
    line_bytes = len(line.encode("utf-8"))
    max_file_bytes = max(128 * 1024, CHAT_HISTORY_MAX_FILE_BYTES)
    target = con.execute(
        """
        select * from web_chat_history_files
        where user_id = ?
        order by sequence desc
        limit 1
        """,
        (user_id,),
    ).fetchone()
    if target is None or (int(target["size_bytes"] or 0) > 0 and int(target["size_bytes"]) + line_bytes > max_file_bytes):
        sequence = 1 if target is None else int(target["sequence"]) + 1
        target = create_chat_history_file(con, user_id, sequence)

    if github_is_configured(GITHUB_CHAT_HISTORY_REPOSITORY, GITHUB_CHAT_HISTORY_TOKEN):
        stored = github_read_json_file(
            GITHUB_CHAT_HISTORY_REPOSITORY,
            GITHUB_CHAT_HISTORY_BRANCH,
            GITHUB_CHAT_HISTORY_TOKEN,
            target["object_key"],
            "chat history",
        )
        current_content = (stored or {}).get("content") or ""
        sha = (stored or {}).get("sha") or None
    else:
        current_content = github_read_raw_file(target["content_url"], GITHUB_CHAT_HISTORY_TOKEN, "chat history") or ""
        sha = None
    if current_content and len(current_content.encode("utf-8")) + line_bytes > max_file_bytes:
        target = create_chat_history_file(con, user_id, int(target["sequence"]) + 1)
        current_content = ""
        sha = None

    written = github_write_file(
        GITHUB_CHAT_HISTORY_REPOSITORY,
        GITHUB_CHAT_HISTORY_BRANCH,
        GITHUB_CHAT_HISTORY_TOKEN,
        target["object_key"],
        current_content + line,
        f"Append web chat history {user_id}",
        "chat history",
        sha=sha,
    )
    con.execute(
        """
        update web_chat_history_files
        set content_url = ?, size_bytes = ?, turn_count = ?, updated_at = ?
        where id = ?
        """,
        (written["url"], written["size"], int(target["turn_count"] or 0) + 1, now_iso(), target["id"]),
    )

