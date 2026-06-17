#!/usr/bin/env python3
"""Pass one agent-runner-work.v1 packet to Claude CLI, Agent SDK, or Messages API."""
from __future__ import annotations

import asyncio
import json
import os
import shlex
import subprocess
import sys
from typing import Any
from urllib import error, request

SENSITIVE_LEVELS = {"confidential", "restricted"}

DEFAULT_PROMPT = """You are a Claude agent receiving an agent-bus work packet from a runner.
Handle the JSON work packet provided on stdin.
Use referenced files when needed, respect sensitivity and retention fields, and return a concise bus report.
Autonomous work is the default. Do not create tickets for routine next steps.
Report only the result text. Include judgment, output, risk, and next action when they matter."""


def env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None or value == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def sensitive_marks(value: Any) -> set[str]:
    marks: set[str] = set()
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


def load_work() -> dict[str, Any]:
    try:
        value = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(f"invalid work JSON: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    if not isinstance(value, dict):
        print("work packet must be a JSON object", file=sys.stderr)
        raise SystemExit(1)
    if sensitive_marks(value) & SENSITIVE_LEVELS and not os.environ.get("AGENTBUS_ALLOW_SENSITIVE"):
        print("sensitive work packet blocked; set AGENTBUS_ALLOW_SENSITIVE to run", file=sys.stderr)
        raise SystemExit(2)
    return value


def mode_name() -> str:
    mode = os.environ.get("CLAUDE_RUNNER_MODE", "cli").strip().lower() or "cli"
    if mode == "auto":
        try:
            import claude_agent_sdk  # noqa: F401
        except ImportError:
            if os.environ.get("ANTHROPIC_API_KEY"):
                return "api"
            return "cli"
        return "sdk"
    if mode not in {"cli", "sdk", "api"}:
        print("CLAUDE_RUNNER_MODE must be cli, sdk, api, or auto", file=sys.stderr)
        raise SystemExit(1)
    return mode


def base_prompt(work: dict[str, Any]) -> str:
    prompt = os.environ.get("CLAUDE_RUNNER_PROMPT", DEFAULT_PROMPT).strip() or DEFAULT_PROMPT
    subject = str(work.get("subject") or "").strip()
    task_id = str(work.get("taskId") or "").strip()
    message_id = str(work.get("messageId") or "").strip()
    header = []
    if subject:
        header.append(f"Subject: {subject}")
    if task_id:
        header.append(f"Task: {task_id}")
    if message_id:
        header.append(f"Message: {message_id}")
    if header:
        prompt = prompt + "\n\n" + "\n".join(header)
    return prompt


def work_json(work: dict[str, Any]) -> str:
    return json.dumps(work, ensure_ascii=False, sort_keys=True, indent=2)


def dry_run(mode: str, work: dict[str, Any]) -> int:
    print(json.dumps({
        "ok": True,
        "dryRun": True,
        "mode": mode,
        "prompt": base_prompt(work),
        "messageId": work.get("messageId", ""),
        "taskId": work.get("taskId", ""),
        "subject": work.get("subject", ""),
        "work": work,
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def timeout_seconds() -> float | None:
    raw = os.environ.get("CLAUDE_RUNNER_TIMEOUT", "0").strip()
    if not raw:
        return None
    try:
        value = float(raw)
    except ValueError as exc:
        print("CLAUDE_RUNNER_TIMEOUT must be a number", file=sys.stderr)
        raise SystemExit(1) from exc
    return value if value > 0 else None


def run_cli(work: dict[str, Any]) -> int:
    cli = shlex.split(os.environ.get("CLAUDE_RUNNER_CLI", "claude")) or ["claude"]
    args = cli[:]
    model = os.environ.get("CLAUDE_RUNNER_MODEL", "").strip()
    permission_mode = os.environ.get("CLAUDE_RUNNER_PERMISSION_MODE", "").strip()
    max_turns = os.environ.get("CLAUDE_RUNNER_MAX_TURNS", "").strip()
    output_format = os.environ.get("CLAUDE_RUNNER_OUTPUT_FORMAT", "").strip()
    cwd = os.environ.get("CLAUDE_RUNNER_CWD", "").strip()
    extra = os.environ.get("CLAUDE_RUNNER_EXTRA_ARGS", "").strip()
    if env_bool("CLAUDE_RUNNER_BARE"):
        args.append("--bare")
    if model:
        args.extend(["--model", model])
    if permission_mode:
        args.extend(["--permission-mode", permission_mode])
    if max_turns:
        args.extend(["--max-turns", max_turns])
    if output_format:
        args.extend(["--output-format", output_format])
    if extra:
        args.extend(shlex.split(extra))
    args.extend(["-p", base_prompt(work)])
    try:
        proc = subprocess.run(
            args,
            input=work_json(work) + "\n",
            text=True,
            cwd=cwd or None,
            capture_output=True,
            timeout=timeout_seconds(),
            check=False,
        )
    except FileNotFoundError:
        print(f"claude CLI not found: {cli[0]}", file=sys.stderr)
        return 127
    except subprocess.TimeoutExpired:
        print("claude CLI timed out", file=sys.stderr)
        return 124
    if proc.stderr:
        print(proc.stderr, file=sys.stderr, end="")
    if proc.stdout:
        print(proc.stdout.strip())
    return proc.returncode


def collect_sdk_text(message: Any) -> str:
    result = getattr(message, "result", None)
    if result:
        return str(result)
    content = getattr(message, "content", None)
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            text = getattr(block, "text", None)
            if text is None and isinstance(block, dict):
                text = block.get("text")
            if text:
                parts.append(str(text))
        return "\n".join(parts)
    return ""


async def run_sdk_async(work: dict[str, Any]) -> int:
    try:
        from claude_agent_sdk import ClaudeAgentOptions, query
    except ImportError:
        print("claude-agent-sdk package required for CLAUDE_RUNNER_MODE=sdk", file=sys.stderr)
        return 127
    kwargs: dict[str, Any] = {}
    model = os.environ.get("CLAUDE_RUNNER_MODEL", "").strip()
    cwd = os.environ.get("CLAUDE_RUNNER_CWD", "").strip()
    permission_mode = os.environ.get("CLAUDE_RUNNER_PERMISSION_MODE", "").strip()
    allowed_tools = [
        item.strip()
        for item in os.environ.get("CLAUDE_RUNNER_ALLOWED_TOOLS", "").split(",")
        if item.strip()
    ]
    if model:
        kwargs["model"] = model
    if cwd:
        kwargs["cwd"] = cwd
    if permission_mode:
        kwargs["permission_mode"] = permission_mode
    if allowed_tools:
        kwargs["allowed_tools"] = allowed_tools
    kwargs["system_prompt"] = base_prompt(work)
    options = ClaudeAgentOptions(**kwargs)
    out: list[str] = []
    async for message in query(prompt="Work packet JSON:\n" + work_json(work), options=options):
        text = collect_sdk_text(message)
        if text:
            out.append(text)
    if out:
        print("\n".join(out).strip())
    return 0


def run_sdk(work: dict[str, Any]) -> int:
    try:
        return asyncio.run(run_sdk_async(work))
    except TypeError as exc:
        print(f"claude-agent-sdk option error: {exc}", file=sys.stderr)
        return 1


def api_key() -> str:
    key_env = os.environ.get("CLAUDE_RUNNER_API_KEY_ENV", "ANTHROPIC_API_KEY").strip() or "ANTHROPIC_API_KEY"
    value = os.environ.get(key_env, "").strip()
    if not value:
        print(f"{key_env} required for CLAUDE_RUNNER_MODE=api", file=sys.stderr)
        raise SystemExit(1)
    return value


def max_tokens() -> int:
    raw = os.environ.get("CLAUDE_RUNNER_MAX_TOKENS", "1024").strip() or "1024"
    try:
        value = int(raw)
    except ValueError as exc:
        print("CLAUDE_RUNNER_MAX_TOKENS must be an integer", file=sys.stderr)
        raise SystemExit(1) from exc
    if value <= 0:
        print("CLAUDE_RUNNER_MAX_TOKENS must be positive", file=sys.stderr)
        raise SystemExit(1)
    return value


def api_model() -> str:
    model = os.environ.get("CLAUDE_RUNNER_MODEL", "").strip() or os.environ.get("ANTHROPIC_MODEL", "").strip()
    if not model:
        print("CLAUDE_RUNNER_MODEL or ANTHROPIC_MODEL required for CLAUDE_RUNNER_MODE=api", file=sys.stderr)
        raise SystemExit(1)
    return model


def run_api(work: dict[str, Any]) -> int:
    endpoint = os.environ.get("CLAUDE_RUNNER_ENDPOINT", "https://api.anthropic.com/v1/messages").strip()
    version = os.environ.get("CLAUDE_RUNNER_ANTHROPIC_VERSION", "2023-06-01").strip() or "2023-06-01"
    body: dict[str, Any] = {
        "model": api_model(),
        "max_tokens": max_tokens(),
        "system": base_prompt(work),
        "messages": [{"role": "user", "content": "Work packet JSON:\n" + work_json(work)}],
    }
    extra = os.environ.get("CLAUDE_RUNNER_EXTRA_JSON", "").strip()
    if extra:
        try:
            extra_value = json.loads(extra)
        except json.JSONDecodeError as exc:
            print(f"invalid CLAUDE_RUNNER_EXTRA_JSON: {exc}", file=sys.stderr)
            return 1
        if not isinstance(extra_value, dict):
            print("CLAUDE_RUNNER_EXTRA_JSON must be a JSON object", file=sys.stderr)
            return 1
        body.update(extra_value)
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = request.Request(
        endpoint,
        data=data,
        method="POST",
        headers={
            "content-type": "application/json",
            "anthropic-version": version,
            "x-api-key": api_key(),
        },
    )
    try:
        with request.urlopen(req, timeout=timeout_seconds()) as resp:
            response = json.loads(resp.read().decode("utf-8"))
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")
        print(f"Claude Messages API failed: HTTP {exc.code} {detail}", file=sys.stderr)
        return 1
    except error.URLError as exc:
        print(f"Claude Messages API failed: {exc}", file=sys.stderr)
        return 1
    text_parts = [
        str(block.get("text"))
        for block in response.get("content", [])
        if isinstance(block, dict) and block.get("type") == "text" and block.get("text")
    ]
    if text_parts:
        print("\n".join(text_parts).strip())
    else:
        print(json.dumps(response, ensure_ascii=False, sort_keys=True))
    return 0


def main() -> int:
    work = load_work()
    mode = mode_name()
    if env_bool("CLAUDE_RUNNER_DRY_RUN"):
        return dry_run(mode, work)
    if mode == "sdk":
        return run_sdk(work)
    if mode == "api":
        return run_api(work)
    return run_cli(work)


if __name__ == "__main__":
    raise SystemExit(main())
