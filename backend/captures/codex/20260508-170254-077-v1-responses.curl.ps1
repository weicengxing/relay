$bodyPath = 'D:\relay\backend\captures\codex\20260508-170254-077-v1-responses.body.json'
curl.exe -N 'http://localhost:8080/v1/responses' `
  -H 'x-codex-beta-features: terminal_resize_reflow' `
  -H 'x-codex-turn-metadata: {"session_id":"019e06d2-b552-74d2-b79b-bb88e02b601d","thread_source":"user","turn_id":"019e06d2-b616-7e20-b12c-d1a9c954dbf6","workspaces":{"D:\\relay":{"associated_remote_urls":{"origin":"https://github.com/weicengxing/relay.git"},"latest_git_commit_hash":"4a3fe781427d0e4e5a5ebe7d48117392c2eab97a","has_changes":true}},"sandbox":"windows_elevated","turn_started_at_unix_ms":1778230933093}' `
  -H 'x-codex-window-id: 019e06d2-b552-74d2-b79b-bb88e02b601d:0' `
  -H 'x-client-request-id: 019e06d2-b552-74d2-b79b-bb88e02b601d' `
  -H 'session_id: 019e06d2-b552-74d2-b79b-bb88e02b601d' `
  -H 'accept: text/event-stream' `
  -H 'authorization: Bearer relay_BgV7MZudDLOUS5EiZZpi_f9hMZ5ZsxecqtZjLPXstoI' `
  -H 'content-type: application/json' `
  -H 'originator: Codex Desktop' `
  -H 'user-agent: Codex Desktop/0.128.0-alpha.1 (Windows 10.0.19045; x86_64) unknown (Codex Desktop; 26.429.30905)' `
  --data-binary "@$bodyPath"
