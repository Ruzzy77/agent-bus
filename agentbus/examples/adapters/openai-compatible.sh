#!/usr/bin/env sh
# OpenAI-compatible outbound adapter. Reads one JSON payload from stdin.
# Required: OPENAI_COMPAT_ENDPOINT, OPENAI_COMPAT_MODEL, and API key env.
# Default API key env: OPENAI_COMPAT_API_KEY. Override with OPENAI_COMPAT_TOKEN_ENV.

set -eu

payload_tmp=$(mktemp "${TMPDIR:-/tmp}/agentbus-openai-payload.XXXXXX")
cleanup() { rm -f "$payload_tmp"; }
trap cleanup EXIT INT TERM
cat > "$payload_tmp"

python3 - "$payload_tmp" <<'PY'
import json
import os
import shlex
import subprocess
import sys
import urllib.error
import urllib.request

payload_path = sys.argv[1]
with open(payload_path, encoding="utf-8") as f:
    payload = json.load(f)


def sensitive_marks(value):
    marks = set()
    if isinstance(value, dict):
        level = str(value.get("sensitivity", "")).strip().lower()
        if level:
            marks.add(level)
        for child in value.values():
            marks.update(sensitive_marks(child))
    elif isinstance(value, list):
        for child in value:
            marks.update(sensitive_marks(child))
    return marks


if sensitive_marks(payload) & {"confidential", "restricted"}:
    if not os.environ.get("AGENTBUS_ALLOW_SENSITIVE"):
        print("sensitive payload blocked; set AGENTBUS_ALLOW_SENSITIVE to send", file=sys.stderr)
        raise SystemExit(2)

endpoint = os.environ.get("OPENAI_COMPAT_ENDPOINT", "").strip()
model = os.environ.get("OPENAI_COMPAT_MODEL", "").strip()
token_env = os.environ.get("OPENAI_COMPAT_TOKEN_ENV", "OPENAI_COMPAT_API_KEY").strip() or "OPENAI_COMPAT_API_KEY"
token = os.environ.get(token_env, "")
if not endpoint:
    print("OPENAI_COMPAT_ENDPOINT required", file=sys.stderr)
    raise SystemExit(1)
if not model:
    print("OPENAI_COMPAT_MODEL required", file=sys.stderr)
    raise SystemExit(1)
if not token:
    print(f"{token_env} required", file=sys.stderr)
    raise SystemExit(1)

system = os.environ.get(
    "OPENAI_COMPAT_SYSTEM",
    "You read local coordination payloads and return concise assessment, next action, or decision support.",
)
instruction = os.environ.get(
    "OPENAI_COMPAT_INSTRUCTION",
    "Read this JSON payload. Preserve important evidence, disagreements, evidence gaps, and decisions needed.",
)
request_body = {
    "model": model,
    "messages": [
        {"role": "system", "content": system},
        {"role": "user", "content": instruction + "\n\n" + json.dumps(payload, ensure_ascii=False, sort_keys=True)},
    ],
}
extra = os.environ.get("OPENAI_COMPAT_EXTRA_JSON", "").strip()
if extra:
    request_body.update(json.loads(extra))

headers = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {token}",
}
if os.environ.get("OPENAI_COMPAT_REFERER"):
    headers["HTTP-Referer"] = os.environ["OPENAI_COMPAT_REFERER"]
if os.environ.get("OPENAI_COMPAT_TITLE"):
    headers["X-Title"] = os.environ["OPENAI_COMPAT_TITLE"]

timeout = float(os.environ.get("OPENAI_COMPAT_TIMEOUT", "60"))
req = urllib.request.Request(
    endpoint,
    data=json.dumps(request_body, ensure_ascii=False).encode("utf-8"),
    headers=headers,
    method="POST",
)
try:
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        response_text = resp.read().decode("utf-8")
except urllib.error.HTTPError as exc:
    detail = exc.read().decode("utf-8", errors="replace")
    print(f"HTTP {exc.code}: {detail}", file=sys.stderr)
    raise SystemExit(1)
except urllib.error.URLError as exc:
    print(str(exc), file=sys.stderr)
    raise SystemExit(1)

try:
    response = json.loads(response_text)
except json.JSONDecodeError:
    print("response was not JSON", file=sys.stderr)
    print(response_text, file=sys.stderr)
    raise SystemExit(1)

content = ""
choices = response.get("choices")
if isinstance(choices, list) and choices:
    first = choices[0]
    if isinstance(first, dict):
        message = first.get("message")
        if isinstance(message, dict):
            value = message.get("content")
            if isinstance(value, list):
                content = "\n".join(
                    str(part.get("text", "")) if isinstance(part, dict) else str(part)
                    for part in value
                ).strip()
            elif value is not None:
                content = str(value).strip()
        if not content and first.get("text") is not None:
            content = str(first.get("text", "")).strip()
if not content and response.get("output_text") is not None:
    content = str(response.get("output_text", "")).strip()
if not content:
    content = json.dumps(response, ensure_ascii=False, sort_keys=True)

summary = {
    "ok": True,
    "model": response.get("model") or model,
    "responseId": response.get("id", ""),
    "content": content,
}
if isinstance(response.get("usage"), dict):
    summary["usage"] = response["usage"]
print(json.dumps(summary, ensure_ascii=False, sort_keys=True))

to = os.environ.get("OPENAI_COMPAT_RESPONSE_TO", "").strip()
if to:
    cli = shlex.split(os.environ.get("AGENTBUS_CLI", "agentbus")) or ["agentbus"]
    sender = os.environ.get("OPENAI_COMPAT_RESPONSE_FROM", "openai-compatible")
    kind = os.environ.get("OPENAI_COMPAT_RESPONSE_KIND", "report")
    subject = os.environ.get("OPENAI_COMPAT_RESPONSE_SUBJECT", "Model response")
    subprocess.run(
        cli + ["send", "--from", sender, "--to", to, "--kind", kind, "--subject", subject, "--body", content],
        check=True,
        stdout=subprocess.DEVNULL,
    )
PY
