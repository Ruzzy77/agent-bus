#!/usr/bin/env python3
"""Pass one agent-runner-work.v1 packet to Codex CLI or SDK."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
from typing import Any

SENSITIVE_LEVELS = {"confidential", "restricted"}

DEFAULT_PROMPT = """You are a Codex agent receiving an agent-bus work packet from a runner.
Handle the JSON work packet provided on stdin.
Use referenced files when needed, respect sensitivity and retention fields, and return a concise bus report.
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
    mode = os.environ.get("CODEX_RUNNER_MODE", "cli").strip().lower() or "cli"
    if mode == "auto":
        try:
            import openai_codex  # noqa: F401
        except ImportError:
            return "cli"
        return "sdk"
    if mode not in {"cli", "sdk"}:
        print("CODEX_RUNNER_MODE must be cli, sdk, or auto", file=sys.stderr)
        raise SystemExit(1)
    return mode


def base_prompt(work: dict[str, Any]) -> str:
    prompt = os.environ.get("CODEX_RUNNER_PROMPT", DEFAULT_PROMPT).strip() or DEFAULT_PROMPT
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
    raw = os.environ.get("CODEX_RUNNER_TIMEOUT", "0").strip()
    if not raw:
        return None
    try:
        value = float(raw)
    except ValueError as exc:
        print("CODEX_RUNNER_TIMEOUT must be a number", file=sys.stderr)
        raise SystemExit(1) from exc
    return value if value > 0 else None


def run_cli(work: dict[str, Any]) -> int:
    cli = shlex.split(os.environ.get("CODEX_RUNNER_CLI", "codex")) or ["codex"]
    resume = os.environ.get("CODEX_RUNNER_RESUME", "").strip()
    model = os.environ.get("CODEX_RUNNER_MODEL", "").strip()
    sandbox = os.environ.get("CODEX_RUNNER_SANDBOX", "").strip()
    cwd = os.environ.get("CODEX_RUNNER_CWD", "").strip()
    extra = os.environ.get("CODEX_RUNNER_EXTRA_ARGS", "").strip()
    if resume:
        args = cli + ["exec", "resume"]
        if model:
            args.extend(["--model", model])
        if extra:
            args.extend(shlex.split(extra))
        args.append("--last" if resume == "last" else resume)
        if sandbox or cwd:
            print("CODEX_RUNNER_SANDBOX and CODEX_RUNNER_CWD are ignored with CODEX_RUNNER_RESUME", file=sys.stderr)
    else:
        args = cli + ["exec"]
        if model:
            args.extend(["--model", model])
        if sandbox:
            args.extend(["--sandbox", sandbox])
        if cwd:
            args.extend(["--cd", cwd])
        if extra:
            args.extend(shlex.split(extra))
    args.append(base_prompt(work))
    try:
        proc = subprocess.run(
            args,
            input=work_json(work) + "\n",
            text=True,
            capture_output=True,
            timeout=timeout_seconds(),
            check=False,
        )
    except FileNotFoundError:
        print(f"codex CLI not found: {cli[0]}", file=sys.stderr)
        return 127
    except subprocess.TimeoutExpired:
        print("codex CLI timed out", file=sys.stderr)
        return 124
    if proc.stderr:
        print(proc.stderr, file=sys.stderr, end="")
    if proc.stdout:
        print(proc.stdout.strip())
    return proc.returncode


def sdk_sandbox(value: str):
    if not value:
        return None
    try:
        from openai_codex import Sandbox
    except ImportError as exc:
        print("openai-codex package required for CODEX_RUNNER_MODE=sdk", file=sys.stderr)
        raise SystemExit(127) from exc
    name = value.strip().lower().replace("-", "_")
    try:
        return getattr(Sandbox, name)
    except AttributeError:
        print("CODEX_RUNNER_SANDBOX must be read-only, workspace-write, or full-access for sdk mode", file=sys.stderr)
        raise SystemExit(1)


def run_sdk(work: dict[str, Any]) -> int:
    try:
        from openai_codex import Codex
    except ImportError:
        print("openai-codex package required for CODEX_RUNNER_MODE=sdk", file=sys.stderr)
        return 127
    cwd = os.environ.get("CODEX_RUNNER_CWD", "").strip()
    old_cwd = None
    if cwd:
        old_cwd = Path.cwd()
        os.chdir(cwd)
    model = os.environ.get("CODEX_RUNNER_MODEL", "").strip()
    sandbox = sdk_sandbox(os.environ.get("CODEX_RUNNER_SANDBOX", "").strip())
    kwargs: dict[str, Any] = {}
    if model:
        kwargs["model"] = model
    if sandbox is not None:
        kwargs["sandbox"] = sandbox
    prompt = base_prompt(work) + "\n\nWork packet JSON:\n" + work_json(work)
    try:
        with Codex() as codex:
            thread = codex.thread_start(**kwargs)
            result = thread.run(prompt)
    finally:
        if old_cwd is not None:
            os.chdir(old_cwd)
    final = getattr(result, "final_response", "")
    if final:
        print(str(final).strip())
    return 0


def main() -> int:
    work = load_work()
    mode = mode_name()
    if env_bool("CODEX_RUNNER_DRY_RUN"):
        return dry_run(mode, work)
    if mode == "sdk":
        return run_sdk(work)
    return run_cli(work)


if __name__ == "__main__":
    raise SystemExit(main())
