def find_or_create_web_session(user_id: str) -> dict[str, Any]:
    with db() as con:
        row = con.execute(
            """
            select s.user_id, s.conversation_id, s.parent_message_id,
                   c.*
            from web_chat_user_sessions s
            join web_chat_model_configs c on c.id = s.config_id
            where s.user_id = ? and c.enabled = 1
            """,
            (user_id,),
        ).fetchone()
        if row:
            return row_to_dict(row)
        configs = con.execute("select * from web_chat_model_configs where enabled = 1 order by id").fetchall()
        if not configs:
            raise AppError(404, "NOT_FOUND", "No web chat model config is enabled")
        config = configs[abs(hash(user_id)) % len(configs)]
        con.execute(
            """
            insert into web_chat_user_sessions(user_id, config_id, conversation_id, parent_message_id, updated_at)
            values (?, ?, null, ?, ?)
            on conflict(user_id) do update set config_id=excluded.config_id, updated_at=excluded.updated_at
            """,
            (user_id, config["id"], ROOT_PARENT_MESSAGE_ID, now_iso()),
        )
        return row_to_dict(
            con.execute(
                """
                select s.user_id, s.conversation_id, s.parent_message_id, c.*
                from web_chat_user_sessions s join web_chat_model_configs c on c.id = s.config_id
                where s.user_id = ?
                """,
                (user_id,),
            ).fetchone()
        )


def session_response(session: dict[str, Any]) -> dict[str, Any]:
    conversation_id = session.get("conversation_id")
    return {
        "configId": session["id"],
        "configName": session["name"],
        "model": first_non_blank(session.get("model"), DEFAULT_WEB_MODEL),
        "conversationId": conversation_id,
        "hasConversation": bool(conversation_id),
    }


def send_web_chat_turn(
    user_id: str,
    request_payload: WebChatMessageRequest,
    sink: Any,
    sse_emit: bool = False,
) -> dict[str, Any]:
    message = (request_payload.message or "").strip()
    images = request_payload.images or []
    if not message and not images:
        raise AppError(400, "VALIDATION_FAILED", "Message or image is required")
    session = find_or_create_web_session(user_id)
    new_conversation = bool(request_payload.newConversation)
    conversation_id = None if new_conversation else first_non_blank(session.get("conversation_id"))
    parent_message_id = ROOT_PARENT_MESSAGE_ID if new_conversation else first_non_blank(session.get("parent_message_id"), ROOT_PARENT_MESSAGE_ID)
    model = first_non_blank(request_payload.model, session.get("model"), DEFAULT_WEB_MODEL)
    conduit_token = session.get("conduit_token")
    if session.get("call_prepare"):
        conduit_token = prepare_web_turn(session, message, model, conversation_id, parent_message_id)
    if not conduit_token:
        raise AppError(503, "VALIDATION_FAILED", "Web chat config requires conduit_token or call_prepare=true")
    uploaded_images = upload_web_images(session, images)
    events: list[str] = []

    def emit(kind: str, data: dict[str, Any]) -> None:
        if sse_emit:
            events.append(sse_event(kind, data))
        if sink:
            sink(kind, data)

    result = send_web_conversation(session, message, model, conversation_id, parent_message_id, conduit_token, uploaded_images, emit)
    next_conversation_id = first_non_blank(result.get("conversationId"), conversation_id)
    next_parent_id = first_non_blank(result.get("parentMessageId"), parent_message_id)
    response = {
        "answer": result.get("answer") or "",
        "images": result.get("images") or [],
        "sources": result.get("sources") or [],
        "conversationId": next_conversation_id,
        "parentMessageId": next_parent_id,
        "model": model,
        "configId": session["id"],
        "configName": session["name"],
    }
    with db() as con:
        con.execute(
            """
            update web_chat_user_sessions
            set conversation_id = ?, parent_message_id = ?, updated_at = ?
            where user_id = ?
            """,
            (next_conversation_id, next_parent_id, now_iso(), user_id),
        )
        append_web_chat_history(con, user_id, request_payload, response)
    if sse_emit:
        response["_events"] = events
    return response


def stream_web_chat_turn(user_id: str, request_payload: WebChatMessageRequest) -> Iterable[str | dict[str, Any]]:
    message = (request_payload.message or "").strip()
    images = request_payload.images or []
    if not message and not images:
        raise AppError(400, "VALIDATION_FAILED", "Message or image is required")
    session = find_or_create_web_session(user_id)
    new_conversation = bool(request_payload.newConversation)
    conversation_id = None if new_conversation else first_non_blank(session.get("conversation_id"))
    parent_message_id = ROOT_PARENT_MESSAGE_ID if new_conversation else first_non_blank(session.get("parent_message_id"), ROOT_PARENT_MESSAGE_ID)
    model = first_non_blank(request_payload.model, session.get("model"), DEFAULT_WEB_MODEL)
    conduit_token = session.get("conduit_token")
    if session.get("call_prepare"):
        conduit_token = prepare_web_turn(session, message, model, conversation_id, parent_message_id)
    if not conduit_token:
        raise AppError(503, "VALIDATION_FAILED", "Web chat config requires conduit_token or call_prepare=true")
    uploaded_images = upload_web_images(session, images)

    path = "/backend-api/f/conversation"
    update_last_used_model_config(session, model, conversation_id)
    body = conversation_payload(message, model, conversation_id, parent_message_id, uploaded_images)
    headers = web_headers(session, path, conversation_id, "text/event-stream", conduit_token)
    url = trim_slash(session.get("base_url") or "https://chatgpt.com") + path
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
        with client.stream("POST", url, json=body, headers=headers) as response:
            if response.status_code < 200 or response.status_code >= 300:
                upstream_body = response.read().decode("utf-8", "replace")
                raise AppError(502, "INTERNAL_ERROR", truncate(upstream_body or f"Web chat upstream HTTP {response.status_code}", 1000))
            for line in response.iter_lines():
                event = parse_sse_data_line(line)
                if event is None:
                    continue
                if event == "[DONE]":
                    break
                for image in collect_generated_images(event, session):
                    if append_unique_image(response_images, image):
                        yield sse_event("image", image)
                new_candidates = collect_web_image_candidates(event)
                web_image_candidates.extend(new_candidates)
                for candidate in new_candidates:
                    image = direct_web_image_from_candidate(candidate)
                    if image and append_unique_image(response_images, image):
                        yield sse_event("image", image)
                for source in collect_web_sources(event):
                    if append_unique_source(web_sources, source):
                        yield sse_event("source", source)
                next_answer = apply_event(answer, event)
                if next_answer is not None and next_answer != answer:
                    next_placeholder_total = web_image_placeholder_count(next_answer)
                    if next_placeholder_total > image_placeholder_total:
                        image_placeholder_total = next_placeholder_total
                        yield sse_event("image_placeholder", {"count": image_placeholder_total})
                    if next_answer.startswith(answer):
                        delta = next_answer[len(answer) :]
                        if delta:
                            yield sse_event("delta", {"delta": delta})
                    else:
                        yield sse_event("replace", {"text": next_answer})
                    answer = next_answer
                result_conversation_id = first_non_blank(get_text(event, "conversation_id"), result_conversation_id)
                assistant_id = first_non_blank(extract_assistant_message_id(event), assistant_id)
                if get_text(event, "type") == "stream_handoff":
                    stream_handoff = True
                handoff_topic_id = first_non_blank(extract_topic_id(event), handoff_topic_id)
                if stream_handoff and handoff_topic_id:
                    for handoff in read_handoff_topic_stream(session, handoff_topic_id, result_conversation_id, answer):
                        for image in handoff.get("images") or []:
                            if append_unique_image(response_images, image):
                                yield sse_event("image", image)
                        new_candidates = handoff.get("webImageCandidates") or []
                        web_image_candidates.extend(new_candidates)
                        for candidate in new_candidates:
                            image = direct_web_image_from_candidate(candidate)
                            if image and append_unique_image(response_images, image):
                                yield sse_event("image", image)
                        for source in handoff.get("webSources") or []:
                            if append_unique_source(web_sources, source):
                                yield sse_event("source", source)
                        if handoff["type"] == "delta":
                            next_placeholder_total = web_image_placeholder_count(handoff["answer"])
                            if next_placeholder_total > image_placeholder_total:
                                image_placeholder_total = next_placeholder_total
                                yield sse_event("image_placeholder", {"count": image_placeholder_total})
                            answer = handoff["answer"]
                            assistant_id = handoff.get("assistantMessageId") or assistant_id
                            yield sse_event("delta", {"delta": handoff["delta"]})
                        elif handoff["type"] == "replace":
                            next_placeholder_total = web_image_placeholder_count(handoff["answer"])
                            if next_placeholder_total > image_placeholder_total:
                                image_placeholder_total = next_placeholder_total
                                yield sse_event("image_placeholder", {"count": image_placeholder_total})
                            answer = handoff["answer"]
                            assistant_id = handoff.get("assistantMessageId") or assistant_id
                            yield sse_event("replace", {"text": answer})
                        elif handoff["type"] == "done":
                            answer = handoff["answer"]
                            assistant_id = handoff.get("assistantMessageId") or assistant_id
                    handoff_completed = True
                    break
                if is_done_event(event):
                    break
    if stream_handoff and handoff_topic_id and not handoff_completed:
        for handoff in read_handoff_topic_stream(session, handoff_topic_id, result_conversation_id, answer):
            for image in handoff.get("images") or []:
                if append_unique_image(response_images, image):
                    yield sse_event("image", image)
            new_candidates = handoff.get("webImageCandidates") or []
            web_image_candidates.extend(new_candidates)
            for candidate in new_candidates:
                image = direct_web_image_from_candidate(candidate)
                if image and append_unique_image(response_images, image):
                    yield sse_event("image", image)
            for source in handoff.get("webSources") or []:
                if append_unique_source(web_sources, source):
                    yield sse_event("source", source)
            if handoff["type"] == "delta":
                next_placeholder_total = web_image_placeholder_count(handoff["answer"])
                if next_placeholder_total > image_placeholder_total:
                    image_placeholder_total = next_placeholder_total
                    yield sse_event("image_placeholder", {"count": image_placeholder_total})
                answer = handoff["answer"]
                assistant_id = handoff.get("assistantMessageId") or assistant_id
                yield sse_event("delta", {"delta": handoff["delta"]})
            elif handoff["type"] == "replace":
                next_placeholder_total = web_image_placeholder_count(handoff["answer"])
                if next_placeholder_total > image_placeholder_total:
                    image_placeholder_total = next_placeholder_total
                    yield sse_event("image_placeholder", {"count": image_placeholder_total})
                answer = handoff["answer"]
                assistant_id = handoff.get("assistantMessageId") or assistant_id
                yield sse_event("replace", {"text": answer})
            elif handoff["type"] == "done":
                answer = handoff["answer"]
                assistant_id = handoff.get("assistantMessageId") or assistant_id
    cleaned_answer = clean_web_answer(answer)
    if cleaned_answer != answer:
        answer = cleaned_answer
        yield sse_event("replace", {"text": answer})
    for image in resolve_web_images(answer, web_image_candidates):
        if append_unique_image(response_images, image):
            yield sse_event("image", image)
    next_conversation_id = first_non_blank(result_conversation_id, conversation_id)
    next_parent_id = first_non_blank(assistant_id, parent_message_id)
    result_payload = {
        "answer": answer,
        "images": response_images,
        "sources": web_sources,
        "conversationId": next_conversation_id,
        "parentMessageId": next_parent_id,
        "model": model,
        "configId": session["id"],
        "configName": session["name"],
    }
    with db() as con:
        con.execute(
            """
            update web_chat_user_sessions
            set conversation_id = ?, parent_message_id = ?, updated_at = ?
            where user_id = ?
            """,
            (next_conversation_id, next_parent_id, now_iso(), user_id),
        )
        append_web_chat_history(con, user_id, request_payload, result_payload)
    yield result_payload


