@app.get("/api/novels")
def list_novels(
    page: int = 1,
    size: int = 20,
    q: str = "",
    cursor: str = "",
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    user_id = current_user_id(authorization)
    page = max(1, page)
    size = max(1, min(size, 100))
    conditions: list[str] = []
    params: list[Any] = []
    total_params: list[Any] = []
    trimmed_query = q.strip()
    if trimmed_query:
        query = f"%{trimmed_query}%"
        conditions.append("(title like ? or author like ? or excerpt like ?)")
        params.extend([query, query, query])
        total_params.extend([query, query, query])
    if cursor.strip():
        cursor_created_at, cursor_id = decode_novel_cursor(cursor.strip())
        conditions.append("(created_at < ? or (created_at = ? and id < ?))")
        params.extend([cursor_created_at, cursor_created_at, cursor_id])
    where_sql = f"where {' and '.join(conditions)}" if conditions else ""
    total_where_sql = (
        "where title like ? or author like ? or excerpt like ?" if trimmed_query else ""
    )
    with db() as con:
        total = con.execute(f"select count(*) from novels {total_where_sql}", tuple(total_params)).fetchone()[0]
        rows = con.execute(
            f"select * from novels {where_sql} order by created_at desc, id desc limit ?",
            tuple(params) + (size + 1,),
        ).fetchall()
        page_rows = rows[:size]
        ratings = my_ratings(con, user_id)
    has_more = len(rows) > size
    return api_ok(
        {
            "items": [novel_summary(row, ratings.get(row["id"])) for row in page_rows],
            "page": page,
            "size": size,
            "total": total,
            "totalRatings": sum(row["rating_count"] for row in page_rows),
            "hasMore": has_more,
            "nextCursor": encode_novel_cursor(page_rows[-1]) if has_more and page_rows else "",
        }
    )


@app.get("/api/novels/ranking")
def ranking(limit: int = 20, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    user_id = current_user_id(authorization)
    limit = max(1, min(limit, 100))
    with db() as con:
        rows = con.execute(
            "select * from novels order by rating_count desc, cast(rating_total as real) desc, created_at desc limit ?",
            (limit,),
        ).fetchall()
        ratings = my_ratings(con, user_id)
    return api_ok([novel_summary(row, ratings.get(row["id"])) for row in rows])


@app.get("/api/novels/{novel_id}")
def novel_detail(novel_id: int, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    user_id = current_user_id(authorization)
    with db() as con:
        row = con.execute("select * from novels where id = ?", (novel_id,)).fetchone()
        if not row:
            raise AppError(404, "NOT_FOUND", "Novel not found")
        rating = con.execute(
            "select score from novel_ratings where novel_id = ? and user_id = ?", (novel_id, user_id)
        ).fetchone()
    return api_ok(novel_full(row, rating["score"] if rating else None))


@app.post("/api/novels")
@db_write_api
def create_novel(payload: CreateNovelRequest, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    user_id = current_user_id(authorization)
    title = payload.title.strip()
    content = payload.content.strip()
    if not title or not content:
        raise AppError(400, "VALIDATION_FAILED", "Title and content are required")
    excerpt = content[:180]
    ts = now_iso()
    storage = store_novel_to_github(user_id, title, content)
    with db() as con:
        con.execute(
            """
            insert into novels(
              user_id, title, author, excerpt, content_object_key, content_url,
              content_size, content_sha256, created_at, updated_at
            )
            values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                title,
                (payload.author or "").strip(),
                excerpt,
                storage["objectKey"],
                storage["url"],
                storage["size"],
                storage["sha256"],
                ts,
                ts,
            ),
        )
        row = con.execute("select * from novels where id = last_insert_rowid()").fetchone()
    return api_ok(novel_full(row, None))


@app.post("/api/novels/{novel_id}/ratings")
@db_write_api
def rate_novel(novel_id: int, payload: RateNovelRequest, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    user_id = current_user_id(authorization)
    if payload.score < 1 or payload.score > 5:
        raise AppError(400, "VALIDATION_FAILED", "Score must be between 1 and 5")
    ts = now_iso()
    with db() as con:
        row = con.execute("select * from novels where id = ?", (novel_id,)).fetchone()
        if not row:
            raise AppError(404, "NOT_FOUND", "Novel not found")
        old = con.execute(
            "select score from novel_ratings where novel_id = ? and user_id = ?", (novel_id, user_id)
        ).fetchone()
        if old:
            delta_count = 0
            delta_total = payload.score - int(old["score"])
            con.execute(
                "update novel_ratings set score = ?, updated_at = ? where novel_id = ? and user_id = ?",
                (payload.score, ts, novel_id, user_id),
            )
        else:
            delta_count = 1
            delta_total = payload.score
            con.execute(
                "insert into novel_ratings(novel_id, user_id, score, created_at, updated_at) values (?, ?, ?, ?, ?)",
                (novel_id, user_id, payload.score, ts, ts),
            )
        con.execute(
            """
            update novels
            set rating_count = rating_count + ?,
                rating_total = cast(cast(rating_total as real) + ? as text),
                updated_at = ?
            where id = ?
            """,
            (delta_count, delta_total, ts, novel_id),
        )
        row = con.execute("select * from novels where id = ?", (novel_id,)).fetchone()
    return api_ok(novel_full(row, payload.score))


def my_ratings(con: sqlite3.Connection, user_id: str) -> dict[int, int]:
    rows = con.execute("select novel_id, score from novel_ratings where user_id = ?", (user_id,)).fetchall()
    return {row["novel_id"]: row["score"] for row in rows}


def safe_novel_title(title: str) -> str:
    value = re.sub(r"[^A-Za-z0-9\u4e00-\u9fa5._-]+", "-", (title or "").strip())
    value = value or "novel"
    return value[:48]


def novel_object_key(user_id: str, title: str) -> str:
    today = datetime.now().date()
    base_path = trim_slashes(GITHUB_NOVEL_BASE_PATH)
    prefix = f"{base_path}/" if base_path else ""
    return f"{prefix}{today.year}/{today.month:02d}/{user_id}-{uuid.uuid4()}-{safe_novel_title(title)}.txt"


def sha256_urlsafe(data: bytes) -> str:
    return b64url(hashlib.sha256(data).digest())


def store_novel_to_github(user_id: str, title: str, content: str) -> dict[str, Any]:
    object_key = novel_object_key(user_id, title)
    written = github_write_file(
        GITHUB_NOVEL_REPOSITORY,
        GITHUB_NOVEL_BRANCH,
        GITHUB_NOVEL_TOKEN,
        object_key,
        content,
        f"Upload novel {title}",
        "novel",
    )
    raw = content.encode("utf-8")
    return {
        "objectKey": object_key,
        "url": written["url"],
        "size": len(raw),
        "sha256": sha256_urlsafe(raw),
    }


def read_novel_from_github(object_key: str, content_url: str = "") -> str:
    if not object_key:
        raise AppError(500, "INTERNAL_ERROR", "Novel content object key is missing")
    content = github_read_file_content(
        GITHUB_NOVEL_REPOSITORY,
        GITHUB_NOVEL_BRANCH,
        GITHUB_NOVEL_TOKEN,
        object_key,
        "novel",
        content_url,
    )
    if not content.strip():
        raise AppError(500, "INTERNAL_ERROR", "GitHub returned empty novel content")
    return content


def avg_rating(row: sqlite3.Row) -> float:
    count = int(row["rating_count"])
    return 0.0 if count <= 0 else float(parse_decimal(row["rating_total"]) / Decimal(count))


def novel_summary(row: sqlite3.Row, my_rating: int | None) -> dict[str, Any]:
    return {
        "id": row["id"],
        "title": row["title"],
        "author": row["author"],
        "excerpt": row["excerpt"],
        "averageRating": avg_rating(row),
        "ratingCount": row["rating_count"],
        "myRating": my_rating,
        "createdAt": row["created_at"],
    }


def novel_full(row: sqlite3.Row, my_rating: int | None) -> dict[str, Any]:
    data = novel_summary(row, my_rating)
    data.update(
        {
            "content": read_novel_from_github(row["content_object_key"], row["content_url"]),
            "contentUrl": row["content_url"],
            "updatedAt": row["updated_at"],
        }
    )
    return data


