$bodyPath = 'D:\relay\backend\captures\codex\20260508-184032-881-v1-responses.body.json'
curl.exe -N 'http://localhost:8080/v1/responses' `
  -H 'x-codex-beta-features: terminal_resize_reflow' `
  -H 'x-codex-turn-metadata: {"session_id":"019e072c-bc32-71a0-807a-5d6ebd893077","thread_source":"user","turn_id":"019e072c-bc4b-78a2-a671-709f03b73093","sandbox":"windows_elevated","turn_started_at_unix_ms":1778236832851}' `
  -H 'x-codex-window-id: 019e072c-bc32-71a0-807a-5d6ebd893077:0' `
  -H 'x-client-request-id: 019e072c-bc32-71a0-807a-5d6ebd893077' `
  -H 'session_id: 019e072c-bc32-71a0-807a-5d6ebd893077' `
  -H 'accept: text/event-stream' `
  -H 'authorization: Bearer relay_BgV7MZudDLOUS5EiZZpi_f9hMZ5ZsxecqtZjLPXstoI' `
  -H 'content-type: application/json' `
  -H 'originator: Codex Desktop' `
  -H 'user-agent: Codex Desktop/0.128.0-alpha.1 (Windows 10.0.19045; x86_64) unknown (Codex Desktop; 26.429.30905)' `
  --data-binary "@$bodyPath"
