$bodyPath = 'D:\relay\backend\captures\codex\20260509-232441-555-v1-responses.body.json'
curl.exe -N 'http://localhost:8080/v1/responses' `
  -H 'Originator: Codex Desktop' `
  -H 'Content-Type: application/json' `
  -H 'Accept: text/event-stream' `
  -H 'X-Client-Request-Id: codex-local-smoke-1742965a-596e-41c1-91d3-88d7f930c236' `
  -H 'Authorization: Bearer relay_6YeQcKIJ7uPavT5q5OyAph8SFTaxDcWcrys72DIf8zo' `
  -H 'X-Codex-Window-Id: codex-local-smoke-1742965a-596e-41c1-91d3-88d7f930c236:0' `
  -H 'User-Agent: Codex Desktop/0.128.0-alpha.1 (Windows 10.0.19045; x86_64)' `
  -H 'Expect: 100-continue' `
  --data-binary "@$bodyPath"
