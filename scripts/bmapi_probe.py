import json, time, uuid, sys
import urllib.request, urllib.error, ssl, socket

BASE  = "https://bmapi.020212.xyz"
KEY   = "sk-edc68fbd91fb69425453f60818d4bea86c649dd04f01f420411d4c48526a1b11"
MODEL = "gpt-5.5"

body = {
    "model": MODEL,
    "instructions": "You are a concise upstream health-check responder.",
    "input": [{
        "type": "message",
        "role": "user",
        "content": [{"type": "input_text", "text": "Reply with exactly this JSON: {\"message\":\"bmapi ok\"}"}],
    }],
    "store": False,
    "parallel_tool_calls": True,
    "reasoning": {"effort": "low"},
    "stream": True,
}

req = urllib.request.Request(
    BASE + "/v1/responses",
    data=json.dumps(body).encode("utf-8"),
    headers={
        "Authorization": "Bearer " + KEY,
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
        "User-Agent": "codex_cli_rs/0.126.0 (Windows 10; x86_64) direct-test",
        "Originator": "codex_cli_rs",
        "X-Client-Request-Id": str(uuid.uuid4()),
    },
    method="POST",
)

print(f"target={BASE}/v1/responses  model={MODEL}  stream=true")
socket.setdefaulttimeout(180)
started = time.perf_counter()
first_ms = None
events = {}
text = []
bytes_read = 0
errs = []
previews = []
status = None
try:
    with urllib.request.urlopen(req, context=ssl.create_default_context(), timeout=180) as resp:
        status = resp.status
        ct = resp.headers.get("Content-Type")
        print(f"http_status={status}  Content-Type={ct}")
        for raw in resp:
            if first_ms is None:
                first_ms = (time.perf_counter() - started) * 1000
            line = raw.decode("utf-8", "replace")
            bytes_read += len(raw)
            for ln in line.splitlines():
                if ln.startswith("event:"):
                    ev = ln[6:].strip()
                elif ln.startswith("data:"):
                    events["data_lines"] = events.get("data_lines", 0) + 1
                    data = ln[5:].lstrip()
                    if data == "[DONE]":
                        events["done"] = events.get("done", 0) + 1
                    else:
                        try:
                            obj = json.loads(data)
                            t = obj.get("type", "?")
                            events[t] = events.get(t, 0) + 1
                            if t in ("response.output_text.delta", "response.refusal.delta"):
                                text.append(obj.get("delta", ""))
                            if "error" in obj:
                                errs.append(json.dumps(obj)[:1500])
                        except Exception:
                            events["bad_json"] = events.get("bad_json", 0) + 1
                    if len(previews) < 3:
                        previews.append(data[:600])
except urllib.error.HTTPError as e:
    status = e.code
    print(f"HTTPError={e.code} body={e.read()[:600]!r}")
except Exception as e:
    errs.append(f"{type(e).__name__}: {e}")
    print(f"EXC: {type(e).__name__}: {e}")

total_ms = (time.perf_counter() - started) * 1000
print(f"total_ms={total_ms:.1f}  first_event_ms={(first_ms or 0):.1f}  bytes={bytes_read}")
print(f"events={events}")
print(f"text_preview={''.join(text)[:400]!r}")
if errs: print(f"errors={errs}")
print("raw_previews:")
for p in previews:
    print("  " + p)
