$bodyPath = 'D:\relay\backend\captures\codex\20260508-164005-768-v1-responses.body.json'
curl.exe -N 'http://localhost:8080/v1/responses' `
  -H 'x-codex-beta-features: terminal_resize_reflow' `
  -H 'x-codex-turn-metadata: {"session_id":"019e06be-74f3-7b53-b6d4-702fb75e9460","thread_source":"user","turn_id":"019e06be-7572-7df3-a483-044a3627b9bb","sandbox":"windows_elevated","turn_started_at_unix_ms":1778229605751}' `
  -H 'x-codex-window-id: 019e06be-74f3-7b53-b6d4-702fb75e9460:0' `
  -H 'x-client-request-id: 019e06be-74f3-7b53-b6d4-702fb75e9460' `
  -H 'session_id: 019e06be-74f3-7b53-b6d4-702fb75e9460' `
  -H 'accept: text/event-stream' `
  -H 'authorization: Bearer relay_BgV7MZudDLOUS5EiZZpi_f9hMZ5ZsxecqtZjLPXstoI' `
  -H 'content-type: application/json' `
  -H 'originator: Codex Desktop' `
  -H 'user-agent: Codex Desktop/0.128.0-alpha.1 (Windows 10.0.19045; x86_64) unknown (Codex Desktop; 26.429.30905)' `
  --data-binary "@$bodyPath"
