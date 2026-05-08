$bodyPath = 'D:\relay\backend\captures\codex\20260508-184037-964-v1-responses.body.json'
curl.exe -N 'http://localhost:8080/v1/responses' `
  -H 'x-codex-beta-features: terminal_resize_reflow' `
  -H 'x-codex-turn-metadata: {"session_id":"019e072c-b100-7462-a432-634d6a26682e","thread_source":"user","turn_id":"019e072c-bc42-7f20-add5-3d0205d5d5d9","sandbox":"windows_elevated","turn_started_at_unix_ms":1778236832922}' `
  -H 'x-codex-window-id: 019e072c-b100-7462-a432-634d6a26682e:0' `
  -H 'x-client-request-id: 019e072c-b100-7462-a432-634d6a26682e' `
  -H 'session_id: 019e072c-b100-7462-a432-634d6a26682e' `
  -H 'accept: text/event-stream' `
  -H 'authorization: Bearer relay_BgV7MZudDLOUS5EiZZpi_f9hMZ5ZsxecqtZjLPXstoI' `
  -H 'content-type: application/json' `
  -H 'originator: Codex Desktop' `
  -H 'user-agent: Codex Desktop/0.128.0-alpha.1 (Windows 10.0.19045; x86_64) unknown (Codex Desktop; 26.429.30905)' `
  --data-binary "@$bodyPath"
