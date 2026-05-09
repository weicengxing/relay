$bodyPath = 'D:\relay\backend\captures\codex\20260509-230504-304-v1-responses.body.json'
curl.exe -N 'http://api.relaywei.ccwu.cc/v1/responses' `
  -H 'User-Agent: Codex Desktop/0.128.0-alpha.1 (Windows 10.0.19045; x86_64)' `
  -H 'Accept: text/event-stream' `
  -H 'Accept-Encoding: gzip' `
  -H 'Authorization: Bearer relay_6YeQcKIJ7uPavT5q5OyAph8SFTaxDcWcrys72DIf8zo' `
  -H 'Cdn-Loop: cloudflare; loops=1' `
  -H 'Cf-Connecting-Ip: 58.194.169.0' `
  -H 'Cf-Ipcountry: CN' `
  -H 'Cf-Ray: 9f9199a8dd588211-SIN' `
  -H 'Cf-Visitor: {"scheme":"http"}' `
  -H 'Cf-Warp-Tag-Id: 929132cd-2637-4154-a5d1-78aaa6b3466d' `
  -H 'Content-Type: application/json' `
  -H 'Originator: Codex Desktop' `
  -H 'X-Client-Request-Id: codex-xiaomi-cleanup-smoke-1' `
  -H 'X-Codex-Window-Id: codex-xiaomi-cleanup-smoke-1:0' `
  -H 'X-Forwarded-For: 58.194.169.0' `
  -H 'X-Forwarded-Proto: http' `
  --data-binary "@$bodyPath"
