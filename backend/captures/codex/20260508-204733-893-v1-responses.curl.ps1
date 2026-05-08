$bodyPath = 'D:\relay\backend\captures\codex\20260508-204733-893-v1-responses.body.json'
curl.exe -N 'http://localhost:8080/v1/responses' `
  -H 'x-codex-beta-features: terminal_resize_reflow' `
  -H 'x-codex-turn-metadata: {"session_id":"019e07a0-ad4b-77e1-8693-bacc898e1f18","thread_source":"user","turn_id":"019e07a0-ad83-7271-8465-f4c52b93e4d4","sandbox":"windows_elevated","turn_started_at_unix_ms":1778244431237}' `
  -H 'x-codex-window-id: 019e07a0-ad4b-77e1-8693-bacc898e1f18:0' `
  -H 'x-client-request-id: 019e07a0-ad4b-77e1-8693-bacc898e1f18' `
  -H 'session_id: 019e07a0-ad4b-77e1-8693-bacc898e1f18' `
  -H 'accept: text/event-stream' `
  -H 'authorization: Bearer relay_BgV7MZudDLOUS5EiZZpi_f9hMZ5ZsxecqtZjLPXstoI' `
  -H 'content-type: application/json' `
  -H 'originator: Codex Desktop' `
  -H 'user-agent: Codex Desktop/0.128.0-alpha.1 (Windows 10.0.19045; x86_64) unknown (Codex Desktop; 26.429.30905)' `
  --data-binary "@$bodyPath"
