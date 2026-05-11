def sse_event(event: str, data: Any) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def web_chat_image_token(config_id: int, file_id: str, ttl_seconds: int = 3600) -> str:
    payload = {"configId": int(config_id), "fileId": file_id, "exp": int(time.time()) + ttl_seconds}
    encoded = b64url(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signature = b64url(hmac.new(JWT_SECRET.encode(), encoded.encode(), hashlib.sha256).digest())
    return f"{encoded}.{signature}"


def verify_web_chat_image_token(config_id: int, file_id: str, token: str) -> None:
    if not re.fullmatch(r"file_[A-Za-z0-9]+", file_id or ""):
        raise AppError(400, "VALIDATION_FAILED", "Invalid image id")
    try:
        encoded, signature = token.split(".", 1)
        expected = b64url(hmac.new(JWT_SECRET.encode(), encoded.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(expected, signature):
            raise ValueError("bad signature")
        payload = json.loads(b64url_decode(encoded).decode("utf-8"))
        if int(payload.get("configId", -1)) != int(config_id) or payload.get("fileId") != file_id:
            raise ValueError("mismatch")
        if int(payload.get("exp", 0)) <= int(time.time()):
            raise ValueError("expired")
    except Exception as exc:
        raise AppError(401, "UNAUTHORIZED", "Invalid image token") from exc


def generated_web_image_url(config: dict[str, Any], file_id: str) -> str:
    config_id = int(config["id"])
    token = web_chat_image_token(config_id, file_id)
    return f"/api/web-chat/images/{config_id}/{quote(file_id, safe='')}?token={quote(token, safe='')}"


def download_generated_web_image(config: dict[str, Any], file_id: str) -> tuple[bytes, str]:
    if not re.fullmatch(r"file_[A-Za-z0-9]+", file_id or ""):
        raise AppError(400, "VALIDATION_FAILED", "Invalid image id")
    base = trim_slash(config.get("base_url") or "https://chatgpt.com")
    metadata_path = f"/backend-api/files/{file_id}/download"
    with httpx.Client(timeout=120, follow_redirects=True) as client:
        metadata_response = client.get(base + metadata_path, headers=web_headers(config, metadata_path, None, "*/*"))
        if metadata_response.status_code < 200 or metadata_response.status_code >= 300:
            raise AppError(
                502,
                "INTERNAL_ERROR",
                truncate(metadata_response.text or f"Image metadata HTTP {metadata_response.status_code}", 1000),
            )
        metadata = metadata_response.json()
        download_url = metadata.get("download_url") if isinstance(metadata, dict) else None
        if not isinstance(download_url, str) or not download_url:
            raise AppError(502, "INTERNAL_ERROR", "Generated image download URL missing")
        parsed = urlparse(download_url)
        content_path = parsed.path or "/backend-api/estuary/content"
        content_url = urljoin(base + "/", download_url)
        image_response = client.get(content_url, headers=web_headers(config, content_path, None, "*/*"))
        if image_response.status_code < 200 or image_response.status_code >= 300:
            raise AppError(
                502,
                "INTERNAL_ERROR",
                truncate(image_response.text or f"Image download HTTP {image_response.status_code}", 1000),
            )
    media_type = image_response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if not media_type.startswith("image/"):
        if image_response.content.startswith(b"\x89PNG\r\n\x1a\n"):
            media_type = "image/png"
        else:
            media_type = metadata.get("mime_type") or "application/octet-stream"
    return image_response.content, media_type


def append_unique_image(images: list[dict[str, Any]], image: dict[str, Any]) -> bool:
    key = image.get("id") or image.get("url") or image.get("pageUrl")
    if not key:
        return False
    for existing in images:
        if key in {existing.get("id"), existing.get("url"), existing.get("pageUrl")}:
            return False
    images.append(image)
    return True


def append_unique_source(sources: list[dict[str, Any]], source: dict[str, Any]) -> bool:
    url = source.get("url")
    if not isinstance(url, str) or not url.startswith(("http://", "https://")):
        return False
    if any(existing.get("url") == url for existing in sources):
        return False
    sources.append(source)
    return True


def collect_web_sources(node: Any) -> list[dict[str, Any]]:
    sources: list[dict[str, Any]] = []

    def add(value: Any) -> None:
        if not isinstance(value, dict):
            return
        url = value.get("url")
        if not isinstance(url, str) or not url.startswith(("http://", "https://")):
            return
        source = {
            "title": str(value.get("title") or value.get("attribution") or url),
            "url": url,
            "attribution": value.get("attribution") or urlparse(url).netloc,
            "snippet": value.get("snippet") or "",
            "pubDate": value.get("pub_date") or value.get("pubDate"),
        }
        append_unique_source(sources, source)

    def walk(value: Any) -> None:
        if isinstance(value, list):
            for item in value:
                walk(item)
            return
        if not isinstance(value, dict):
            return
        if value.get("type") == "search_result":
            add(value)
        for key in ("items", "sources", "supporting_websites", "entries"):
            if isinstance(value.get(key), list):
                for item in value[key]:
                    if isinstance(item, dict):
                        add(item)
                        walk(item)
        for child in value.values():
            walk(child)

    walk(node)
    return sources


def collect_generated_images(node: Any, config: dict[str, Any]) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []

    def walk(value: Any) -> None:
        if isinstance(value, list):
            for item in value:
                walk(item)
            return
        if not isinstance(value, dict):
            return
        asset_pointer = value.get("asset_pointer")
        if value.get("content_type") == "image_asset_pointer" and isinstance(asset_pointer, str):
            file_id = asset_pointer.removeprefix("sediment://")
            if re.fullmatch(r"file_[A-Za-z0-9]+", file_id or ""):
                metadata = value.get("metadata") if isinstance(value.get("metadata"), dict) else {}
                generation = metadata.get("generation") if isinstance(metadata.get("generation"), dict) else {}
                image = {
                    "id": file_id,
                    "fileId": file_id,
                    "name": f"{file_id}.png",
                    "mediaType": "image/png",
                    "size": value.get("size_bytes"),
                    "width": value.get("width"),
                    "height": value.get("height"),
                    "url": generated_web_image_url(config, file_id),
                    "source": "generated",
                }
                if generation.get("gen_id"):
                    image["generationId"] = generation["gen_id"]
                append_unique_image(found, image)
        for child in value.values():
            walk(child)

    walk(node)
    return found


def collect_web_image_candidates(node: Any) -> list[dict[str, str]]:
    candidates: list[dict[str, str]] = []

    def add(url: Any, title: Any = None) -> None:
        if not isinstance(url, str) or not url.startswith(("http://", "https://")):
            return
        if any(item["url"] == url for item in candidates):
            return
        lowered = url.lower()
        title_text = str(title or "")
        if is_probable_web_image_url(lowered) or any(marker in title_text.lower() for marker in ["image", "photo", "picture"]):
            candidates.append({"url": url, "title": title_text})

    def add_urls_from_text(text: Any, title: Any = None) -> None:
        if not isinstance(text, str):
            return
        for url in urls_from_text(text):
            add(url, title)

    def walk(value: Any) -> None:
        if isinstance(value, list):
            for item in value:
                walk(item)
            return
        if not isinstance(value, dict):
            return
        if value.get("type") == "search_result":
            add(value.get("url"), value.get("title"))
        if isinstance(value.get("image_result"), dict):
            image = value["image_result"]
            title = image.get("title")
            for key in ["content_url", "thumbnail_url", "original_content_url", "url"]:
                add(image.get(key), title)
        title = value.get("title") or value.get("alt")
        for key in ["content_url", "thumbnail_url", "original_content_url", "image_url", "url"]:
            add(value.get(key), title)
        safe_urls = value.get("safe_urls")
        if isinstance(safe_urls, list):
            for url in safe_urls:
                add(url, title)
        add_urls_from_text(value.get("alt"), title)
        add_urls_from_text(value.get("matched_text"), title)
        for child in value.values():
            walk(child)

    walk(node)
    return candidates


def is_probable_web_image_url(value: str) -> bool:
    parsed = urlparse(value)
    path = parsed.path.lower()
    host = parsed.netloc.lower()
    return (
        path.endswith((".png", ".jpg", ".jpeg", ".webp", ".gif"))
        or "images.openai.com" in host
        or "image" in path
        or "images" in path
        or "photo" in path
        or "photos" in path
        or "asset" in path
        or "hubble" in path
    )


def urls_from_text(text: str) -> list[str]:
    urls = re.findall(r"https?://[^\s)\]\"<>]+", text or "")
    result: list[str] = []
    for url in urls:
        url = html_lib.unescape(url.rstrip(".,;:"))
        if url not in result:
            result.append(url)
    return result


def clean_web_answer(answer: str) -> str:
    cleaned = re.sub(r"image_group.*?", "", answer or "", flags=re.S)
    cleaned = re.sub(r"(?:cite|i)[^]*", "", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def web_image_placeholder_count(answer: str, limit: int = 8) -> int:
    count = 0
    for match in re.finditer(r"image_group(.*?)(?:|$)", answer or "", flags=re.S):
        payload = match.group(1) or ""
        refs = re.search(r'"image_refs"\s*:\s*\[(.*?)\]', payload, flags=re.S)
        if refs:
            count += len(re.findall(r'"[^"]+"', refs.group(1))) or 1
        else:
            count += 1
    if not count and "image" in (answer or ""):
        count = 1
    return min(count, limit)


def direct_web_image_from_candidate(candidate: dict[str, str]) -> dict[str, Any] | None:
    url = html_lib.unescape(candidate.get("url") or "")
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return None
    host = parsed.netloc.lower()
    path = parsed.path.lower()
    query = parsed.query.lower()
    is_direct = (
        path.endswith((".png", ".jpg", ".jpeg", ".webp", ".gif"))
        or host == "images.openai.com"
        or host.endswith(".images.openai.com")
        or "purpose=fullsize" in query
    )
    if not is_direct:
        return None
    media_type = ""
    if path.endswith(".png"):
        media_type = "image/png"
    elif path.endswith((".jpg", ".jpeg")):
        media_type = "image/jpeg"
    elif path.endswith(".webp"):
        media_type = "image/webp"
    elif path.endswith(".gif"):
        media_type = "image/gif"
    return {
        "id": sha256_urlsafe(url.encode("utf-8"))[:16],
        "name": candidate.get("title") or Path(parsed.path).name or "web image",
        "mediaType": media_type,
        "url": url,
        "pageUrl": url,
        "source": "web",
    }


def resolve_web_images(answer: str, candidates: list[dict[str, str]], limit: int = 8) -> list[dict[str, Any]]:
    merged: list[dict[str, str]] = [{"url": url, "title": ""} for url in urls_from_text(answer)]
    for candidate in candidates:
        if not any(item["url"] == candidate["url"] for item in merged):
            merged.append(candidate)

    images: list[dict[str, Any]] = []
    ordered = sorted(enumerate(merged), key=lambda item: (-web_image_candidate_score(item[1]["url"]), item[0]))
    for _, candidate in ordered[:48]:
        resolved = resolve_web_image(candidate["url"], candidate.get("title") or "")
        if resolved and append_unique_image(images, resolved) and len(images) >= limit:
            break
    return images


def web_image_candidate_score(url: str) -> int:
    parsed = urlparse(html_lib.unescape(url or ""))
    host = parsed.netloc.lower()
    path = parsed.path.lower()
    query = parsed.query.lower()
    if path.endswith((".png", ".jpg", ".jpeg", ".webp", ".gif")):
        return 5
    if host == "images.openai.com" or host.endswith(".images.openai.com"):
        return 4
    if "purpose=fullsize" in query:
        return 4
    if "thumbnail" in path or "purpose=inline" in query:
        return 3
    if any(marker in path for marker in ["/image", "/images", "/photo", "/photos", "/asset"]):
        return 2
    return 1


def resolve_web_image(url: str, title: str = "") -> dict[str, Any] | None:
    url = html_lib.unescape(url)
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return None
    try:
        with httpx.Client(timeout=8, follow_redirects=True) as client:
            response = client.get(url, headers={"accept": "image/*,text/html;q=0.9,*/*;q=0.8"})
    except Exception:
        return None
    content_type = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    final_url = str(response.url)
    if response.status_code >= 200 and response.status_code < 300 and content_type.startswith("image/"):
        return {
            "id": sha256_urlsafe(final_url.encode("utf-8"))[:16],
            "name": title or Path(urlparse(final_url).path).name or "web image",
            "mediaType": content_type,
            "url": final_url,
            "pageUrl": final_url,
            "source": "web",
        }
    if response.status_code < 200 or response.status_code >= 300 or "html" not in content_type:
        return None
    html = response.text[:262144]
    image_url = first_non_blank(
        html_meta_content(html, "og:image"),
        html_meta_content(html, "twitter:image"),
        html_link_href(html, "image_src"),
    )
    if not image_url:
        return None
    image_url = html_lib.unescape(urljoin(final_url, image_url))
    return {
        "id": sha256_urlsafe((final_url + "\n" + image_url).encode("utf-8"))[:16],
        "name": title or html_title(html) or Path(urlparse(image_url).path).name or "web image",
        "mediaType": "",
        "url": image_url,
        "pageUrl": final_url,
        "source": "web",
    }


def html_meta_content(html: str, property_name: str) -> str | None:
    pattern = rf'<meta\s+[^>]*(?:property|name)=["\']{re.escape(property_name)}["\'][^>]*content=["\']([^"\']+)["\']'
    match = re.search(pattern, html, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    pattern = rf'<meta\s+[^>]*content=["\']([^"\']+)["\'][^>]*(?:property|name)=["\']{re.escape(property_name)}["\']'
    match = re.search(pattern, html, re.IGNORECASE)
    return match.group(1).strip() if match else None


def html_link_href(html: str, rel_name: str) -> str | None:
    pattern = rf'<link\s+[^>]*rel=["\'][^"\']*{re.escape(rel_name)}[^"\']*["\'][^>]*href=["\']([^"\']+)["\']'
    match = re.search(pattern, html, re.IGNORECASE)
    return match.group(1).strip() if match else None


def html_title(html: str) -> str | None:
    match = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    if not match:
        return None
    return re.sub(r"\s+", " ", match.group(1)).strip()


