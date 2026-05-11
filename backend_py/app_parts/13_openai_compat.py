def openai_error(status: int, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"error": {"message": message, "type": "relay_error", "code": "relay_error"}},
    )


def openai_messages_to_text(messages: Any) -> str:
    if not isinstance(messages, list):
        return ""
    parts: list[str] = []
    for message in messages:
        if not isinstance(message, dict):
            continue
        role = str(message.get("role") or "user")
        content = openai_content_to_text(message.get("content"))
        if content:
            parts.append(f"{role}: {content}" if role in {"system", "developer"} else content)
    return "\n\n".join(parts).strip()


def openai_content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if not isinstance(item, dict):
                continue
            if item.get("type") == "text" and isinstance(item.get("text"), str):
                parts.append(item["text"])
        return "\n".join(part.strip() for part in parts if part and part.strip())
    return ""


def openai_messages_to_images(messages: Any) -> list[dict[str, Any]]:
    images: list[dict[str, Any]] = []
    if not isinstance(messages, list):
        return images
    for message in messages:
        if not isinstance(message, dict):
            continue
        content = message.get("content")
        if not isinstance(content, list):
            continue
        for item in content:
            if not isinstance(item, dict) or item.get("type") != "image_url":
                continue
            image_url = item.get("image_url")
            url = image_url.get("url") if isinstance(image_url, dict) else image_url
            if isinstance(url, str) and url.strip():
                images.append({"url": url.strip(), "name": "image"})
    return images


def openai_chat_completion_response(model: str, answer: str) -> dict[str, Any]:
    completion_id = "chatcmpl-" + uuid.uuid4().hex
    created = int(time.time())
    return {
        "id": completion_id,
        "object": "chat.completion",
        "created": created,
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": answer},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }


def openai_chat_completion_stream(user_id: str, payload: WebChatMessageRequest, model: str) -> Iterable[str]:
    completion_id = "chatcmpl-" + uuid.uuid4().hex
    created = int(time.time())
    yield "data: " + json.dumps(
        {
            "id": completion_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": model,
            "choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}],
        },
        ensure_ascii=False,
        separators=(",", ":"),
    ) + "\n\n"
    try:
        for item in stream_web_chat_turn(user_id, payload):
            if isinstance(item, str):
                chunk = sse_data_from_line(item)
                if isinstance(chunk, dict) and isinstance(chunk.get("delta"), str) and chunk["delta"]:
                    yield "data: " + json.dumps(
                        {
                            "id": completion_id,
                            "object": "chat.completion.chunk",
                            "created": created,
                            "model": model,
                            "choices": [{"index": 0, "delta": {"content": chunk["delta"]}, "finish_reason": None}],
                        },
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ) + "\n\n"
    except Exception as exc:
        message = exc.message if isinstance(exc, AppError) else exception_summary(exc)
        yield "data: " + json.dumps({"error": {"message": message, "type": "relay_error", "code": "relay_error"}}, ensure_ascii=False) + "\n\n"
    yield "data: " + json.dumps(
        {
            "id": completion_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": model,
            "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
        },
        ensure_ascii=False,
        separators=(",", ":"),
    ) + "\n\n"
    yield "data: [DONE]\n\n"


def sse_data_from_line(line: str) -> Any:
    for text in line.splitlines():
        text = text.strip()
        if not text.startswith("data:"):
            continue
        data = text[5:].strip()
        if not data or data == "[DONE]":
            return None
        try:
            return json.loads(data)
        except Exception:
            return None
    return None


