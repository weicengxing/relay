def web_headers(config: dict[str, Any], path: str, conversation_id: str | None, accept: str, conduit: str | None = None) -> dict[str, str]:
    base = trim_slash(config.get("base_url") or "https://chatgpt.com")
    referer = f"{base}/c/{conversation_id}" if conversation_id else f"{base}/"
    headers = {
        "accept": accept,
        "content-type": "application/json",
        "origin": base,
        "referer": referer,
        "user-agent": first_non_blank(config.get("user_agent"), DEFAULT_USER_AGENT),
        "oai-language": "zh-CN",
        "oai-client-build-number": first_non_blank(config.get("oai_client_build_number"), DEFAULT_OAI_CLIENT_BUILD_NUMBER),
        "oai-client-version": first_non_blank(config.get("oai_client_version"), DEFAULT_OAI_CLIENT_VERSION),
        "x-openai-target-path": path,
        "x-openai-target-route": path,
    }
    auth = first_non_blank(config.get("auth_header"))
    if not auth and config.get("bearer_token"):
        token = str(config["bearer_token"]).strip()
        auth = token if token.lower().startswith("bearer ") else f"Bearer {token}"
    if auth:
        headers["authorization"] = auth
    for name, key in [
        ("ChatGPT-Account-ID", "account_id"),
        ("cookie", "cookie"),
        ("oai-device-id", "oai_device_id"),
        ("oai-session-id", "oai_session_id"),
        ("openai-sentinel-chat-requirements-token", "sentinel_token"),
        ("x-oai-is", "oai_is"),
    ]:
        value = config.get(key)
        if value and not str(value).startswith("PASTE_"):
            headers[name] = str(value)
    if conduit:
        headers["x-conduit-token"] = conduit
    headers["x-oai-turn-trace-id"] = str(uuid.uuid4())
    return headers


def prepare_web_turn(config: dict[str, Any], message: str, model: str, conversation_id: str | None, parent_id: str) -> str:
    payload: dict[str, Any] = {
        "action": "next",
        "fork_from_shared_post": False,
        "parent_message_id": parent_id,
        "model": model,
        "timezone_offset_min": -480,
        "timezone": "Asia/Shanghai",
        "conversation_mode": {"kind": "primary_assistant"},
        "system_hints": [],
        "supports_buffering": True,
        "supported_encodings": ["v1"],
        "client_contextual_info": {"app_name": "chatgpt.com"},
    }
    if conversation_id:
        payload["conversation_id"] = conversation_id
    else:
        payload["partial_query"] = {
            "id": str(uuid.uuid4()),
            "author": {"role": "user"},
            "content": {"content_type": "text", "parts": [message]},
        }
    data = send_web_json(config, "/backend-api/f/conversation/prepare", payload, conversation_id, "*/*")
    token = data.get("conduit_token") if isinstance(data, dict) else None
    if not token:
        raise AppError(502, "INTERNAL_ERROR", "Web chat prepare did not return conduit_token")
    return str(token)


def send_web_json(config: dict[str, Any], path: str, payload: dict[str, Any], conversation_id: str | None, accept: str) -> Any:
    url = trim_slash(config.get("base_url") or "https://chatgpt.com") + path
    with httpx.Client(timeout=120) as client:
        response = client.post(url, json=payload, headers=web_headers(config, path, conversation_id, accept))
    if response.status_code < 200 or response.status_code >= 300:
        raise AppError(502, "INTERNAL_ERROR", truncate(response.text or f"Web chat upstream HTTP {response.status_code}", 1000))
    try:
        return response.json()
    except Exception as exc:
        raise AppError(502, "INTERNAL_ERROR", "Unexpected web chat JSON response") from exc


def upload_web_images(config: dict[str, Any], images: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [upload_web_image(config, image) for image in images]


def upload_web_image(config: dict[str, Any], image: dict[str, Any]) -> dict[str, Any]:
    normalized = normalize_web_image(image)
    create_payload = {
        "file_name": normalized["name"],
        "file_size": normalized["size"],
        "use_case": "multimodal",
        "timezone_offset_min": -480,
        "reset_rate_limits": False,
        "store_in_library": True,
    }
    created = send_web_json(config, "/backend-api/files", create_payload, None, "application/json")
    file_id = created.get("file_id") if isinstance(created, dict) else None
    upload_url = created.get("upload_url") if isinstance(created, dict) else None
    if not isinstance(file_id, str) or not isinstance(upload_url, str):
        raise AppError(502, "INTERNAL_ERROR", "Unexpected image upload create response")
    upload_raw_web_image(config, upload_url, normalized["bytes"], normalized["mediaType"])
    library_file_id = process_uploaded_web_file(config, file_id, normalized["name"])
    return {
        "fileId": file_id,
        "libraryFileId": library_file_id,
        "name": normalized["name"],
        "mediaType": normalized["mediaType"],
        "size": normalized["size"],
        "width": normalized["width"],
        "height": normalized["height"],
    }


def normalize_web_image(image: dict[str, Any]) -> dict[str, Any]:
    media_type = str(image.get("mediaType") or image.get("media_type") or "").strip().lower()
    if media_type == "image/jpg":
        media_type = "image/jpeg"
    if media_type not in SUPPORTED_IMAGE_MEDIA_TYPES:
        raise AppError(400, "VALIDATION_FAILED", f"Unsupported image media type: {media_type or '<empty>'}")
    encoded = str(image.get("data") or "")
    if encoded.startswith("data:") and "," in encoded:
        encoded = encoded.split(",", 1)[1]
    try:
        image_bytes = base64.b64decode(re.sub(r"\s+", "", encoded), validate=True)
    except Exception as exc:
        raise AppError(400, "VALIDATION_FAILED", "Image data must be valid base64") from exc
    if not image_bytes or len(image_bytes) > MAX_IMAGE_BYTES:
        raise AppError(400, "VALIDATION_FAILED", "Image size must be between 1 byte and 10 MB")
    width = int(image.get("width") or 0)
    height = int(image.get("height") or 0)
    if width <= 0 or height <= 0:
        raise AppError(400, "VALIDATION_FAILED", "Image width and height are required")
    name = first_non_blank(image.get("name"), f"{uuid.uuid4()}{image_extension(media_type)}")
    return {
        "bytes": image_bytes,
        "mediaType": media_type,
        "name": name,
        "size": len(image_bytes),
        "width": width,
        "height": height,
    }


def upload_raw_web_image(config: dict[str, Any], upload_url: str, image_bytes: bytes, media_type: str) -> None:
    base = trim_slash(config.get("base_url") or "https://chatgpt.com")
    headers = {
        "content-type": media_type,
        "origin": base,
        "referer": base + "/",
        "x-ms-blob-type": "BlockBlob",
        "user-agent": first_non_blank(config.get("user_agent"), DEFAULT_USER_AGENT),
    }
    with httpx.Client(timeout=120) as client:
        response = client.put(upload_url, content=image_bytes, headers=headers)
    if response.status_code not in {200, 201}:
        raise AppError(502, "INTERNAL_ERROR", truncate(response.text or f"Image upload HTTP {response.status_code}", 1000))


def process_uploaded_web_file(config: dict[str, Any], file_id: str, file_name: str) -> str | None:
    path = "/backend-api/files/process_upload_stream"
    payload = {
        "file_id": file_id,
        "use_case": "multimodal",
        "index_for_retrieval": False,
        "file_name": file_name,
        "metadata": {"store_in_library": True},
    }
    url = trim_slash(config.get("base_url") or "https://chatgpt.com") + path
    headers = web_headers(config, path, None, "text/event-stream")
    library_file_id = None
    with httpx.Client(timeout=120) as client:
        with client.stream("POST", url, json=payload, headers=headers) as response:
            if response.status_code < 200 or response.status_code >= 300:
                body = response.read().decode("utf-8", "replace")
                raise AppError(502, "INTERNAL_ERROR", truncate(body or f"Image processing HTTP {response.status_code}", 1000))
            for line in response.iter_lines():
                event = parse_sse_data_line(line)
                if not isinstance(event, dict):
                    continue
                extra = event.get("extra")
                if isinstance(extra, dict) and isinstance(extra.get("metadata_object_id"), str):
                    library_file_id = extra["metadata_object_id"]
                if event.get("event") == "file.processing.failed":
                    raise AppError(502, "INTERNAL_ERROR", event.get("message") or "Failed processing uploaded image")
    return library_file_id


def image_extension(media_type: str) -> str:
    return {
        "image/png": ".png",
        "image/jpeg": ".jpg",
        "image/jpg": ".jpg",
        "image/webp": ".webp",
        "image/gif": ".gif",
    }.get(media_type, ".img")


def send_web_conversation(
    config: dict[str, Any],
    message: str,
    model: str,
    conversation_id: str | None,
    parent_id: str,
    conduit_token: str,
    images: list[dict[str, Any]],
    emit: Any,
) -> dict[str, Any]:
    path = "/backend-api/f/conversation"
    update_last_used_model_config(config, model, conversation_id)
    payload = conversation_payload(message, model, conversation_id, parent_id, images)
    headers = web_headers(config, path, conversation_id, "text/event-stream", conduit_token)
    url = trim_slash(config.get("base_url") or "https://chatgpt.com") + path
    answer = ""
    response_images: list[dict[str, Any]] = []
    web_image_candidates: list[dict[str, str]] = []
    web_sources: list[dict[str, Any]] = []
    image_placeholder_total = 0
    result_conversation_id = conversation_id
    assistant_id = None
    handoff_topic_id = None
    stream_handoff = False
    handoff_completed = False
    with httpx.Client(timeout=180) as client:
        with client.stream("POST", url, json=payload, headers=headers) as response:
            if response.status_code < 200 or response.status_code >= 300:
                body = response.read().decode("utf-8", "replace")
                raise AppError(502, "INTERNAL_ERROR", truncate(body or f"Web chat upstream HTTP {response.status_code}", 1000))
            for line in response.iter_lines():
                event = parse_sse_data_line(line)
                if event is None:
                    continue
                if event == "[DONE]":
                    break
                for image in collect_generated_images(event, config):
                    if append_unique_image(response_images, image):
                        emit("image", image)
                new_candidates = collect_web_image_candidates(event)
                web_image_candidates.extend(new_candidates)
                for candidate in new_candidates:
                    image = direct_web_image_from_candidate(candidate)
                    if image and append_unique_image(response_images, image):
                        emit("image", image)
                for source in collect_web_sources(event):
                    if append_unique_source(web_sources, source):
                        emit("source", source)
                next_answer = apply_event(answer, event)
                if next_answer is not None and next_answer != answer:
                    next_placeholder_total = web_image_placeholder_count(next_answer)
                    if next_placeholder_total > image_placeholder_total:
                        image_placeholder_total = next_placeholder_total
                        emit("image_placeholder", {"count": image_placeholder_total})
                    if next_answer.startswith(answer):
                        delta = next_answer[len(answer) :]
                        if delta:
                            emit("delta", {"delta": delta})
                    else:
                        emit("replace", {"text": next_answer})
                    answer = next_answer
                result_conversation_id = first_non_blank(get_text(event, "conversation_id"), result_conversation_id)
                assistant_id = first_non_blank(extract_assistant_message_id(event), assistant_id)
                if get_text(event, "type") == "stream_handoff":
                    stream_handoff = True
                handoff_topic_id = first_non_blank(extract_topic_id(event), handoff_topic_id)
                if stream_handoff and handoff_topic_id:
                    for handoff in read_handoff_topic_stream(config, handoff_topic_id, result_conversation_id, answer):
                        for image in handoff.get("images") or []:
                            if append_unique_image(response_images, image):
                                emit("image", image)
                        new_candidates = handoff.get("webImageCandidates") or []
                        web_image_candidates.extend(new_candidates)
                        for candidate in new_candidates:
                            image = direct_web_image_from_candidate(candidate)
                            if image and append_unique_image(response_images, image):
                                emit("image", image)
                        for source in handoff.get("webSources") or []:
                            if append_unique_source(web_sources, source):
                                emit("source", source)
                        if handoff["type"] in {"delta", "replace"}:
                            next_answer = handoff["answer"]
                            next_placeholder_total = web_image_placeholder_count(next_answer)
                            if next_placeholder_total > image_placeholder_total:
                                image_placeholder_total = next_placeholder_total
                                emit("image_placeholder", {"count": image_placeholder_total})
                            if handoff["type"] == "delta":
                                emit("delta", {"delta": handoff["delta"]})
                            else:
                                emit("replace", {"text": next_answer})
                            answer = next_answer
                            assistant_id = handoff.get("assistantMessageId") or assistant_id
                        elif handoff["type"] == "done":
                            answer = handoff["answer"]
                            assistant_id = handoff.get("assistantMessageId") or assistant_id
                    handoff_completed = True
                    break
                if is_done_event(event):
                    break
    if stream_handoff and handoff_topic_id and not handoff_completed:
        for handoff in read_handoff_topic_stream(config, handoff_topic_id, result_conversation_id, answer):
            for image in handoff.get("images") or []:
                if append_unique_image(response_images, image):
                    emit("image", image)
            new_candidates = handoff.get("webImageCandidates") or []
            web_image_candidates.extend(new_candidates)
            for candidate in new_candidates:
                image = direct_web_image_from_candidate(candidate)
                if image and append_unique_image(response_images, image):
                    emit("image", image)
            for source in handoff.get("webSources") or []:
                if append_unique_source(web_sources, source):
                    emit("source", source)
            if handoff["type"] in {"delta", "replace"}:
                next_answer = handoff["answer"]
                next_placeholder_total = web_image_placeholder_count(next_answer)
                if next_placeholder_total > image_placeholder_total:
                    image_placeholder_total = next_placeholder_total
                    emit("image_placeholder", {"count": image_placeholder_total})
                if handoff["type"] == "delta":
                    emit("delta", {"delta": handoff["delta"]})
                else:
                    emit("replace", {"text": next_answer})
                answer = next_answer
                assistant_id = handoff.get("assistantMessageId") or assistant_id
            elif handoff["type"] == "done":
                answer = handoff["answer"]
                assistant_id = handoff.get("assistantMessageId") or assistant_id
    cleaned_answer = clean_web_answer(answer)
    if cleaned_answer != answer:
        answer = cleaned_answer
        emit("replace", {"text": answer})
    for image in resolve_web_images(answer, web_image_candidates):
        if append_unique_image(response_images, image):
            emit("image", image)
    return {
        "answer": answer,
        "images": response_images,
        "sources": web_sources,
        "conversationId": result_conversation_id,
        "parentMessageId": assistant_id,
    }


def conversation_payload(message: str, model: str, conversation_id: str | None, parent_id: str, images: list[dict[str, Any]]) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "developer_mode_connector_ids": [],
        "selected_connector_ids": [],
        "selected_sync_knowledge_store_ids": [],
        "selected_sources": [],
        "selected_github_repos": [],
        "selected_all_github_repos": False,
        "serialization_metadata": {"custom_symbol_offsets": []},
    }
    content: dict[str, Any]
    if images:
        parts: list[Any] = []
        attachments: list[dict[str, Any]] = []
        for image in images:
            file_id = image.get("fileId") or image.get("file_id")
            parts.append(
                {
                    "content_type": "image_asset_pointer",
                    "asset_pointer": f"sediment://{file_id}",
                    "size_bytes": image.get("size") or 0,
                    "width": image.get("width"),
                    "height": image.get("height"),
                }
            )
            attachment = {
                "id": file_id,
                "size": image.get("size") or 0,
                "name": image.get("name"),
                "mime_type": image.get("mediaType") or image.get("media_type"),
                "width": image.get("width"),
                "height": image.get("height"),
                "source": "local",
                "is_big_paste": False,
            }
            library_file_id = image.get("libraryFileId") or image.get("library_file_id")
            if library_file_id:
                attachment["library_file_id"] = library_file_id
            attachments.append(attachment)
        parts.append(message)
        content = {"content_type": "multimodal_text", "parts": parts}
        metadata["attachments"] = attachments
    else:
        content = {"content_type": "text", "parts": [message]}
    payload: dict[str, Any] = {
        "action": "next",
        "messages": [
            {
                "id": str(uuid.uuid4()),
                "author": {"role": "user"},
                "create_time": time.time(),
                "content": content,
                "metadata": metadata,
            }
        ],
        "parent_message_id": parent_id,
        "model": model,
        "timezone_offset_min": -480,
        "timezone": "Asia/Shanghai",
        "conversation_mode": {"kind": "primary_assistant"},
        "enable_message_followups": True,
        "system_hints": [],
        "supports_buffering": True,
        "supported_encodings": ["v1"],
        "client_contextual_info": {
            "is_dark_mode": False,
            "time_since_loaded": 1,
            "page_height": 703,
            "page_width": 1008,
            "pixel_ratio": 1.25,
            "screen_height": 864,
            "screen_width": 1536,
            "app_name": "chat.sharedchat.cc",
        },
        "paragen_cot_summary_display_override": "allow",
        "force_parallel_switch": "auto",
    }
    if "thinking" in model or model.endswith("-pro"):
        payload["thinking_effort"] = "extended"
    if conversation_id:
        payload["conversation_id"] = conversation_id
    return payload


def update_last_used_model_config(config: dict[str, Any], model: str, conversation_id: str | None) -> None:
    path = "/backend-api/settings/user_last_used_model_config"
    url = trim_slash(config.get("base_url") or "https://chatgpt.com") + path + "?model_slug=" + quote(model)
    try:
        with httpx.Client(timeout=30) as client:
            client.patch(url, content="{}", headers=web_headers(config, path, conversation_id, "application/json"))
    except Exception:
        pass


