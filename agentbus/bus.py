#!/usr/bin/env python3
"""File-based message, status, and task bus for local agents.

Stdlib only. Config precedence: CLI flag > AGENTBUS_* env > cwd.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import json
import os
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _env_path(name: str, fallback: Path) -> Path:
    value = os.environ.get(name)
    return Path(value).expanduser() if value else fallback


def _env_int(name: str, fallback: int) -> int:
    value = os.environ.get(name)
    if not value:
        return fallback
    try:
        return int(value)
    except ValueError:
        return fallback


def _clean_text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text or default


def _required_text(value: Any, name: str) -> str:
    text = _clean_text(value)
    if not text:
        raise ValueError(f"{name} required")
    return text


def _choice(value: Any, name: str, choices: list[str]) -> str:
    text = _required_text(value, name)
    if text not in choices:
        raise ValueError(f"invalid {name}: {text}")
    return text


def _string_list(value: object) -> list[str]:
    if isinstance(value, (list, tuple, set)):
        return [str(v).strip() for v in value if v is not None and str(v).strip()]
    if isinstance(value, str):
        return [v.strip() for v in value.split(",") if v.strip()]
    return []


def _value_list(value: object) -> list[str]:
    if isinstance(value, (list, tuple, set)):
        return [str(v).strip() for v in value if v is not None and str(v).strip()]
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    return []


def _flat_string_list(values: object) -> list[str]:
    if isinstance(values, (list, tuple, set)):
        out: list[str] = []
        for value in values:
            out.extend(_string_list(value))
        return out
    return _string_list(values)


def _optional_choice(value: Any, name: str, choices: list[str]) -> str:
    text = _clean_text(value).lower()
    if not text:
        return ""
    if text not in choices:
        raise ValueError(f"invalid {name}: {text}")
    return text


def security_fields(sensitivity: object = "", retention: object = "") -> dict[str, str]:
    fields: dict[str, str] = {}
    level = _optional_choice(sensitivity, "sensitivity", SENSITIVITY_LEVELS)
    policy = _optional_choice(retention, "retention", RETENTION_POLICIES)
    if level and level != "public":
        fields["sensitivity"] = level
    if policy and policy != "normal":
        fields["retention"] = policy
    return fields


def effective_sensitivity(value: Any) -> str:
    if not isinstance(value, dict):
        return "public"
    text = _clean_text(value.get("sensitivity")).lower()
    if not text:
        return "public"
    return text if text in SENSITIVITY_LEVELS else "restricted"


def effective_retention(value: Any) -> str:
    if not isinstance(value, dict):
        return "normal"
    text = _clean_text(value.get("retention")).lower()
    if not text:
        return "normal"
    return text if text in RETENTION_POLICIES else "normal"


def security_marks(value: Any) -> dict[str, set[str]]:
    sensitivities: set[str] = set()
    retentions: set[str] = set()

    def walk(item: Any) -> None:
        if isinstance(item, dict):
            if "sensitivity" in item:
                sensitivities.add(effective_sensitivity(item))
            if "retention" in item:
                retentions.add(effective_retention(item))
            for child in item.values():
                walk(child)
        elif isinstance(item, list):
            for child in item:
                walk(child)

    walk(value)
    return {"sensitivity": sensitivities, "retention": retentions}


def payload_is_sensitive(value: Any) -> bool:
    return bool(security_marks(value)["sensitivity"] & SENSITIVE_LEVELS)


def sensitive_summary(value: Any) -> str:
    marks = security_marks(value)
    levels = sorted(marks["sensitivity"] & SENSITIVE_LEVELS)
    policies = sorted(p for p in marks["retention"] if p != "normal")
    parts = []
    if levels:
        parts.append("sensitivity=" + ",".join(levels))
    if policies:
        parts.append("retention=" + ",".join(policies))
    return "; ".join(parts) or "no sensitive marks"


def allow_sensitive_env() -> bool:
    return os.environ.get("AGENTBUS_ALLOW_SENSITIVE", "").lower() in {"1", "true", "yes"}


# 기본 경로: AGENTBUS_* env, cwd 순서. CLI 인자가 최우선이다.
DEFAULT_BUS_DIR = _env_path("AGENTBUS_BUS_DIR", Path.cwd() / ".agent-bus")
CARDS_DIR = _env_path("AGENTBUS_CARDS_DIR", Path.cwd() / "agent-cards")
DEFAULT_ROOT = _env_path("AGENTBUS_ROOT", Path.cwd())
DEFAULT_PORT = _env_int("AGENTBUS_PORT", 8765)
WORKFLOW_PATH = Path(__file__).resolve().parent / "skills" / "agent-bus-workflow" / "SKILL.md"
LOOP_PATH = Path(__file__).resolve().parent / "skills" / "agent-bus-loop" / "SKILL.md"
EXAMPLES_DIR = Path(__file__).resolve().parent / "examples"

# 작업 상태값.
TASK_STATES = ["submitted", "working", "input_required", "completed", "failed", "canceled"]
AGENT_STATES = ["running", "waiting", "done", "error"]
ISSUE_STATES = ["open", "accepted", "rejected"]
SENSITIVITY_LEVELS = ["public", "internal", "confidential", "restricted"]
RETENTION_POLICIES = ["normal", "session", "no_archive"]
SENSITIVE_LEVELS = {"confidential", "restricted"}
EVENT_VERSION = "agentbus.event.v1"
EVENT_LOGS = ("messages", "message_deletes", "tasks", "issues", "acks", "delivered")
WAKEUP_PROFILE_VERSION = "wakeup-profile.v1"
WAKEUP_MODES = {"inbox", "events"}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def archive_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _archive_name_parts(path: Path, key: str) -> tuple[str, int]:
    body = path.name.removeprefix(f"{key}.").removesuffix(".jsonl")
    stamp, dot, suffix = body.rpartition(".")
    if dot and suffix.isdecimal():
        return stamp, int(suffix)
    return body, 0


def _archive_sort_key(path: Path, key: str) -> tuple[str, int, str]:
    stamp, suffix = _archive_name_parts(path, key)
    return stamp, suffix, path.name


def _archive_paths(archive_dir: Path, key: str) -> list[Path]:
    return sorted(archive_dir.glob(f"{key}.*.jsonl"), key=lambda path: _archive_sort_key(path, key))


def _next_archive_path(archive_dir: Path, key: str, stamp: str) -> Path:
    suffixes = []
    for path in archive_dir.glob(f"{key}.{stamp}*.jsonl"):
        existing_stamp, suffix = _archive_name_parts(path, key)
        if existing_stamp == stamp:
            suffixes.append(suffix)
    if not suffixes:
        return archive_dir / f"{key}.{stamp}.jsonl"
    return archive_dir / f"{key}.{stamp}.{max(suffixes) + 1}.jsonl"


def _prune_archives(archive_dir: Path, key: str) -> None:
    keep = _env_int("AGENTBUS_ARCHIVE_KEEP", 0)
    if keep <= 0:
        return
    for old in _archive_paths(archive_dir, key)[:-keep]:
        old.unlink(missing_ok=True)


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    tmp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        tmp.write_text(text, encoding="utf-8")
        _chmod_private(tmp)
        os.replace(tmp, path)
        _chmod_private(path)
    finally:
        tmp.unlink(missing_ok=True)


def _chmod_private(path: Path) -> None:
    try:
        path.chmod(0o600)
    except OSError:
        pass


@contextmanager
def file_lock(path: Path, timeout_seconds: float = 5.0, stale_seconds: float = 30.0):
    lock = path.with_name(path.name + ".lock")
    token = f"{os.getpid()} {uuid.uuid4().hex} {now_iso()}\n"
    deadline = time.time() + timeout_seconds
    while True:
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(token)
            break
        except FileExistsError:
            try:
                if time.time() - lock.stat().st_mtime > stale_seconds:
                    lock.unlink()
                    continue
            except FileNotFoundError:
                continue
            if time.time() >= deadline:
                raise TimeoutError(f"lock timeout: {lock}")
            time.sleep(0.05)
    try:
        yield
    finally:
        try:
            if lock.read_text(encoding="utf-8") == token:
                lock.unlink()
        except FileNotFoundError:
            pass


def _append_jsonl_unlocked(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n")
    _chmod_private(path)


def append_jsonl(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with file_lock(path):
        _append_jsonl_unlocked(path, value)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            rows.append({"_decode_error": line})
    return rows


def paths(bus_dir: Path) -> dict[str, Path]:
    return {
        "messages": bus_dir / "messages.jsonl",
        "message_deletes": bus_dir / "message_deletes.jsonl",
        "acks": bus_dir / "acks.jsonl",
        "delivered": bus_dir / "delivered.jsonl",
        "status": bus_dir / "status.json",
        "stop": bus_dir / "stop.json",
        "tasks": bus_dir / "tasks.jsonl",
        "issues": bus_dir / "issues.jsonl",
    }


def fold_tasks(bus_dir: Path) -> list[dict[str, Any]]:
    """tasks.jsonl은 append 전용 이벤트 로그다. 현재 상태는 이벤트를 접어 만든다.

    삭제는 last-event-wins로 처리한다. deleted 이후 같은 task에 새 이벤트가 오면 다시 살아난다.
    """
    tasks: dict[str, dict[str, Any]] = {}
    for row in read_jsonl(paths(bus_dir)["tasks"]):
        tid = row.get("task_id")
        if not tid:
            continue
        t = tasks.setdefault(tid, {"task_id": tid, "state": "submitted", "deleted": False})
        if row.get("event") == "created":
            t.update({
                "title": row.get("title", ""),
                "by": row.get("by", ""),
                "assign": row.get("assign", []),
                "created_at": row.get("time"),
                "deleted": False,
            })
            t.update(security_fields(effective_sensitivity(row), effective_retention(row)))
        elif row.get("event") == "state":
            t["state"] = row.get("state", t["state"])
            t["note"] = row.get("note", "")
            t["state_by"] = row.get("by", "")
            t["deleted"] = False
        elif row.get("event") == "deleted":
            t["deleted"] = True
        t["updated_at"] = row.get("time")
    live = (t for t in tasks.values() if not t.get("deleted"))
    return sorted(
        ({k: v for k, v in t.items() if k != "deleted"} for t in live),
        key=lambda t: t.get("updated_at") or "", reverse=True,
    )


def _fold_issues_rows(rows: list[dict[str, Any]], include_closed: bool = False) -> list[dict[str, Any]]:
    issues: dict[str, dict[str, Any]] = {}
    for row in rows:
        iid = row.get("issue_id")
        if not iid:
            continue
        issue = issues.setdefault(iid, {"issue_id": iid, "state": "open"})
        if row.get("event") == "created":
            issue.update({
                "title": row.get("title", ""),
                "body": row.get("body", ""),
                "refs": row.get("refs", []),
                "by": row.get("by", ""),
                "created_at": row.get("time"),
                "state": "open",
            })
            issue.update(security_fields(effective_sensitivity(row), effective_retention(row)))
        elif row.get("event") in ("accepted", "rejected"):
            issue["state"] = row.get("event")
            issue["state_by"] = row.get("by", "")
            issue["note"] = row.get("note", "")
            if row.get("task_id"):
                issue["task_id"] = row.get("task_id")
            if row.get("message_id"):
                issue["message_id"] = row.get("message_id")
        issue["updated_at"] = row.get("time")
    rows_out = issues.values() if include_closed else (i for i in issues.values() if i.get("state") == "open")
    return sorted(rows_out, key=lambda i: i.get("updated_at") or "", reverse=True)


def fold_issues(bus_dir: Path, include_closed: bool = False) -> list[dict[str, Any]]:
    return _fold_issues_rows(read_jsonl(paths(bus_dir)["issues"]), include_closed)


def deleted_message_ids(bus_dir: Path) -> set[str]:
    return {
        str(row.get("id") or "")
        for row in read_jsonl(paths(bus_dir)["message_deletes"])
        if row.get("event") == "deleted" and row.get("id")
    }


def live_messages(bus_dir: Path) -> list[dict[str, Any]]:
    deleted = deleted_message_ids(bus_dir)
    return [row for row in read_jsonl(paths(bus_dir)["messages"]) if row.get("id") not in deleted]


def _event_object(source: str, row: dict[str, Any]) -> dict[str, str]:
    if source in ("messages", "message_deletes", "acks", "delivered"):
        return {"type": "message", "id": str(row.get("id") or "")}
    if source == "tasks":
        return {"type": "task", "id": str(row.get("task_id") or "")}
    return {"type": "ticket", "id": str(row.get("issue_id") or "")}


def _event_type(source: str, row: dict[str, Any]) -> str:
    if source == "messages":
        return "message.created"
    if source == "message_deletes":
        return "message.deleted"
    if source == "acks":
        return "message.acked"
    if source == "delivered":
        return "message.delivered"
    if source == "tasks":
        event = row.get("event") or "changed"
        return "task.state" if event == "state" else f"task.{event}"
    if source == "issues":
        return f"ticket.{row.get('event') or 'changed'}"
    return f"log.{source}"


def _event_actor(source: str, row: dict[str, Any]) -> str:
    if source == "messages":
        return str(row.get("from") or "")
    if source in ("acks", "delivered"):
        return str(row.get("agent") or "")
    return str(row.get("by") or "")


def _event_target(source: str, row: dict[str, Any]) -> str | list[str]:
    if source == "messages":
        return str(row.get("to") or "")
    if source == "tasks":
        return _value_list(row.get("assign"))
    if source == "issues":
        return str(row.get("to") or "")
    return ""


def _event_row(source: str, line: int, row: dict[str, Any]) -> dict[str, Any]:
    obj = _event_object(source, row)
    event_id = f"{source}:{line}:{row.get('time') or ''}:{obj.get('id') or ''}"
    return {
        "version": EVENT_VERSION,
        "id": event_id,
        "cursor": event_id,
        "time": row.get("time") or "",
        "type": _event_type(source, row),
        "source": f"{source}.jsonl",
        "actor": _event_actor(source, row),
        "target": _event_target(source, row),
        "object": obj,
        "data": row,
    }


def parse_event_types(value: object) -> set[str]:
    return {v.strip() for v in str(value or "").split(",") if v.strip()}


def parse_event_targets(value: object) -> set[str]:
    return {v.strip() for v in str(value or "").split(",") if v.strip()}


def _match_event_type(event_type: str, patterns: set[str]) -> bool:
    if not patterns:
        return True
    for pattern in patterns:
        if pattern == event_type:
            return True
        if pattern.endswith(".*") and event_type.startswith(pattern[:-1]):
            return True
    return False


def _match_event_target(target: str | list[str], patterns: set[str]) -> bool:
    if not patterns:
        return True
    values = target if isinstance(target, list) else [target]
    values = [str(v) for v in values if str(v)]
    return any(v in patterns or v in ("all", "*") for v in values)


def bus_events(
    bus_dir: Path,
    types: set[str] | None = None,
    targets: set[str] | None = None,
    after: str = "",
    limit: int = 0,
) -> list[dict[str, Any]]:
    ensure_bus(bus_dir)
    ps = paths(bus_dir)
    order = {name: idx for idx, name in enumerate(EVENT_LOGS)}
    rows: list[dict[str, Any]] = []
    for source in EVENT_LOGS:
        for line, row in enumerate(read_jsonl(ps[source]), 1):
            if not isinstance(row, dict) or row.get("_decode_error"):
                continue
            event = _event_row(source, line, row)
            if _match_event_type(event["type"], types or set()) and _match_event_target(event["target"], targets or set()):
                rows.append(event)
    rows.sort(key=lambda e: (e.get("time") or "", order.get(e["source"].removesuffix(".jsonl"), 99), e["id"]))
    if after:
        for i, event in enumerate(rows):
            if event["cursor"] == after or event["id"] == after:
                rows = rows[i + 1:]
                break
    if limit > 0:
        rows = rows[-limit:]
    return rows


def _open_issue_from_rows(rows: list[dict[str, Any]], issue_id: str) -> dict[str, Any]:
    for issue in _fold_issues_rows(rows, include_closed=True):
        if issue.get("issue_id") == issue_id:
            if issue.get("state") != "open":
                raise ValueError(f"ticket already {issue.get('state')}")
            return issue
    raise ValueError("ticket not found")


def load_cards(cards_dir: Path = CARDS_DIR) -> dict[str, Any]:
    cards: dict[str, Any] = {}
    if cards_dir.is_dir():
        for path in sorted(cards_dir.glob("*.json")):
            card = load_json(path, None)
            if isinstance(card, dict):
                cards[card.get("idShort") or path.stem] = card
    return cards


def ensure_bus(bus_dir: Path) -> None:
    """Create the bus directory and status.json."""
    existed = bus_dir.exists()
    bus_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    if not existed:
        try:
            bus_dir.chmod(0o700)
        except OSError:
            pass
    ps = paths(bus_dir)
    if not ps["status"].exists():
        write_json(ps["status"], {"created_at": now_iso(), "agents": {}})


def make_message(
    sender: object,
    to: object,
    kind: object,
    subject: object,
    body: object,
    refs: object = None,
    task_id: object = "",
    reply_to: object = "",
    sensitivity: object = "",
    retention: object = "",
) -> dict[str, Any]:
    body_text = "" if body is None else str(body)
    if not body_text.strip():
        raise ValueError("body required")
    msg = {
        "id": uuid.uuid4().hex[:12],
        "time": now_iso(),
        "from": _clean_text(sender, "user"),
        "to": _clean_text(to, "all"),
        "kind": _clean_text(kind, "note"),
        "subject": _clean_text(subject),
        "body": body_text,
        "refs": _value_list(refs),
    }
    task = _clean_text(task_id)
    reply = _clean_text(reply_to)
    if task:
        msg["task_id"] = task
    if reply:
        msg["reply_to"] = reply
    msg.update(security_fields(sensitivity, retention))
    return msg


def create_task(
    bus_dir: Path,
    title: object,
    by: object,
    assign: object = None,
    task_id: object = "",
    sensitivity: object = "",
    retention: object = "",
) -> str:
    ensure_bus(bus_dir)
    tid = _clean_text(task_id) or ("t-" + uuid.uuid4().hex[:8])
    row = {
        "time": now_iso(),
        "event": "created",
        "task_id": tid,
        "title": _required_text(title, "title"),
        "by": _clean_text(by, "user"),
        "assign": _string_list(assign),
        "state": "submitted",
    }
    row.update(security_fields(sensitivity, retention))
    append_jsonl(paths(bus_dir)["tasks"], row)
    return tid


def set_task_state(bus_dir: Path, task_id: object, state: object, by: object, note: object = "") -> None:
    ensure_bus(bus_dir)
    append_jsonl(paths(bus_dir)["tasks"], {
        "time": now_iso(),
        "event": "state",
        "task_id": _required_text(task_id, "task_id"),
        "state": _choice(state, "state", TASK_STATES),
        "by": _clean_text(by, "user"),
        "note": _clean_text(note),
    })


def delete_task(bus_dir: Path, task_id: object, by: object) -> None:
    ensure_bus(bus_dir)
    append_jsonl(paths(bus_dir)["tasks"], {
        "time": now_iso(),
        "event": "deleted",
        "task_id": _required_text(task_id, "task_id"),
        "by": _clean_text(by, "user"),
    })


def delete_message(bus_dir: Path, message_id: object, by: object) -> None:
    ensure_bus(bus_dir)
    mid = _required_text(message_id, "message_id")
    ps = paths(bus_dir)
    with file_lock(ps["messages"]):
        if not any(row.get("id") == mid for row in read_jsonl(ps["messages"])):
            raise ValueError("message not found")
        if mid in deleted_message_ids(bus_dir):
            return
        _append_jsonl_unlocked(ps["message_deletes"], {
            "time": now_iso(),
            "event": "deleted",
            "id": mid,
            "by": _clean_text(by, "user"),
        })


def create_issue(
    bus_dir: Path,
    title: object,
    by: object,
    body: object = "",
    refs: object = None,
    sensitivity: object = "",
    retention: object = "",
) -> str:
    ensure_bus(bus_dir)
    iid = "i-" + uuid.uuid4().hex[:8]
    row = {
        "time": now_iso(),
        "event": "created",
        "issue_id": iid,
        "title": _required_text(title, "title"),
        "body": _clean_text(body),
        "refs": _value_list(refs),
        "by": _clean_text(by, "user"),
    }
    row.update(security_fields(sensitivity, retention))
    append_jsonl(paths(bus_dir)["issues"], row)
    return iid


def accept_issue(bus_dir: Path, issue_id: object, by: object, to: object, note: object = "") -> dict[str, str]:
    ensure_bus(bus_dir)
    iid = _required_text(issue_id, "issue_id")
    assignee = _required_text(to, "to")
    actor = _clean_text(by, "user")
    note_text = _clean_text(note)
    issue_path = paths(bus_dir)["issues"]
    with file_lock(issue_path):
        issue = _open_issue_from_rows(read_jsonl(issue_path), iid)
        sensitivity = issue.get("sensitivity", "")
        retention = issue.get("retention", "")
        task_id = create_task(bus_dir, issue.get("title", ""), actor, [assignee], "", sensitivity, retention)
        body_parts = [p for p in [issue.get("body", ""), note_text] if p]
        msg = make_message(
            actor,
            assignee,
            "request",
            issue.get("title", ""),
            "\n\n".join(body_parts) or issue.get("title", ""),
            issue.get("refs", []),
            task_id,
            "",
            sensitivity,
            retention,
        )
        append_message(bus_dir, msg)
        _append_jsonl_unlocked(issue_path, {
            "time": now_iso(),
            "event": "accepted",
            "issue_id": iid,
            "by": actor,
            "to": assignee,
            "note": note_text,
            "task_id": task_id,
            "message_id": msg["id"],
        })
    return {"task_id": task_id, "message_id": msg["id"]}


def reject_issue(bus_dir: Path, issue_id: object, by: object, note: object = "") -> None:
    ensure_bus(bus_dir)
    iid = _required_text(issue_id, "issue_id")
    issue_path = paths(bus_dir)["issues"]
    with file_lock(issue_path):
        _open_issue_from_rows(read_jsonl(issue_path), iid)
        _append_jsonl_unlocked(issue_path, {
            "time": now_iso(),
            "event": "rejected",
            "issue_id": iid,
            "by": _clean_text(by, "user"),
            "note": _clean_text(note),
        })


def write_stop(bus_dir: Path, by: object, reason: object, detail: Any = "") -> None:
    ensure_bus(bus_dir)
    write_json(paths(bus_dir)["stop"], {
        "time": now_iso(),
        "by": _clean_text(by, "user"),
        "reason": _clean_text(reason, "user_stop"),
        "detail": detail,
    })


def delete_agent_status(bus_dir: Path, agent: object) -> None:
    ensure_bus(bus_dir)
    name = _required_text(agent, "agent")
    ps = paths(bus_dir)
    with file_lock(ps["status"]):
        status = load_json(ps["status"], {"agents": {}})
        agents = status.get("agents")
        if not isinstance(agents, dict):
            status["agents"] = {}
            agents = status["agents"]
        agents.pop(name, None)
        write_json(ps["status"], status)


def set_agent_status(bus_dir: Path, agent: object, state: object, task: object = "", note: object = "") -> None:
    ensure_bus(bus_dir)
    ps = paths(bus_dir)
    with file_lock(ps["status"]):
        data = load_json(ps["status"], {"agents": {}})
        agents = data.get("agents")
        if not isinstance(agents, dict):
            data["agents"] = {}
            agents = data["agents"]
        agents[_required_text(agent, "agent")] = {
            "state": _choice(state, "state", AGENT_STATES),
            "task": _clean_text(task),
            "note": _clean_text(note),
            "updated_at": now_iso(),
            "heartbeat": time.time(),
        }
        write_json(ps["status"], data)


def init_bus(args: argparse.Namespace) -> int:
    ensure_bus(args.bus_dir)
    print(args.bus_dir)
    return 0


def show_status(args: argparse.Namespace) -> int:
    ensure_bus(args.bus_dir)
    status = load_json(paths(args.bus_dir)["status"], {"agents": {}})
    print(json.dumps(status, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def check_stop(args: argparse.Namespace) -> int:
    stop = paths(args.bus_dir)["stop"]
    if stop.exists():
        print(json.dumps(load_json(stop, {}), ensure_ascii=False, indent=2, sort_keys=True))
        return 2
    print("no stop")
    return 0


def send(args: argparse.Namespace) -> int:
    ensure_bus(args.bus_dir)
    msg = make_message(
        args.sender, args.to, args.kind, args.subject, args.body, args.ref or [],
        args.task, args.reply_to, args.sensitivity, args.retention,
    )
    append_message(args.bus_dir, msg)
    print(msg["id"])
    return 0


def acked_ids(bus_dir: Path, agent: str) -> set[str]:
    return {row.get("id", "") for row in read_jsonl(paths(bus_dir)["acks"]) if row.get("agent") == agent}


def delivered_ids(bus_dir: Path, agent: str) -> set[str]:
    return {row.get("id", "") for row in read_jsonl(paths(bus_dir)["delivered"]) if row.get("agent") == agent}


def unique_acks(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for row in rows:
        key = (str(row.get("id") or ""), str(row.get("agent") or ""))
        if not key[0] or not key[1] or key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


def agent_targets(agent: str) -> set[str]:
    return {agent, "all", "*"}


def pending_messages(
    bus_dir: Path,
    agent: str,
    kinds: set[str],
    suppress_delivered: bool = False,
) -> list[dict[str, Any]]:
    seen = acked_ids(bus_dir, agent)
    delivered = delivered_ids(bus_dir, agent) if suppress_delivered else set()
    targets = agent_targets(agent)
    return [
        row for row in live_messages(bus_dir)
        if row.get("to") in targets
        and row.get("id") not in seen
        and row.get("id") not in delivered
        and (not kinds or row.get("kind") in kinds)
    ]


def format_message_digest(rows: list[dict[str, Any]], max_body_chars: int = 1200) -> str:
    parts: list[str] = []
    for row in rows:
        thread = ""
        if row.get("task_id"):
            thread += f" task={row['task_id']}"
        if row.get("reply_to"):
            thread += f" reply_to={row['reply_to']}"
        parts.append(
            f"[{row.get('id')}] {row.get('time')} {row.get('from')} -> {row.get('to')} "
            f"{row.get('kind')} {row.get('subject')}{thread}"
        )
        refs = " ".join(row.get("refs") or [])
        if refs:
            parts.append(f"refs: {refs}")
        body = row.get("body") or ""
        if body:
            if max_body_chars and len(body) > max_body_chars:
                body = body[:max_body_chars].rstrip() + "…"
            parts.append(body)
        parts.append("---")
    return "\n".join(parts)


def inbox(args: argparse.Namespace) -> int:
    ensure_bus(args.bus_dir)
    rows = pending_messages(args.bus_dir, args.agent, set())
    if rows:
        print(format_message_digest(rows[-args.limit:], max_body_chars=0))
    else:
        print("empty")
    return 0


def ack(args: argparse.Namespace) -> int:
    ensure_bus(args.bus_dir)
    acks_path = paths(args.bus_dir)["acks"]
    with file_lock(acks_path):
        seen = {row.get("id", "") for row in read_jsonl(acks_path) if row.get("agent") == args.agent}
        if args.message_id not in seen:
            _append_jsonl_unlocked(acks_path, {"time": now_iso(), "agent": args.agent, "id": args.message_id})
    print("acked", args.message_id)
    return 0


def message_delete(args: argparse.Namespace) -> int:
    try:
        delete_message(args.bus_dir, args.id, args.by)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print("deleted", args.id)
    return 0


def watch(args: argparse.Namespace) -> int:
    """Print unacked messages. delivered.jsonl does not count as ack."""
    ensure_bus(args.bus_dir)
    kinds = {k.strip() for k in args.kinds.split(",") if k.strip()}
    exit_code = 0
    while True:
        if paths(args.bus_dir)["stop"].exists():
            print("stop present")
            return 2
        # --once는 delivered와 무관하게 ack만 본다.
        # 연속 watch는 delivered를 숨긴다(--include-delivered로 해제).
        suppress_delivered = (not args.once) and (not args.include_delivered)
        rows = pending_messages(args.bus_dir, args.agent, kinds, suppress_delivered=suppress_delivered)
        if rows:
            rows = rows[-args.limit:]
            if args.json:
                print(json.dumps({"agent": args.agent, "pending": rows}, ensure_ascii=False))
            else:
                print(format_message_digest(rows, args.max_body_chars))
            if args.mark_delivered:
                for row in rows:
                    append_jsonl(paths(args.bus_dir)["delivered"], {
                        "time": now_iso(),
                        "agent": args.agent,
                        "id": row.get("id"),
                        "kind": row.get("kind"),
                        "subject": row.get("subject"),
                        "by": "watch",
                    })
        else:
            if args.once:
                print("empty")
            exit_code = 0
        if args.once:
            return exit_code
        time.sleep(args.interval_seconds)


def _sensitive_event_notice(event: dict[str, Any]) -> dict[str, Any]:
    return {
        "version": EVENT_VERSION,
        "id": event.get("id", ""),
        "time": event.get("time", ""),
        "type": event.get("type", ""),
        "object": event.get("object", {}),
        "blocked": True,
        "reason": "sensitive payload blocked",
        "sensitive": sensitive_summary(event),
    }


def _sensitive_wakeup_notice(payload: dict[str, Any]) -> dict[str, Any]:
    pending = [row for row in payload.get("pending") or [] if isinstance(row, dict)]
    return {
        "schemaVersion": WAKEUP_PROFILE_VERSION,
        "profile": payload.get("profile", ""),
        "mode": payload.get("mode", ""),
        "agent": payload.get("agent", ""),
        "blocked": True,
        "reason": "sensitive payload blocked",
        "sensitive": sensitive_summary(payload),
        "pendingCount": len(pending),
        "messageIds": [row.get("id") for row in pending if row.get("id")],
    }


def _print_json(value: dict[str, Any]) -> None:
    print(json.dumps(value, ensure_ascii=False, sort_keys=True), flush=True)


def _print_event(event: dict[str, Any], allow_sensitive: bool = True) -> None:
    _print_json(event if allow_sensitive or not payload_is_sensitive(event) else _sensitive_event_notice(event))


def _read_cursor(path: Path | None) -> str:
    if not path or not path.exists():
        return ""
    return path.read_text(encoding="utf-8").strip()


def _write_cursor(path: Path | None, cursor: str) -> None:
    if not path:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with file_lock(path):
        path.write_text(cursor + "\n", encoding="utf-8")
        _chmod_private(path)


def _append_event_failure(
    path: Path | None,
    event: dict[str, Any],
    command: str,
    returncode: int,
    error: str = "",
    include_event: bool = True,
) -> None:
    if not path:
        return
    row = {
        "time": now_iso(),
        "event_id": event.get("id"),
        "event_type": event.get("type"),
        "object": event.get("object"),
        "command": command,
        "returncode": returncode,
    }
    if include_event:
        row["event"] = event
    if error:
        row["error"] = error
    append_jsonl(path, row)


def _run_json_command(
    command: str,
    value: dict[str, Any],
    env_extra: dict[str, str] | None = None,
    timeout: float = 60.0,
) -> int:
    if not command:
        return 0
    env = os.environ.copy()
    env.update(env_extra or {})
    try:
        proc = subprocess.run(
            command,
            input=json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n",
            text=True,
            shell=True,
            env=env,
            timeout=timeout if timeout > 0 else None,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return 124
    return proc.returncode


def _run_event_command(command: str, event: dict[str, Any], timeout: float = 60.0, allow_sensitive: bool = False) -> int:
    env = {
        "AGENTBUS_EVENT_ID": str(event.get("id") or ""),
        "AGENTBUS_EVENT_TYPE": str(event.get("type") or ""),
        "AGENTBUS_OBJECT_TYPE": str((event.get("object") or {}).get("type") or ""),
        "AGENTBUS_OBJECT_ID": str((event.get("object") or {}).get("id") or ""),
    }
    if allow_sensitive:
        env["AGENTBUS_ALLOW_SENSITIVE"] = "1"
    return _run_json_command(command, event, env, timeout)


def events(args: argparse.Namespace) -> int:
    rows = bus_events(
        args.bus_dir,
        types=parse_event_types(args.types),
        targets=parse_event_targets(args.target),
        after=args.after,
        limit=max(0, args.limit),
    )
    if args.jsonl:
        for event in rows:
            _print_event(event)
    else:
        print(json.dumps({"version": EVENT_VERSION, "events": rows}, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def watch_events(args: argparse.Namespace) -> int:
    types = parse_event_types(args.types)
    targets = parse_event_targets(args.target)
    cursor_file = args.cursor_file
    fail_log = args.fail_log
    cursor = _read_cursor(cursor_file)
    seen = set()
    if args.from_start:
        cursor = ""
    elif cursor_file:
        if not cursor:
            existing = bus_events(args.bus_dir, types=types, targets=targets)
            if existing:
                cursor = existing[-1]["cursor"]
                if not args.dry_run:
                    _write_cursor(cursor_file, cursor)
    else:
        seen = {event["id"] for event in bus_events(args.bus_dir, types=types, targets=targets)}
    exit_code = 0
    while True:
        for event in bus_events(args.bus_dir, types=types, targets=targets, after=cursor):
            if not cursor_file and event["id"] in seen:
                continue
            allow_sensitive = args.allow_sensitive or allow_sensitive_env()
            blocked_sensitive = payload_is_sensitive(event) and not allow_sensitive
            _print_event(event, allow_sensitive=not blocked_sensitive)
            if blocked_sensitive:
                if args.dry_run:
                    seen.add(event["id"])
                    continue
                rc = 2
                error = "sensitive event blocked; rerun with --allow-sensitive"
                _append_event_failure(fail_log, event, args.exec, rc, error, include_event=False)
                if exit_code == 0:
                    exit_code = rc
                seen.add(event["id"])
                cursor = event["cursor"]
                _write_cursor(cursor_file, cursor)
                if args.once:
                    return exit_code
                continue
            if args.dry_run:
                seen.add(event["id"])
                continue
            if args.exec:
                rc = _run_event_command(
                    args.exec,
                    event,
                    args.exec_timeout,
                    allow_sensitive,
                )
                if rc and exit_code == 0:
                    exit_code = rc
                if rc:
                    error = "adapter timeout" if rc == 124 else ""
                    _append_event_failure(fail_log, event, args.exec, rc, error)
                    if args.once:
                        return exit_code
                    break
            seen.add(event["id"])
            cursor = event["cursor"]
            _write_cursor(cursor_file, cursor)
        if args.once:
            return exit_code
        time.sleep(args.interval_seconds)


def _profile_list(profile: dict[str, Any], key: str) -> list[str]:
    value = profile.get(key)
    if value in (None, ""):
        return []
    if not isinstance(value, (str, list, tuple, set)):
        raise ValueError(f"{key} must be a string or list")
    return _flat_string_list(value)


def _profile_bool(profile: dict[str, Any], key: str, default: bool = False) -> bool:
    value = profile.get(key, default)
    if isinstance(value, bool):
        return value
    raise ValueError(f"{key} must be boolean")


def _profile_float(profile: dict[str, Any], key: str, default: float) -> float:
    value = profile.get(key, default)
    if value in (None, ""):
        return default
    try:
        out = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{key} must be a number") from exc
    if out < 0:
        raise ValueError(f"{key} must be >= 0")
    return out


def _safe_profile_name(value: object) -> str:
    text = _clean_text(value, "wakeup")
    safe = "".join(c if c.isalnum() or c in "._-" else "_" for c in text)
    return safe.strip("._-") or "wakeup"


def _profile_state_path(profile: dict[str, Any], bus_dir: Path, key: str, suffix: str) -> Path:
    value = _clean_text(profile.get(key))
    if value:
        path = Path(value).expanduser()
        return path if path.is_absolute() else bus_dir / path
    return bus_dir / "adapters" / f"{_safe_profile_name(profile.get('name'))}.{suffix}"


def validate_wakeup_profile(profile: Any, check_env: bool = True) -> list[str]:
    errors: list[str] = []
    required_env: list[str] = []
    if not isinstance(profile, dict):
        return ["profile must be a JSON object"]
    if profile.get("schemaVersion") != WAKEUP_PROFILE_VERSION:
        errors.append(f"schemaVersion must be {WAKEUP_PROFILE_VERSION}")
    if not _clean_text(profile.get("name")):
        errors.append("name required")
    mode = _clean_text(profile.get("mode"))
    if mode not in WAKEUP_MODES:
        errors.append("mode must be inbox or events")
    try:
        required_env = _profile_list(profile, "requiredEnv")
        _profile_float(profile, "intervalSeconds", 30.0 if mode == "inbox" else 1.0)
        _profile_float(profile, "maxSeconds", 0.0)
        _profile_float(profile, "execTimeout", 60.0)
        _profile_bool(profile, "allowSensitive", False)
        if "command" in profile and profile.get("command") not in (None, "") and not isinstance(profile.get("command"), str):
            errors.append("command must be a string")
        if "cursorFile" in profile and profile.get("cursorFile") not in (None, "") and not isinstance(profile.get("cursorFile"), str):
            errors.append("cursorFile must be a string")
        if "failLog" in profile and profile.get("failLog") not in (None, "") and not isinstance(profile.get("failLog"), str):
            errors.append("failLog must be a string")
    except ValueError as exc:
        errors.append(str(exc))
    if mode == "inbox":
        if not _clean_text(profile.get("agent")):
            errors.append("agent required for inbox mode")
        try:
            _profile_list(profile, "kinds")
            _profile_bool(profile, "markDelivered", True)
        except ValueError as exc:
            errors.append(str(exc))
    elif mode == "events":
        try:
            if not _profile_list(profile, "types"):
                errors.append("types required for events mode")
            _profile_list(profile, "target")
            _profile_bool(profile, "fromStart", False)
        except ValueError as exc:
            errors.append(str(exc))
    if check_env:
        for name in required_env:
            if not os.environ.get(name):
                errors.append(f"requiredEnv not set: {name}")
    return errors


def load_wakeup_profile(path: Path, check_env: bool = True) -> dict[str, Any]:
    try:
        profile = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(str(exc)) from exc
    errors = validate_wakeup_profile(profile, check_env=check_env)
    if errors:
        raise ValueError("; ".join(errors))
    return profile


def _append_wakeup_failure(
    path: Path | None,
    payload: dict[str, Any],
    command: str,
    returncode: int,
    error: str = "",
    include_payload: bool = True,
) -> None:
    if not path:
        return
    row: dict[str, Any] = {
        "time": now_iso(),
        "profile": payload.get("profile"),
        "mode": payload.get("mode"),
        "command": command,
        "returncode": returncode,
    }
    if payload.get("mode") == "inbox":
        row["agent"] = payload.get("agent")
        row["message_ids"] = [m.get("id") for m in payload.get("pending") or [] if isinstance(m, dict)]
    if include_payload:
        row["payload"] = payload
    if error:
        row["error"] = error
    append_jsonl(path, row)


def _run_wakeup_payload_command(
    command: str,
    payload: dict[str, Any],
    timeout: float,
    allow_sensitive: bool,
) -> int:
    env = {
        "AGENTBUS_WAKEUP_PROFILE": str(payload.get("profile") or ""),
        "AGENTBUS_WAKEUP_MODE": str(payload.get("mode") or ""),
        "AGENTBUS_WAKEUP_AGENT": str(payload.get("agent") or ""),
    }
    if allow_sensitive:
        env["AGENTBUS_ALLOW_SENSITIVE"] = "1"
    return _run_json_command(command, payload, env, timeout)


def _write_delivered_for_wakeup(bus_dir: Path, agent: str, rows: list[dict[str, Any]], profile_name: str) -> None:
    delivered = delivered_ids(bus_dir, agent)
    for row in rows:
        mid = row.get("id")
        if not mid or mid in delivered:
            continue
        append_jsonl(paths(bus_dir)["delivered"], {
            "time": now_iso(),
            "agent": agent,
            "id": mid,
            "kind": row.get("kind"),
            "subject": row.get("subject"),
            "by": "wakeup",
            "profile": profile_name,
        })


def _print_wakeup_payload(payload: dict[str, Any], allow_sensitive: bool = True) -> None:
    _print_json(payload if allow_sensitive or not payload_is_sensitive(payload) else _sensitive_wakeup_notice(payload))


def _wakeup_inbox(args: argparse.Namespace, profile: dict[str, Any]) -> int:
    ensure_bus(args.bus_dir)
    name = _clean_text(profile.get("name"))
    agent = _required_text(profile.get("agent"), "agent")
    kinds = set(_profile_list(profile, "kinds") or ["request"])
    command = _clean_text(profile.get("command"))
    interval = _profile_float(profile, "intervalSeconds", 30.0)
    max_seconds = _profile_float(profile, "maxSeconds", 0.0)
    timeout = _profile_float(profile, "execTimeout", 60.0)
    mark_delivered = _profile_bool(profile, "markDelivered", True)
    allow_sensitive = _profile_bool(profile, "allowSensitive", False) or allow_sensitive_env()
    fail_log = _profile_state_path(profile, args.bus_dir, "failLog", "failures.jsonl")
    deadline = time.time() + max_seconds if max_seconds > 0 else 0.0
    while True:
        stop_path = paths(args.bus_dir)["stop"]
        if stop_path.exists():
            print(json.dumps(load_json(stop_path, {}), ensure_ascii=False, indent=2, sort_keys=True))
            return 2
        rows = pending_messages(args.bus_dir, agent, kinds, suppress_delivered=mark_delivered)
        if rows:
            payload = {
                "schemaVersion": WAKEUP_PROFILE_VERSION,
                "profile": name,
                "mode": "inbox",
                "agent": agent,
                "pending": rows,
            }
            blocked_sensitive = payload_is_sensitive(payload) and not allow_sensitive
            _print_wakeup_payload(payload, allow_sensitive=not blocked_sensitive)
            if blocked_sensitive:
                if args.dry_run:
                    return 0
                rc = 2
                error = "sensitive inbox blocked; rerun with allowSensitive"
                _append_wakeup_failure(fail_log, payload, command, rc, error, include_payload=False)
                return rc
            if args.dry_run:
                return 0
            rc = _run_wakeup_payload_command(command, payload, timeout, allow_sensitive)
            if rc:
                error = "wakeup command timeout" if rc == 124 else ""
                _append_wakeup_failure(fail_log, payload, command, rc, error)
                return rc
            if mark_delivered:
                _write_delivered_for_wakeup(args.bus_dir, agent, rows, name)
            return 0
        idle = {
            "schemaVersion": WAKEUP_PROFILE_VERSION,
            "profile": name,
            "mode": "inbox",
            "agent": agent,
            "pending": [],
            "status": "idle",
        }
        if args.once or (deadline and time.time() >= deadline):
            _print_wakeup_payload(idle)
            return 0
        time.sleep(interval)


def _wakeup_events(args: argparse.Namespace, profile: dict[str, Any]) -> int:
    ensure_bus(args.bus_dir)
    types = set(_profile_list(profile, "types"))
    targets = set(_profile_list(profile, "target"))
    command = _clean_text(profile.get("command"))
    interval = _profile_float(profile, "intervalSeconds", 1.0)
    max_seconds = _profile_float(profile, "maxSeconds", 0.0)
    exec_timeout = _profile_float(profile, "execTimeout", 60.0)
    allow_sensitive = _profile_bool(profile, "allowSensitive", False) or allow_sensitive_env()
    cursor_file = _profile_state_path(profile, args.bus_dir, "cursorFile", "cursor")
    fail_log = _profile_state_path(profile, args.bus_dir, "failLog", "failures.jsonl")
    cursor = _read_cursor(cursor_file)
    if _profile_bool(profile, "fromStart", False):
        cursor = ""
    elif not cursor:
        existing = bus_events(args.bus_dir, types=types, targets=targets)
        if existing:
            cursor = existing[-1]["cursor"]
            if not args.dry_run:
                _write_cursor(cursor_file, cursor)
    deadline = time.time() + max_seconds if max_seconds > 0 else 0.0
    exit_code = 0
    while True:
        for event in bus_events(args.bus_dir, types=types, targets=targets, after=cursor):
            blocked_sensitive = payload_is_sensitive(event) and not allow_sensitive
            _print_event(event, allow_sensitive=not blocked_sensitive)
            if blocked_sensitive:
                if args.dry_run:
                    continue
                rc = 2
                error = "sensitive event blocked; rerun with allowSensitive"
                _append_event_failure(fail_log, event, command, rc, error, include_event=False)
                if exit_code == 0:
                    exit_code = rc
                cursor = event["cursor"]
                _write_cursor(cursor_file, cursor)
                if args.once:
                    return exit_code
                continue
            if args.dry_run:
                continue
            if command:
                rc = _run_event_command(command, event, exec_timeout, allow_sensitive)
                if rc and exit_code == 0:
                    exit_code = rc
                if rc:
                    error = "adapter timeout" if rc == 124 else ""
                    _append_event_failure(fail_log, event, command, rc, error)
                    if args.once:
                        return exit_code
                    break
            cursor = event["cursor"]
            _write_cursor(cursor_file, cursor)
        if args.once or (deadline and time.time() >= deadline):
            return exit_code
        time.sleep(interval)


def wakeup_check(args: argparse.Namespace) -> int:
    try:
        load_wakeup_profile(args.file)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print("wakeup-profile-ok")
    return 0


def wakeup(args: argparse.Namespace) -> int:
    try:
        profile = load_wakeup_profile(args.profile)
        if profile.get("mode") == "inbox":
            return _wakeup_inbox(args, profile)
        if profile.get("mode") == "events":
            return _wakeup_events(args, profile)
        raise ValueError("mode must be inbox or events")
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1


def _adapter_failure_summary(row: dict[str, Any]) -> dict[str, Any]:
    out = {
        "time": row.get("time", ""),
        "returncode": row.get("returncode", ""),
        "error": row.get("error", ""),
    }
    for key in ("event_id", "event_type", "profile", "mode", "agent", "message_ids", "object", "endpoint", "status"):
        if key in row:
            out[key] = row.get(key)
    return {key: value for key, value in out.items() if value not in (None, "", [], {})}


def adapter_status_rows(bus_dir: Path) -> list[dict[str, Any]]:
    adapter_dir = bus_dir / "adapters"
    names: set[str] = set()
    if adapter_dir.exists():
        for path in adapter_dir.iterdir():
            if path.name.endswith(".cursor"):
                names.add(path.name[:-7])
            elif path.name.endswith(".failures.jsonl"):
                names.add(path.name[:-15])
    rows = []
    for name in sorted(names):
        cursor_path = adapter_dir / f"{name}.cursor"
        failure_path = adapter_dir / f"{name}.failures.jsonl"
        failures = read_jsonl(failure_path)
        row: dict[str, Any] = {
            "name": name,
            "cursor": _read_cursor(cursor_path),
            "cursorFile": str(cursor_path),
            "failLog": str(failure_path),
            "failureCount": len(failures),
        }
        if cursor_path.exists():
            row["cursorUpdatedAt"] = datetime.fromtimestamp(cursor_path.stat().st_mtime, timezone.utc).isoformat().replace("+00:00", "Z")
        if failures:
            row["lastFailure"] = _adapter_failure_summary(failures[-1])
            if failure_path.exists():
                row["failLogUpdatedAt"] = datetime.fromtimestamp(failure_path.stat().st_mtime, timezone.utc).isoformat().replace("+00:00", "Z")
        rows.append(row)
    return rows


def adapter_status(args: argparse.Namespace) -> int:
    rows = adapter_status_rows(args.bus_dir)
    if args.json:
        print(json.dumps({"adapters": rows}, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    if not rows:
        print("no adapters")
        return 0
    for row in rows:
        parts = [
            row["name"],
            f"cursor={row.get('cursor') or '-'}",
            f"failures={row.get('failureCount', 0)}",
        ]
        last = row.get("lastFailure")
        if isinstance(last, dict) and last:
            parts.append(f"lastFailure={last.get('time', '-')}")
            if last.get("returncode") not in (None, ""):
                parts.append(f"rc={last.get('returncode')}")
        print(" ".join(parts))
    return 0


def set_status(args: argparse.Namespace) -> int:
    set_agent_status(args.bus_dir, args.agent, args.state, args.task, args.note)
    print(args.agent, args.state)
    return 0


def stop(args: argparse.Namespace) -> int:
    ensure_bus(args.bus_dir)
    write_stop(args.bus_dir, args.by, args.reason, args.detail)
    print("stop written")
    return 0


def task_new(args: argparse.Namespace) -> int:
    ensure_bus(args.bus_dir)
    tid = create_task(args.bus_dir, args.title, args.by, args.assign, args.id, args.sensitivity, args.retention)
    print(tid)
    return 0


def task_state(args: argparse.Namespace) -> int:
    ensure_bus(args.bus_dir)
    set_task_state(args.bus_dir, args.id, args.state, args.by, args.note)
    print(args.id, args.state)
    return 0


def task_delete(args: argparse.Namespace) -> int:
    ensure_bus(args.bus_dir)
    delete_task(args.bus_dir, args.id, args.by)
    print("deleted", args.id)
    return 0


def task_list(args: argparse.Namespace) -> int:
    ensure_bus(args.bus_dir)
    tasks = fold_tasks(args.bus_dir)
    if not tasks:
        print("no tasks")
        return 0
    for t in tasks:
        assign = ",".join(t.get("assign") or [])
        print(f"[{t['task_id']}] {t.get('state'):14} {t.get('title','')}  ({assign})")
        if t.get("note"):
            print(f"  note: {t['note']}")
    return 0


def task_report_rows(bus_dir: Path, task_id: str = "", max_body_chars: int = 240) -> list[dict[str, Any]]:
    tasks = fold_tasks(bus_dir)
    task_map = {str(t.get("task_id") or ""): t for t in tasks if t.get("task_id")}
    messages = live_messages(bus_dir)
    message_task_ids = {str(m.get("task_id") or "") for m in messages if m.get("task_id")}
    task_ids = [task_id] if task_id else sorted(set(task_map) | message_task_ids)
    rows: list[dict[str, Any]] = []
    for tid in task_ids:
        task = task_map.get(tid, {"task_id": tid, "title": "", "assign": [], "state": ""})
        task_messages = [m for m in messages if str(m.get("task_id") or "") == tid]
        reports = [m for m in task_messages if m.get("kind") == "report"]
        latest_activity = max(
            [str(item.get("time") or "") for item in task_messages] + [str(task.get("updated_at") or "")],
            default="",
        )
        report_rows = []
        for report in reports:
            body = str(report.get("body") or "")
            if max_body_chars > 0 and len(body) > max_body_chars:
                body = body[:max_body_chars].rstrip() + "…"
            report_rows.append({
                "id": report.get("id", ""),
                "time": report.get("time", ""),
                "from": report.get("from", ""),
                "subject": report.get("subject", ""),
                "reply_to": report.get("reply_to", ""),
                "refs": report.get("refs") or [],
                "body": body,
            })
        rows.append({
            "task_id": tid,
            "title": task.get("title", ""),
            "state": task.get("state", ""),
            "assign": task.get("assign") or [],
            "reports": report_rows,
            "latest_activity": latest_activity,
            "message_count": len(task_messages),
            "report_count": len(reports),
        })
    return sorted(rows, key=lambda row: row.get("latest_activity") or "", reverse=True)


def issue_new(args: argparse.Namespace) -> int:
    iid = create_issue(args.bus_dir, args.title, args.by, args.body, args.ref or [], args.sensitivity, args.retention)
    print(iid)
    return 0


def issue_list(args: argparse.Namespace) -> int:
    ensure_bus(args.bus_dir)
    issues = fold_issues(args.bus_dir, include_closed=args.all)
    if args.json:
        print(json.dumps(issues, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    if not issues:
        print("no tickets")
        return 0
    for issue in issues:
        print(f"[{issue['issue_id']}] {issue.get('state','open'):8} {issue.get('title','')}")
        if issue.get("body"):
            print(f"  {issue['body']}")
        refs = " ".join(issue.get("refs") or [])
        if refs:
            print(f"  refs: {refs}")
    return 0


def issue_accept(args: argparse.Namespace) -> int:
    try:
        result = accept_issue(args.bus_dir, args.id, args.by, args.to, args.note)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(args.id, "accepted", "task", result["task_id"], "message", result["message_id"])
    return 0


def issue_reject(args: argparse.Namespace) -> int:
    try:
        reject_issue(args.bus_dir, args.id, args.by, args.note)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(args.id, "rejected")
    return 0


def _security_file_mode_warnings(bus_dir: Path) -> list[Path]:
    ps = paths(bus_dir)
    candidates = [path for path in ps.values() if path.exists() and path.is_file()]
    archive = bus_dir / "archive"
    if archive.is_dir():
        candidates.extend(path for path in archive.rglob("*.jsonl") if path.is_file())
    adapters = bus_dir / "adapters"
    if adapters.is_dir():
        candidates.extend(path for path in adapters.rglob("*.jsonl") if path.is_file())
    out: list[Path] = []
    for path in sorted(set(candidates), key=lambda p: str(p)):
        try:
            mode = path.stat().st_mode & 0o777
        except OSError:
            continue
        if mode & 0o077:
            out.append(path)
    return out


def _format_path_examples(paths_in: list[Path], limit: int = 3) -> str:
    if not paths_in:
        return "none"
    examples = ", ".join(str(path) for path in paths_in[:limit])
    if len(paths_in) > limit:
        examples += f", +{len(paths_in) - limit} more"
    return examples


def security_check(args: argparse.Namespace) -> int:
    ensure_bus(args.bus_dir)
    mode = args.bus_dir.stat().st_mode & 0o777
    messages = live_messages(args.bus_dir)
    tasks = fold_tasks(args.bus_dir)
    issues = fold_issues(args.bus_dir, include_closed=True)
    sensitive_messages = [m for m in messages if effective_sensitivity(m) in SENSITIVE_LEVELS]
    sensitive_tasks = [t for t in tasks if effective_sensitivity(t) in SENSITIVE_LEVELS]
    sensitive_issues = [i for i in issues if effective_sensitivity(i) in SENSITIVE_LEVELS]
    no_archive = [m for m in messages if effective_retention(m) == "no_archive"]
    loose_files = _security_file_mode_warnings(args.bus_dir)
    checks = [
        {
            "status": "warn" if mode & 0o077 else "ok",
            "name": "bus_dir_permissions",
            "detail": f"{args.bus_dir} mode {mode:03o}",
        },
        {
            "status": "warn" if loose_files else "ok",
            "name": "bus_file_permissions",
            "detail": f"group/other bits on {len(loose_files)} files: {_format_path_examples(loose_files)}",
        },
        {
            "status": "warn" if sensitive_messages or sensitive_tasks or sensitive_issues else "ok",
            "name": "sensitive_records",
            "detail": f"messages={len(sensitive_messages)} tasks={len(sensitive_tasks)} tickets={len(sensitive_issues)}",
        },
        {
            "status": "warn" if no_archive else "ok",
            "name": "no_archive_messages",
            "detail": f"messages={len(no_archive)}",
        },
        {
            "status": "warn" if allow_sensitive_env() else "ok",
            "name": "allow_sensitive_env",
            "detail": "AGENTBUS_ALLOW_SENSITIVE is set" if allow_sensitive_env() else "not set",
        },
    ]
    report = {"bus_dir": str(args.bus_dir), "checks": checks}
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    for check in checks:
        print(f"{check['status']:4} {check['name']}  {check['detail']}")
    return 0


def add_ticket_parsers(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("ticket-new", help="승격 전 티켓 등록")
    p.add_argument("--title", required=True)
    p.add_argument("--by", required=True)
    p.add_argument("--body", default="")
    p.add_argument("--ref", action="append")
    p.add_argument("--sensitivity", choices=SENSITIVITY_LEVELS, default="", help="민감도 표시")
    p.add_argument("--retention", choices=RETENTION_POLICIES, default="", help="보관 힌트")
    p.set_defaults(func=issue_new)
    p = sub.add_parser("ticket-list", help="티켓 확인")
    p.add_argument("--all", action="store_true", help="accepted/rejected까지 표시")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=issue_list)
    p = sub.add_parser("ticket-accept", help="티켓을 task와 request 메시지로 승격")
    p.add_argument("--id", required=True)
    p.add_argument("--by", required=True)
    p.add_argument("--to", required=True, help="작업을 받을 에이전트")
    p.add_argument("--note", default="")
    p.set_defaults(func=issue_accept)
    p = sub.add_parser("ticket-reject", help="티켓 반려")
    p.add_argument("--id", required=True)
    p.add_argument("--by", required=True)
    p.add_argument("--note", default="")
    p.set_defaults(func=issue_reject)


def supervise(args: argparse.Namespace) -> int:
    ensure_bus(args.bus_dir)
    start = time.time()
    agents = [a.strip() for a in args.agents.split(",") if a.strip()]
    while True:
        if paths(args.bus_dir)["stop"].exists():
            print("stop already present")
            return 0
        data = load_json(paths(args.bus_dir)["status"], {"agents": {}}).get("agents", {})
        now = time.time()
        states = {a: data.get(a, {}) for a in agents}
        if states and all(v.get("state") == "done" for v in states.values()):
            write_stop(args.bus_dir, "supervisor", "all_done", agents)
            print("all done")
            return 0
        errors = [a for a, v in states.items() if v.get("state") == "error"]
        if errors:
            write_stop(args.bus_dir, "supervisor", "agent_error", errors)
            print("agent error", ",".join(errors))
            return 1
        if now - start > args.max_minutes * 60:
            write_stop(args.bus_dir, "supervisor", "time_limit", f"{args.max_minutes} minutes")
            print("time limit")
            return 1
        if now - start > args.startup_grace_seconds:
            stale = [
                a for a, v in states.items()
                if v.get("heartbeat") and now - float(v.get("heartbeat", 0)) > args.stale_seconds
            ]
            if stale:
                write_stop(args.bus_dir, "supervisor", "stale_agent", stale)
                print("stale", ",".join(stale))
                return 1
        time.sleep(args.interval_seconds)


def serve_cmd(args: argparse.Namespace) -> int:
    from . import dashboard  # 지연 임포트로 순환 방지
    return dashboard.serve(args.bus_dir, args.port, args.root, args.cards_dir)


def clear_bus(bus_dir: Path, all_: bool = False) -> None:
    """메시지·ack·delivered를 비운다(타임라인 초기화). all_이면 작업·상태·정지까지 초기화."""
    ensure_bus(bus_dir)
    ps = paths(bus_dir)
    for key in ["messages", "message_deletes", "acks", "delivered"] + (["tasks", "issues"] if all_ else []):
        p = ps[key]
        p.parent.mkdir(parents=True, exist_ok=True)
        with file_lock(p):
            p.write_text("", encoding="utf-8")
            _chmod_private(p)
    if all_:
        with file_lock(ps["status"]):
            write_json(ps["status"], {"created_at": now_iso(), "agents": {}})
        ps["stop"].unlink(missing_ok=True)


def _rotate_log_unlocked(bus_dir: Path, key: str, path: Path) -> Path | None:
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8")
    if not text.strip():
        return None
    archive_dir = bus_dir / "archive"
    archive_dir.mkdir(parents=True, exist_ok=True)
    dest = _next_archive_path(archive_dir, key, archive_stamp())
    if key == "messages":
        archive_lines: list[str] = []
        retained_lines: list[str] = []
        for line in text.splitlines():
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                archive_lines.append(line)
                continue
            target = retained_lines if effective_retention(row) == "no_archive" else archive_lines
            target.append(line)
        if not archive_lines:
            return None
        dest.write_text("\n".join(archive_lines) + "\n", encoding="utf-8")
        _chmod_private(dest)
        path.write_text(("\n".join(retained_lines) + "\n") if retained_lines else "", encoding="utf-8")
        _chmod_private(path)
    else:
        os.replace(path, dest)
        _chmod_private(dest)
        path.write_text("", encoding="utf-8")
        _chmod_private(path)
    if key == "messages":
        if not path.read_text(encoding="utf-8").strip():
            deletes = paths(bus_dir)["message_deletes"]
            deletes.write_text("", encoding="utf-8")
            _chmod_private(deletes)
    _prune_archives(archive_dir, key)
    return dest


def rotate_log(bus_dir: Path, key: str = "messages") -> Path | None:
    """현재 로그를 archive/로 옮기고 빈 파일로 다시 시작한다. 비어 있으면 None."""
    p = paths(bus_dir)[key]
    p.parent.mkdir(parents=True, exist_ok=True)
    with file_lock(p):
        return _rotate_log_unlocked(bus_dir, key, p)


def _should_rotate(path: Path, extra_bytes: int) -> bool:
    limit = _env_int("AGENTBUS_MAX_BYTES", 5_000_000)
    if limit <= 0:
        return False
    try:
        return path.stat().st_size + extra_bytes >= limit
    except FileNotFoundError:
        return False


def append_message(bus_dir: Path, msg: dict[str, Any]) -> None:
    """메시지를 추가한다. 임계 초과가 예상되면 같은 잠금 안에서 회전 후 기록한다."""
    ensure_bus(bus_dir)
    p = paths(bus_dir)["messages"]
    p.parent.mkdir(parents=True, exist_ok=True)
    line_bytes = len(json.dumps(msg, ensure_ascii=False, sort_keys=True).encode("utf-8")) + 1
    with file_lock(p):
        if _should_rotate(p, line_bytes):
            _rotate_log_unlocked(bus_dir, "messages", p)
        _append_jsonl_unlocked(p, msg)


def clear(args: argparse.Namespace) -> int:
    ensure_bus(args.bus_dir)
    scope = "세션 전체(메시지·ack·delivered·작업·티켓·상태)" if args.all else "메시지·ack·delivered"
    if not args.yes:
        if sys.stdin.isatty():
            if input(f"{scope}를 비웁니다. 계속? [y/N] ").strip().lower() not in ("y", "yes"):
                print("취소")
                return 1
        else:
            print("clear는 확인이 필요하다: --yes 를 붙인다", file=sys.stderr)
            return 1
    clear_bus(args.bus_dir, args.all)
    print("cleared:", scope)
    return 0


def rotate(args: argparse.Namespace) -> int:
    ensure_bus(args.bus_dir)
    dest = rotate_log(args.bus_dir, "messages")
    print("rotated:", dest if dest else "nothing to rotate")
    return 0


def _load_operational_data(path_text: str) -> Any:
    if path_text == "-":
        return json.load(sys.stdin)
    return json.loads(Path(path_text).read_text(encoding="utf-8"))


def _load_optional_json(path_text: str) -> Any:
    if not path_text:
        return None
    return _load_operational_data(path_text)


def aas_packet(args: argparse.Namespace) -> int:
    from .assessment import assessment_packet

    try:
        if args.data == "-" and args.assessment_summary == "-":
            raise ValueError("--data and --assessment-summary cannot both read stdin")
        data = _load_operational_data(args.data)
        assessment_summary = _load_optional_json(args.assessment_summary)
        packet = assessment_packet(
            args.bus_dir,
            data,
            args.asset_id,
            args.asset_name,
            "stdin" if args.data == "-" else args.data,
            args.event_cursor,
            args.include_messages,
            assessment_summary,
            args.sensitivity,
            args.retention,
        )
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    text = json.dumps(packet, ensure_ascii=False, separators=(",", ":") if args.compact else None, indent=None if args.compact else 2, sort_keys=True)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n", encoding="utf-8")
    else:
        print(text)
    return 0


def aas_packet_check(args: argparse.Namespace) -> int:
    from .assessment import validate_assessment_packet

    try:
        packet = _load_operational_data(args.file)
    except (OSError, json.JSONDecodeError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    errors = validate_assessment_packet(packet)
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1
    print("packet-ok")
    return 0


def a2a_card(args: argparse.Namespace) -> int:
    from . import a2a

    cards = load_cards(args.cards_dir)
    key = args.agent
    if not key and len(cards) == 1:
        key = next(iter(cards))
    if not key:
        print("agent required when more than one card exists", file=sys.stderr)
        return 1
    card = cards.get(key)
    if not isinstance(card, dict):
        print(f"card not found: {key}", file=sys.stderr)
        return 1
    try:
        projected = a2a.agent_card(card, args.url, args.tenant or key)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    text = json.dumps(projected, ensure_ascii=False, separators=(",", ":") if args.compact else None, indent=None if args.compact else 2, sort_keys=True)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n", encoding="utf-8")
    else:
        print(text)
    return 0


def a2a_card_check(args: argparse.Namespace) -> int:
    from . import a2a

    try:
        card = _load_operational_data(args.file)
    except (OSError, json.JSONDecodeError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    errors = a2a.validate_agent_card(card)
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1
    print("card-ok")
    return 0


def a2a_rpc(args: argparse.Namespace) -> int:
    from . import a2a

    try:
        row = a2a.find_message(args.bus_dir, args.message_id)
        data_parts = [
            (_load_operational_data(path), "stdin" if path == "-" else path)
            for path in (args.data or [])
        ]
        request = a2a.send_message_request(
            row,
            args.request_id,
            args.role,
            args.context_id,
            args.tenant,
            data_parts,
            _flat_string_list(args.accepted_output) or None,
            not args.wait,
        )
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    text = json.dumps(request, ensure_ascii=False, separators=(",", ":") if args.compact else None, indent=None if args.compact else 2, sort_keys=True)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n", encoding="utf-8")
    else:
        print(text)
    return 0


def a2a_rpc_check(args: argparse.Namespace) -> int:
    from . import a2a

    try:
        request = _load_operational_data(args.file)
    except (OSError, json.JSONDecodeError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    errors = a2a.validate_rpc(request)
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1
    print("rpc-ok")
    return 0


def _credential_header_names(headers: dict[str, str]) -> list[str]:
    exact = {
        "authorization",
        "proxy-authorization",
        "cookie",
        "x-api-key",
        "api-key",
        "apikey",
    }
    out: list[str] = []
    for name in headers:
        normalized = name.strip().lower().replace("_", "-")
        if (
            normalized in exact
            or "authorization" in normalized
            or "api-key" in normalized
            or "apikey" in normalized
            or normalized == "auth"
            or normalized.endswith("-auth")
            or "token" in normalized
            or "secret" in normalized
            or "credential" in normalized
        ):
            out.append(name)
    return sorted(out)


def a2a_post(args: argparse.Namespace) -> int:
    from . import a2a

    try:
        request_body = _load_operational_data(args.file)
        if payload_is_sensitive(request_body) and not (args.allow_sensitive or allow_sensitive_env()):
            raise ValueError(f"sensitive request blocked; rerun with --allow-sensitive ({sensitive_summary(request_body)})")
        endpoint = _required_text(args.endpoint, "endpoint")
        insecure_http = endpoint.lower().startswith("http://")
        bearer_token = a2a.read_token(args.bearer_token, args.token_env)
        headers = a2a.header_pairs(args.header)
        credential_headers = _credential_header_names(headers)
        if insecure_http and bearer_token and not args.allow_insecure:
            raise ValueError("bearer token over http blocked; use https or rerun with --allow-insecure")
        if insecure_http and credential_headers and not args.allow_insecure:
            raise ValueError(f"credential header over http blocked ({', '.join(credential_headers)}); use https or rerun with --allow-insecure")
        if insecure_http and payload_is_sensitive(request_body) and not args.allow_insecure:
            raise ValueError("sensitive request over http blocked; use https or rerun with --allow-insecure")
        result = a2a.post_rpc(
            request_body,
            endpoint,
            bearer_token,
            headers,
            args.timeout,
        )
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        error_record = {
            "time": now_iso(),
            "endpoint": args.endpoint,
            "status": 0,
            "error": str(exc),
        }
        a2a.log_adapter_failure(args.fail_log, error_record)
        print(str(exc), file=sys.stderr)
        return 1
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(result.get("body", "") + "\n", encoding="utf-8")
    recorded_id = ""
    recorded = {}
    if args.record_response_to:
        recorded = a2a.record_rpc_result(args.bus_dir, request_body, result, args.record_response_to, args.response_from)
        recorded_id = recorded.get("messageId", "")
    if not result.get("ok"):
        failure = {
            "time": now_iso(),
            "endpoint": endpoint,
            "requestId": request_body.get("id") if isinstance(request_body, dict) else "",
            "status": result.get("status"),
            "error": result.get("error"),
            "body": result.get("body", ""),
        }
        a2a.log_adapter_failure(args.fail_log, failure)
    summary = {
        "ok": bool(result.get("ok")),
        "status": result.get("status"),
        "error": result.get("error") or "",
        "recordedMessageId": recorded_id,
        "recorded": recorded,
        "response": result.get("response"),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result.get("ok") else 1


def parse_args(parser: argparse.ArgumentParser, argv: list[str] | None = None) -> argparse.Namespace:
    args = list(sys.argv[1:] if argv is None else argv)
    aliases = {
        "issue-new": "ticket-new",
        "issue-list": "ticket-list",
        "issue-accept": "ticket-accept",
        "issue-reject": "ticket-reject",
    }
    for i, arg in enumerate(args):
        if arg in aliases:
            args[i] = aliases[arg]
            break
    return parser.parse_args(args)


def workflow_text() -> str:
    return WORKFLOW_PATH.read_text(encoding="utf-8")


def loop_text() -> str:
    return LOOP_PATH.read_text(encoding="utf-8")


def workflow(args: argparse.Namespace) -> int:
    if args.path:
        print(WORKFLOW_PATH)
        return 0
    try:
        print(workflow_text(), end="")
        return 0
    except OSError as exc:
        print(f"workflow file not found: {exc}", file=sys.stderr)
        return 1


def loop(args: argparse.Namespace) -> int:
    if args.path:
        print(LOOP_PATH)
        return 0
    try:
        print(loop_text(), end="")
        return 0
    except OSError as exc:
        print(f"loop skill file not found: {exc}", file=sys.stderr)
        return 1


def _example_path(name: str) -> Path:
    if not name:
        return EXAMPLES_DIR
    rel = Path(name)
    if rel.is_absolute() or ".." in rel.parts:
        raise ValueError("example path must be relative")
    path = (EXAMPLES_DIR / rel).resolve()
    try:
        path.relative_to(EXAMPLES_DIR.resolve())
    except ValueError as exc:
        raise ValueError("example path must stay under examples") from exc
    if not path.exists():
        raise ValueError(f"example not found: {name}")
    return path


def examples(args: argparse.Namespace) -> int:
    try:
        path = _example_path(args.name)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    if args.name:
        print(path)
        return 0
    if not EXAMPLES_DIR.exists():
        return 0
    for item in sorted(EXAMPLES_DIR.rglob("*")):
        if item.is_file() and item.name != ".DS_Store":
            print(item.relative_to(EXAMPLES_DIR).as_posix())
    return 0


def main() -> int:
    from .a2a import A2A_ROLES

    parser = argparse.ArgumentParser(
        prog="agentbus",
        description="로컬 다중 에이전트 파일 버스: 메시지·ack·상태·작업. stdlib 전용 포터블 도구.",
        epilog=(
            "작업 수명주기: submitted → working → input_required → completed/failed/canceled.\n"
            "에이전트 상태(status --state)는 작업과 별개: running/waiting/done/error.\n"
            "스레딩: send --task <id>, --reply-to <id>.\n"
            "카드: 기본 ./agent-cards/*.json. 옵션: agentbus <명령> --help."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--bus-dir", type=Path, default=DEFAULT_BUS_DIR)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("serve", help="로컬 대시보드 실행 (127.0.0.1)")
    p.add_argument("--port", type=int, default=DEFAULT_PORT)
    p.add_argument("--root", type=Path, default=DEFAULT_ROOT, help="@ 파일 색인 루트 (기본 현재 디렉터리)")
    p.add_argument("--cards-dir", dest="cards_dir", type=Path, default=CARDS_DIR)
    p.set_defaults(func=serve_cmd)

    p = sub.add_parser("init", help="버스 디렉터리 초기화")
    p.set_defaults(func=init_bus)
    p = sub.add_parser("show-status", help="현재 에이전트 상태 요약")
    p.set_defaults(func=show_status)
    p = sub.add_parser("check-stop", help="정지 요청(stop.json) 확인")
    p.set_defaults(func=check_stop)
    p = sub.add_parser("send", help="메시지 전송 (--task/--reply-to로 스레딩)")
    p.add_argument("--from", dest="sender", required=True)
    p.add_argument("--to", required=True)
    p.add_argument("--kind", default="note")
    p.add_argument("--subject", required=True)
    p.add_argument("--body", required=True)
    p.add_argument("--ref", action="append")
    p.add_argument("--task", default="", help="연관 task_id (스레딩)")
    p.add_argument("--reply-to", dest="reply_to", default="", help="응답 대상 message_id")
    p.add_argument("--sensitivity", choices=SENSITIVITY_LEVELS, default="", help="민감도 표시")
    p.add_argument("--retention", choices=RETENTION_POLICIES, default="", help="보관 힌트")
    p.set_defaults(func=send)
    p = sub.add_parser("inbox", help="에이전트 수신함 읽기")
    p.add_argument("--agent", required=True)
    p.add_argument("--limit", type=int, default=50)
    p.set_defaults(func=inbox)
    p = sub.add_parser("ack", help="메시지 확인 표시")
    p.add_argument("--agent", required=True)
    p.add_argument("message_id")
    p.set_defaults(func=ack)
    p = sub.add_parser("message-delete", help="메시지 삭제 이벤트 기록")
    p.add_argument("--id", required=True)
    p.add_argument("--by", required=True)
    p.set_defaults(func=message_delete)
    p = sub.add_parser("watch", help="ack 기준 미확인 request 감시 (delivered는 ack와 분리)")
    p.add_argument("--agent", required=True)
    p.add_argument("--kinds", default="request", help="쉼표 구분 kind 필터 (기본 request)")
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--max-body-chars", type=int, default=1200)
    p.add_argument("--interval-seconds", type=float, default=2.5)
    p.add_argument("--once", action="store_true", help="한 번만 확인하고 종료")
    p.add_argument("--json", action="store_true", help="pending 메시지를 JSON으로 출력")
    p.add_argument("--mark-delivered", action="store_true", help="delivered.jsonl에 기록해 중복 표시 방지")
    p.add_argument("--include-delivered", action="store_true", help="연속 watch에서도 이미 delivered 처리된 미ack 메시지를 다시 표시")
    p.set_defaults(func=watch)
    p = sub.add_parser("events", help="버스 이벤트 스트림 출력")
    p.add_argument("--types", default="", help="쉼표 구분 이벤트 타입 필터. ticket.* 허용")
    p.add_argument("--target", default="", help="쉼표 구분 target 필터. all/* 이벤트도 포함")
    p.add_argument("--after", default="", help="이 cursor 이후 이벤트만 출력")
    p.add_argument("--limit", type=int, default=0, help="마지막 N개만 출력")
    p.add_argument("--jsonl", action="store_true", help="JSON Lines로 출력")
    p.set_defaults(func=events)
    p = sub.add_parser("watch-events", help="새 버스 이벤트 감시")
    p.add_argument("--types", default="", help="쉼표 구분 이벤트 타입 필터. message.*, ticket.* 허용")
    p.add_argument("--target", default="", help="쉼표 구분 target 필터. all/* 이벤트도 포함")
    p.add_argument("--interval-seconds", type=float, default=1.0)
    p.add_argument("--once", action="store_true", help="현재 새 이벤트만 확인하고 종료")
    p.add_argument("--from-start", action="store_true", help="현재 로그의 기존 이벤트부터 출력")
    p.add_argument("--cursor-file", type=Path, default=None, help="처리한 마지막 event cursor 저장")
    p.add_argument("--dry-run", action="store_true", help="이벤트만 출력하고 adapter와 cursor를 변경하지 않음")
    p.add_argument("--fail-log", type=Path, default=None, help="adapter 실패 JSONL 기록")
    p.add_argument("--exec", default="", help="각 이벤트 JSON을 stdin으로 넘길 shell 명령")
    p.add_argument("--exec-timeout", type=float, default=60.0, help="adapter timeout seconds. 0이면 비활성")
    p.add_argument("--allow-sensitive", action="store_true", help="민감 이벤트의 외부 adapter 실행 허용")
    p.set_defaults(func=watch_events)
    p = sub.add_parser("wakeup", help="JSON profile로 inbox 또는 event wakeup 실행")
    p.add_argument("--profile", type=Path, required=True, help="wakeup profile JSON 경로")
    p.add_argument("--once", action="store_true", help="한 번 확인하고 종료")
    p.add_argument("--dry-run", action="store_true", help="출력만 하고 command/cursor/delivered는 변경하지 않음")
    p.set_defaults(func=wakeup)
    p = sub.add_parser("wakeup-check", help="wakeup profile JSON 검사")
    p.add_argument("--file", type=Path, required=True, help="wakeup profile JSON 경로")
    p.set_defaults(func=wakeup_check)
    p = sub.add_parser("adapter-status", help="adapter cursor와 실패 요약 출력")
    p.add_argument("--json", action="store_true", help="JSON으로 출력")
    p.set_defaults(func=adapter_status)
    p = sub.add_parser("status", help="에이전트 상태 갱신 (running/waiting/done/error)")
    p.add_argument("--agent", required=True)
    p.add_argument("--state", choices=AGENT_STATES, required=True)
    p.add_argument("--task", default="")
    p.add_argument("--note", default="")
    p.set_defaults(func=set_status)
    p = sub.add_parser("stop", help="협력적 정지 요청 기록")
    p.add_argument("--by", required=True)
    p.add_argument("--reason", required=True)
    p.add_argument("--detail", default="")
    p.set_defaults(func=stop)
    p = sub.add_parser("supervise", help="감독 루프 (heartbeat·정체·시간 초과 시 정지)")
    p.add_argument("--agents", default="my-agent", help="감독할 에이전트 이름 목록(쉼표 구분)")
    p.add_argument("--stale-seconds", type=int, default=900)
    p.add_argument("--startup-grace-seconds", type=int, default=600)
    p.add_argument("--max-minutes", type=int, default=120)
    p.add_argument("--interval-seconds", type=int, default=30)
    p.set_defaults(func=supervise)
    p = sub.add_parser("task-new", help="작업 생성 (이벤트 로그)")
    p.add_argument("--title", required=True)
    p.add_argument("--by", required=True)
    p.add_argument("--assign", default="", help="쉼표 구분 담당 에이전트")
    p.add_argument("--id", default="", help="명시 task_id (생략 시 자동)")
    p.add_argument("--sensitivity", choices=SENSITIVITY_LEVELS, default="", help="민감도 표시")
    p.add_argument("--retention", choices=RETENTION_POLICIES, default="", help="보관 힌트")
    p.set_defaults(func=task_new)
    p = sub.add_parser("task-state", help="task 수명주기 상태 갱신")
    p.add_argument("--id", required=True)
    p.add_argument("--state", choices=TASK_STATES, required=True)
    p.add_argument("--by", required=True)
    p.add_argument("--note", default="")
    p.set_defaults(func=task_state)
    p = sub.add_parser("task-delete", help="task 삭제 이벤트 기록")
    p.add_argument("--id", required=True)
    p.add_argument("--by", required=True)
    p.set_defaults(func=task_delete)
    p = sub.add_parser("task-list", help="현재 task 상태 (이벤트 접기)")
    p.set_defaults(func=task_list)
    add_ticket_parsers(sub)
    p = sub.add_parser("clear", help="메시지·ack·delivered 비우기 (--all: 작업·티켓·상태까지)")
    p.add_argument("--all", action="store_true", help="작업·티켓·상태·정지까지 초기화")
    p.add_argument("--yes", action="store_true", help="확인 없이 진행")
    p.set_defaults(func=clear)
    p = sub.add_parser("rotate", help="메시지 로그를 archive/로 회전")
    p.set_defaults(func=rotate)
    p = sub.add_parser("security-check", help="로컬 보안 가드레일 점검")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=security_check)
    p = sub.add_parser("aas-packet", help="운용 데이터와 판단 기록을 assessment packet JSON으로 묶기")
    p.add_argument("--data", required=True, help="운용 데이터 JSON 경로. stdin은 '-'")
    p.add_argument("--asset-id", required=True, help="대상 asset 식별자")
    p.add_argument("--asset-name", default="", help="표시용 asset 이름")
    p.add_argument("--event-cursor", default="", help="이 cursor 이후 change event만 포함")
    p.add_argument("--include-messages", type=int, default=50, help="최근 communication record 개수")
    p.add_argument("--assessment-summary", default="", help="판단 요약 JSON 경로. stdin은 '-'")
    p.add_argument("--sensitivity", choices=SENSITIVITY_LEVELS, default="", help="packet 민감도 표시")
    p.add_argument("--retention", choices=RETENTION_POLICIES, default="", help="packet 보관 힌트")
    p.add_argument("--out", type=Path, default=None, help="출력 파일. 생략하면 stdout")
    p.add_argument("--compact", action="store_true", help="공백 없는 JSON 출력")
    p.set_defaults(func=aas_packet)
    p = sub.add_parser("aas-packet-check", help="assessment packet 최소 계약 확인")
    p.add_argument("--file", required=True, help="packet JSON 경로. stdin은 '-'")
    p.set_defaults(func=aas_packet_check)
    p = sub.add_parser("a2a-card", help="로컬 에이전트 카드를 A2A Agent Card로 투영")
    p.add_argument("--agent", default="", help="카드 idShort 또는 파일명")
    p.add_argument("--cards-dir", dest="cards_dir", type=Path, default=CARDS_DIR)
    p.add_argument("--url", default="http://127.0.0.1:8765/a2a/rpc", help="A2A JSON-RPC endpoint URL")
    p.add_argument("--tenant", default="", help="supportedInterfaces[].tenant")
    p.add_argument("--out", type=Path, default=None, help="출력 파일. 생략하면 stdout")
    p.add_argument("--compact", action="store_true", help="공백 없는 JSON 출력")
    p.set_defaults(func=a2a_card)
    p = sub.add_parser("a2a-card-check", help="A2A Agent Card 최소 계약 확인")
    p.add_argument("--file", required=True, help="Agent Card JSON 경로. stdin은 '-'")
    p.set_defaults(func=a2a_card_check)
    p = sub.add_parser("a2a-rpc", help="메시지를 A2A SendMessage JSON-RPC request로 투영")
    p.add_argument("--message-id", required=True, help="보낼 메시지 id")
    p.add_argument("--request-id", default="", help="JSON-RPC id. 생략하면 자동")
    p.add_argument("--role", choices=A2A_ROLES, default="ROLE_USER")
    p.add_argument("--context-id", default="", help="A2A contextId")
    p.add_argument("--tenant", default="", help="A2A tenant routing value")
    p.add_argument("--data", action="append", help="추가할 structured JSON part 경로. stdin은 '-'")
    p.add_argument("--accepted-output", action="append", help="허용할 output MIME. 쉼표 구분 가능")
    p.add_argument("--wait", action="store_true", help="returnImmediately=false로 생성")
    p.add_argument("--out", type=Path, default=None, help="출력 파일. 생략하면 stdout")
    p.add_argument("--compact", action="store_true", help="공백 없는 JSON 출력")
    p.set_defaults(func=a2a_rpc)
    p = sub.add_parser("a2a-rpc-check", help="A2A SendMessage JSON-RPC 최소 계약 확인")
    p.add_argument("--file", required=True, help="request JSON 경로. stdin은 '-'")
    p.set_defaults(func=a2a_rpc_check)
    p = sub.add_parser("a2a-post", help="A2A JSON-RPC request를 HTTP(S) endpoint로 전송")
    p.add_argument("--file", required=True, help="request JSON 경로. stdin은 '-'")
    p.add_argument("--endpoint", required=True, help="A2A JSON-RPC HTTP(S) endpoint")
    p.add_argument("--bearer-token", default="", help="Authorization: Bearer 토큰")
    p.add_argument("--token-env", default="", help="Bearer 토큰을 읽을 환경변수 이름")
    p.add_argument("--header", action="append", help="추가 HTTP header. 예: 'X-Trace: 1'")
    p.add_argument("--timeout", type=float, default=30.0, help="HTTP timeout seconds")
    p.add_argument("--allow-sensitive", action="store_true", help="민감 request 외부 전송 허용")
    p.add_argument("--allow-insecure", action="store_true", help="http endpoint로 token/sensitive request 전송 허용")
    p.add_argument("--fail-log", type=Path, default=None, help="실패 JSONL 기록")
    p.add_argument("--out", type=Path, default=None, help="응답 body 저장 파일")
    p.add_argument("--record-response-to", default="", help="응답을 bus 메시지로 받을 에이전트")
    p.add_argument("--response-from", default="a2a", help="응답 기록 메시지의 sender")
    p.set_defaults(func=a2a_post)
    p = sub.add_parser("workflow", help="에이전트 협업 워크플로와 종료 보고서 template 출력")
    p.add_argument("--path", action="store_true", help="패키지에 포함된 SKILL.md 경로만 출력")
    p.set_defaults(func=workflow)
    p = sub.add_parser("loop", help="에이전트 루프 엔트리와 종료 보고 안내 출력")
    p.add_argument("--path", action="store_true", help="패키지에 포함된 SKILL.md 경로만 출력")
    p.set_defaults(func=loop)
    p = sub.add_parser("examples", help="패키지 예제 목록 또는 경로 출력")
    p.add_argument("name", nargs="?", default="", help="예: wakeup/claude-inbox.json")
    p.set_defaults(func=examples)
    args = parse_args(parser)
    try:
        return args.func(args)
    except TimeoutError as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
