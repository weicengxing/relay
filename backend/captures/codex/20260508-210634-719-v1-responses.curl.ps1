$bodyPath = 'D:\relay\backend\captures\codex\20260508-210634-719-v1-responses.body.json'
curl.exe -N 'http://localhost:8080/v1/responses' `
  -H 'x-codex-beta-features: terminal_resize_reflow' `
  -H 'x-codex-turn-metadata: {"session_id":"019e06a5-1b02-7f50-8a08-ae2c1a2c529b","thread_source":"user","turn_id":"019e07b1-3565-7c11-91e4-66ca1dadd0d9","workspaces":{"D:\\relay":{"associated_remote_urls":{"origin":"https://github.com/weicengxing/relay.git"},"latest_git_commit_hash":"6128e238e0064141e1112da6949e1e2f3fa0ca1a"}},"sandbox":"windows_elevated","turn_started_at_unix_ms":1778245514710}' `
  -H 'x-codex-window-id: 019e06a5-1b02-7f50-8a08-ae2c1a2c529b:2' `
  -H 'x-client-request-id: 019e06a5-1b02-7f50-8a08-ae2c1a2c529b' `
  -H 'session_id: 019e06a5-1b02-7f50-8a08-ae2c1a2c529b' `
  -H 'accept: text/event-stream' `
  -H 'authorization: Bearer relay_BgV7MZudDLOUS5EiZZpi_f9hMZ5ZsxecqtZjLPXstoI' `
  -H 'content-type: application/json' `
  -H 'originator: Codex Desktop' `
  -H 'user-agent: Codex Desktop/0.128.0-alpha.1 (Windows 10.0.19045; x86_64) unknown (Codex Desktop; 26.429.30905)' `
  --data-binary "@$bodyPath"
