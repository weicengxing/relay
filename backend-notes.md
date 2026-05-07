# Backend Notes

## Current Temporary Choices

- Passwords are stored directly in the `users.password_hash` column for now, per current project preference. The column name remains unchanged to avoid schema churn during early setup.
- API rate limiting is currently in process memory through `RateLimitFilter`. This means counters reset when the service restarts and are not shared across multiple backend instances.
- Redis is not wired yet. Replace the in-memory rate-limit bucket with Redis or Upstash before multi-instance deployment or public traffic.
- Auth tokens are HMAC-signed locally with `JWT_SECRET`, but there is not yet a full authentication filter that protects downstream APIs.
- QQ SMTP settings are only configuration placeholders. Email verification or notification sending is not implemented yet.
- `openai_services.token` currently stores the token directly. If this becomes sensitive production data, decide later whether to encrypt at rest.

## Follow-Up Work

- Add Redis-backed rate limiting.
- Add auth middleware for protected APIs.
- Decide whether registration should require QQ email verification.
- Add migrations once schema changes become frequent.
- Add admin APIs for managing `openai_services`.
