$bodyPath = 'D:\relay\backend\captures\codex\20260508-214053-518-v1-responses.body.json'
curl.exe -N 'http://localhost:8080/v1/responses' `
  -H 'x-codex-beta-features: terminal_resize_reflow' `
  -H 'x-codex-turn-metadata: {"session_id":"019e07d1-d5f6-7ba2-8c76-da75c70ccae8","thread_source":"user","turn_id":"019e07d1-d74d-78a1-a17e-7b728586d7c3","sandbox":"windows_elevated","turn_started_at_unix_ms":1778247653219}' `
  -H 'x-codex-window-id: 019e07d1-d5f6-7ba2-8c76-da75c70ccae8:0' `
  -H 'x-client-request-id: 019e07d1-d5f6-7ba2-8c76-da75c70ccae8' `
  -H 'session_id: 019e07d1-d5f6-7ba2-8c76-da75c70ccae8' `
  -H 'accept: text/event-stream' `
  -H 'authorization: Bearer relay_BgV7MZudDLOUS5EiZZpi_f9hMZ5ZsxecqtZjLPXstoI' `
  -H 'content-type: application/json' `
  -H 'originator: Codex Desktop' `
  -H 'user-agent: Codex Desktop/0.128.0-alpha.1 (Windows 10.0.19045; x86_64) unknown (Codex Desktop; 26.429.30905)' `
  --data-binary "@$bodyPath"
