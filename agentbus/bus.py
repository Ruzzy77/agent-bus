#!/usr/bin/env python3
"""Secure capsule channel for local agent coordination.

Config precedence: CLI flag > AGENTBUS_* env > cwd.
"""
from __future__ import annotations

import argparse
import base64
from contextlib import contextmanager, redirect_stderr, redirect_stdout
import io
import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
import subprocess
import urllib.error
import urllib.request
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


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
    if level and level != "normal":
        fields["sensitivity"] = level
    if policy and policy != "normal":
        fields["retention"] = policy
    return fields


def effective_sensitivity(value: Any) -> str:
    if not isinstance(value, dict):
        return "normal"
    text = _clean_text(value.get("sensitivity")).lower()
    if not text:
        return "normal"
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


# 기본 경로: AGENTBUS_* env, cwd 순서. CLI 인자가 최우선이다.
DEFAULT_BUS_DIR = _env_path("AGENTBUS_BUS_DIR", Path.cwd() / ".agent-bus")
CARDS_DIR = _env_path("AGENTBUS_CARDS_DIR", Path.cwd() / "agent-cards")
DEFAULT_ROOT = _env_path("AGENTBUS_ROOT", Path.cwd())
DEFAULT_PORT = _env_int("AGENTBUS_PORT", 8765)
WORKFLOW_PATH = Path(__file__).resolve().parent / "skills" / "agent-bus-workflow" / "SKILL.md"
LOOP_PATH = Path(__file__).resolve().parent / "skills" / "agent-bus-loop" / "SKILL.md"
RESOURCES_DIR = Path(__file__).resolve().parent / "resources"

# 작업 상태값.
TASK_STATES = ["submitted", "working", "input_required", "completed", "failed", "canceled"]
AGENT_STATES = ["running", "waiting", "done", "error"]
ISSUE_STATES = ["open", "accepted", "rejected"]
SENSITIVITY_LEVELS = ["normal", "internal", "restricted"]
RETENTION_POLICIES = ["normal", "session", "no_archive"]
SENSITIVE_LEVELS = {"restricted"}
EXTERNAL_RAW_BLOCK_LEVELS = {"internal", "restricted"}
REDACTED_TEXT = "[redacted]"
CONTENT_FIELDS = {
    "message": ("subject", "body", "refs"),
    "task": ("title", "note"),
    "ticket": ("title", "body", "refs", "note"),
}
SEALED_KIND_DIR = {"message": "messages", "task": "tasks", "ticket": "tickets"}
SEALED_ALG = "AESGCM-256"
AUTH_HASH_ALG = "pbkdf2-sha256"
AUTH_HASH_ITERATIONS = 200_000
SKILL_STATES = ["candidate", "active", "retired"]
SKILL_EVIDENCE_TYPES = ["grounding", "check", "gap", "risk"]
SKILL_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,80}$")
EVENT_VERSION = "agentbus.event.v1"
EVENT_LOGS = ("messages", "message_deletes", "tasks", "issues", "acks", "delivered")
CAPSULE_VERSION = "agentbus.capsule.v1"
CAPSULE_STORE_VERSION = 1
CAPSULE_RECORD_FILES = {
    "messages.jsonl": "messages",
    "message_deletes.jsonl": "message_deletes",
    "tasks.jsonl": "tasks",
    "issues.jsonl": "issues",
    "acks.jsonl": "acks",
    "delivered.jsonl": "delivered",
}
CAPSULE_DOC_FILES = {
    "status.json": "status",
    "stop.json": "stop",
}
BRIDGE_PROFILE_VERSION = "bridge-profile.v1"
BRIDGE_HANDLER_TYPES = {"monitor", "agent", "http", "openai-compatible"}
BRIDGE_AGENT_PROVIDERS = {"codex", "claude", "gemini"}
BRIDGE_ENV_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
BRIDGE_EVENT_RE = re.compile(r"^[a-z][a-z0-9_-]*(\.[a-z][a-z0-9_-]*|\.\*)+$")
BRIDGE_TEMPLATE_NAME = "profile.template.json"
BRIDGE_TEMPLATE = {
    "schemaVersion": BRIDGE_PROFILE_VERSION,
    "name": "local-monitor",
    "event": "message.created",
    "matcher": {
        "target": "agent-id",
        "kind": ["request"],
    },
    "handler": {
        "type": "monitor",
    },
    "fromStart": False,
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _parse_iso_datetime(value: object) -> datetime | None:
    text = _clean_text(value)
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


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


def _read_json_file(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default


def _read_jsonl_file(path: Path) -> list[dict[str, Any]]:
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


def _write_json_file(path: Path, value: Any) -> None:
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


def _agentbus_config_dir() -> Path:
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "agent-bus"
    base = os.environ.get("XDG_CONFIG_HOME")
    return (Path(base).expanduser() if base else Path.home() / ".config") / "agent-bus"


def _capsule_key_path(capsule_id: str) -> Path:
    return _agentbus_config_dir() / "keys" / f"{capsule_id}.json"


def _capsule_channel_path(bus_dir: Path) -> Path:
    return bus_dir / "channel.json"


def _capsule_db_path(bus_dir: Path) -> Path:
    return bus_dir / "store" / "capsule.sqlite"


def _capsule_channel(bus_dir: Path) -> dict[str, Any]:
    data = _read_json_file(_capsule_channel_path(bus_dir), {})
    return data if isinstance(data, dict) else {}


def _capsule_id(bus_dir: Path) -> str:
    return _required_text(_capsule_channel(bus_dir).get("id"), "capsule id")


def _capsule_path_info(path: Path) -> tuple[Path, str, str] | None:
    path = Path(path)
    if path.name in CAPSULE_RECORD_FILES:
        bus_dir = path.parent
        kind = "record"
        name = CAPSULE_RECORD_FILES[path.name]
    elif path.name in CAPSULE_DOC_FILES:
        bus_dir = path.parent
        kind = "doc"
        name = CAPSULE_DOC_FILES[path.name]
    elif path.name == "auth.json" and path.parent.name == "security":
        bus_dir = path.parent.parent
        kind = "doc"
        name = "auth"
    else:
        return None
    if _capsule_channel_path(bus_dir).exists():
        return bus_dir, kind, name
    return None


def _capsule_connect(bus_dir: Path) -> sqlite3.Connection:
    db_path = _capsule_db_path(bus_dir)
    db_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    _chmod_private_dir(db_path.parent)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute(
        "CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS docs (name TEXT PRIMARY KEY, nonce TEXT NOT NULL, payload TEXT NOT NULL, updated_at TEXT NOT NULL)"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS records (seq INTEGER PRIMARY KEY AUTOINCREMENT, stream TEXT NOT NULL, nonce TEXT NOT NULL, payload TEXT NOT NULL, meta TEXT NOT NULL, created_at TEXT NOT NULL)"
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_records_stream_seq ON records(stream, seq)")
    conn.execute(
        "INSERT OR REPLACE INTO meta(key, value) VALUES('schemaVersion', ?)",
        (CAPSULE_VERSION,),
    )
    conn.execute(
        "INSERT OR REPLACE INTO meta(key, value) VALUES('storeVersion', ?)",
        (str(CAPSULE_STORE_VERSION),),
    )
    conn.commit()
    _chmod_private(db_path)
    return conn


def _load_capsule_key(bus_dir: Path, create: bool = False) -> bytes:
    channel_id = _capsule_id(bus_dir)
    key_path = _capsule_key_path(channel_id)
    if create and not key_path.exists():
        key_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        _chmod_private_dir(key_path.parent)
        _write_json_file(key_path, {
            "schemaVersion": "agentbus.capsule-key.v1",
            "capsuleId": channel_id,
            "alg": SEALED_ALG,
            "key": _b64_encode(AESGCM.generate_key(bit_length=256)),
            "createdAt": now_iso(),
        })
    data = _read_json_file(key_path, {})
    if not isinstance(data, dict) or data.get("alg") != SEALED_ALG or not data.get("key"):
        raise ValueError("capsule key not initialized; run agentbus bus init")
    return _b64_decode(data["key"])


def _capsule_aad(bus_dir: Path, purpose: str) -> bytes:
    return f"{CAPSULE_VERSION}:{_capsule_id(bus_dir)}:{purpose}".encode("utf-8")


def _capsule_encrypt(bus_dir: Path, purpose: str, value: Any) -> tuple[str, str]:
    nonce = secrets.token_bytes(12)
    plaintext = json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ciphertext = AESGCM(_load_capsule_key(bus_dir)).encrypt(nonce, plaintext, _capsule_aad(bus_dir, purpose))
    return _b64_encode(nonce), _b64_encode(ciphertext)


def _capsule_decrypt(bus_dir: Path, purpose: str, nonce: str, payload: str) -> Any:
    plaintext = AESGCM(_load_capsule_key(bus_dir)).decrypt(
        _b64_decode(nonce),
        _b64_decode(payload),
        _capsule_aad(bus_dir, purpose),
    )
    return json.loads(plaintext.decode("utf-8"))


def _capsule_record_meta(row: Any) -> dict[str, Any]:
    if not isinstance(row, dict):
        return {}
    out: dict[str, Any] = {}
    for key in ("id", "task_id", "issue_id", "time", "event", "kind", "from", "to", "by", "state", "sensitivity", "retention"):
        if key in row:
            out[key] = row.get(key)
    return out


def _capsule_read_records(bus_dir: Path, stream: str) -> list[dict[str, Any]]:
    with _capsule_connect(bus_dir) as conn:
        rows = conn.execute("SELECT nonce, payload FROM records WHERE stream=? ORDER BY seq", (stream,)).fetchall()
    out: list[dict[str, Any]] = []
    for nonce, payload in rows:
        try:
            value = _capsule_decrypt(bus_dir, f"record:{stream}", nonce, payload)
            out.append(value if isinstance(value, dict) else {"_decode_error": value})
        except (ValueError, json.JSONDecodeError):
            out.append({"_decode_error": "encrypted record"})
    return out


def _capsule_append_record(bus_dir: Path, stream: str, value: Any) -> None:
    nonce, payload = _capsule_encrypt(bus_dir, f"record:{stream}", value)
    meta = json.dumps(_capsule_record_meta(value), ensure_ascii=False, sort_keys=True)
    with _capsule_connect(bus_dir) as conn:
        conn.execute(
            "INSERT INTO records(stream, nonce, payload, meta, created_at) VALUES(?, ?, ?, ?, ?)",
            (stream, nonce, payload, meta, now_iso()),
        )
        conn.commit()


def _capsule_read_doc(bus_dir: Path, name: str, default: Any) -> Any:
    with _capsule_connect(bus_dir) as conn:
        row = conn.execute("SELECT nonce, payload FROM docs WHERE name=?", (name,)).fetchone()
    if not row:
        return default
    try:
        return _capsule_decrypt(bus_dir, f"doc:{name}", row[0], row[1])
    except (ValueError, json.JSONDecodeError):
        return default


def _capsule_write_doc(bus_dir: Path, name: str, value: Any) -> None:
    nonce, payload = _capsule_encrypt(bus_dir, f"doc:{name}", value)
    with _capsule_connect(bus_dir) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO docs(name, nonce, payload, updated_at) VALUES(?, ?, ?, ?)",
            (name, nonce, payload, now_iso()),
        )
        conn.commit()


def _capsule_delete_doc(bus_dir: Path, name: str) -> None:
    with _capsule_connect(bus_dir) as conn:
        conn.execute("DELETE FROM docs WHERE name=?", (name,))
        conn.commit()


def _capsule_doc_exists(path: Path) -> bool:
    info = _capsule_path_info(path)
    if not info or info[1] != "doc":
        return Path(path).exists()
    bus_dir, _, name = info
    with _capsule_connect(bus_dir) as conn:
        row = conn.execute("SELECT 1 FROM docs WHERE name=?", (name,)).fetchone()
    return bool(row)


def path_exists(path: Path) -> bool:
    return _capsule_doc_exists(path)


def delete_path(path: Path) -> None:
    info = _capsule_path_info(path)
    if info and info[1] == "doc":
        _capsule_delete_doc(info[0], info[2])
        return
    Path(path).unlink(missing_ok=True)


def _capsule_clear_stream(bus_dir: Path, stream: str) -> None:
    with _capsule_connect(bus_dir) as conn:
        conn.execute("DELETE FROM records WHERE stream=?", (stream,))
        conn.commit()


def _capsule_replace_stream(bus_dir: Path, stream: str, rows: list[dict[str, Any]]) -> None:
    with _capsule_connect(bus_dir) as conn:
        conn.execute("DELETE FROM records WHERE stream=?", (stream,))
        conn.commit()
    for row in rows:
        _capsule_append_record(bus_dir, stream, row)


def load_json(path: Path, default: Any) -> Any:
    info = _capsule_path_info(path)
    if info:
        bus_dir, kind, name = info
        if kind == "doc":
            return _capsule_read_doc(bus_dir, name, default)
    return _read_json_file(path, default)


def write_json(path: Path, value: Any) -> None:
    info = _capsule_path_info(path)
    if info:
        bus_dir, kind, name = info
        if kind == "doc":
            _capsule_write_doc(bus_dir, name, value)
            return
    _write_json_file(path, value)


def _chmod_private(path: Path) -> None:
    try:
        path.chmod(0o600)
    except OSError:
        pass


@contextmanager
def file_lock(path: Path, timeout_seconds: float = 5.0, stale_seconds: float = 30.0):
    info = _capsule_path_info(path)
    if info:
        path = _capsule_db_path(info[0])
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
    info = _capsule_path_info(path)
    if info and info[1] == "record":
        _capsule_append_record(info[0], info[2], value)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n")
    _chmod_private(path)


def append_jsonl(path: Path, value: Any) -> None:
    info = _capsule_path_info(path)
    if info and info[1] == "record":
        with file_lock(path):
            _capsule_append_record(info[0], info[2], value)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with file_lock(path):
        _append_jsonl_unlocked(path, value)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    info = _capsule_path_info(path)
    if info and info[1] == "record":
        return _capsule_read_records(info[0], info[2])
    return _read_jsonl_file(path)


def paths(bus_dir: Path) -> dict[str, Path]:
    return {
        "channel": bus_dir / "channel.json",
        "store": bus_dir / "store",
        "capsule_db": _capsule_db_path(bus_dir),
        "messages": bus_dir / "messages.jsonl",
        "message_deletes": bus_dir / "message_deletes.jsonl",
        "acks": bus_dir / "acks.jsonl",
        "delivered": bus_dir / "delivered.jsonl",
        "status": bus_dir / "status.json",
        "stop": bus_dir / "stop.json",
        "tasks": bus_dir / "tasks.jsonl",
        "issues": bus_dir / "issues.jsonl",
        "skills": bus_dir / "skills",
        "security": bus_dir / "security",
        "auth": bus_dir / "security" / "auth.json",
        "key": _capsule_key_path(_capsule_channel(bus_dir).get("id", "uninitialized")),
        "sealed": bus_dir / "sealed",
    }


def _chmod_private_dir(path: Path) -> None:
    try:
        path.chmod(0o700)
    except OSError:
        pass


def _b64_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii")


def _b64_decode(text: object) -> bytes:
    return base64.urlsafe_b64decode(_required_text(text, "base64").encode("ascii"))


def _sealed_root(bus_dir: Path) -> Path:
    return paths(bus_dir)["sealed"]


def ensure_security(bus_dir: Path, create_key: bool = False) -> None:
    ensure_bus(bus_dir)
    ps = paths(bus_dir)
    if not _capsule_doc_exists(ps["auth"]):
        write_json(ps["auth"], {"schemaVersion": "agentbus.auth.v1", "agents": {}, "viewers": {}})
    if create_key:
        _load_capsule_key(bus_dir, create=True)


def _load_bus_key(bus_dir: Path) -> bytes:
    return _load_capsule_key(bus_dir)


def _auth_store(bus_dir: Path) -> dict[str, Any]:
    data = load_json(paths(bus_dir)["auth"], {"agents": {}, "viewers": {}})
    return data if isinstance(data, dict) else {"agents": {}, "viewers": {}}


def _auth_subjects(bus_dir: Path, bucket: str) -> dict[str, Any]:
    subjects = _auth_store(bus_dir).get(bucket)
    return subjects if isinstance(subjects, dict) else {}


def _auth_agents(bus_dir: Path) -> dict[str, Any]:
    return _auth_subjects(bus_dir, "agents")


def _auth_viewers(bus_dir: Path) -> dict[str, Any]:
    return _auth_subjects(bus_dir, "viewers")


def _hash_agent_token(token: str, salt_hex: str, iterations: int = AUTH_HASH_ITERATIONS) -> str:
    digest = hashlib.pbkdf2_hmac("sha256", token.encode("utf-8"), bytes.fromhex(salt_hex), iterations)
    return digest.hex()


def _auth_subject_can_read_restricted(bus_dir: Path, bucket: str, name: object, token: object) -> bool:
    subject = _clean_text(name)
    token_text = _clean_text(token)
    if not subject or not token_text:
        return False
    row = _auth_subjects(bus_dir, bucket).get(subject)
    if not isinstance(row, dict) or not row.get("canReadRestricted"):
        return False
    expires_at = _parse_iso_datetime(row.get("expiresAt"))
    if expires_at and expires_at <= datetime.now(timezone.utc):
        return False
    salt = _clean_text(row.get("salt"))
    token_hash = _clean_text(row.get("tokenHash"))
    iterations = int(row.get("iterations") or AUTH_HASH_ITERATIONS)
    if not salt or not token_hash:
        return False
    try:
        candidate = _hash_agent_token(token_text, salt, iterations)
    except ValueError:
        return False
    return hmac.compare_digest(candidate, token_hash)


def agent_can_read_restricted(bus_dir: Path, agent: object) -> bool:
    return _auth_subject_can_read_restricted(bus_dir, "agents", agent, os.environ.get("AGENTBUS_AGENT_TOKEN", ""))


def viewer_can_read_restricted(bus_dir: Path, viewer: object, token: object) -> bool:
    return _auth_subject_can_read_restricted(bus_dir, "viewers", viewer, token)


def auth_subject_session_claim(bus_dir: Path, bucket: str, name: object) -> dict[str, str] | None:
    subject = _clean_text(name)
    if not subject:
        return None
    row = _auth_subjects(bus_dir, bucket).get(subject)
    if not isinstance(row, dict) or not row.get("canReadRestricted"):
        return None
    expires_at = _parse_iso_datetime(row.get("expiresAt"))
    if expires_at and expires_at <= datetime.now(timezone.utc):
        return None
    token_hash = _clean_text(row.get("tokenHash"))
    if not token_hash:
        return None
    return {
        "tokenHash": token_hash,
        "expiresAt": _clean_text(row.get("expiresAt")),
    }


def auth_subject_session_ttl(bus_dir: Path, bucket: str, name: object, default_seconds: int) -> int:
    claim = auth_subject_session_claim(bus_dir, bucket, name)
    if not claim:
        return 0
    expires_at = _parse_iso_datetime(claim.get("expiresAt"))
    if not expires_at:
        return int(default_seconds)
    remaining = int((expires_at - datetime.now(timezone.utc)).total_seconds())
    return max(0, min(int(default_seconds), remaining))


def auth_init(args: argparse.Namespace) -> int:
    ensure_security(args.bus_dir, create_key=True)
    print(paths(args.bus_dir)["security"])
    return 0


def _expires_at_after(seconds: int) -> str:
    if seconds <= 0:
        raise ValueError("ttl-seconds must be positive")
    return (datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat(timespec="milliseconds")


def _auth_arg(args: argparse.Namespace) -> tuple[str, str]:
    agent = _clean_text(getattr(args, "agent", ""))
    viewer = _clean_text(getattr(args, "viewer", ""))
    if agent:
        return "agents", agent
    if viewer:
        return "viewers", viewer
    raise ValueError("agent or viewer required")


def _grant_auth_token(bus_dir: Path, bucket: str, name: str, expires_at: str = "") -> str:
    if bucket not in {"agents", "viewers"}:
        raise ValueError("invalid auth bucket")
    ensure_security(bus_dir, create_key=True)
    subject = _required_text(name, "auth subject")
    token = secrets.token_urlsafe(32)
    salt = secrets.token_hex(16)
    ps = paths(bus_dir)
    with file_lock(ps["auth"]):
        data = load_json(ps["auth"], {"schemaVersion": "agentbus.auth.v1", "agents": {}, "viewers": {}})
        if not isinstance(data, dict):
            data = {"schemaVersion": "agentbus.auth.v1"}
        data.setdefault("schemaVersion", "agentbus.auth.v1")
        subjects = data.setdefault(bucket, {})
        if not isinstance(subjects, dict):
            data[bucket] = {}
            subjects = data[bucket]
        row = {
            "hashAlg": AUTH_HASH_ALG,
            "iterations": AUTH_HASH_ITERATIONS,
            "salt": salt,
            "tokenHash": _hash_agent_token(token, salt),
            "canReadRestricted": True,
            "grantedAt": now_iso(),
        }
        if expires_at:
            row["expiresAt"] = expires_at
        subjects[subject] = row
        write_json(ps["auth"], data)
    return token


def auth_grant(args: argparse.Namespace) -> int:
    bucket, name = _auth_arg(args)
    ttl_arg = getattr(args, "ttl_seconds", None)
    expires_at = _expires_at_after(int(ttl_arg)) if ttl_arg is not None else ""
    token = _grant_auth_token(args.bus_dir, bucket, name, expires_at)
    print(token)
    return 0


DEMO_RESTRICTED_SUBJECT = "Demo restricted view"
DEMO_RESTRICTED_BODY = (
    "This is sample-only restricted demo text. Use it to confirm that dashboard "
    "viewer authentication can switch a local capsule view from redacted to raw."
)
DEMO_RESTRICTED_SEED = {
    "messages": {
        "m-demo-002": {
            "subject": "Prepare field assessment packet",
            "body": "Create a compact assessment packet for press line telemetry. Keep external send blocked until approval.",
            "refs": ["agentbus/resources/aas/operational-data.sample.json"],
        },
        "m-demo-004": {
            "subject": "Runner boundary",
            "body": "Codex and Claude runner examples stay optional. Core bus and dashboard keep agent process execution outside the bus boundary.",
        },
    },
    "issues": {
        "i-demo-nda": {
            "title": "Define NDA packet redaction example",
            "body": "Add only if a demo buyer needs a visible protected-data path.",
            "refs": ["README.md", "agentbus/resources/aas/assessment-summary.sample.json"],
        },
    },
}


def _ensure_demo_restricted_sample(bus_dir: Path) -> str:
    ensure_bus(bus_dir)
    for row in read_jsonl(paths(bus_dir)["messages"]):
        if row.get("subject") == DEMO_RESTRICTED_SUBJECT and row.get("from") == "demo":
            return _clean_text(row.get("id"))
    msg = make_message(
        "demo",
        "operator",
        "note",
        DEMO_RESTRICTED_SUBJECT,
        DEMO_RESTRICTED_BODY,
        ["demo://restricted-view"],
        sensitivity="restricted",
        retention="no_archive",
    )
    append_message(bus_dir, msg)
    return _clean_text(msg.get("id"))


def _demo_seed_record_id(stream: str, row: dict[str, Any]) -> str:
    if stream == "messages":
        return _clean_text(row.get("id"))
    if stream == "issues":
        return _clean_text(row.get("issue_id"))
    return ""


def _replace_record_stream(bus_dir: Path, stream: str, rows: list[dict[str, Any]]) -> None:
    ps = paths(bus_dir)
    target = {
        "messages": ps["messages"],
        "issues": ps["issues"],
        "tasks": ps["tasks"],
    }.get(stream)
    if target is None:
        raise ValueError("unsupported record stream")
    info = _capsule_path_info(target)
    if info and info[1] == "record":
        _capsule_replace_stream(bus_dir, stream, rows)
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    text = "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows)
    target.write_text(text, encoding="utf-8")
    _chmod_private(target)


def _ensure_demo_seed_raw_records(bus_dir: Path) -> list[str]:
    if not _capsule_channel_path(bus_dir).exists():
        return []
    updated: list[str] = []
    ps = paths(bus_dir)
    for stream, seed in DEMO_RESTRICTED_SEED.items():
        path = ps["messages"] if stream == "messages" else ps["issues"]
        rows = read_jsonl(path)
        changed = False
        next_rows: list[dict[str, Any]] = []
        for row in rows:
            record_id = _demo_seed_record_id(stream, row)
            patch = seed.get(record_id)
            if patch and effective_sensitivity(row) == "restricted":
                needs_update = bool(row.get("redacted")) or any(row.get(key) != value for key, value in patch.items())
                if not needs_update:
                    next_rows.append(row)
                    continue
                next_row = dict(row)
                next_row.update(patch)
                next_row["redacted"] = False
                next_row.pop("redactionScope", None)
                next_row.pop("redactionReason", None)
                next_row.pop("redactedFields", None)
                row = next_row
                changed = True
                updated.append(record_id)
            next_rows.append(row)
        if changed:
            _replace_record_stream(bus_dir, stream, next_rows)
    return updated


def auth_demo(args: argparse.Namespace) -> int:
    viewer = _clean_text(args.viewer, "demo")
    ttl_seconds = max(60, int(args.ttl_seconds or 3600))
    expires_at = _expires_at_after(ttl_seconds)
    token = _grant_auth_token(args.bus_dir, "viewers", viewer, expires_at)
    demo_record_ids = _ensure_demo_seed_raw_records(args.bus_dir)
    message_id = "" if args.no_sample else _ensure_demo_restricted_sample(args.bus_dir)
    payload = {
        "viewer": viewer,
        "token": token,
        "expiresAt": expires_at,
        "messageId": message_id,
        "demoRecordIds": demo_record_ids,
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    print(f"viewer\t{viewer}")
    print(f"token\t{token}")
    print(f"expires\t{expires_at}")
    if message_id:
        print(f"message\t{message_id}")
    if demo_record_ids:
        print(f"unlocked\t{','.join(demo_record_ids)}")
    return 0


def auth_revoke(args: argparse.Namespace) -> int:
    ensure_security(args.bus_dir)
    bucket, name = _auth_arg(args)
    ps = paths(args.bus_dir)
    with file_lock(ps["auth"]):
        data = load_json(ps["auth"], {"schemaVersion": "agentbus.auth.v1", "agents": {}, "viewers": {}})
        if not isinstance(data, dict):
            data = {"schemaVersion": "agentbus.auth.v1"}
        subjects = data.setdefault(bucket, {})
        if not isinstance(subjects, dict):
            data[bucket] = {}
            subjects = data[bucket]
        subjects.pop(name, None)
        write_json(ps["auth"], data)
    print("revoked", name)
    return 0


def _auth_rows_for(bus_dir: Path, bucket: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for name, row in sorted(_auth_subjects(bus_dir, bucket).items()):
        if not isinstance(row, dict):
            continue
        rows.append({
            "name": name,
            "canReadRestricted": bool(row.get("canReadRestricted")),
            "grantedAt": row.get("grantedAt", ""),
            "expiresAt": row.get("expiresAt", ""),
            "expired": bool((expires_at := _parse_iso_datetime(row.get("expiresAt"))) and expires_at <= datetime.now(timezone.utc)),
        })
    return rows


def auth_rows(bus_dir: Path) -> list[dict[str, Any]]:
    return [dict(row, agent=row["name"]) for row in _auth_rows_for(bus_dir, "agents")]


def viewer_auth_rows(bus_dir: Path) -> list[dict[str, Any]]:
    return [dict(row, viewer=row["name"]) for row in _auth_rows_for(bus_dir, "viewers")]


def auth_list(args: argparse.Namespace) -> int:
    ensure_security(args.bus_dir)
    agents = auth_rows(args.bus_dir)
    viewers = viewer_auth_rows(args.bus_dir)
    if args.json:
        print(json.dumps({"agents": agents, "viewers": viewers}, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    if not agents and not viewers:
        print("no auth grants")
        return 0
    def parts(kind: str, row: dict[str, Any]) -> list[str]:
        name = row[kind]
        granted = row.get("grantedAt") or "-"
        if row.get("expired"):
            expiry = "expired"
        elif row.get("expiresAt"):
            expiry = f"expires={row['expiresAt']}"
        else:
            expiry = "expires=-"
        return [kind, name, f"restricted={str(row['canReadRestricted']).lower()}", f"granted={granted}", expiry]
    for row in agents:
        print("\t".join(parts("agent", row)))
    for row in viewers:
        print("\t".join(parts("viewer", row)))
    return 0

def _record_kind(row: dict[str, Any]) -> str:
    if "issue_id" in row:
        return "ticket"
    if "id" in row and ("body" in row or "subject" in row or "from" in row or "to" in row):
        return "message"
    if "task_id" in row:
        return "task"
    return ""


def _record_id(kind: str, row: dict[str, Any]) -> str:
    if kind == "message":
        return _required_text(row.get("id"), "message id")
    if kind == "task":
        return _required_text(row.get("task_id"), "task id")
    if kind == "ticket":
        return _required_text(row.get("issue_id"), "ticket id")
    raise ValueError("unsupported sealed record kind")


def _record_content_fields(kind: str, row: dict[str, Any]) -> list[str]:
    return [field for field in CONTENT_FIELDS.get(kind, ()) if field in row]


def _redacted_value(value: Any) -> Any:
    if isinstance(value, list):
        return [REDACTED_TEXT] if value else []
    if isinstance(value, dict):
        return {"redacted": True}
    return REDACTED_TEXT if value not in (None, "") else value


def redact_record(record: dict[str, Any], scope: str = "local") -> dict[str, Any]:
    row = dict(record)
    level = effective_sensitivity(row)
    should_redact = level == "restricted" or (scope == "external" and level == "internal")
    if not should_redact:
        return row
    kind = _record_kind(row)
    fields = _record_content_fields(kind, row)
    for field in fields:
        row[field] = _redacted_value(row.get(field))
    row["redacted"] = True
    row["redactedFields"] = fields
    row["redactionScope"] = scope
    row["redactionReason"] = level
    return row


def redact_event(event: dict[str, Any], scope: str = "local") -> dict[str, Any]:
    out = dict(event)
    data = event.get("data")
    if isinstance(data, dict):
        out["data"] = redact_record(data, scope)
    return out


def redact_payload(value: Any, level: str = "internal") -> Any:
    if level not in EXTERNAL_RAW_BLOCK_LEVELS:
        return value
    return {
        "redacted": True,
        "redactionScope": "external",
        "redactionReason": level,
        "sensitivity": level,
    }


def _raw_content_payload(kind: str, row: dict[str, Any]) -> dict[str, Any]:
    fields = _record_content_fields(kind, row)
    return {field: row.get(field) for field in fields}


def _has_raw_content(kind: str, row: dict[str, Any]) -> bool:
    for field in _record_content_fields(kind, row):
        value = row.get(field)
        if value in (None, "", [], {}, REDACTED_TEXT):
            continue
        if isinstance(value, list) and all(item == REDACTED_TEXT for item in value):
            continue
        return True
    return False


def _sealed_path(bus_dir: Path, kind: str, record_id: str) -> Path:
    directory = _sealed_root(bus_dir) / SEALED_KIND_DIR[kind]
    return directory / f"{record_id}.json.enc"


def _sealed_aad(kind: str, record_id: str) -> str:
    return f"agentbus.sealed.v1:{kind}:{record_id}"


def seal_record_content(bus_dir: Path, kind: str, record: dict[str, Any]) -> dict[str, Any]:
    row = dict(record)
    if _capsule_channel_path(bus_dir).exists():
        return row
    if effective_sensitivity(row) != "restricted":
        return row
    if row.get("sealed") and row.get("redacted"):
        return row
    if not _has_raw_content(kind, row):
        return redact_record(row, "local")
    key = _load_bus_key(bus_dir)
    record_id = _record_id(kind, row)
    fields = _record_content_fields(kind, row)
    aad = _sealed_aad(kind, record_id)
    nonce = secrets.token_bytes(12)
    sealed_at = now_iso()
    plaintext = json.dumps(_raw_content_payload(kind, row), ensure_ascii=False, sort_keys=True).encode("utf-8")
    ciphertext = AESGCM(key).encrypt(nonce, plaintext, aad.encode("utf-8"))
    blob = {
        "alg": SEALED_ALG,
        "nonce": _b64_encode(nonce),
        "aad": aad,
        "fields": fields,
        "sealedAt": sealed_at,
        "ciphertext": _b64_encode(ciphertext),
    }
    path = _sealed_path(bus_dir, kind, record_id)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    _chmod_private_dir(path.parent)
    write_json(path, blob)
    row["sealed"] = {key_: blob[key_] for key_ in ("alg", "nonce", "aad", "fields", "sealedAt")}
    return redact_record(row, "local")


def _unseal_record_content(bus_dir: Path, record: dict[str, Any]) -> dict[str, Any]:
    row = dict(record)
    if _capsule_channel_path(bus_dir).exists():
        return row
    if effective_sensitivity(row) != "restricted":
        return row
    kind = _record_kind(row)
    if not kind:
        return redact_record(row, "local")
    record_id = _record_id(kind, row)
    blob = load_json(_sealed_path(bus_dir, kind, record_id), {})
    if not isinstance(blob, dict) or blob.get("alg") != SEALED_ALG:
        return redact_record(row, "local")
    key = _load_bus_key(bus_dir)
    aad = _required_text(blob.get("aad"), "sealed aad")
    plaintext = AESGCM(key).decrypt(_b64_decode(blob.get("nonce")), _b64_decode(blob.get("ciphertext")), aad.encode("utf-8"))
    payload = json.loads(plaintext.decode("utf-8"))
    if isinstance(payload, dict):
        row.update({field: payload.get(field) for field in blob.get("fields") or [] if field in payload})
    row["redacted"] = False
    row.pop("redactionScope", None)
    row.pop("redactionReason", None)
    row.pop("redactedFields", None)
    return row


def _load_legacy_bus_key(bus_dir: Path) -> bytes | None:
    data = _read_json_file(bus_dir / "security" / "key.json", {})
    if not isinstance(data, dict) or data.get("alg") != SEALED_ALG or not data.get("key"):
        return None
    return _b64_decode(data["key"])


def _legacy_unseal_record_content(bus_dir: Path, record: dict[str, Any]) -> dict[str, Any]:
    row = dict(record)
    if effective_sensitivity(row) != "restricted" or not row.get("sealed"):
        return row
    kind = _record_kind(row)
    if not kind:
        return row
    try:
        record_id = _record_id(kind, row)
    except ValueError:
        return row
    key = _load_legacy_bus_key(bus_dir)
    if not key:
        return row
    blob = _read_json_file(bus_dir / "sealed" / SEALED_KIND_DIR[kind] / f"{record_id}.json.enc", {})
    if not isinstance(blob, dict) or blob.get("alg") != SEALED_ALG:
        return row
    try:
        plaintext = AESGCM(key).decrypt(
            _b64_decode(blob.get("nonce")),
            _b64_decode(blob.get("ciphertext")),
            _required_text(blob.get("aad"), "sealed aad").encode("utf-8"),
        )
        payload = json.loads(plaintext.decode("utf-8"))
    except (ValueError, json.JSONDecodeError):
        return row
    if isinstance(payload, dict):
        row.update({field: payload.get(field) for field in blob.get("fields") or [] if field in payload})
    row["redacted"] = False
    row.pop("redactionScope", None)
    row.pop("redactionReason", None)
    row.pop("redactedFields", None)
    return row


def record_for_agent(bus_dir: Path, record: dict[str, Any], agent: object) -> dict[str, Any]:
    if effective_sensitivity(record) != "restricted":
        return dict(record)
    if agent_can_read_restricted(bus_dir, agent):
        try:
            return _unseal_record_content(bus_dir, record)
        except (OSError, json.JSONDecodeError, ValueError):
            return redact_record(record, "local")
    return redact_record(record, "local")


def record_for_dashboard(bus_dir: Path, record: dict[str, Any], raw_restricted: bool = False) -> dict[str, Any]:
    if not raw_restricted:
        return redact_record(record, "local")
    if effective_sensitivity(record) != "restricted":
        return dict(record)
    try:
        return _unseal_record_content(bus_dir, record)
    except (OSError, json.JSONDecodeError, ValueError):
        return redact_record(record, "local")


def event_for_agent(bus_dir: Path, event: dict[str, Any], agent: object) -> dict[str, Any]:
    out = dict(event)
    data = event.get("data")
    if isinstance(data, dict):
        out["data"] = record_for_agent(bus_dir, data, agent)
    return out


def event_for_dashboard(bus_dir: Path, event: dict[str, Any], raw_restricted: bool = False) -> dict[str, Any]:
    out = dict(event)
    data = event.get("data")
    if isinstance(data, dict):
        out["data"] = record_for_dashboard(bus_dir, data, raw_restricted)
    return out


def external_event(event: dict[str, Any]) -> dict[str, Any]:
    return redact_event(event, "external")


def _payload_marks(value: Any) -> dict[str, bool]:
    marks = {"restricted": False, "internal_raw": False}

    def walk(item: Any) -> None:
        if isinstance(item, dict):
            level = effective_sensitivity(item) if "sensitivity" in item else "normal"
            if level == "restricted":
                marks["restricted"] = True
            if level == "internal" and not item.get("redacted"):
                marks["internal_raw"] = True
            for child in item.values():
                walk(child)
        elif isinstance(item, list):
            for child in item:
                walk(child)

    walk(value)
    return marks


def _skill_id(value: object) -> str:
    skill_id = _required_text(value, "skill_id")
    if not SKILL_ID_RE.match(skill_id) or "/" in skill_id or "\\" in skill_id:
        raise ValueError("skill_id must use letters, numbers, dot, underscore, or hyphen")
    return skill_id


def _skill_dir(bus_dir: Path, skill_id: object) -> Path:
    return paths(bus_dir)["skills"] / _skill_id(skill_id)


def _skill_path(bus_dir: Path, skill_id: object) -> Path:
    return _skill_dir(bus_dir, skill_id) / "SKILL.md"


def _skill_evidence_path(bus_dir: Path, skill_id: object) -> Path:
    return _skill_dir(bus_dir, skill_id) / "evidence.jsonl"


def _strip_simple_quotes(value: str) -> str:
    text = value.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {"'", '"'}:
        return text[1:-1]
    return text


def _parse_skill_frontmatter(text: str) -> dict[str, str]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    end = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end = i
            break
    if end is None:
        return {}

    data: dict[str, str] = {}
    fm = lines[1:end]
    i = 0
    key_re = re.compile(r"^([A-Za-z0-9_-]+):(?:\s*(.*))?$")
    while i < len(fm):
        line = fm[i]
        match = key_re.match(line)
        if not match:
            i += 1
            continue
        key, raw = match.group(1), (match.group(2) or "").strip()
        if raw in {">", ">-", ">+", "|", "|-", "|+"}:
            folded = raw.startswith(">")
            block: list[str] = []
            i += 1
            while i < len(fm):
                nxt = fm[i]
                if key_re.match(nxt):
                    break
                block.append(nxt.strip() if folded else nxt.lstrip())
                i += 1
            if folded:
                data[key] = " ".join(part for part in block if part).strip()
            else:
                data[key] = "\n".join(block).strip()
            continue
        data[key] = _strip_simple_quotes(raw)
        i += 1
    return data


def _frontmatter_bounds(text: str) -> tuple[list[str], int, int] | None:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            return lines, 0, i
    return None


def _set_frontmatter_value(text: str, key: str, value: str) -> str:
    bounds = _frontmatter_bounds(text)
    if bounds is None:
        body = text if text.startswith("\n") else "\n" + text
        return f"---\n{key}: {value}\n---\n{body}"
    lines, start, end = bounds
    key_re = re.compile(rf"^{re.escape(key)}\s*:")
    for i in range(start + 1, end):
        if key_re.match(lines[i]):
            lines[i] = f"{key}: {value}"
            return "\n".join(lines) + ("\n" if text.endswith("\n") else "")
    lines.insert(end, f"{key}: {value}")
    return "\n".join(lines) + ("\n" if text.endswith("\n") else "")


def _skill_template(skill_id: str, description: str, state: str) -> str:
    desc = _safe_inline(description, 500)
    return (
        "---\n"
        f"name: {skill_id}\n"
        "description: >-\n"
        f"  {desc}\n"
        f"state: {state}\n"
        "---\n\n"
        f"# {skill_id}\n\n"
        f"{desc}\n"
    )


def _safe_inline(value: object, limit: int = 160) -> str:
    text = re.sub(r"[\x00-\x1f\x7f]+", " ", str(value or ""))
    text = re.sub(r"\s+", " ", text).strip()
    if limit > 0 and len(text) > limit:
        return text[: max(0, limit - 1)].rstrip() + "…"
    return text


def _skill_evidence_rows(skill_dir: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in read_jsonl(skill_dir / "evidence.jsonl"):
        rows.append(row if isinstance(row, dict) else {"_decode_error": json.dumps(row, ensure_ascii=False)})
    return rows


def _skill_pending(evidence: list[dict[str, Any]]) -> tuple[dict[str, int], list[str]]:
    warnings: list[str] = []
    start = 0
    for i, row in enumerate(evidence):
        if row.get("_decode_error"):
            warnings.append("evidence decode error")
            continue
        if row.get("type") == "decision":
            start = i + 1

    counts: dict[str, int] = {}
    for row in evidence[start:]:
        evidence_type = row.get("type")
        if row.get("_decode_error"):
            continue
        if evidence_type in {"grounding", "check", "gap", "risk"}:
            counts[evidence_type] = counts.get(evidence_type, 0) + 1
        elif evidence_type:
            warnings.append(f"unknown evidence type: {evidence_type}")
    return counts, sorted(set(warnings))


def _skill_row(skill_path: Path) -> dict[str, Any]:
    skill_id = skill_path.parent.name
    warnings: list[str] = []
    try:
        text = skill_path.read_text(encoding="utf-8")
    except OSError as exc:
        text = ""
        warnings.append(f"read error: {exc}")
    meta = _parse_skill_frontmatter(text)
    name = _safe_inline(meta.get("name") or skill_id, 80) or skill_id
    description = _safe_inline(meta.get("description") or "", 220)
    state = _safe_inline(meta.get("state") or "candidate", 40).lower()
    if state not in SKILL_STATES:
        warnings.append(f"unknown state: {state}")
        state = "candidate"
    if not meta.get("description"):
        warnings.append("description missing")
    pending, evidence_warnings = _skill_pending(_skill_evidence_rows(skill_path.parent))
    warnings.extend(evidence_warnings)
    return {
        "skill_id": skill_id,
        "name": name,
        "description": description,
        "state": state,
        "path": str(skill_path),
        "evidence_path": str(skill_path.parent / "evidence.jsonl"),
        "pending": pending,
        "warnings": sorted(set(warnings)),
    }


def skill_rows(bus_dir: Path, include_retired: bool = False) -> list[dict[str, Any]]:
    root = paths(bus_dir)["skills"]
    if not root.is_dir():
        return []
    rows: list[dict[str, Any]] = []
    for skill_path in sorted(root.glob("*/SKILL.md")):
        try:
            _skill_id(skill_path.parent.name)
        except ValueError:
            continue
        row = _skill_row(skill_path)
        if row["state"] == "retired" and not include_retired:
            continue
        rows.append(row)
    order = {state: i for i, state in enumerate(("active", "candidate", "retired"))}
    return sorted(rows, key=lambda r: (order.get(r["state"], 99), r["name"].lower(), r["skill_id"]))


def _format_pending(pending: dict[str, int]) -> str:
    order = ["grounding", "check", "gap", "risk"]
    parts = [f"{key} {pending[key]}" for key in order if pending.get(key)]
    return ", ".join(parts)


def skill_prompt_summary(bus_dir: Path, limit: int = 12) -> str:
    rows = skill_rows(bus_dir)
    if not rows:
        return ""
    out = [
        "## Bus-local skill summary",
        "Metadata summaries for `.agent-bus/skills/<skill-id>/SKILL.md`. Open and apply a skill only after the current task calls for it.",
    ]
    for row in rows[:limit]:
        desc = f" description={row['description']!r}" if row.get("description") else ""
        pending = _format_pending(row.get("pending") or {})
        tail = f" (pending evidence: {pending})" if pending else ""
        out.append(f"- {row['skill_id']} state={row['state']}{desc}{tail}")
    if len(rows) > limit:
        out.append(f"- +{len(rows) - limit} more; run `agentbus skill list`.")
    out.append("Use `agentbus skill show <skill-id>` for the full text and `agentbus skill evidence <skill-id> ...` after a skill-guided work slice reveals reusable evidence.")
    return "\n".join(out) + "\n"


def create_skill(bus_dir: Path, skill_id: object, description: object, state: object = "candidate") -> str:
    ensure_bus(bus_dir)
    sid = _skill_id(skill_id)
    desc = _required_text(description, "description")
    skill_state = _choice(state, "state", SKILL_STATES)
    directory = _skill_dir(bus_dir, sid)
    path = directory / "SKILL.md"
    if path.exists():
        raise ValueError(f"skill already exists: {sid}")
    directory.mkdir(parents=True, exist_ok=False)
    path.write_text(_skill_template(sid, desc, skill_state), encoding="utf-8")
    _chmod_private(path)
    return sid


def set_skill_state(bus_dir: Path, skill_id: object, state: object) -> str:
    sid = _skill_id(skill_id)
    skill_state = _choice(state, "state", SKILL_STATES)
    path = _skill_path(bus_dir, sid)
    if not path.is_file():
        raise ValueError(f"skill not found: {sid}")
    text = path.read_text(encoding="utf-8")
    path.write_text(_set_frontmatter_value(text, "state", skill_state), encoding="utf-8")
    _chmod_private(path)
    return skill_state


def fold_tasks(bus_dir: Path) -> list[dict[str, Any]]:
    """Task stream은 append 전용 이벤트 로그다. 현재 상태는 이벤트를 접어 만든다.

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
        "position": event_id,
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
            if event["position"] == after or event["id"] == after:
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


def _legacy_bus_has_data(bus_dir: Path) -> bool:
    for file_name in list(CAPSULE_RECORD_FILES) + ["status.json", "stop.json"]:
        path = bus_dir / file_name
        if path.is_file() and path.read_text(encoding="utf-8", errors="ignore").strip():
            return True
    return False


def ensure_bus(bus_dir: Path, allow_existing_legacy: bool = False) -> None:
    """Create the secure capsule channel."""
    existed = bus_dir.exists()
    bus_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    if not existed:
        try:
            bus_dir.chmod(0o700)
        except OSError:
            pass
    channel_path = _capsule_channel_path(bus_dir)
    if not channel_path.exists():
        if _legacy_bus_has_data(bus_dir) and not allow_existing_legacy:
            raise ValueError(f"legacy JSONL bus found: run agentbus bus migrate --from {bus_dir} --bus-dir {bus_dir}")
        channel = {
            "schemaVersion": CAPSULE_VERSION,
            "id": uuid.uuid4().hex,
            "createdAt": now_iso(),
            "store": "store/capsule.sqlite",
            "endpoint": f"http://127.0.0.1:{DEFAULT_PORT}",
        }
        _write_json_file(channel_path, channel)
    _load_capsule_key(bus_dir, create=True)
    _capsule_connect(bus_dir).close()
    bridge_dir = bus_dir / "bridge"
    bridge_dir.mkdir(parents=True, exist_ok=True)
    _chmod_private_dir(bridge_dir)
    template_path = bridge_dir / BRIDGE_TEMPLATE_NAME
    if not template_path.exists():
        _write_json_file(template_path, BRIDGE_TEMPLATE)
    ps = paths(bus_dir)
    if not _capsule_doc_exists(ps["status"]):
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
    row = seal_record_content(bus_dir, "task", row)
    append_jsonl(paths(bus_dir)["tasks"], row)
    return tid


def set_task_state(bus_dir: Path, task_id: object, state: object, by: object, note: object = "") -> None:
    ensure_bus(bus_dir)
    tid = _required_text(task_id, "task_id")
    current = next((task for task in fold_tasks(bus_dir) if task.get("task_id") == tid), {})
    row = {
        "time": now_iso(),
        "event": "state",
        "task_id": tid,
        "state": _choice(state, "state", TASK_STATES),
        "by": _clean_text(by, "user"),
        "note": _clean_text(note),
    }
    row.update(security_fields(effective_sensitivity(current), effective_retention(current)))
    row = seal_record_content(bus_dir, "task", row)
    append_jsonl(paths(bus_dir)["tasks"], row)


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
    row = seal_record_content(bus_dir, "ticket", row)
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
        if effective_sensitivity(issue) == "restricted":
            issue = _unseal_record_content(bus_dir, issue)
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
        row = {
            "time": now_iso(),
            "event": "accepted",
            "issue_id": iid,
            "by": actor,
            "to": assignee,
            "note": note_text,
            "task_id": task_id,
            "message_id": msg["id"],
        }
        row.update(security_fields(sensitivity, retention))
        _append_jsonl_unlocked(issue_path, seal_record_content(bus_dir, "ticket", row))
    return {"task_id": task_id, "message_id": msg["id"]}


def reject_issue(bus_dir: Path, issue_id: object, by: object, note: object = "") -> None:
    ensure_bus(bus_dir)
    iid = _required_text(issue_id, "issue_id")
    issue_path = paths(bus_dir)["issues"]
    with file_lock(issue_path):
        issue = _open_issue_from_rows(read_jsonl(issue_path), iid)
        row = {
            "time": now_iso(),
            "event": "rejected",
            "issue_id": iid,
            "by": _clean_text(by, "user"),
            "note": _clean_text(note),
        }
        row.update(security_fields(effective_sensitivity(issue), effective_retention(issue)))
        _append_jsonl_unlocked(issue_path, seal_record_content(bus_dir, "ticket", row))


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


def migrate_bus(args: argparse.Namespace) -> int:
    src = Path(args.from_dir)
    dst = Path(args.bus_dir)
    if not src.is_dir():
        print(f"source bus not found: {src}", file=sys.stderr)
        return 1
    record_rows: dict[str, list[dict[str, Any]]] = {}
    for file_name, stream in CAPSULE_RECORD_FILES.items():
        rows = []
        for row in _read_jsonl_file(src / file_name):
            if isinstance(row, dict) and not row.get("_decode_error"):
                rows.append(_legacy_unseal_record_content(src, row))
        record_rows[stream] = rows
    status = _read_json_file(src / "status.json", {"created_at": now_iso(), "agents": {}})
    stop = _read_json_file(src / "stop.json", None)
    auth = _read_json_file(src / "security" / "auth.json", {"schemaVersion": "agentbus.auth.v1", "agents": {}, "viewers": {}})
    ensure_bus(dst, allow_existing_legacy=True)
    ps = paths(dst)
    for stream, rows in record_rows.items():
        _capsule_clear_stream(dst, stream)
        for row in rows:
            _capsule_append_record(dst, stream, row)
    write_json(ps["status"], status if isinstance(status, dict) else {"created_at": now_iso(), "agents": {}})
    if isinstance(auth, dict):
        write_json(ps["auth"], auth)
    if stop is not None:
        write_json(ps["stop"], stop)
    elif path_exists(ps["stop"]):
        delete_path(ps["stop"])
    if src.resolve() == dst.resolve():
        for file_name in CAPSULE_RECORD_FILES:
            (dst / file_name).unlink(missing_ok=True)
        for file_name in ("status.json", "stop.json"):
            (dst / file_name).unlink(missing_ok=True)
        for dirname in ("security", "sealed"):
            root = dst / dirname
            if root.is_dir():
                for item in sorted(root.rglob("*"), reverse=True):
                    if item.is_file():
                        item.unlink(missing_ok=True)
                    elif item.is_dir():
                        item.rmdir()
                root.rmdir()
    print(dst)
    return 0


def _export_rows(rows: list[dict[str, Any]], redacted: bool) -> list[dict[str, Any]]:
    if not redacted:
        raise ValueError("raw export requires an admin raw-export flow")
    out: list[dict[str, Any]] = []
    for row in rows:
        redacted_row = redact_record(row, "external")
        kind = _record_kind(redacted_row)
        for field in _record_content_fields(kind, redacted_row):
            if field in redacted_row:
                redacted_row[field] = _redacted_value(redacted_row.get(field))
        if kind:
            redacted_row["redacted"] = True
            redacted_row["redactedFields"] = sorted(set(redacted_row.get("redactedFields") or []) | set(_record_content_fields(kind, redacted_row)))
            redacted_row["redactionScope"] = "export"
        out.append(redacted_row)
    return out


def export_bus(args: argparse.Namespace) -> int:
    ensure_bus(args.bus_dir)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    ps = paths(args.bus_dir)
    for file_name, stream in CAPSULE_RECORD_FILES.items():
        rows = _export_rows(read_jsonl(ps[file_name.removesuffix(".jsonl")]), args.redacted)
        target = out / file_name
        target.write_text(
            "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
            encoding="utf-8",
        )
        _chmod_private(target)
    _write_json_file(out / "status.json", load_json(ps["status"], {"created_at": now_iso(), "agents": {}}))
    if path_exists(ps["stop"]):
        _write_json_file(out / "stop.json", load_json(ps["stop"], None))
    print(out)
    return 0


def show_status(args: argparse.Namespace) -> int:
    ensure_bus(args.bus_dir)
    ps = paths(args.bus_dir)
    status = load_json(ps["status"], {"agents": {}})
    stop_path = ps["stop"]
    stop_record = load_json(stop_path, {}) if _capsule_doc_exists(stop_path) else None
    if getattr(args, "stop_exit_code", False):
        if stop_record:
            print(json.dumps(stop_record, ensure_ascii=False, indent=2, sort_keys=True))
            return 2
        print("no stop")
        return 0
    payload = dict(status) if isinstance(status, dict) else {"agents": {}}
    payload["stop"] = stop_record
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def agent_list(args: argparse.Namespace) -> int:
    ensure_bus(args.bus_dir)
    agents = load_json(paths(args.bus_dir)["status"], {"agents": {}}).get("agents", {})
    if args.json:
        print(json.dumps({"agents": agents}, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    if not agents:
        print("no agents")
        return 0
    for name, row in sorted(agents.items()):
        bits = [name, str(row.get("state") or "-")]
        if row.get("task"):
            bits.append(f"task={row['task']}")
        if row.get("note"):
            bits.append(str(row["note"]))
        print("	".join(bits))
    return 0


def agent_delete(args: argparse.Namespace) -> int:
    try:
        delete_agent_status(args.bus_dir, args.agent)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print("deleted", args.agent)
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
    rows = [record_for_agent(args.bus_dir, row, args.agent) for row in pending_messages(args.bus_dir, args.agent, set())]
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
    """Print unacked messages."""
    ensure_bus(args.bus_dir)
    kinds = {k.strip() for k in args.kinds.split(",") if k.strip()}
    exit_code = 0
    while True:
        if _capsule_doc_exists(paths(args.bus_dir)["stop"]):
            print("stop present")
            return 2
        rows = pending_messages(args.bus_dir, args.agent, kinds)
        if rows:
            rows = [record_for_agent(args.bus_dir, row, args.agent) for row in rows[-args.limit:]]
            if args.json:
                print(json.dumps({"agent": args.agent, "pending": rows}, ensure_ascii=False))
            else:
                print(format_message_digest(rows, args.max_body_chars))
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
        "reason": "restricted payload redacted",
        "sensitive": sensitive_summary(event),
    }


def _print_json(value: dict[str, Any]) -> None:
    print(json.dumps(value, ensure_ascii=False, sort_keys=True), flush=True)


def _print_event(event: dict[str, Any]) -> None:
    _print_json(event)


def _read_position(path: Path | None) -> str:
    if not path or not path.exists():
        return ""
    return path.read_text(encoding="utf-8").strip()


def _write_position(path: Path | None, position: str) -> None:
    if not path:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with file_lock(path):
        path.write_text(position + "\n", encoding="utf-8")
        _chmod_private(path)


def _append_event_failure(
    path: Path | None,
    event: dict[str, Any],
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
        "returncode": returncode,
    }
    if include_event:
        row["event"] = event
    if error:
        row["error"] = error
    append_jsonl(path, row)


def events(args: argparse.Namespace) -> int:
    rows = [
        _sensitive_event_notice(event) if payload_is_sensitive(event) else external_event(event)
        for event in bus_events(
        args.bus_dir,
        types=parse_event_types(args.types),
        targets=parse_event_targets(args.target),
        after=args.after,
        limit=max(0, args.limit),
        )
    ]
    if args.jsonl:
        for event in rows:
            _print_event(event)
    else:
        print(json.dumps({"version": EVENT_VERSION, "events": rows}, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def watch_events(args: argparse.Namespace) -> int:
    types = parse_event_types(args.types)
    targets = parse_event_targets(args.target)
    position_file = args.position_file
    position = _read_position(position_file)
    seen = set()
    if args.from_start:
        position = ""
    elif position_file:
        if not position:
            existing = bus_events(args.bus_dir, types=types, targets=targets)
            if existing:
                position = existing[-1]["position"]
                if not args.dry_run:
                    _write_position(position_file, position)
    else:
        seen = {event["id"] for event in bus_events(args.bus_dir, types=types, targets=targets)}
    exit_code = 0
    while True:
        for event in bus_events(args.bus_dir, types=types, targets=targets, after=position):
            if not position_file and event["id"] in seen:
                continue
            _print_event(_sensitive_event_notice(event) if payload_is_sensitive(event) else external_event(event))
            if not args.dry_run:
                position = event["position"]
                _write_position(position_file, position)
            seen.add(event["id"])
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


def _profile_dict(profile: dict[str, Any], key: str) -> dict[str, Any]:
    value = profile.get(key)
    if value in (None, ""):
        return {}
    if not isinstance(value, dict):
        raise ValueError(f"{key} must be an object")
    return value


def _profile_args(value: Any, key: str = "args") -> list[str]:
    if value in (None, ""):
        return []
    if not isinstance(value, list):
        raise ValueError(f"{key} must be a list")
    out: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item:
            raise ValueError(f"{key} must contain non-empty strings")
        out.append(item)
    return out


def _safe_profile_name(value: object) -> str:
    text = _clean_text(value, "bridge")
    safe = "".join(c if c.isalnum() or c in "._-" else "_" for c in text)
    return safe.strip("._-") or "bridge"


def _profile_state_path(profile: dict[str, Any], bus_dir: Path, key: str, suffix: str) -> Path:
    value = _clean_text(profile.get(key))
    if value:
        path = Path(value).expanduser()
        return path if path.is_absolute() else bus_dir / path
    return bus_dir / "bridge" / f"{_safe_profile_name(profile.get('name'))}.{suffix}"


def _bridge_profile_events(profile: dict[str, Any]) -> list[str]:
    return _profile_list(profile, "event")


def _bridge_envs(profile: dict[str, Any]) -> list[str]:
    return _profile_list(profile, "envs")


def _validate_matcher(matcher: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    allowed = {"target", "kind", "actor", "objectType", "objectId"}
    for key, value in matcher.items():
        if key not in allowed:
            errors.append(f"matcher.{key} is not supported")
            continue
        try:
            values = _profile_list(matcher, key)
        except ValueError as exc:
            errors.append(str(exc))
            continue
        if key == "target":
            if not isinstance(value, str):
                errors.append("matcher.target must be a single agent id string")
            elif len(values) != 1:
                errors.append("matcher.target must contain one agent id")
            elif values[0] in {"all", "*"}:
                errors.append("matcher.target must be a concrete agent id")
    return errors


def _handler_type(handler: dict[str, Any]) -> str:
    return _clean_text(handler.get("type"))


def validate_bridge_profile(profile: Any, check_env: bool = True) -> list[str]:
    errors: list[str] = []
    envs: list[str] = []
    if not isinstance(profile, dict):
        return ["profile must be a JSON object"]
    if profile.get("schemaVersion") != BRIDGE_PROFILE_VERSION:
        errors.append(f"schemaVersion must be {BRIDGE_PROFILE_VERSION}")
    if not _clean_text(profile.get("name")):
        errors.append("name required")
    allowed_profile_fields = {
        "schemaVersion",
        "name",
        "event",
        "matcher",
        "handler",
        "envs",
        "intervalSeconds",
        "maxSeconds",
        "timeoutSeconds",
        "fromStart",
        "markDelivered",
        "positionFile",
        "failLog",
    }
    unknown = sorted(str(key) for key in profile if key not in allowed_profile_fields)
    if unknown:
        errors.append("unsupported bridge profile fields: " + ", ".join(unknown))
    try:
        events = _bridge_profile_events(profile)
        if not events:
            errors.append("event required")
        for event in events:
            if not BRIDGE_EVENT_RE.match(event):
                errors.append(f"invalid event: {event}")
        matcher = _profile_dict(profile, "matcher")
        errors.extend(_validate_matcher(matcher))
        envs = _bridge_envs(profile)
        for name in envs:
            if not BRIDGE_ENV_RE.match(name):
                errors.append(f"invalid env name: {name}")
        _profile_float(profile, "intervalSeconds", 1.0)
        _profile_float(profile, "maxSeconds", 0.0)
        _profile_float(profile, "timeoutSeconds", 60.0)
        _profile_bool(profile, "fromStart", False)
        _profile_bool(profile, "markDelivered", False)
        if "positionFile" in profile and profile.get("positionFile") not in (None, "") and not isinstance(profile.get("positionFile"), str):
            errors.append("positionFile must be a string")
        if "failLog" in profile and profile.get("failLog") not in (None, "") and not isinstance(profile.get("failLog"), str):
            errors.append("failLog must be a string")
        handler = _profile_dict(profile, "handler")
        handler_type = _handler_type(handler)
        if handler_type not in BRIDGE_HANDLER_TYPES:
            errors.append("handler.type must be monitor, agent, http, or openai-compatible")
        if handler_type == "agent":
            provider = _clean_text(handler.get("provider"))
            if provider not in BRIDGE_AGENT_PROVIDERS:
                errors.append("handler.provider must be codex, claude, or gemini")
            _profile_args(handler.get("args"), "handler.args")
            if provider in {"claude", "gemini"}:
                args = _profile_args(handler.get("args"), "handler.args")
                if "-p" in args or "--prompt" in args:
                    errors.append("handler.args must not set -p/--prompt; agent-bus supplies the prompt")
        elif handler_type == "http":
            protocol = _clean_text(handler.get("protocol"), "http")
            if protocol not in {"http", "a2a"}:
                errors.append("handler.protocol must be http or a2a")
            if not _clean_text(handler.get("url")):
                errors.append("handler.url required")
        elif handler_type == "openai-compatible":
            for key in ("endpoint", "model", "apiKey"):
                if not _clean_text(handler.get(key)):
                    errors.append(f"handler.{key} required")
    except ValueError as exc:
        errors.append(str(exc))
    if check_env:
        for name in envs:
            if not os.environ.get(name):
                errors.append(f"env not set: {name}")
    return errors


def load_bridge_profile(path: Path, check_env: bool = True) -> dict[str, Any]:
    try:
        profile = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(str(exc)) from exc
    errors = validate_bridge_profile(profile, check_env=check_env)
    if errors:
        raise ValueError("; ".join(errors))
    return profile


def _append_bridge_failure(
    path: Path | None,
    profile: dict[str, Any],
    event: dict[str, Any],
    handler: str,
    returncode: int,
    error: str = "",
    include_event: bool = True,
) -> None:
    if not path:
        return
    row: dict[str, Any] = {
        "time": now_iso(),
        "profile": profile.get("name"),
        "event_id": event.get("id"),
        "event_type": event.get("type"),
        "object": event.get("object"),
        "handler": handler,
        "returncode": returncode,
    }
    if include_event:
        row["event"] = event
    if error:
        row["error"] = error
    append_jsonl(path, row)


def _bridge_matcher_values(matcher: dict[str, Any], key: str) -> set[str]:
    return set(_profile_list(matcher, key))


def _match_value(value: Any, patterns: set[str]) -> bool:
    if not patterns:
        return True
    values = value if isinstance(value, list) else [value]
    cleaned = {str(v) for v in values if str(v)}
    return bool(cleaned & patterns) or bool(cleaned & {"all", "*"})


def _match_bridge_event(event: dict[str, Any], profile: dict[str, Any]) -> bool:
    events = set(_bridge_profile_events(profile))
    if not _match_event_type(str(event.get("type") or ""), events):
        return False
    matcher = _profile_dict(profile, "matcher")
    if not _match_value(event.get("target"), _bridge_matcher_values(matcher, "target")):
        return False
    if not _match_value((event.get("data") or {}).get("kind"), _bridge_matcher_values(matcher, "kind")):
        return False
    if not _match_value(event.get("actor"), _bridge_matcher_values(matcher, "actor")):
        return False
    obj = event.get("object") or {}
    if not _match_value(obj.get("type"), _bridge_matcher_values(matcher, "objectType")):
        return False
    if not _match_value(obj.get("id"), _bridge_matcher_values(matcher, "objectId")):
        return False
    return True


def _resolve_profile_value(value: Any) -> str:
    if value is None:
        return ""
    text = str(value)
    if text.startswith("$") and BRIDGE_ENV_RE.match(text[1:]):
        return os.environ.get(text[1:], "")
    return text


def _required_resolved_text(value: Any, name: str) -> str:
    text = _resolve_profile_value(value).strip()
    if not text:
        raise ValueError(f"{name} required")
    return text


def _bridge_handler_label(handler: dict[str, Any]) -> str:
    handler_type = _handler_type(handler)
    if handler_type == "agent":
        return _clean_text(handler.get("provider"), "agent")
    if handler_type == "http":
        return _clean_text(handler.get("protocol"), "http")
    return handler_type


def _bridge_target_agent(profile: dict[str, Any], fallback: str = "") -> str:
    matcher = _profile_dict(profile, "matcher")
    targets = _profile_list(matcher, "target")
    return targets[0] if targets else fallback


BRIDGE_AGENT_PROMPT = """You are an agent-bus runtime receiving one agent-runner-work.v1 JSON packet on stdin.
Read the packet, do the requested work, and write a concise report to stdout.
Use referenced files when needed. Respect sensitivity and retention fields. Include result, judgment, risk, and next action only when they matter."""


def _bridge_work_packet(profile: dict[str, Any], event: dict[str, Any], provider: str, agent: str) -> dict[str, Any]:
    message = event.get("data") if isinstance(event.get("data"), dict) else {}
    return {
        "schemaVersion": "agent-runner-work.v1",
        "agent": agent,
        "provider": provider,
        "messageId": message.get("id", ""),
        "taskId": message.get("task_id", ""),
        "subject": message.get("subject", ""),
        "body": message.get("body", ""),
        "refs": message.get("refs") or [],
        "message": message,
        "event": {k: event.get(k) for k in ("id", "time", "type", "source", "actor", "target", "object")},
        "source": {"schemaVersion": BRIDGE_PROFILE_VERSION, "profile": profile.get("name", "")},
    }


def _bridge_agent_prompt(work: dict[str, Any]) -> str:
    header = []
    if work.get("subject"):
        header.append(f"Subject: {work['subject']}")
    if work.get("taskId"):
        header.append(f"Task: {work['taskId']}")
    if work.get("messageId"):
        header.append(f"Message: {work['messageId']}")
    return BRIDGE_AGENT_PROMPT + ("\n\n" + "\n".join(header) if header else "")


def _bridge_agent_cmd(provider: str, args: list[str], prompt: str) -> list[str]:
    if provider == "codex":
        return ["codex", "exec", *args, prompt]
    if provider == "claude":
        return ["claude", *args, "-p", prompt]
    if provider == "gemini":
        return ["gemini", *args, "-p", prompt]
    raise ValueError("unsupported agent provider")


def _ack_message_for_bridge(bus_dir: Path, agent: str, message_id: str) -> None:
    if not message_id:
        return
    acks_path = paths(bus_dir)["acks"]
    with file_lock(acks_path):
        seen = {row.get("id", "") for row in read_jsonl(acks_path) if row.get("agent") == agent}
        if message_id not in seen:
            _append_jsonl_unlocked(acks_path, {"time": now_iso(), "agent": agent, "id": message_id})


def _write_delivered_for_bridge(bus_dir: Path, agent: str, message: dict[str, Any], profile_name: str) -> None:
    mid = message.get("id")
    if not mid or mid in delivered_ids(bus_dir, agent):
        return
    append_jsonl(paths(bus_dir)["delivered"], {
        "time": now_iso(),
        "agent": agent,
        "id": mid,
        "kind": message.get("kind"),
        "subject": message.get("subject"),
        "by": "bridge",
        "profile": profile_name,
    })


def _run_bridge_agent(args: argparse.Namespace, profile: dict[str, Any], event: dict[str, Any], handler: dict[str, Any]) -> int:
    if (event.get("object") or {}).get("type") != "message":
        raise ValueError("agent handler requires a message event")
    provider = _clean_text(handler.get("provider"))
    agent = _bridge_target_agent(profile, provider)
    handler_args = _profile_args(handler.get("args"), "handler.args")
    timeout = _profile_float(profile, "timeoutSeconds", 0.0)
    projected_event = event_for_agent(args.bus_dir, event, agent)
    work = _bridge_work_packet(profile, projected_event, provider, agent)
    message = work.get("message") or {}
    task_id = _clean_text(work.get("taskId"))
    message_id = _clean_text(work.get("messageId"))
    if task_id:
        set_task_state(args.bus_dir, task_id, "working", agent, f"runner started from {message_id}")
    cmd = _bridge_agent_cmd(provider, handler_args, _bridge_agent_prompt(work))
    try:
        proc = subprocess.run(
            cmd,
            input=json.dumps(work, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            text=True,
            capture_output=True,
            timeout=timeout if timeout > 0 else None,
            check=False,
        )
    except FileNotFoundError:
        if task_id:
            set_task_state(args.bus_dir, task_id, "failed", agent, "runner not found")
        print(f"{provider} CLI not found", file=sys.stderr)
        return 127
    except subprocess.TimeoutExpired:
        if task_id:
            set_task_state(args.bus_dir, task_id, "failed", agent, "runner timeout")
        print(f"{provider} runner timed out", file=sys.stderr)
        return 124
    if proc.stderr:
        print(proc.stderr, file=sys.stderr, end="")
    body = proc.stdout.strip() or proc.stderr.strip() or "completed"
    if proc.returncode:
        if task_id:
            set_task_state(args.bus_dir, task_id, "failed", agent, f"runner exit {proc.returncode}")
        return proc.returncode
    to = _clean_text(message.get("from"))
    if to:
        report = make_message(
            agent,
            to,
            "report",
            f"Result: {message.get('subject', '')}".strip(),
            body,
            [],
            task_id,
            message_id,
            message.get("sensitivity", ""),
            message.get("retention", ""),
        )
        append_message(args.bus_dir, report)
    if task_id:
        set_task_state(args.bus_dir, task_id, "completed", agent, f"runner completed from {message_id}")
    _ack_message_for_bridge(args.bus_dir, agent, message_id)
    if _profile_bool(profile, "markDelivered", True):
        _write_delivered_for_bridge(args.bus_dir, agent, message, str(profile.get("name") or ""))
    return 0


def _a2a_send_event(args: argparse.Namespace, profile: dict[str, Any], event: dict[str, Any], handler: dict[str, Any]) -> int:
    if (event.get("object") or {}).get("type") != "message":
        return 0
    from . import a2a

    endpoint = _required_resolved_text(handler.get("url"), "handler.url")
    message = event.get("data") if isinstance(event.get("data"), dict) else {}
    request_body = a2a.send_message_request(
        message,
        _clean_text(handler.get("requestId")) or "",
        _clean_text(handler.get("role"), "user"),
        _clean_text(handler.get("contextId")),
        _clean_text(handler.get("tenant")),
        [],
        None,
        True,
    )
    token_env = _clean_text(handler.get("tokenEnv"))
    token = a2a.read_token(token_env) if token_env else ""
    result = a2a.post_rpc(request_body, endpoint, token, {}, _profile_float(profile, "timeoutSeconds", 60.0))
    if handler.get("recordResponseTo"):
        a2a.record_rpc_result(args.bus_dir, request_body, result, _resolve_profile_value(handler.get("recordResponseTo")), _clean_text(handler.get("responseFrom"), "a2a"))
    if not result.get("ok"):
        return 1
    return 0


def _http_send_event(profile: dict[str, Any], event: dict[str, Any], handler: dict[str, Any]) -> int:
    url = _required_resolved_text(handler.get("url"), "handler.url")
    body = json.dumps(event, ensure_ascii=False, sort_keys=True).encode("utf-8")
    req = urllib.request.Request(url, data=body, method=_clean_text(handler.get("method"), "POST").upper())
    req.add_header("Content-Type", "application/json")
    timeout = _profile_float(profile, "timeoutSeconds", 60.0)
    try:
        with urllib.request.urlopen(req, timeout=timeout if timeout > 0 else None) as res:
            return 0 if 200 <= getattr(res, "status", 200) < 300 else 1
    except (OSError, urllib.error.URLError):
        return 1


def _openai_compatible_send(args: argparse.Namespace, profile: dict[str, Any], event: dict[str, Any], handler: dict[str, Any]) -> int:
    endpoint = _required_resolved_text(handler.get("endpoint"), "handler.endpoint")
    model = _required_resolved_text(handler.get("model"), "handler.model")
    api_key = _required_resolved_text(handler.get("apiKey"), "handler.apiKey")
    system = _resolve_profile_value(handler.get("system") or "Inspect local coordination payloads and return concise assessment, next action, or decision support.")
    instruction = _resolve_profile_value(handler.get("instruction") or "Read this JSON payload. Preserve important evidence, disagreements, evidence gaps, and decisions needed.")
    request_body = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": instruction + "\n\n" + json.dumps(event, ensure_ascii=False, sort_keys=True)},
        ],
    }
    data = json.dumps(request_body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(endpoint, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Authorization", "Bearer " + api_key)
    timeout = _profile_float(profile, "timeoutSeconds", 60.0)
    try:
        with urllib.request.urlopen(req, timeout=timeout if timeout > 0 else None) as res:
            raw = res.read().decode("utf-8", "replace")
            status = getattr(res, "status", 200)
    except (OSError, urllib.error.URLError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    if not (200 <= status < 300):
        print(raw, file=sys.stderr)
        return 1
    text = raw
    try:
        parsed = json.loads(raw)
        choices = parsed.get("choices") if isinstance(parsed, dict) else None
        if choices and isinstance(choices[0], dict):
            msg = choices[0].get("message") or {}
            text = str(msg.get("content") or choices[0].get("text") or raw).strip()
    except json.JSONDecodeError:
        pass
    response_to = _resolve_profile_value(handler.get("responseTo"))
    if response_to:
        msg = make_message(
            _clean_text(handler.get("responseFrom"), "openai-compatible"),
            response_to,
            "report",
            f"Bridge response: {event.get('type', '')}".strip(),
            text or raw,
            [],
            "",
            "",
        )
        append_message(args.bus_dir, msg)
    else:
        print(text or raw)
    return 0


def _run_bridge_handler(args: argparse.Namespace, profile: dict[str, Any], event: dict[str, Any]) -> int:
    handler = _profile_dict(profile, "handler")
    handler_type = _handler_type(handler)
    if handler_type == "monitor":
        return 0
    if handler_type == "agent":
        return _run_bridge_agent(args, profile, event, handler)
    if handler_type == "http":
        protocol = _clean_text(handler.get("protocol"), "http")
        if protocol == "a2a":
            return _a2a_send_event(args, profile, event, handler)
        return _http_send_event(profile, event, handler)
    if handler_type == "openai-compatible":
        return _openai_compatible_send(args, profile, event, handler)
    raise ValueError("unsupported handler")


def _bridge_run_events(args: argparse.Namespace, profile: dict[str, Any]) -> int:
    ensure_bus(args.bus_dir)
    events_filter = set(_bridge_profile_events(profile))
    interval = _profile_float(profile, "intervalSeconds", 1.0)
    max_seconds = _profile_float(profile, "maxSeconds", 0.0)
    position_file = _profile_state_path(profile, args.bus_dir, "positionFile", "position")
    fail_log = _profile_state_path(profile, args.bus_dir, "failLog", "failures.jsonl")
    position = _read_position(position_file)
    if _profile_bool(profile, "fromStart", False):
        position = ""
    elif not position:
        existing = [e for e in bus_events(args.bus_dir, types=events_filter) if _match_bridge_event(e, profile)]
        if existing:
            position = existing[-1]["position"]
            if not args.dry_run:
                _write_position(position_file, position)
    deadline = time.time() + max_seconds if max_seconds > 0 else 0.0
    exit_code = 0
    handler = _profile_dict(profile, "handler")
    handler_label = _bridge_handler_label(handler)
    handler_type = _handler_type(handler)
    while True:
        for event in bus_events(args.bus_dir, types=events_filter, after=position):
            if not _match_bridge_event(event, profile):
                continue
            restricted_event = payload_is_sensitive(event)
            if restricted_event and handler_type not in {"agent", "monitor"}:
                _print_event(_sensitive_event_notice(event))
                if args.dry_run:
                    position = event["position"]
                    continue
                rc = 2
                error = "restricted event blocked for external bridge handler"
                _append_bridge_failure(fail_log, profile, event, handler_label, rc, error, include_event=False)
                if exit_code == 0:
                    exit_code = rc
                position = event["position"]
                _write_position(position_file, position)
                if args.once:
                    return exit_code
                continue
            if handler_type == "agent":
                agent = _bridge_target_agent(profile, _clean_text(handler.get("provider"), "agent"))
                handler_event = event
                display_event = event_for_agent(args.bus_dir, event, agent)
            else:
                handler_event = _sensitive_event_notice(event) if restricted_event else external_event(event)
                display_event = handler_event
            _print_event(display_event)
            if args.dry_run:
                position = event["position"]
                continue
            rc = _run_bridge_handler(args, profile, handler_event)
            if rc:
                if exit_code == 0:
                    exit_code = rc
                error = "bridge handler failed"
                _append_bridge_failure(fail_log, profile, display_event, handler_label, rc, error)
                if args.once:
                    return exit_code
                break
            position = event["position"]
            _write_position(position_file, position)
        if args.once or (deadline and time.time() >= deadline):
            return exit_code
        time.sleep(interval)


def bridge_check(args: argparse.Namespace) -> int:
    try:
        load_bridge_profile(args.file)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print("bridge-profile-ok")
    return 0


def bridge_run(args: argparse.Namespace) -> int:
    try:
        profile = load_bridge_profile(args.profile)
        return _bridge_run_events(args, profile)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1

def _bridge_failure_summary(row: dict[str, Any]) -> dict[str, Any]:
    out = {
        "time": row.get("time", ""),
        "returncode": row.get("returncode", ""),
        "error": row.get("error", ""),
    }
    for key in ("event_id", "event_type", "profile", "handler", "object", "endpoint", "status"):
        if key in row:
            out[key] = row.get(key)
    return {key: value for key, value in out.items() if value not in (None, "", [], {})}


def bridge_status_rows(bus_dir: Path) -> list[dict[str, Any]]:
    bridge_dir = bus_dir / "bridge"
    names: set[str] = set()
    if bridge_dir.exists():
        for path in bridge_dir.iterdir():
            if path.name.endswith(".position"):
                names.add(path.name[:-9])
            elif path.name.endswith(".failures.jsonl"):
                names.add(path.name[:-15])
    rows = []
    for name in sorted(names):
        position_path = bridge_dir / f"{name}.position"
        failure_path = bridge_dir / f"{name}.failures.jsonl"
        failures = read_jsonl(failure_path)
        row: dict[str, Any] = {
            "name": name,
            "position": _read_position(position_path),
            "positionFile": str(position_path),
            "failureLog": str(failure_path),
            "failureCount": len(failures),
        }
        if position_path.exists():
            row["positionUpdatedAt"] = datetime.fromtimestamp(position_path.stat().st_mtime, timezone.utc).isoformat().replace("+00:00", "Z")
        if failures:
            row["lastFailure"] = _bridge_failure_summary(failures[-1])
            if failure_path.exists():
                row["failureLogUpdatedAt"] = datetime.fromtimestamp(failure_path.stat().st_mtime, timezone.utc).isoformat().replace("+00:00", "Z")
        rows.append(row)
    return rows


def _bridge_profile_list(profile: dict[str, Any], key: str) -> list[str]:
    try:
        return _profile_list(profile, key)
    except ValueError:
        return []


def _bridge_profile_dict(profile: dict[str, Any], key: str) -> dict[str, Any]:
    try:
        return _profile_dict(profile, key)
    except ValueError:
        return {}


def _bridge_matcher_summary(matcher: dict[str, Any]) -> str:
    parts: list[str] = []
    for key in ("target", "kind", "actor", "objectType", "objectId"):
        values = _bridge_profile_list(matcher, key)
        if values:
            parts.append(", ".join(values))
    return " · ".join(parts)


def _bridge_profile_row(path: Path, source: str) -> dict[str, Any]:
    profile: Any
    try:
        profile = json.loads(path.read_text(encoding="utf-8"))
    except OSError:
        return {
            "name": path.stem,
            "source": source,
            "state": "invalid",
            "warnings": ["profile cannot be read"],
        }
    except json.JSONDecodeError:
        return {
            "name": path.stem,
            "source": source,
            "state": "invalid",
            "warnings": ["profile json is invalid"],
        }
    errors = validate_bridge_profile(profile, check_env=False)
    if not isinstance(profile, dict):
        return {
            "name": path.stem,
            "source": source,
            "state": "invalid",
            "warnings": errors,
        }
    envs = _bridge_profile_list(profile, "envs")
    missing_env = [name for name in envs if not os.environ.get(name)]
    handler = _bridge_profile_dict(profile, "handler")
    handler_type = _handler_type(handler)
    protocol = _clean_text(handler.get("protocol"))
    provider = _clean_text(handler.get("provider"))
    matcher = _bridge_profile_dict(profile, "matcher")
    row: dict[str, Any] = {
        "name": _clean_text(profile.get("name")) or path.stem,
        "source": source,
        "event": ", ".join(_bridge_profile_list(profile, "event")),
        "matcher": _bridge_matcher_summary(matcher),
        "matcherTargets": _bridge_profile_list(matcher, "target"),
        "matcherKinds": _bridge_profile_list(matcher, "kind"),
        "matcherActors": _bridge_profile_list(matcher, "actor"),
        "matcherObjectTypes": _bridge_profile_list(matcher, "objectType"),
        "matcherObjectIds": _bridge_profile_list(matcher, "objectId"),
        "handler": _bridge_handler_label(handler) if handler else "",
        "handlerType": handler_type,
        "provider": provider,
        "protocol": protocol,
        "state": "invalid" if errors else ("needs_config" if missing_env else "ready"),
        "hasExecution": handler_type in {"agent", "http", "openai-compatible"},
        "envCount": len(envs),
        "warnings": errors,
    }
    return row


def bridge_profile_rows(bus_dir: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    local = bus_dir / "bridge"
    if local.is_dir():
        for path in sorted(local.glob("*.json")):
            if path.name.endswith(".template.json"):
                continue
            rows.append(_bridge_profile_row(path, "local"))
    return sorted(rows, key=lambda row: str(row.get("name") or ""))


def bridge_dashboard_status_rows(bus_dir: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in bridge_status_rows(bus_dir):
        last = row.get("lastFailure") if isinstance(row.get("lastFailure"), dict) else {}
        clean_last = {
            key: last.get(key)
            for key in ("time", "returncode", "event_type", "profile", "handler", "status")
            if last.get(key) not in (None, "", [], {})
        }
        clean: dict[str, Any] = {
            "name": row.get("name", ""),
            "hasPosition": bool(row.get("position")),
            "failureCount": row.get("failureCount", 0),
        }
        for key in ("positionUpdatedAt", "failureLogUpdatedAt"):
            if row.get(key):
                clean[key] = row.get(key)
        if clean_last:
            clean["lastFailure"] = clean_last
        rows.append(clean)
    return rows


def bridge_gateway_rows(port: int = 0) -> list[dict[str, Any]]:
    base = f"http://127.0.0.1:{port}" if port else "http://127.0.0.1"
    return [
        {
            "name": "Agent-Bus API",
            "protocol": "http",
            "endpoint": base + "/api/state",
            "state": "ready",
            "access": "local only",
        },
        {
            "name": "Agent-Bus messages",
            "protocol": "http",
            "endpoint": base + "/api/send",
            "state": "ready",
            "access": "local origin",
        },
        {
            "name": "A2A inbound",
            "protocol": "a2a",
            "endpoint": base + "/a2a/rpc",
            "state": "ready",
            "access": "local only",
        },
    ]

def bridge_status(args: argparse.Namespace) -> int:
    rows = bridge_status_rows(args.bus_dir)
    if args.json:
        print(json.dumps({"bridges": rows}, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    if not rows:
        print("no bridges")
        return 0
    for row in rows:
        parts = [
            row["name"],
            f"position={row.get('position') or '-'}",
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


def task_report_rows(bus_dir: Path, task_id: str = "", max_body_chars: int = 240, raw_restricted: bool = False) -> list[dict[str, Any]]:
    tasks = [record_for_dashboard(bus_dir, row, raw_restricted) for row in fold_tasks(bus_dir)]
    task_map = {str(t.get("task_id") or ""): t for t in tasks if t.get("task_id")}
    messages = [record_for_dashboard(bus_dir, row, raw_restricted) for row in live_messages(bus_dir)]
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
    bridge = bus_dir / "bridge"
    if bridge.is_dir():
        candidates.extend(path for path in bridge.rglob("*.jsonl") if path.is_file())
    for root_key in ("security", "sealed"):
        root = ps[root_key]
        if root.exists():
            candidates.extend(path for path in root.rglob("*") if path.is_file())
    out: list[Path] = []
    for path in sorted(set(candidates), key=lambda p: str(p)):
        try:
            mode = path.stat().st_mode & 0o777
        except OSError:
            continue
        if mode & 0o077:
            out.append(path)
    return out


SECRET_PATTERN = re.compile(
    r"(?i)(api[_-]?key|secret|token|password|bearer)\s*[:=]\s*['\"]?[A-Za-z0-9._~+/=-]{12,}"
)


def _security_scan_rows(bus_dir: Path) -> list[tuple[str, dict[str, Any]]]:
    ps = paths(bus_dir)
    rows: list[tuple[str, dict[str, Any]]] = []
    rows.extend(("message", row) for row in read_jsonl(ps["messages"]) if isinstance(row, dict))
    rows.extend(("task", row) for row in read_jsonl(ps["tasks"]) if isinstance(row, dict))
    rows.extend(("ticket", row) for row in read_jsonl(ps["issues"]) if isinstance(row, dict))
    return rows


def _restricted_missing_sealed(bus_dir: Path, rows: list[tuple[str, dict[str, Any]]]) -> list[str]:
    out: list[str] = []
    for kind, row in rows:
        if effective_sensitivity(row) != "restricted":
            continue
        try:
            record_id = _record_id(kind, row)
        except ValueError:
            continue
        if not row.get("sealed") or not _sealed_path(bus_dir, kind, record_id).exists():
            out.append(f"{kind}:{record_id}")
    return out


def _restricted_raw_residue(rows: list[tuple[str, dict[str, Any]]]) -> list[str]:
    out: list[str] = []
    for kind, row in rows:
        if effective_sensitivity(row) == "restricted" and _has_raw_content(kind, row):
            try:
                out.append(f"{kind}:{_record_id(kind, row)}")
            except ValueError:
                out.append(kind)
    return out


def _content_strings(kind: str, row: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for field in _record_content_fields(kind, row):
        value = row.get(field)
        if isinstance(value, str):
            values.append(value)
        elif isinstance(value, list):
            values.extend(item for item in value if isinstance(item, str))
        elif isinstance(value, dict):
            values.append(json.dumps(value, ensure_ascii=False, sort_keys=True))
    return [value for value in values if value and value != REDACTED_TEXT and len(value.encode("utf-8")) >= 8]


def _capsule_plaintext_residue(bus_dir: Path, rows: list[tuple[str, dict[str, Any]]]) -> list[str]:
    db_path = paths(bus_dir)["capsule_db"]
    try:
        haystack = db_path.read_bytes()
    except OSError:
        return ["capsule_db"]
    out: list[str] = []
    for kind, row in rows:
        try:
            record_id = _record_id(kind, row)
        except ValueError:
            record_id = "unknown"
        for value in _content_strings(kind, row):
            if value.encode("utf-8") in haystack:
                out.append(f"{kind}:{record_id}")
                break
    return out


def _unmarked_secret_rows(rows: list[tuple[str, dict[str, Any]]]) -> list[str]:
    out: list[str] = []
    for kind, row in rows:
        if effective_sensitivity(row) == "restricted":
            continue
        text = "\n".join(
            json.dumps(row.get(field), ensure_ascii=False, sort_keys=True)
            for field in _record_content_fields(kind, row)
            if field in row
        )
        if SECRET_PATTERN.search(text):
            try:
                out.append(f"{kind}:{_record_id(kind, row)}")
            except ValueError:
                out.append(kind)
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
    capsule = _capsule_channel_path(args.bus_dir).exists()
    mode = args.bus_dir.stat().st_mode & 0o777
    messages = live_messages(args.bus_dir)
    tasks = fold_tasks(args.bus_dir)
    issues = fold_issues(args.bus_dir, include_closed=True)
    security_rows = _security_scan_rows(args.bus_dir)
    sensitive_messages = [m for m in messages if effective_sensitivity(m) in SENSITIVE_LEVELS]
    sensitive_tasks = [t for t in tasks if effective_sensitivity(t) in SENSITIVE_LEVELS]
    sensitive_issues = [i for i in issues if effective_sensitivity(i) in SENSITIVE_LEVELS]
    no_archive = [m for m in messages if effective_retention(m) == "no_archive"]
    loose_files = _security_file_mode_warnings(args.bus_dir)
    missing_sealed = [] if capsule else _restricted_missing_sealed(args.bus_dir, security_rows)
    raw_residue = [] if capsule else _restricted_raw_residue(security_rows)
    capsule_residue = _capsule_plaintext_residue(args.bus_dir, security_rows) if capsule else []
    secret_rows = _unmarked_secret_rows(security_rows)
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
            "status": "warn" if os.environ.get("AGENTBUS_AGENT_TOKEN") else "ok",
            "name": "agent_token_env",
            "detail": "AGENTBUS_AGENT_TOKEN is set in this shell" if os.environ.get("AGENTBUS_AGENT_TOKEN") else "not set",
        },
        {
            "status": "warn" if secret_rows else "ok",
            "name": "unmarked_secret_pattern",
            "detail": f"records={len(secret_rows)}: {', '.join(secret_rows[:5]) or 'none'}",
        },
    ]
    if capsule:
        checks.insert(2, {
            "status": "ok" if paths(args.bus_dir)["capsule_db"].exists() else "warn",
            "name": "capsule_store",
            "detail": str(paths(args.bus_dir)["capsule_db"]),
        })
        checks.insert(4, {
            "status": "warn" if capsule_residue else "ok",
            "name": "capsule_plaintext_residue",
            "detail": f"records={len(capsule_residue)}: {', '.join(capsule_residue[:5]) or 'none'}",
        })
    else:
        checks.insert(3, {
            "status": "warn" if missing_sealed else "ok",
            "name": "restricted_missing_sealed_blob",
            "detail": f"records={len(missing_sealed)}: {', '.join(missing_sealed[:5]) or 'none'}",
        })
        checks.insert(4, {
            "status": "warn" if raw_residue else "ok",
            "name": "restricted_raw_residue",
            "detail": f"records={len(raw_residue)}: {', '.join(raw_residue[:5]) or 'none'}",
        })
    report = {"bus_dir": str(args.bus_dir), "checks": checks}
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    for check in checks:
        print(f"{check['status']:4} {check['name']}  {check['detail']}")
    return 0


def skill_list(args: argparse.Namespace) -> int:
    rows = skill_rows(args.bus_dir, include_retired=args.all)
    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    if args.prompt:
        text = skill_prompt_summary(args.bus_dir)
        if text:
            print(text, end="")
        return 0
    if not rows:
        print("no bus-local skills")
        return 0
    for row in rows:
        pending = _format_pending(row.get("pending") or {})
        bits = [row["skill_id"], row["state"], row["name"]]
        if row.get("description"):
            bits.append(row["description"])
        if pending:
            bits.append(f"pending: {pending}")
        if row.get("warnings"):
            bits.append(f"warnings: {len(row['warnings'])}")
        print("\t".join(bits))
    return 0


def skill_new(args: argparse.Namespace) -> int:
    try:
        sid = create_skill(args.bus_dir, args.skill_id, args.description, args.state)
        print(sid)
        return 0
    except (OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


def skill_show(args: argparse.Namespace) -> int:
    try:
        path = _skill_path(args.bus_dir, args.skill_id)
        if not path.is_file():
            raise ValueError(f"skill not found: {args.skill_id}")
        print(path.read_text(encoding="utf-8"), end="")
        return 0
    except (OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


def skill_state(args: argparse.Namespace) -> int:
    try:
        state = set_skill_state(args.bus_dir, args.skill_id, args.state)
        append_jsonl(_skill_evidence_path(args.bus_dir, _skill_id(args.skill_id)), {
            "type": "decision",
            "ref": "skill state",
            "note": f"state set to {state}",
            "decision": state,
        })
        print(args.skill_id, state)
        return 0
    except (OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


def skill_review(args: argparse.Namespace) -> int:
    rows = skill_rows(args.bus_dir, include_retired=args.all)
    review = [
        row for row in rows
        if row.get("pending") or row.get("warnings") or args.all
    ]
    if args.json:
        print(json.dumps(review, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    if not review:
        print("no skill review items")
        return 0
    for row in review:
        pending = _format_pending(row.get("pending") or {}) or "none"
        warnings = ", ".join(row.get("warnings") or []) or "none"
        print(f"{row['skill_id']}\t{row['state']}\tpending: {pending}\twarnings: {warnings}")
    return 0


def skill_evidence(args: argparse.Namespace) -> int:
    try:
        skill_id = _skill_id(args.skill_id)
        skill_path = _skill_path(args.bus_dir, skill_id)
        if not skill_path.is_file():
            raise ValueError(f"skill not found: {skill_id}")
        evidence_type = _choice(args.type, "type", SKILL_EVIDENCE_TYPES)
        row = {
            "type": evidence_type,
            "ref": _safe_inline(_required_text(args.ref, "ref"), 240),
            "note": _safe_inline(_required_text(args.note, "note"), 1000),
        }
        append_jsonl(_skill_evidence_path(args.bus_dir, skill_id), row)
        print(f"evidence-appended {skill_id} {evidence_type}")
        return 0
    except (TimeoutError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


def add_skill_parsers(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("skill", help="로컬 스킬 조회·생성·검수")
    skill_sub = p.add_subparsers(dest="skill_cmd", required=True)
    p_new = skill_sub.add_parser("new", help="로컬 스킬 초안 생성")
    p_new.add_argument("skill_id", help="생성할 skill id. 영문자·숫자·점·밑줄·하이픈 사용")
    p_new.add_argument("--description", required=True, help="skill 요약 설명. guide 출력의 발견 요약에도 표시")
    p_new.add_argument("--state", choices=SKILL_STATES, default="candidate", help="초기 skill 상태")
    p_new.set_defaults(func=skill_new)
    p_list = skill_sub.add_parser("list", help="로컬 스킬 목록")
    p_list.add_argument("--all", action="store_true", help="retired skill까지 표시")
    list_out = p_list.add_mutually_exclusive_group()
    list_out.add_argument("--json", action="store_true", help="skill 목록을 JSON으로 출력")
    list_out.add_argument("--prompt", action="store_true", help="guide에 붙는 skill 요약 형식으로 출력")
    p_list.set_defaults(func=skill_list)
    p_show = skill_sub.add_parser("show", help="로컬 SKILL.md 출력")
    p_show.add_argument("skill_id", help="출력할 bus-local skill id")
    p_show.set_defaults(func=skill_show)
    p_state = skill_sub.add_parser("state", help="로컬 스킬 상태 변경")
    p_state.add_argument("skill_id", help="상태를 바꿀 bus-local skill id")
    p_state.add_argument("--state", choices=SKILL_STATES, required=True, help="새 skill 상태")
    p_state.set_defaults(func=skill_state)
    p_review = skill_sub.add_parser("review", help="처리할 skill 근거와 경고 요약")
    p_review.add_argument("--all", action="store_true", help="처리 대기 근거가 없는 skill도 표시")
    p_review.add_argument("--json", action="store_true", help="검수 항목을 JSON으로 출력")
    p_review.set_defaults(func=skill_review)
    p_ev = skill_sub.add_parser("evidence", help="skill 사용 뒤 재사용 근거를 기록")
    p_ev.add_argument("skill_id", help="근거를 붙일 bus-local skill id")
    p_ev.add_argument("--type", choices=SKILL_EVIDENCE_TYPES, required=True, help="근거 종류: grounding/check/gap/risk")
    p_ev.add_argument("--ref", required=True, help="메시지 id, 파일 경로, 실행 결과 같은 근거 참조")
    p_ev.add_argument("--note", required=True, help="재사용 판단에 필요한 짧은 근거 설명")
    p_ev.set_defaults(func=skill_evidence)


def _add_task_new_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--title", required=True, help="작업 또는 티켓 제목")
    p.add_argument("--by", required=True, help="기록을 남기는 사용자 또는 에이전트")
    p.add_argument("--assign", default="", help="쉼표 구분 담당 에이전트")
    p.add_argument("--id", default="", help="명시 task_id (생략 시 자동)")
    p.add_argument("--sensitivity", choices=SENSITIVITY_LEVELS, default="", help="민감도 표시")
    p.add_argument("--retention", choices=RETENTION_POLICIES, default="", help="보관 힌트")


def _add_task_state_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--id", required=True, help="상태를 바꿀 task_id")
    p.add_argument("--state", choices=TASK_STATES, required=True, help="새 작업 상태")
    p.add_argument("--by", required=True, help="기록을 남기는 사용자 또는 에이전트")
    p.add_argument("--note", default="", help="상태 변경 이유나 처리 메모")


def _add_task_delete_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--id", required=True, help="삭제 표시할 task_id")
    p.add_argument("--by", required=True, help="기록을 남기는 사용자 또는 에이전트")


def add_task_group_parsers(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("task", help="작업 생성·상태·목록·삭제")
    task_sub = p.add_subparsers(dest="task_cmd", required=True)
    p_new = task_sub.add_parser("new", help="작업 생성")
    _add_task_new_args(p_new)
    p_new.set_defaults(func=task_new)
    p_state = task_sub.add_parser("state", help="작업 상태 갱신")
    _add_task_state_args(p_state)
    p_state.set_defaults(func=task_state)
    p_list = task_sub.add_parser("list", help="현재 작업 목록")
    p_list.set_defaults(func=task_list)
    p_delete = task_sub.add_parser("delete", help="작업 삭제 이벤트 기록")
    _add_task_delete_args(p_delete)
    p_delete.set_defaults(func=task_delete)


def _add_ticket_new_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--title", required=True, help="작업 또는 티켓 제목")
    p.add_argument("--by", required=True, help="기록을 남기는 사용자 또는 에이전트")
    p.add_argument("--body", default="", help="티켓 본문")
    p.add_argument("--ref", action="append", help="관련 파일, 메시지, URL 참조. 여러 번 지정 가능")
    p.add_argument("--sensitivity", choices=SENSITIVITY_LEVELS, default="", help="민감도 표시")
    p.add_argument("--retention", choices=RETENTION_POLICIES, default="", help="보관 힌트")


def _add_ticket_list_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--all", action="store_true", help="accepted/rejected까지 표시")
    p.add_argument("--json", action="store_true", help="JSON으로 출력")


def _add_ticket_accept_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--id", required=True, help="수락할 ticket_id")
    p.add_argument("--by", required=True, help="기록을 남기는 사용자 또는 에이전트")
    p.add_argument("--to", required=True, help="작업을 받을 에이전트")
    p.add_argument("--note", default="", help="상태 변경 이유나 처리 메모")


def _add_ticket_reject_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--id", required=True, help="반려할 ticket_id")
    p.add_argument("--by", required=True, help="기록을 남기는 사용자 또는 에이전트")
    p.add_argument("--note", default="", help="상태 변경 이유나 처리 메모")


def add_ticket_group_parsers(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("ticket", help="티켓 생성·목록·수락·반려")
    ticket_sub = p.add_subparsers(dest="ticket_cmd", required=True)
    p_new = ticket_sub.add_parser("new", help="승격 전 티켓 등록")
    _add_ticket_new_args(p_new)
    p_new.set_defaults(func=issue_new)
    p_list = ticket_sub.add_parser("list", help="티켓 확인")
    _add_ticket_list_args(p_list)
    p_list.set_defaults(func=issue_list)
    p_accept = ticket_sub.add_parser("accept", help="티켓을 task와 request 메시지로 승격")
    _add_ticket_accept_args(p_accept)
    p_accept.set_defaults(func=issue_accept)
    p_reject = ticket_sub.add_parser("reject", help="티켓 반려")
    _add_ticket_reject_args(p_reject)
    p_reject.set_defaults(func=issue_reject)

def supervise(args: argparse.Namespace) -> int:
    ensure_bus(args.bus_dir)
    start = time.time()
    agents = [a.strip() for a in args.agents.split(",") if a.strip()]
    while True:
        if _capsule_doc_exists(paths(args.bus_dir)["stop"]):
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


def capsule_endpoint(bus_dir: Path) -> str:
    env = os.environ.get("AGENTBUS_ENDPOINT")
    if env:
        return env.rstrip("/")
    channel = _capsule_channel(bus_dir)
    endpoint = _clean_text(channel.get("endpoint"))
    return endpoint.rstrip("/") if endpoint else f"http://127.0.0.1:{DEFAULT_PORT}"


def update_capsule_endpoint(bus_dir: Path, port: int) -> None:
    channel = _capsule_channel(bus_dir)
    if not channel:
        return
    channel["endpoint"] = f"http://127.0.0.1:{port}"
    channel["updatedAt"] = now_iso()
    _write_json_file(_capsule_channel_path(bus_dir), channel)


def _argv_with_bus_dir(argv: list[str], bus_dir: Path) -> list[str]:
    if "--bus-dir" in argv:
        return argv
    return ["--bus-dir", str(bus_dir)] + argv


def _is_local_command(args: argparse.Namespace) -> bool:
    if os.environ.get("AGENTBUS_CAPSULE_SERVER") == "1":
        return True
    if args.cmd in {"guide", "resource"}:
        return True
    if args.cmd == "bus" and getattr(args, "bus_cmd", "") in {"init", "serve", "migrate", "export", "security-check"}:
        return True
    if args.cmd == "bridge" and getattr(args, "bridge_cmd", "") == "check":
        return True
    return False


def _proxy_cli_if_needed(args: argparse.Namespace, argv: list[str]) -> int | None:
    if _is_local_command(args):
        return None
    bus_dir = Path(args.bus_dir)
    if not _capsule_channel_path(bus_dir).exists():
        print("capsule channel not initialized; run agentbus bus init, then agentbus bus serve", file=sys.stderr)
        return 1
    payload = {
        "argv": _argv_with_bus_dir(argv, bus_dir),
        "env": {
            "AGENTBUS_AGENT_TOKEN": os.environ.get("AGENTBUS_AGENT_TOKEN", ""),
        },
    }
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        capsule_endpoint(bus_dir) + "/api/cli",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            result = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        print(f"capsule daemon unavailable at {capsule_endpoint(bus_dir)}: HTTP {exc.code}; run agentbus bus serve", file=sys.stderr)
        return 1
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
        print(f"capsule daemon unavailable at {capsule_endpoint(bus_dir)}: {exc}; run agentbus bus serve", file=sys.stderr)
        return 1
    stdout = result.get("stdout") or ""
    stderr = result.get("stderr") or ""
    if stdout:
        print(stdout, end="")
    if stderr:
        print(stderr, end="", file=sys.stderr)
    return int(result.get("code") or 0)


@contextmanager
def _temporary_env(values: dict[str, str]):
    old = {key: os.environ.get(key) for key in values}
    try:
        for key, value in values.items():
            if value:
                os.environ[key] = value
            else:
                os.environ.pop(key, None)
        yield
    finally:
        for key, value in old.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def run_cli_in_capsule(argv: list[str], env: dict[str, str] | None = None) -> dict[str, Any]:
    out = io.StringIO()
    err = io.StringIO()
    with _temporary_env({"AGENTBUS_CAPSULE_SERVER": "1", **(env or {})}):
        with redirect_stdout(out), redirect_stderr(err):
            code = main(argv)
    return {"code": code, "stdout": out.getvalue(), "stderr": err.getvalue()}


def clear_bus(bus_dir: Path, all_: bool = False) -> None:
    """세션 로그를 비운다. all_이면 작업·상태·정지까지 초기화."""
    ensure_bus(bus_dir)
    ps = paths(bus_dir)
    for key in ["messages", "message_deletes", "acks", "delivered"] + (["tasks", "issues"] if all_ else []):
        info = _capsule_path_info(ps[key])
        if info and info[1] == "record":
            _capsule_clear_stream(bus_dir, info[2])
        else:
            p = ps[key]
            p.parent.mkdir(parents=True, exist_ok=True)
            with file_lock(p):
                p.write_text("", encoding="utf-8")
                _chmod_private(p)
    if all_:
        with file_lock(ps["status"]):
            write_json(ps["status"], {"created_at": now_iso(), "agents": {}})
        if _capsule_path_info(ps["stop"]):
            delete_path(ps["stop"])
        else:
            ps["stop"].unlink(missing_ok=True)


def _rotate_log_unlocked(bus_dir: Path, key: str, path: Path) -> Path | None:
    info = _capsule_path_info(path)
    if info and info[1] == "record":
        stream = info[2]
        rows = read_jsonl(path)
        if not rows:
            return None
        if key == "messages":
            retained = [row for row in rows if effective_retention(row) == "no_archive"]
            if len(retained) == len(rows):
                return None
            _capsule_replace_stream(bus_dir, stream, retained)
            if not retained:
                _capsule_clear_stream(bus_dir, "message_deletes")
            return None
        _capsule_clear_stream(bus_dir, stream)
        return None
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
    msg = seal_record_content(bus_dir, "message", msg)
    p = paths(bus_dir)["messages"]
    p.parent.mkdir(parents=True, exist_ok=True)
    line_bytes = len(json.dumps(msg, ensure_ascii=False, sort_keys=True).encode("utf-8")) + 1
    with file_lock(p):
        if not _capsule_path_info(p) and _should_rotate(p, line_bytes):
            _rotate_log_unlocked(bus_dir, "messages", p)
        _append_jsonl_unlocked(p, msg)


def clear(args: argparse.Namespace) -> int:
    ensure_bus(args.bus_dir)
    scope = "세션 전체(메시지·작업·티켓·상태)" if args.all else "메시지 세션 로그"
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


def _write_json_value(value: Any, out: Path | None = None, compact: bool = False) -> None:
    text = json.dumps(value, ensure_ascii=False, separators=(",", ":") if compact else None, indent=None if compact else 2, sort_keys=True)
    if out:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text + "\n", encoding="utf-8")
    else:
        print(text)


def _packet_protocol(args: argparse.Namespace, expected: str) -> bool:
    if args.protocol != expected:
        print(f"unsupported protocol for this command: {args.protocol}", file=sys.stderr)
        return False
    return True


def packet_data(args: argparse.Namespace) -> int:
    if not _packet_protocol(args, "aas"):
        return 1
    from .assessment import assessment_packet, validate_assessment_packet

    try:
        if args.file:
            packet = _load_operational_data(args.file)
            errors = validate_assessment_packet(packet)
            if errors:
                for error in errors:
                    print(error, file=sys.stderr)
                return 1
            print("packet-data-ok")
            return 0
        if not args.data:
            raise ValueError("--data required unless --file is used")
        if not args.asset_id:
            raise ValueError("--asset-id required unless --file is used")
        if args.data == "-" and args.assessment_summary == "-":
            raise ValueError("--data and --assessment-summary cannot both read stdin")
        data = _load_operational_data(args.data)
        data_level = _clean_text(args.sensitivity) or effective_sensitivity(data)
        data = redact_payload(data, data_level) if data_level in EXTERNAL_RAW_BLOCK_LEVELS else data
        assessment_summary = _load_optional_json(args.assessment_summary)
        packet = assessment_packet(
            args.bus_dir,
            data,
            args.asset_id,
            args.asset_name,
            "stdin" if args.data == "-" else args.data,
            args.event_position,
            args.include_messages,
            assessment_summary,
            args.sensitivity,
            args.retention,
        )
        if data_level in EXTERNAL_RAW_BLOCK_LEVELS:
            packet["redacted"] = True
            packet["redactionScope"] = "external"
            packet["redactionReason"] = data_level
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    _write_json_value(packet, args.out, args.compact)
    return 0


def _a2a_transport_artifact(value: Any) -> str:
    if isinstance(value, dict):
        if value.get("jsonrpc") == "2.0" or value.get("method") == "SendMessage":
            return "message"
        if isinstance(value.get("supportedInterfaces"), list) or isinstance(value.get("skills"), list):
            return "card"
    return ""


def _check_a2a_transport_file(path_text: str, artifact: str = "") -> int:
    from . import a2a

    try:
        value = _load_operational_data(path_text)
    except (OSError, json.JSONDecodeError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    kind = artifact or _a2a_transport_artifact(value)
    if kind == "card":
        errors = a2a.validate_agent_card(value)
        ok = "packet-transport-card-ok"
    elif kind == "message":
        errors = a2a.validate_rpc(value)
        ok = "packet-transport-message-ok"
    else:
        print("--artifact required for unknown transport file", file=sys.stderr)
        return 1
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1
    print(ok)
    return 0


def packet_transport(args: argparse.Namespace) -> int:
    if not _packet_protocol(args, "a2a"):
        return 1
    from . import a2a

    if args.file:
        return _check_a2a_transport_file(args.file, args.artifact)
    if not args.artifact:
        print("--artifact required unless --file is used", file=sys.stderr)
        return 1
    try:
        if args.artifact == "card":
            cards = load_cards(args.cards_dir)
            key = args.agent
            if not key and len(cards) == 1:
                key = next(iter(cards))
            if not key:
                raise ValueError("agent required when more than one card exists")
            card = cards.get(key)
            if not isinstance(card, dict):
                raise ValueError(f"card not found: {key}")
            projected = a2a.agent_card(card, args.url, args.tenant or key)
            _write_json_value(projected, args.out, args.compact)
            return 0
        if args.artifact == "message":
            if not args.message_id:
                raise ValueError("--message-id required for --artifact message")
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
            _write_json_value(request, args.out, args.compact)
            return 0
        raise ValueError(f"unsupported artifact: {args.artifact}")
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


def packet_receive_a2a_request(bus_dir: Path, request: dict[str, Any], recipient: str = "all", sender: str = "a2a") -> tuple[dict[str, Any], dict[str, Any]]:
    from . import a2a

    msg = a2a.inbound_message_to_bus(bus_dir, request, recipient, sender)
    return msg, a2a.inbound_success_response(request, msg)


def packet_receive(args: argparse.Namespace) -> int:
    if not _packet_protocol(args, "a2a"):
        return 1
    from . import a2a

    try:
        request = _load_operational_data(args.file)
        msg, response = packet_receive_a2a_request(args.bus_dir, request, args.to, args.sender)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        if args.response:
            print(json.dumps(a2a.error_response(None, -32602, str(exc)), ensure_ascii=False, indent=2, sort_keys=True))
        else:
            print(str(exc), file=sys.stderr)
        return 1
    if args.response:
        print(json.dumps(response, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(json.dumps({"messageId": msg.get("id", ""), "protocol": "a2a", "received": True}, ensure_ascii=False, indent=2, sort_keys=True))
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


def packet_send(args: argparse.Namespace) -> int:
    if not _packet_protocol(args, "a2a"):
        return 1
    from . import a2a

    try:
        request_body = _load_operational_data(args.file)
        marks = _payload_marks(request_body)
        if marks["restricted"]:
            raise ValueError(f"restricted request blocked for external send ({sensitive_summary(request_body)})")
        if marks["internal_raw"]:
            raise ValueError("internal raw request blocked; send a redacted projection")
        endpoint = _required_text(args.endpoint, "endpoint")
        insecure_http = endpoint.lower().startswith("http://")
        bearer_token = a2a.read_token(args.token_env)
        headers = a2a.header_pairs(args.header)
        credential_headers = _credential_header_names(headers)
        if insecure_http and bearer_token and not args.allow_insecure:
            raise ValueError("bearer token over http blocked; use https or rerun with --allow-insecure")
        if insecure_http and credential_headers and not args.allow_insecure:
            raise ValueError(f"credential header over http blocked ({', '.join(credential_headers)}); use https or rerun with --allow-insecure")
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
        a2a.log_bridge_failure(args.fail_log, error_record)
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
        a2a.log_bridge_failure(args.fail_log, failure)
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



def add_bus_parsers(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("bus", help="secure capsule channel 초기화·대시보드·상태·정리")
    bus_sub = p.add_subparsers(dest="bus_cmd", required=True)
    p_init = bus_sub.add_parser("init", help="secure capsule channel 초기화")
    p_init.set_defaults(func=init_bus)
    p_migrate = bus_sub.add_parser("migrate", help="기존 JSONL bus를 secure capsule로 변환")
    p_migrate.add_argument("--from", dest="from_dir", type=Path, required=True, help="기존 JSONL bus 디렉터리")
    p_migrate.set_defaults(func=migrate_bus)
    p_export = bus_sub.add_parser("export", help="capsule bus를 redacted JSONL로 내보내기")
    p_export.add_argument("--out", type=Path, required=True, help="내보낼 디렉터리")
    p_export.add_argument("--redacted", action="store_true", default=True, help="redacted export (기본)")
    p_export.add_argument("--raw", dest="redacted", action="store_false", help="원문 export 요청. 현재는 admin raw-export flow 전까지 차단")
    p_export.set_defaults(func=export_bus)
    p_serve = bus_sub.add_parser("serve", help="로컬 대시보드 실행 (127.0.0.1)")
    p_serve.add_argument("--port", type=int, default=DEFAULT_PORT, help="대시보드 포트")
    p_serve.add_argument("--root", type=Path, default=DEFAULT_ROOT, help="@ 파일 색인 루트 (기본 현재 디렉터리)")
    p_serve.add_argument("--cards-dir", dest="cards_dir", type=Path, default=CARDS_DIR, help="에이전트 카드 JSON 디렉터리")
    p_serve.set_defaults(func=serve_cmd)
    p_status = bus_sub.add_parser("status", help="버스 상태와 정지 요청 확인")
    p_status.add_argument("--stop-exit-code", action="store_true", help="정지 요청이 있으면 exit 2로 종료")
    p_status.set_defaults(func=show_status)
    p_stop = bus_sub.add_parser("stop", help="협력적 정지 요청 기록")
    p_stop.add_argument("--by", required=True, help="정지 요청을 남기는 사용자 또는 에이전트")
    p_stop.add_argument("--reason", required=True, help="정지 사유 키. 예: user_stop, loop_closed")
    p_stop.add_argument("--detail", default="", help="대시보드와 보고서에 남길 세부 설명")
    p_stop.set_defaults(func=stop)
    p_clear = bus_sub.add_parser("clear", help="메시지 세션 로그 비우기 (--all: 작업·티켓·상태까지)")
    p_clear.add_argument("--all", action="store_true", help="작업·티켓·상태·정지까지 초기화")
    p_clear.add_argument("--yes", action="store_true", help="확인 없이 진행")
    p_clear.set_defaults(func=clear)
    p_rotate = bus_sub.add_parser("rotate", help="메시지 로그를 archive/로 회전")
    p_rotate.set_defaults(func=rotate)
    p_security = bus_sub.add_parser("security-check", help="로컬 보안 가드레일 점검")
    p_security.add_argument("--json", action="store_true", help="점검 결과를 JSON으로 출력")
    p_security.set_defaults(func=security_check)
    p_supervise = bus_sub.add_parser("supervise", help="감독 루프 (heartbeat·정체·시간 초과 시 정지)")
    p_supervise.add_argument("--agents", default="my-agent", help="감독할 에이전트 이름 목록(쉼표 구분)")
    p_supervise.add_argument("--stale-seconds", type=int, default=900, help="heartbeat가 정체로 처리되는 초 단위 기준")
    p_supervise.add_argument("--startup-grace-seconds", type=int, default=600, help="시작 직후 정체 판정을 미루는 초 단위 유예")
    p_supervise.add_argument("--max-minutes", type=int, default=120, help="감독 루프 최대 실행 시간(분)")
    p_supervise.add_argument("--interval-seconds", type=int, default=30, help="상태 확인 주기(초)")
    p_supervise.set_defaults(func=supervise)


def add_agent_parsers(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("agent", help="에이전트 상태·수신함·ack·watch")
    agent_sub = p.add_subparsers(dest="agent_cmd", required=True)
    p_list = agent_sub.add_parser("list", help="에이전트 상태 목록")
    p_list.add_argument("--json", action="store_true", help="JSON으로 출력")
    p_list.set_defaults(func=agent_list)
    p_set = agent_sub.add_parser("set", help="에이전트 상태 갱신 (running/waiting/done/error)")
    p_set.add_argument("--agent", required=True, help="상태를 갱신할 에이전트 이름")
    p_set.add_argument("--state", choices=AGENT_STATES, required=True, help="새 에이전트 상태")
    p_set.add_argument("--task", default="", help="현재 연결된 task_id")
    p_set.add_argument("--note", default="", help="상태 설명 또는 현재 작업 메모")
    p_set.set_defaults(func=set_status)
    p_delete = agent_sub.add_parser("delete", help="에이전트 상태 삭제")
    p_delete.add_argument("--agent", required=True, help="삭제할 에이전트 상태 이름")
    p_delete.set_defaults(func=agent_delete)
    p_inbox = agent_sub.add_parser("inbox", help="에이전트 수신함 읽기")
    p_inbox.add_argument("--agent", required=True, help="수신함을 읽을 에이전트 이름")
    p_inbox.add_argument("--limit", type=int, default=50, help="표시할 최대 메시지 수")
    p_inbox.set_defaults(func=inbox)
    p_ack = agent_sub.add_parser("ack", help="메시지 확인 표시")
    p_ack.add_argument("--agent", required=True, help="메시지를 처리한 에이전트 이름")
    p_ack.add_argument("message_id", help="ack할 메시지 id")
    p_ack.set_defaults(func=ack)
    p_watch = agent_sub.add_parser("watch", help="ack 기준 미확인 메시지 감시")
    p_watch.add_argument("--agent", required=True, help="감시할 에이전트 수신 대상")
    p_watch.add_argument("--kinds", default="request", help="쉼표 구분 kind 필터 (기본 request)")
    p_watch.add_argument("--limit", type=int, default=20, help="한 번에 표시할 최대 메시지 수")
    p_watch.add_argument("--max-body-chars", type=int, default=1200, help="메시지 본문 최대 표시 글자 수")
    p_watch.add_argument("--interval-seconds", type=float, default=2.5, help="반복 감시 주기(초)")
    p_watch.add_argument("--once", action="store_true", help="한 번만 확인하고 종료")
    p_watch.add_argument("--json", action="store_true", help="미처리 메시지를 JSON으로 출력")
    p_watch.set_defaults(func=watch)


def add_message_parsers(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("message", help="메시지 전송·삭제")
    message_sub = p.add_subparsers(dest="message_cmd", required=True)
    p_send = message_sub.add_parser("send", help="메시지 전송 (--task/--reply-to로 스레딩)")
    p_send.add_argument("--from", dest="sender", required=True, help="보내는 사용자 또는 에이전트")
    p_send.add_argument("--to", required=True, help="받는 에이전트, user, all 또는 *")
    p_send.add_argument("--kind", default="note", help="메시지 종류. 예: note, request, report")
    p_send.add_argument("--subject", required=True, help="짧은 메시지 제목")
    p_send.add_argument("--body", required=True, help="메시지 본문")
    p_send.add_argument("--ref", action="append", help="관련 파일, 메시지, URL 참조. 여러 번 지정 가능")
    p_send.add_argument("--task", default="", help="연관 task_id (스레딩)")
    p_send.add_argument("--reply-to", dest="reply_to", default="", help="응답 대상 message_id")
    p_send.add_argument("--sensitivity", choices=SENSITIVITY_LEVELS, default="", help="민감도 표시")
    p_send.add_argument("--retention", choices=RETENTION_POLICIES, default="", help="보관 힌트")
    p_send.set_defaults(func=send)
    p_delete = message_sub.add_parser("delete", help="메시지 삭제 이벤트 기록")
    p_delete.add_argument("--id", required=True, help="삭제 표시할 메시지 id")
    p_delete.add_argument("--by", required=True, help="삭제 이벤트를 남기는 사용자 또는 에이전트")
    p_delete.set_defaults(func=message_delete)


def add_auth_parsers(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("auth", help="capsule 원문 접근 권한 관리")
    auth_sub = p.add_subparsers(dest="auth_cmd", required=True)
    p_init = auth_sub.add_parser("init", help="capsule auth 상태 확인/준비")
    p_init.set_defaults(func=auth_init)
    p_grant = auth_sub.add_parser("grant", help="restricted token 발급")
    grant_target = p_grant.add_mutually_exclusive_group(required=True)
    grant_target.add_argument("--agent", help="권한을 부여할 에이전트 이름")
    grant_target.add_argument("--viewer", help="대시보드 원문 보기를 허용할 사용자 이름")
    p_grant.add_argument("--ttl-seconds", type=int, help="token 유효 시간. 생략하면 만료 없음")
    p_grant.set_defaults(func=auth_grant)
    p_demo = auth_sub.add_parser("demo", help="demo viewer token과 demo 전용 restricted 샘플 생성")
    p_demo.add_argument("--viewer", default="demo", help="demo dashboard viewer 이름")
    p_demo.add_argument("--ttl-seconds", type=int, default=3600, help="demo token 유효 시간")
    p_demo.add_argument("--no-sample", action="store_true", help="demo-only restricted sample message를 만들지 않음")
    p_demo.add_argument("--json", action="store_true", help="JSON으로 출력")
    p_demo.set_defaults(func=auth_demo)
    p_revoke = auth_sub.add_parser("revoke", help="restricted token 폐기")
    revoke_target = p_revoke.add_mutually_exclusive_group(required=True)
    revoke_target.add_argument("--agent", help="권한을 폐기할 에이전트 이름")
    revoke_target.add_argument("--viewer", help="대시보드 원문 보기 권한을 폐기할 사용자 이름")
    p_revoke.set_defaults(func=auth_revoke)
    p_list = auth_sub.add_parser("list", help="restricted 권한 목록")
    p_list.add_argument("--json", action="store_true", help="JSON으로 출력")
    p_list.set_defaults(func=auth_list)


def add_bridge_parsers(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("bridge", help="event bridge와 runtime 연결")
    bridge_sub = p.add_subparsers(dest="bridge_cmd", required=True)

    p_events = bridge_sub.add_parser("events", help="bus event stream 조회")
    p_events.add_argument("--types", default="", help="쉼표 구분 이벤트 타입 필터. ticket.* 허용")
    p_events.add_argument("--target", default="", help="쉼표 구분 대상 필터. all/* 이벤트도 포함")
    p_events.add_argument("--after", default="", help="이 위치 이후 이벤트만 출력")
    p_events.add_argument("--limit", type=int, default=0, help="마지막 N개만 출력")
    p_events.add_argument("--jsonl", action="store_true", help="JSON Lines로 출력")
    p_events.set_defaults(func=events)

    p_watch = bridge_sub.add_parser("watch", help="bus event stream 감지")
    p_watch.add_argument("--types", default="", help="쉼표 구분 이벤트 타입 필터. message.*, ticket.* 허용")
    p_watch.add_argument("--target", default="", help="쉼표 구분 대상 필터. all/* 이벤트도 포함")
    p_watch.add_argument("--interval-seconds", type=float, default=1.0, help="반복 감시 주기(초)")
    p_watch.add_argument("--once", action="store_true", help="현재 새 이벤트만 확인하고 종료")
    p_watch.add_argument("--from-start", action="store_true", help="현재 로그의 기존 이벤트부터 출력")
    p_watch.add_argument("--position-file", dest="position_file", metavar="POSITION_FILE", type=Path, default=None, help="처리 위치 저장 파일")
    p_watch.add_argument("--dry-run", action="store_true", help="이벤트만 출력하고 처리 위치를 변경하지 않음")
    p_watch.set_defaults(func=watch_events)

    p_run = bridge_sub.add_parser("run", help="bridge profile 실행")
    p_run.add_argument("--profile", type=Path, required=True, help="bridge profile JSON 경로")
    p_run.add_argument("--once", action="store_true", help="한 번 확인하고 종료")
    p_run.add_argument("--dry-run", action="store_true", help="출력만 하고 명령 실행과 처리 위치 저장을 건너뜀")
    p_run.set_defaults(func=bridge_run)

    p_check = bridge_sub.add_parser("check", help="bridge profile JSON 검사")
    p_check.add_argument("--file", type=Path, required=True, help="bridge profile JSON 경로")
    p_check.set_defaults(func=bridge_check)

    p_status = bridge_sub.add_parser("status", help="bridge 처리 위치와 실패 요약 출력")
    p_status.add_argument("--json", action="store_true", help="JSON으로 출력")
    p_status.set_defaults(func=bridge_status)


def add_packet_parsers(sub: argparse._SubParsersAction) -> None:
    from .a2a import A2A_ROLES

    p = sub.add_parser("packet", help="외부 protocol packet 교환")
    packet_sub = p.add_subparsers(dest="packet_cmd", required=True)

    p_data = packet_sub.add_parser("data", help="data packet 생성 또는 검사")
    p_data.add_argument("--protocol", choices=["aas"], required=True, help="data protocol")
    p_data.add_argument("--file", default="", help="검사할 packet JSON 경로. stdin은 '-'")
    p_data.add_argument("--data", default="", help="운용 데이터 JSON 경로. stdin은 '-'")
    p_data.add_argument("--asset-id", default="", help="대상 asset 식별자")
    p_data.add_argument("--asset-name", default="", help="표시용 asset 이름")
    p_data.add_argument("--event-position", default="", help="이 event position 이후 change event만 포함")
    p_data.add_argument("--include-messages", type=int, default=50, help="최근 communication record 개수")
    p_data.add_argument("--assessment-summary", default="", help="판단 요약 JSON 경로. stdin은 '-'")
    p_data.add_argument("--sensitivity", choices=SENSITIVITY_LEVELS, default="", help="packet 민감도 표시")
    p_data.add_argument("--retention", choices=RETENTION_POLICIES, default="", help="packet 보관 힌트")
    p_data.add_argument("--out", type=Path, default=None, help="출력 파일. 생략하면 stdout")
    p_data.add_argument("--compact", action="store_true", help="공백 없는 JSON 출력")
    p_data.set_defaults(func=packet_data)

    p_transport = packet_sub.add_parser("transport", help="transport artifact 생성 또는 검사")
    p_transport.add_argument("--protocol", choices=["a2a"], required=True, help="transport protocol")
    p_transport.add_argument("--artifact", choices=["card", "message"], default="", help="생성 또는 검사할 artifact")
    p_transport.add_argument("--file", default="", help="검사할 transport artifact JSON 경로. stdin은 '-'")
    p_transport.add_argument("--agent", default="", help="card artifact용 카드 idShort 또는 파일명")
    p_transport.add_argument("--cards-dir", dest="cards_dir", type=Path, default=CARDS_DIR, help="에이전트 카드 JSON 디렉터리")
    p_transport.add_argument("--url", default="http://127.0.0.1:8765/a2a/rpc", help="transport endpoint URL")
    p_transport.add_argument("--tenant", default="", help="transport routing value")
    p_transport.add_argument("--message-id", default="", help="message artifact용 bus message id")
    p_transport.add_argument("--request-id", default="", help="transport request id. 생략하면 자동")
    p_transport.add_argument("--role", choices=A2A_ROLES, default="ROLE_USER", help="transport message role")
    p_transport.add_argument("--context-id", default="", help="transport context id")
    p_transport.add_argument("--data", action="append", help="추가할 structured JSON part 경로. stdin은 '-'")
    p_transport.add_argument("--accepted-output", action="append", help="허용할 output MIME. 쉼표 구분 가능")
    p_transport.add_argument("--wait", action="store_true", help="returnImmediately=false로 생성")
    p_transport.add_argument("--out", type=Path, default=None, help="출력 파일. 생략하면 stdout")
    p_transport.add_argument("--compact", action="store_true", help="공백 없는 JSON 출력")
    p_transport.set_defaults(func=packet_transport)

    p_send = packet_sub.add_parser("send", help="transport artifact 외부 전송")
    p_send.add_argument("--protocol", choices=["a2a"], required=True, help="transport protocol")
    p_send.add_argument("--file", required=True, help="transport request JSON 경로. stdin은 '-'")
    p_send.add_argument("--endpoint", required=True, help="HTTP(S) endpoint")
    p_send.add_argument("--token-env", default="", help="Bearer 토큰을 읽을 환경변수 이름")
    p_send.add_argument("--header", action="append", help="추가 HTTP header. 예: 'X-Trace: 1'")
    p_send.add_argument("--timeout", type=float, default=30.0, help="HTTP 응답 대기 시간(초)")
    p_send.add_argument("--allow-insecure", action="store_true", help="http endpoint로 token 또는 credential header 전송 허용")
    p_send.add_argument("--fail-log", type=Path, default=None, help="실패 JSONL 기록")
    p_send.add_argument("--out", type=Path, default=None, help="응답 body 저장 파일")
    p_send.add_argument("--record-response-to", default="", help="응답을 bus 메시지로 받을 에이전트")
    p_send.add_argument("--response-from", default="a2a", help="응답 기록 메시지의 발신자")
    p_send.set_defaults(func=packet_send)

    p_receive = packet_sub.add_parser("receive", help="transport artifact를 bus 기록으로 반영")
    p_receive.add_argument("--protocol", choices=["a2a"], required=True, help="transport protocol")
    p_receive.add_argument("--file", required=True, help="받은 transport request JSON 경로. stdin은 '-'")
    p_receive.add_argument("--to", default="all", help="metadata recipient가 없을 때 받을 대상")
    p_receive.add_argument("--from", dest="sender", default="a2a", help="metadata sender가 없을 때 보낼 주체")
    p_receive.add_argument("--response", action="store_true", help="수신 결과를 transport response JSON으로 출력")
    p_receive.set_defaults(func=packet_receive)


def add_guide_parsers(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("guide", help="루프·워크플로 안내 출력")
    guide_sub = p.add_subparsers(dest="guide_cmd", required=True)
    p_workflow = guide_sub.add_parser("workflow", help="에이전트 협업 워크플로와 종료 보고서 template 출력")
    p_workflow.add_argument("--path", action="store_true", help="패키지에 포함된 SKILL.md 경로만 출력")
    p_workflow.set_defaults(func=workflow)
    p_loop = guide_sub.add_parser("loop", help="에이전트 루프 엔트리와 종료 보고 안내 출력")
    p_loop.add_argument("--path", action="store_true", help="패키지에 포함된 SKILL.md 경로만 출력")
    p_loop.set_defaults(func=loop)


def add_resource_parsers(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("resource", help="package resource 목록 또는 경로 출력")
    resource_sub = p.add_subparsers(dest="resource_cmd", required=True)
    p_list = resource_sub.add_parser("list", help="package resource 목록 출력")
    p_list.set_defaults(func=resources, name="")
    p_path = resource_sub.add_parser("path", help="package resource 경로 출력")
    p_path.add_argument("name", help="예: bridge/claude-inbox.json")
    p_path.set_defaults(func=resources)

def parse_args(parser: argparse.ArgumentParser, argv: list[str] | None = None) -> argparse.Namespace:
    return parser.parse_args(sys.argv[1:] if argv is None else argv)


def workflow_text() -> str:
    return WORKFLOW_PATH.read_text(encoding="utf-8")


def loop_text() -> str:
    return LOOP_PATH.read_text(encoding="utf-8")


def _print_skill_augmented(text: str, bus_dir: Path) -> None:
    print(text, end="")
    summary = skill_prompt_summary(bus_dir)
    if summary:
        if not text.endswith("\n"):
            print()
        print("\n" + summary, end="")


def workflow(args: argparse.Namespace) -> int:
    if args.path:
        print(WORKFLOW_PATH)
        return 0
    try:
        _print_skill_augmented(workflow_text(), args.bus_dir)
        return 0
    except OSError as exc:
        print(f"workflow file not found: {exc}", file=sys.stderr)
        return 1


def loop(args: argparse.Namespace) -> int:
    if args.path:
        print(LOOP_PATH)
        return 0
    try:
        _print_skill_augmented(loop_text(), args.bus_dir)
        return 0
    except OSError as exc:
        print(f"loop skill file not found: {exc}", file=sys.stderr)
        return 1


def _resource_path(name: str) -> Path:
    if not name:
        return RESOURCES_DIR
    rel = Path(name)
    if rel.is_absolute() or ".." in rel.parts:
        raise ValueError("resource path must be relative")
    path = (RESOURCES_DIR / rel).resolve()
    try:
        path.relative_to(RESOURCES_DIR.resolve())
    except ValueError as exc:
        raise ValueError("resource path must stay under packaged resources") from exc
    if not path.exists():
        raise ValueError(f"resource not found: {name}")
    return path


def resources(args: argparse.Namespace) -> int:
    try:
        path = _resource_path(args.name)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    if args.name:
        print(path)
        return 0
    if not RESOURCES_DIR.exists():
        return 0
    for item in sorted(RESOURCES_DIR.rglob("*")):
        if not item.is_file():
            continue
        if item.name == ".DS_Store" or "__pycache__" in item.parts or item.suffix == ".pyc":
            continue
        print(item.relative_to(RESOURCES_DIR).as_posix())
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="agentbus",
        description="로컬 다중 에이전트 secure capsule channel: 메시지·ack·상태·작업.",
        epilog=(
            "작업 수명주기: submitted → working → input_required → completed/failed/canceled.\n"
            "에이전트 상태(agent set --state)는 작업과 별개: running/waiting/done/error.\n"
            "스레딩: message send --task <id>, --reply-to <id>.\n"
            "카드: 기본 ./agent-cards/*.json. 세부 도움말: agentbus <command> --help."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--bus-dir", type=Path, default=DEFAULT_BUS_DIR, help="channel 디렉터리. 기본 ./.agent-bus 또는 AGENTBUS_BUS_DIR")
    sub = parser.add_subparsers(dest="cmd", required=True, metavar="command")

    add_bus_parsers(sub)
    add_agent_parsers(sub)
    add_message_parsers(sub)
    add_auth_parsers(sub)
    add_bridge_parsers(sub)
    add_task_group_parsers(sub)
    add_ticket_group_parsers(sub)
    add_skill_parsers(sub)
    add_packet_parsers(sub)
    add_guide_parsers(sub)
    add_resource_parsers(sub)
    argv_list = sys.argv[1:] if argv is None else argv
    args = parse_args(parser, argv_list)
    proxied = _proxy_cli_if_needed(args, argv_list)
    if proxied is not None:
        return proxied
    try:
        return args.func(args)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except TimeoutError as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
