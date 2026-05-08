$bodyPath = 'D:\relay\backend\captures\codex\20260508-204726-790-v1-responses.body.json'
curl.exe -N 'http://localhost:8080/v1/responses' `
  -H 'x-codex-beta-features: terminal_resize_reflow' `
  -H 'x-codex-turn-metadata: {"session_id":"019e07a0-ac85-7ca1-9727-ab7fb02ce2ee","thread_source":"user","turn_id":"019e07a0-ad63-7843-9634-404c0ca93ae3","sandbox":"windows_elevated","turn_started_at_unix_ms":1778244431377}' `
  -H 'x-codex-window-id: 019e07a0-ac85-7ca1-9727-ab7fb02ce2ee:0' `
  -H 'x-client-request-id: 019e07a0-ac85-7ca1-9727-ab7fb02ce2ee' `
  -H 'session_id: 019e07a0-ac85-7ca1-9727-ab7fb02ce2ee' `
  -H 'accept: text/event-stream' `
  -H 'authorization: Bearer relay_BgV7MZudDLOUS5EiZZpi_f9hMZ5ZsxecqtZjLPXstoI' `
  -H 'content-type: application/json' `
  -H 'originator: Codex Desktop' `
  -H 'user-agent: Codex Desktop/0.128.0-alpha.1 (Windows 10.0.19045; x86_64) unknown (Codex Desktop; 26.429.30905)' `
  --data-binary "@$bodyPath"
