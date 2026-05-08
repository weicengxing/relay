$bodyPath = 'D:\relay\backend\captures\codex\20260508-172504-509-v1-responses.body.json'
curl.exe -N 'http://localhost:8080/v1/responses' `
  -H 'x-codex-beta-features: terminal_resize_reflow' `
  -H 'x-codex-turn-metadata: {"session_id":"019e06e7-8ef6-7ae1-8286-e66d1d4839ba","thread_source":"user","turn_id":"019e06e7-8fa2-7f21-b9c7-53feb511b767","sandbox":"windows_elevated","turn_started_at_unix_ms":1778232299459}' `
  -H 'x-codex-window-id: 019e06e7-8ef6-7ae1-8286-e66d1d4839ba:0' `
  -H 'x-client-request-id: 019e06e7-8ef6-7ae1-8286-e66d1d4839ba' `
  -H 'session_id: 019e06e7-8ef6-7ae1-8286-e66d1d4839ba' `
  -H 'accept: text/event-stream' `
  -H 'authorization: Bearer relay_BgV7MZudDLOUS5EiZZpi_f9hMZ5ZsxecqtZjLPXstoI' `
  -H 'content-type: application/json' `
  -H 'originator: Codex Desktop' `
  -H 'user-agent: Codex Desktop/0.128.0-alpha.1 (Windows 10.0.19045; x86_64) unknown (Codex Desktop; 26.429.30905)' `
  --data-binary "@$bodyPath"
