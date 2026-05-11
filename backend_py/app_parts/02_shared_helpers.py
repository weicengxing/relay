def is_placeholder(value: Any) -> bool:
    if value is None:
        return True
    text = str(value).strip()
    return not text or text.startswith("PASTE_")


def first_non_blank(*values: Any) -> str | None:
    for value in values:
        if value is not None and str(value).strip():
            return str(value).strip()
    return None


def decimal_text(value: Decimal | str | float | int) -> str:
    return str(Decimal(str(value)).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP))


def parse_decimal(value: Any) -> Decimal:
    return Decimal(str(value or "0"))


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def b64url_decode(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def encode_novel_cursor(row: sqlite3.Row) -> str:
    payload = {"createdAt": row["created_at"], "id": row["id"]}
    return b64url(json.dumps(payload, separators=(",", ":")).encode("utf-8"))


def decode_novel_cursor(cursor: str) -> tuple[str, int]:
    try:
        payload = json.loads(b64url_decode(cursor).decode("utf-8"))
        created_at = str(payload["createdAt"])
        novel_id = int(payload["id"])
        if not created_at or novel_id < 1:
            raise ValueError
        return created_at, novel_id
    except Exception as exc:
        raise AppError(400, "VALIDATION_FAILED", "Invalid novel cursor") from exc


def trim_slashes(value: Any) -> str:
    return str(value or "").strip().strip("/")


def github_repo_ref(repository: str) -> tuple[str, str]:
    value = (repository or "").strip()
    if value.startswith("https://github.com/"):
        value = value[len("https://github.com/") :]
    elif value.startswith("git@github.com:"):
        value = value[len("git@github.com:") :]
    if value.endswith(".git"):
        value = value[:-4]
    parts = trim_slashes(value).split("/")
    if len(parts) != 2 or not parts[0] or not parts[1]:
        return "", ""
    return parts[0], parts[1]


def github_encode_path(path: str) -> str:
    return "/".join(quote(part, safe="") for part in str(path or "").split("/"))


def github_branch(branch: str) -> str:
    return (branch or "").strip() or "main"


def github_headers(token: str, accept: str) -> dict[str, str]:
    return {
        "Accept": accept,
        "Authorization": f"Bearer {token.strip()}",
        "User-Agent": "relay-backend-local",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def github_require_config(repository: str, token: str, label: str) -> tuple[str, str]:
    owner, repo = github_repo_ref(repository)
    if not owner or not repo or not (token or "").strip():
        raise AppError(500, "INTERNAL_ERROR", f"GitHub {label} storage is not configured")
    return owner, repo


def github_is_configured(repository: str, token: str) -> bool:
    owner, repo = github_repo_ref(repository)
    return bool(owner and repo and (token or "").strip())


def github_contents_url(repository: str, object_key: str, branch: str, include_ref: bool) -> str:
    owner, repo = github_repo_ref(repository)
    url = f"{GITHUB_API_BASE}/{owner}/{repo}/contents/{github_encode_path(object_key)}"
    if include_ref:
        url += f"?ref={quote(github_branch(branch), safe='')}"
    return url


def github_raw_url(repository: str, object_key: str, branch: str) -> str:
    owner, repo = github_repo_ref(repository)
    return (
        f"https://raw.githubusercontent.com/{owner}/{repo}/"
        f"{quote(github_branch(branch), safe='')}/{github_encode_path(object_key)}"
    )


def github_read_json_file(repository: str, branch: str, token: str, object_key: str, label: str) -> dict[str, Any] | None:
    github_require_config(repository, token, label)
    url = github_contents_url(repository, object_key, branch, True)
    try:
        with httpx.Client(timeout=60) as client:
            response = client.get(url, headers=github_headers(token, "application/vnd.github+json"))
    except Exception as exc:
        raise AppError(500, "INTERNAL_ERROR", f"Unable to read {label} from GitHub: {exc}") from exc
    if response.status_code == 404:
        return None
    if response.status_code < 200 or response.status_code >= 300:
        raise AppError(500, "INTERNAL_ERROR", f"Unable to read {label} from GitHub: {truncate(response.text, 1000)}")
    payload = response.json()
    encoded = str(payload.get("content") or "")
    content = ""
    if encoded.strip():
        content = base64.b64decode(encoded).decode("utf-8")
    return {"content": content, "sha": payload.get("sha") or "", "size": len(content.encode("utf-8"))}


def github_read_raw_file(content_url: str, token: str, label: str) -> str | None:
    url = str(content_url or "").strip()
    if not url:
        return None
    if not url.startswith("https://raw.githubusercontent.com/"):
        raise AppError(500, "INTERNAL_ERROR", f"Invalid GitHub {label} raw URL")
    headers = {"User-Agent": "relay-backend-local"}
    if (token or "").strip():
        headers["Authorization"] = f"Bearer {token.strip()}"
    try:
        with httpx.Client(timeout=60) as client:
            response = client.get(url, headers=headers)
    except Exception as exc:
        raise AppError(500, "INTERNAL_ERROR", f"Unable to read {label} from GitHub raw URL: {exc}") from exc
    if response.status_code == 404:
        return None
    if response.status_code < 200 or response.status_code >= 300:
        raise AppError(
            500,
            "INTERNAL_ERROR",
            f"Unable to read {label} from GitHub raw URL: {truncate(response.text, 1000)}",
        )
    return response.text


def github_read_file_content(
    repository: str,
    branch: str,
    token: str,
    object_key: str,
    label: str,
    content_url: str = "",
) -> str:
    if github_is_configured(repository, token):
        stored = github_read_json_file(repository, branch, token, object_key, label)
        if stored is not None:
            return str(stored.get("content") or "")
    raw_content = github_read_raw_file(content_url, token, label)
    if raw_content is not None:
        return raw_content
    github_require_config(repository, token, label)
    raise AppError(404, "NOT_FOUND", f"GitHub {label} file not found")


def github_write_file(
    repository: str,
    branch: str,
    token: str,
    object_key: str,
    content: str,
    message: str,
    label: str,
    sha: str | None = None,
) -> dict[str, Any]:
    github_require_config(repository, token, label)
    body: dict[str, Any] = {
        "message": message,
        "content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
        "branch": github_branch(branch),
    }
    if sha:
        body["sha"] = sha
    try:
        with httpx.Client(timeout=120) as client:
            response = client.put(
                github_contents_url(repository, object_key, branch, False),
                json=body,
                headers={**github_headers(token, "application/vnd.github+json"), "Content-Type": "application/json"},
            )
    except Exception as exc:
        raise AppError(500, "INTERNAL_ERROR", f"Unable to write {label} to GitHub: {exc}") from exc
    if response.status_code < 200 or response.status_code >= 300:
        raise AppError(500, "INTERNAL_ERROR", f"Unable to write {label} to GitHub: {truncate(response.text, 1000)}")
    size_bytes = len(content.encode("utf-8"))
    return {"url": github_raw_url(repository, object_key, branch), "size": size_bytes}


def issue_jwt(user: sqlite3.Row) -> str:
    now = int(time.time())
    header = b64url(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode())
    payload = b64url(
        json.dumps(
            {"sub": user["id"], "email": user["email"], "iat": now, "exp": now + 86400},
            separators=(",", ":"),
        ).encode()
    )
    unsigned = f"{header}.{payload}"
    sig = hmac.new(JWT_SECRET.encode(), unsigned.encode(), hashlib.sha256).digest()
    return f"{unsigned}.{b64url(sig)}"


def verify_jwt(token: str | None) -> str:
    if not token:
        raise AppError(401, "UNAUTHORIZED", "Unauthorized")
    parts = token.split(".")
    if len(parts) != 3:
        raise AppError(401, "UNAUTHORIZED", "Unauthorized")
    unsigned = f"{parts[0]}.{parts[1]}"
    expected = b64url(hmac.new(JWT_SECRET.encode(), unsigned.encode(), hashlib.sha256).digest())
    if not hmac.compare_digest(expected, parts[2]):
        raise AppError(401, "UNAUTHORIZED", "Unauthorized")
    try:
        payload = json.loads(b64url_decode(parts[1]))
        if int(payload.get("exp", 0)) <= int(time.time()):
            raise ValueError("expired")
        return str(uuid.UUID(payload["sub"]))
    except Exception as exc:
        raise AppError(401, "UNAUTHORIZED", "Unauthorized") from exc


def bearer_token(authorization: str | None) -> str | None:
    if authorization and authorization.startswith("Bearer "):
        return authorization[len("Bearer ") :].strip()
    return None


def current_user_id(authorization: str | None) -> str:
    return verify_jwt(bearer_token(authorization))


def current_owner_user_id(authorization: str | None) -> str:
    user_id = current_user_id(authorization)
    with db() as con:
        row = con.execute("select email from users where id = ?", (user_id,)).fetchone()
    if not row or str(row["email"]).lower() != OWNER_EMAIL:
        raise AppError(403, "FORBIDDEN", "Owner access required")
    return user_id


def sha256_key(value: str) -> str:
    return b64url(hashlib.sha256(value.encode()).digest())


def issue_api_key() -> str:
    return "relay_" + b64url(secrets.token_bytes(32))


def display_key(key_hash: str) -> str:
    return "relay_" + key_hash[:8] + "..."


def verification_email_html(code: str, ttl_minutes: int) -> str:
    digits = "".join(
        "<td style=\"padding:0 6px\">"
        "<div style=\"width:48px;height:56px;line-height:56px;text-align:center;"
        "font-size:28px;font-weight:700;color:#1a1a2e;background:#f4f5f7;"
        "border-radius:10px;font-family:'SF Mono',Consolas,monospace\">"
        f"{digit}</div></td>"
        for digit in code
    )
    return (
        "<!DOCTYPE html><html><head><meta charset=\"UTF-8\">"
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1.0\"></head>"
        "<body style=\"margin:0;padding:0;background:#f4f5f7;"
        "font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif\">"
        "<table width=\"100%\" cellpadding=\"0\" cellspacing=\"0\" style=\"background:#f4f5f7;padding:32px 16px\">"
        "<tr><td align=\"center\">"
        "<table width=\"100%\" cellpadding=\"0\" cellspacing=\"0\" style=\"max-width:480px;background:#fff;"
        "border-radius:16px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,0.04)\">"
        "<tr><td style=\"padding:36px 36px 0\">"
        "<table cellpadding=\"0\" cellspacing=\"0\"><tr>"
        "<td style=\"width:40px;height:40px;border-radius:10px;background:#6366f1;text-align:center;"
        "vertical-align:middle\"><span style=\"color:#fff;font-size:20px;line-height:40px\">&#9889;</span></td>"
        "<td style=\"padding-left:10px;font-size:20px;font-weight:800;color:#1a1a2e\">Relay</td>"
        "</tr></table></td></tr>"
        "<tr><td style=\"padding:32px 36px 0\">"
        "<h1 style=\"margin:0;font-size:22px;font-weight:700;color:#1a1a2e\">验证你的邮箱</h1>"
        "<p style=\"margin:8px 0 0;font-size:14px;color:#6e7191;line-height:1.6\">"
        "你正在注册 Relay 账户，请使用以下验证码完成验证：</p>"
        "</td></tr>"
        f"<tr><td style=\"padding:28px 36px\"><table cellpadding=\"0\" cellspacing=\"0\" style=\"margin:0 auto\"><tr>{digits}</tr></table></td></tr>"
        "<tr><td style=\"padding:0 36px 28px\">"
        "<table width=\"100%\" cellpadding=\"0\" cellspacing=\"0\" style=\"background:#f9fafb;border-radius:10px;padding:14px 18px\">"
        "<tr><td style=\"font-size:13px;color:#6e7191;line-height:1.5\">"
        f"验证码有效期为 <strong style=\"color:#1a1a2e\">{ttl_minutes} 分钟</strong>。"
        "如果这不是你本人的操作，请忽略此邮件。"
        "</td></tr></table></td></tr>"
        "<tr><td style=\"padding:0 36px 32px\">"
        "<table width=\"100%\" cellpadding=\"0\" cellspacing=\"0\" style=\"border-top:1px solid #f0f0f3;padding-top:20px\">"
        "<tr><td style=\"font-size:12px;color:#a0a3bd;text-align:center;line-height:1.5\">"
        "此邮件由系统自动发送，请勿回复<br>Relay AI 代理平台"
        "</td></tr></table></td></tr>"
        "</table></td></tr></table></body></html>"
    )


def send_verification_email(email: str, code: str, ttl_minutes: int) -> bool:
    if not SMTP_USERNAME.strip() or not SMTP_PASSWORD.strip() or not SMTP_FROM.strip():
        print(f"[backend_py] QQ SMTP is not configured; skipping verification email for {email}")
        return False
    message = EmailMessage()
    message["From"] = SMTP_FROM
    message["To"] = email
    message["Subject"] = "Relay - 验证码"
    message.set_content(f"你的 Relay 验证码是 {code}，有效期 {ttl_minutes} 分钟。")
    message.add_alternative(verification_email_html(code, ttl_minutes), subtype="html")
    try:
        if SMTP_PORT == 465:
            with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=20, context=ssl.create_default_context()) as smtp:
                smtp.login(SMTP_USERNAME, SMTP_PASSWORD)
                smtp.send_message(message)
        else:
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20) as smtp:
                smtp.starttls(context=ssl.create_default_context())
                smtp.login(SMTP_USERNAME, SMTP_PASSWORD)
                smtp.send_message(message)
        print(f"[backend_py] sent register code email to {email}")
        return True
    except Exception as exc:
        print(f"[backend_py] failed to send register code email for {email}: {exc}; code={code}")
        return False


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


def model_to_response(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "name": row["name"],
        "provider": row["provider"],
        "inputPrice": float(row["input_price"]),
        "outputPrice": float(row["output_price"]),
        "cachedInputPrice": float(row["cached_input_price"]),
        "cacheCreationPrice": float(row["cache_creation_price"]),
        "tags": [tag.strip() for tag in (row["tags"] or "").split(",") if tag.strip()],
    }


