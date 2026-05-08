$bodyPath = 'D:\relay\backend\captures\codex\20260508-171412-825-v1-responses.body.json'
curl.exe -N 'http://localhost:8080/v1/responses' `
  -H 'x-codex-beta-features: terminal_resize_reflow' `
  -H 'x-codex-turn-metadata: {"session_id":"019e06dc-2cf4-7931-a035-4c5d804c2c20","thread_source":"user","turn_id":"019e06dc-e42b-7f61-a1e4-b67d5d854f0b","sandbox":"windows_elevated","turn_started_at_unix_ms":1778231600195}' `
  -H 'x-codex-window-id: 019e06dc-2cf4-7931-a035-4c5d804c2c20:0' `
  -H 'x-client-request-id: 019e06dc-2cf4-7931-a035-4c5d804c2c20' `
  -H 'session_id: 019e06dc-2cf4-7931-a035-4c5d804c2c20' `
  -H 'accept: text/event-stream' `
  -H 'authorization: Bearer relay_BgV7MZudDLOUS5EiZZpi_f9hMZ5ZsxecqtZjLPXstoI' `
  -H 'content-type: application/json' `
  -H 'originator: Codex Desktop' `
  -H 'user-agent: Codex Desktop/0.128.0-alpha.1 (Windows 10.0.19045; x86_64) unknown (Codex Desktop; 26.429.30905)' `
  --data-binary "@$bodyPath"
