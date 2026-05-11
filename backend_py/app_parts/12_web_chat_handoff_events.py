def fetch_websocket_url(config: dict[str, Any], conversation_id: str | None) -> str:
    path = "/backend-api/celsius/ws/user"
    url = trim_slash(config.get("base_url") or "https://chatgpt.com") + path
    with httpx.Client(timeout=30) as client:
        response = client.get(url, headers=web_headers(config, path, conversation_id, "*/*"))
    if response.status_code < 200 or response.status_code >= 300:
        raise AppError(502, "INTERNAL_ERROR", truncate(response.text or f"WebSocket URL HTTP {response.status_code}", 1000))
    try:
        ws_url = response.json().get("websocket_url")
    except Exception as exc:
        raise AppError(502, "INTERNAL_ERROR", "Unable to parse web chat websocket response") from exc
    if not isinstance(ws_url, str) or not ws_url.startswith(("ws://", "wss://")):
        raise AppError(502, "INTERNAL_ERROR", "websocket_url missing from upstream response")
    return ws_url


def read_handoff_topic_stream(
    config: dict[str, Any],
    topic_id: str,
    conversation_id: str | None,
    initial_answer: str,
) -> Iterable[dict[str, Any]]:
    try:
        from websockets.sync.client import connect
    except Exception as exc:
        raise AppError(502, "INTERNAL_ERROR", "websockets package is required for stream handoff") from exc

    ws_url = fetch_websocket_url(config, conversation_id)
    answer = initial_answer or ""
    assistant_id = None
    subscribe = json.dumps(websocket_subscribe_frame(topic_id), ensure_ascii=False, separators=(",", ":"))
    try:
        with connect(
            ws_url,
            origin=trim_slash(config.get("base_url") or "https://chatgpt.com"),
            additional_headers=websocket_headers(config),
            user_agent_header=first_non_blank(config.get("user_agent"), DEFAULT_USER_AGENT),
            open_timeout=30,
            ping_interval=20,
            ping_timeout=20,
            max_size=None,
        ) as websocket:
            websocket.send(subscribe)
            deadline = time.monotonic() + 180
            while time.monotonic() < deadline:
                try:
                    text = websocket.recv(timeout=max(1, min(30, int(deadline - time.monotonic()))))
                except TimeoutError:
                    continue
                if not text or topic_id not in str(text):
                    continue
                try:
                    message = json.loads(text)
                except Exception:
                    message = text
                result = handle_handoff_message(message, answer, config)
                next_answer = result["answer"]
                assistant_id = result.get("assistantMessageId") or assistant_id
                extras = {
                    "images": result.get("images") or [],
                    "webImageCandidates": result.get("webImageCandidates") or [],
                    "webSources": result.get("webSources") or [],
                }
                if next_answer != answer:
                    if next_answer.startswith(answer):
                        delta = next_answer[len(answer) :]
                        answer = next_answer
                        if delta:
                            yield {
                                "type": "delta",
                                "delta": delta,
                                "answer": answer,
                                "assistantMessageId": assistant_id,
                                **extras,
                            }
                    else:
                        answer = next_answer
                        yield {"type": "replace", "answer": answer, "assistantMessageId": assistant_id, **extras}
                elif extras["images"] or extras["webImageCandidates"] or extras["webSources"]:
                    yield {"type": "image", "answer": answer, "assistantMessageId": assistant_id, **extras}
                if result["done"]:
                    yield {"type": "done", "answer": answer, "assistantMessageId": assistant_id, **extras}
                    return
    except AppError:
        raise
    except Exception as exc:
        raise AppError(502, "INTERNAL_ERROR", f"Unable to read web chat WebSocket response: {exception_summary(exc)}") from exc
    yield {"type": "done", "answer": answer, "assistantMessageId": assistant_id}


def websocket_headers(config: dict[str, Any]) -> dict[str, str]:
    headers: dict[str, str] = {
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "oai-client-build-number": first_non_blank(config.get("oai_client_build_number"), DEFAULT_OAI_CLIENT_BUILD_NUMBER),
        "oai-client-version": first_non_blank(config.get("oai_client_version"), DEFAULT_OAI_CLIENT_VERSION),
    }
    auth = first_non_blank(config.get("auth_header"))
    if not auth and config.get("bearer_token"):
        token = str(config["bearer_token"]).strip()
        auth = token if token.lower().startswith("bearer ") else f"Bearer {token}"
    optional = {
        "Authorization": auth,
        "chatgpt-account-id": config.get("account_id"),
        "Cookie": config.get("cookie"),
        "oai-device-id": config.get("oai_device_id"),
        "oai-session-id": config.get("oai_session_id"),
        "openai-sentinel-chat-requirements-token": config.get("sentinel_token"),
        "x-oai-is": config.get("oai_is"),
    }
    for key, value in optional.items():
        if value and not str(value).startswith("PASTE_"):
            headers[key] = str(value)
    return headers


def websocket_subscribe_frame(topic_id: str) -> list[dict[str, Any]]:
    offset = f"{int((time.time() - 30) * 1000)}-0"
    return [
        {"id": 1, "command": {"type": "connect", "presence": {"type": "presence", "state": "background"}}},
        {"id": 2, "command": {"type": "subscribe", "topic_id": "conversations"}},
        {"id": 3, "command": {"type": "subscribe", "topic_id": "app_notifications"}},
        {"id": 4, "command": {"type": "subscribe", "topic_id": topic_id, "offset": offset}},
    ]


def handle_handoff_message(message: Any, answer: str, config: dict[str, Any]) -> dict[str, Any]:
    done = False
    assistant_id = None
    images: list[dict[str, Any]] = []
    web_candidates: list[dict[str, str]] = []
    web_sources: list[dict[str, Any]] = []
    for encoded in extract_encoded_items(message):
        for event in parse_encoded_sse(encoded):
            if event == "[DONE]":
                done = True
                continue
            if not isinstance(event, dict):
                continue
            for image in collect_generated_images(event, config):
                append_unique_image(images, image)
            web_candidates.extend(collect_web_image_candidates(event))
            for source in collect_web_sources(event):
                append_unique_source(web_sources, source)
            assistant_id = extract_assistant_message_id(event) or assistant_id
            next_answer = apply_event(answer, event)
            if next_answer is not None:
                answer = next_answer
            if get_text(event, "type") in DONE_TYPES:
                done = True
    if is_ws_done_message(message):
        done = True
    return {
        "answer": answer,
        "done": done,
        "assistantMessageId": assistant_id,
        "images": images,
        "webImageCandidates": web_candidates,
        "webSources": web_sources,
    }


def extract_encoded_items(message: Any) -> list[str]:
    items: list[str] = []

    def walk(node: Any, key: str | None = None) -> None:
        if key == "encoded_item" and isinstance(node, str):
            items.append(node)
            return
        if key is None and isinstance(node, str) and "data:" in node:
            items.append(node)
            return
        if isinstance(node, list):
            for child in node:
                walk(child)
        elif isinstance(node, dict):
            for child_key, child_value in node.items():
                walk(child_value, child_key)

    walk(message)
    return items


def parse_encoded_sse(encoded_item: str) -> list[Any]:
    events: list[Any] = []
    data_lines: list[str] = []

    def flush() -> None:
        nonlocal data_lines
        if not data_lines:
            return
        data = "\n".join(data_lines)
        if data == "[DONE]":
            events.append("[DONE]")
        else:
            try:
                events.append(json.loads(data))
            except Exception:
                pass
        data_lines = []

    for raw_line in encoded_item.splitlines():
        line = raw_line.strip()
        if not line:
            flush()
        elif line.startswith("data:"):
            data_lines.append(line[5:].strip())
    flush()
    return events


def is_ws_done_message(message: Any) -> bool:
    if not isinstance(message, list):
        return False
    for item in message:
        if not isinstance(item, dict):
            continue
        nested = item.get("payload", {}).get("payload") if isinstance(item.get("payload"), dict) else None
        if isinstance(nested, dict) and nested.get("type") == "done":
            return True
    return False


def extract_topic_id(event: Any) -> str | None:
    if not isinstance(event, dict):
        return None
    direct = get_text(event, "topic_id")
    if direct:
        return direct
    options = event.get("options")
    if isinstance(options, list):
        for option in options:
            if isinstance(option, dict) and option.get("topic_id"):
                return str(option["topic_id"])
    return topic_id_from_resume_token(get_text(event, "resume_token") or get_text(event, "token"))


def topic_id_from_resume_token(token: str | None) -> str | None:
    if not token:
        return None
    parts = token.split(".")
    if len(parts) < 2:
        return None
    try:
        payload = json.loads(b64url_decode(parts[1]))
        return first_non_blank(payload.get("turn_topic_id"), payload.get("topic_id"))
    except Exception:
        return None


def parse_sse_data_line(line: str | bytes | None) -> Any:
    if line is None:
        return None
    if isinstance(line, bytes):
        line = line.decode("utf-8", "replace")
    line = line.strip()
    if not line.startswith("data:"):
        return None
    data = line[5:].strip()
    if not data:
        return None
    if data == "[DONE]":
        return "[DONE]"
    try:
        return json.loads(data)
    except Exception:
        return None


def get_text(node: Any, key: str) -> str | None:
    if not isinstance(node, dict):
        return None
    value = node.get(key)
    if value is None or isinstance(value, (dict, list)):
        return None
    text = str(value)
    return text if text else None


def apply_event(answer: str, event: Any) -> str | None:
    if not isinstance(event, dict):
        return answer
    event_type = get_text(event, "type")
    if event_type in TEXT_DELTA_TYPES:
        return answer + (get_text(event, "delta") or "")
    if event_type in TEXT_DONE_TYPES:
        return merge_full_text(answer, get_text(event, "text"))
    if event_type == "response.content_part.done":
        part = event.get("part") if isinstance(event.get("part"), dict) else {}
        return merge_full_text(answer, get_text(part, "text"))
    if event_type in {"response.output_item.done", "response.function_call_arguments.done"}:
        return merge_full_text(answer, extract_output_item_text(event.get("item")))
    if event_type == "response.completed":
        response = event.get("response") if isinstance(event.get("response"), dict) else {}
        return merge_full_text(answer, extract_output_text(response.get("output")))
    full = extract_assistant_message_text(event)
    if full is not None:
        return merge_full_text(answer, full)
    if is_patch_operation(event) and event.get("o") != "patch":
        return apply_patch_operation(answer, event)
    value = event.get("v")
    if isinstance(value, str) and not is_patch_operation(event):
        return answer + value
    if isinstance(value, list):
        updated = answer
        for item in value:
            if is_patch_operation(item):
                updated = apply_patch_operation(updated, item)
        return updated
    return answer


def extract_output_text(output: Any) -> str | None:
    if not isinstance(output, list):
        return None
    parts = [text for item in output if (text := extract_output_item_text(item)) is not None]
    return "".join(parts) if parts else None


def extract_output_item_text(item: Any) -> str | None:
    if not isinstance(item, dict):
        return None
    if isinstance(item.get("text"), str):
        return item["text"]
    content = item.get("content")
    if not isinstance(content, list):
        return None
    parts = []
    for part in content:
        if isinstance(part, dict) and part.get("type") in OUTPUT_TEXT_TYPES and isinstance(part.get("text"), str):
            parts.append(part["text"])
    return "".join(parts) if parts else None


def extract_assistant_message_text(event: dict[str, Any]) -> str | None:
    candidates = []
    if isinstance(event.get("message"), dict):
        candidates.append(event["message"])
    value_message = event.get("v", {}).get("message") if isinstance(event.get("v"), dict) else None
    if isinstance(value_message, dict):
        candidates.append(value_message)
    for candidate in candidates:
        role = candidate.get("author", {}).get("role") if isinstance(candidate.get("author"), dict) else None
        if role and role != "assistant":
            continue
        parts = candidate.get("content", {}).get("parts") if isinstance(candidate.get("content"), dict) else None
        if isinstance(parts, list) and parts and isinstance(parts[0], str):
            return parts[0]
    return None


def extract_assistant_message_id(event: dict[str, Any]) -> str | None:
    if not isinstance(event, dict):
        return None
    for path in [("response", "id"), ("item", "id")]:
        node = event.get(path[0])
        if isinstance(node, dict) and node.get(path[1]):
            return str(node[path[1]])
    for key in ["item_id", "message_id"]:
        if event.get(key):
            return str(event[key])
    message = event.get("message")
    if isinstance(message, dict) and message.get("id"):
        return str(message["id"])
    return None


def is_patch_operation(value: Any) -> bool:
    return isinstance(value, dict) and isinstance(value.get("p"), str) and isinstance(value.get("o"), str)


def apply_patch_operation(answer: str, op: dict[str, Any]) -> str:
    path = op.get("p")
    operation = op.get("o")
    value = op.get("v")
    if path == "/message/content/parts/0" and isinstance(value, str):
        if operation == "append":
            return answer + value
        if operation in {"replace", "add"}:
            return merge_full_text(answer, value)
    if path == "/message/content/parts" and operation in {"replace", "add"} and isinstance(value, list) and value and isinstance(value[0], str):
        return merge_full_text(answer, value[0])
    if path == "/message" and operation in {"replace", "add"} and isinstance(value, dict):
        return merge_full_text(answer, extract_assistant_message_text({"message": value}))
    return answer


def merge_full_text(answer: str, full_text: str | None) -> str:
    if not full_text:
        return answer
    if not answer or full_text.startswith(answer):
        return full_text
    if answer.endswith(full_text):
        return answer
    return answer + "\n\n" + full_text


def is_done_event(event: Any) -> bool:
    return isinstance(event, dict) and event.get("type") in DONE_TYPES


