# Backend Notes

## Current Temporary Choices

- Passwords are stored directly in the `users.password_hash` column for now, per current project preference. The column name remains unchanged to avoid schema churn during early setup.
- API rate limiting now uses Redis counters through `StringRedisTemplate`.
- Registration verification codes now use Redis TTL keys and are removed after successful verification.
- Upstash Redis is expected in deployed environments via `REDIS_URL`.
- Auth tokens are HMAC-signed locally with `JWT_SECRET`, but there is not yet a full authentication filter that protects downstream APIs.
- QQ SMTP sending is wired for registration verification, but it currently fails open for local setup: if SMTP rejects the message, the generated code remains valid and is logged by the backend.
- `openai_services.token` currently stores the token directly. If this becomes sensitive production data, decide later whether to encrypt at rest.
- Upstream concurrency routing now uses Redis counters, so multiple backend instances share the same active request counts.
- The proxy now streams upstream responses with servlet `StreamingResponseBody`, but it still uses a blocking thread per active stream. Revisit this before large traffic.
- `model_catalog` is a database table, but the frontend also has a small fallback list so the model page stays usable before Supabase is seeded.

## Follow-Up Work

- Add production-grade streaming timeout/backpressure handling.
- Add auth middleware for protected APIs.
- Decide whether registration should require QQ email verification.
- Add migrations once schema changes become frequent.
- Add admin APIs for managing `openai_services`.
- Add admin APIs for managing `model_catalog` prices.
