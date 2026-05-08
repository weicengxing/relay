$bodyPath = 'D:\relay\backend\captures\codex\20260508-172459-455-v1-responses.body.json'
curl.exe -N 'http://localhost:8080/v1/responses' `
  -H 'x-codex-beta-features: terminal_resize_reflow' `
  -H 'x-codex-turn-metadata: {"session_id":"019e06e7-8f90-79b2-a8e5-1b8f0c9ad939","thread_source":"user","turn_id":"019e06e7-8fb1-7d90-ab12-c99bda835f8e","sandbox":"windows_elevated","turn_started_at_unix_ms":1778232299444}' `
  -H 'x-codex-window-id: 019e06e7-8f90-79b2-a8e5-1b8f0c9ad939:0' `
  -H 'x-client-request-id: 019e06e7-8f90-79b2-a8e5-1b8f0c9ad939' `
  -H 'session_id: 019e06e7-8f90-79b2-a8e5-1b8f0c9ad939' `
  -H 'accept: text/event-stream' `
  -H 'authorization: Bearer relay_BgV7MZudDLOUS5EiZZpi_f9hMZ5ZsxecqtZjLPXstoI' `
  -H 'content-type: application/json' `
  -H 'originator: Codex Desktop' `
  -H 'user-agent: Codex Desktop/0.128.0-alpha.1 (Windows 10.0.19045; x86_64) unknown (Codex Desktop; 26.429.30905)' `
  --data-binary "@$bodyPath"
