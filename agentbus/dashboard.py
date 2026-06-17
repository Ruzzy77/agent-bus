#!/usr/bin/env python3
"""Localhost dashboard for the agent bus.

Stdlib only. Binds to 127.0.0.1.
"""
from __future__ import annotations

import argparse
import ipaddress
import json
import os
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import bus as agent_bus

# @ 멘션 파일 색인 루트와 카드 디렉터리. serve()에서 덮어쓴다.
FILE_INDEX_ROOT = agent_bus.DEFAULT_ROOT
VENDOR_DIR = Path(__file__).resolve().parent / "vendor"
CARDS_DIR = agent_bus.CARDS_DIR
IGNORE_DIRS = {".git", ".agent-bus", "node_modules", "__pycache__",
               ".venv", "venv", "build", ".pytest_cache", ".mypy_cache", ".ipynb_checkpoints"}
IGNORE_EXT = {".pyc", ".lock", ".aux", ".log", ".out", ".toc"}
_file_cache: dict = {"root": None, "ts": 0.0, "list": []}


def list_files(root: Path) -> list[str]:
    root = Path(root)
    now = time.time()
    if _file_cache["root"] == root and _file_cache["list"] and now - _file_cache["ts"] < 10:
        return _file_cache["list"]
    if not root.is_dir():
        return []
    out: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in IGNORE_DIRS and not d.startswith(".")]
        for f in filenames:
            if f.startswith("."):
                continue
            p = Path(dirpath) / f
            if p.suffix.lower() in IGNORE_EXT:
                continue
            out.append(p.relative_to(root).as_posix())
    out.sort()
    _file_cache["root"] = root
    _file_cache["ts"] = now
    _file_cache["list"] = out
    return out


def match_files(query: str, limit: int = 40) -> list[str]:
    q = query.lower().strip()
    files = list_files(FILE_INDEX_ROOT)
    if not q:
        return files[:limit]

    def rank(f: str) -> tuple:
        fl = f.lower()
        base = fl.rsplit("/", 1)[-1]
        order = 0 if base.startswith(q) else 1 if q in base else 2
        return (order, len(f), f)

    return sorted((f for f in files if q in f.lower()), key=rank)[:limit]

STATIC_DIR = Path(__file__).resolve().parent / "static"
CONTENT_TYPES = {
    ".css": "text/css; charset=utf-8",
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".ttf": "font/ttf",
    ".woff": "font/woff",
    ".woff2": "font/woff2",
}


def content_type(path: Path) -> str:
    return CONTENT_TYPES.get(path.suffix, "application/octet-stream")


def resolve_asset(root: Path, rel: str) -> Path | None:
    base = root.resolve()
    target = (base / rel).resolve()
    try:
        target.relative_to(base)
    except ValueError:
        return None
    return target if target.is_file() else None


def _is_loopback_host(host: str | None) -> bool:
    if not host:
        return False
    text = host.strip().strip("[]").lower()
    if text == "localhost":
        return True
    try:
        return ipaddress.ip_address(text).is_loopback
    except ValueError:
        return False


def _host_port_from_url(value: str, default_scheme: str = "http") -> tuple[str, int] | None:
    parsed = urlparse(value if "://" in value else f"{default_scheme}://{value}")
    if not parsed.hostname:
        return None
    try:
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
    except ValueError:
        return None
    return parsed.hostname, port


def _same_local_origin(value: str, host_header: str) -> bool:
    origin = _host_port_from_url(value)
    request = _host_port_from_url(host_header)
    if not origin or not request:
        return False
    origin_host, origin_port = origin
    request_host, request_port = request
    return _is_loopback_host(origin_host) and _is_loopback_host(request_host) and origin_port == request_port


class Handler(BaseHTTPRequestHandler):
    bus_dir: Path

    def _reply(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code: int, value) -> None:
        self._reply(code, json.dumps(value, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def _file(self, root: Path, rel: str) -> None:
        target = resolve_asset(root, rel)
        if target is None:
            self._json(404, {"error": "not found"})
            return
        self._reply(200, target.read_bytes(), content_type(target))

    def _allow_host(self) -> bool:
        host = self.headers.get("Host") or f"127.0.0.1:{self.server.server_port}"
        request = _host_port_from_url(host)
        if not request or not _is_loopback_host(request[0]) or request[1] != self.server.server_port:
            self._json(403, {"error": "local host required"})
            return False
        return True

    def _allow_write_request(self) -> bool:
        if not self._allow_host():
            return False
        ctype = self.headers.get("Content-Type", "").lower()
        if "application/json" not in ctype:
            self._json(415, {"error": "application/json required"})
            return False
        host = self.headers.get("Host") or f"127.0.0.1:{self.server.server_port}"
        for name in ("Origin", "Referer"):
            value = self.headers.get(name)
            if value and not _same_local_origin(value, host):
                self._json(403, {"error": "local origin required"})
                return False
        return True

    def do_GET(self) -> None:
        if not self._allow_host():
            return
        parsed = urlparse(self.path)
        path = parsed.path
        if path == "/":
            self._file(STATIC_DIR, "dashboard.html")
        elif path == "/.well-known/agent-card.json":
            from . import a2a

            q = parse_qs(parsed.query)
            cards = agent_bus.load_cards(CARDS_DIR)
            key = q.get("agent", [""])[0]
            if not key and len(cards) == 1:
                key = next(iter(cards))
            card = cards.get(key)
            if not key or not isinstance(card, dict):
                self._json(404, {"error": "card not found"})
                return
            host = self.headers.get("Host") or f"127.0.0.1:{self.server.server_port}"
            url = q.get("url", [f"http://{host}/a2a/rpc"])[0]
            self._json(200, a2a.agent_card(card, url, q.get("tenant", [key])[0]))
        elif path == "/api/state":
            ps = agent_bus.paths(self.bus_dir)
            try:
                limit = max(1, min(2000, int(parse_qs(parsed.query).get("limit", ["300"])[0])))
            except ValueError:
                limit = 300
            # 최근 N건만 전송한다. 전체 로그는 파일에 둔다.
            all_msgs = agent_bus.live_messages(self.bus_dir)
            messages = all_msgs[-limit:]
            shown = {m.get("id") for m in messages}
            acks = agent_bus.unique_acks([a for a in agent_bus.read_jsonl(ps["acks"]) if a.get("id") in shown])
            self._json(200, {
                "bus_dir": str(self.bus_dir),
                "root": str(FILE_INDEX_ROOT),
                "now": time.time(),
                "messages": messages,
                "messages_total": len(all_msgs),
                "acks": acks,
                "status": agent_bus.load_json(ps["status"], {"agents": {}}),
                "stop": agent_bus.load_json(ps["stop"], None) if ps["stop"].exists() else None,
                "tasks": agent_bus.fold_tasks(self.bus_dir),
                "task_reports": agent_bus.task_report_rows(self.bus_dir, max_body_chars=160),
                "tickets": agent_bus.fold_issues(self.bus_dir),
                "issues": agent_bus.fold_issues(self.bus_dir),
                "cards": agent_bus.load_cards(CARDS_DIR),
                "task_states": agent_bus.TASK_STATES,
            })
        elif path == "/api/files":
            q = parse_qs(parsed.query).get("q", [""])[0]
            self._json(200, {"files": match_files(q)})
        elif path == "/api/events":
            q = parse_qs(parsed.query)
            try:
                limit = max(0, min(2000, int(q.get("limit", ["0"])[0])))
            except ValueError:
                limit = 0
            events = agent_bus.bus_events(
                self.bus_dir,
                types=agent_bus.parse_event_types(q.get("types", [""])[0]),
                targets=agent_bus.parse_event_targets(q.get("target", [""])[0]),
                after=q.get("after", [""])[0],
                limit=limit,
            )
            self._json(200, {"version": agent_bus.EVENT_VERSION, "events": events})
        elif path.startswith("/static/"):
            self._file(STATIC_DIR, path[len("/static/"):])
        elif path.startswith("/vendor/"):
            self._file(VENDOR_DIR, path[len("/vendor/"):])
        else:
            self._json(404, {"error": "not found"})

    def do_POST(self) -> None:
        if not self._allow_write_request():
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            data = json.loads(self.rfile.read(length) or b"{}")
        except (ValueError, json.JSONDecodeError):
            self._json(400, {"error": "invalid json"})
            return
        if not isinstance(data, dict):
            self._json(400, {"error": "json object required"})
            return
        path = urlparse(self.path).path
        ps = agent_bus.paths(self.bus_dir)
        if path == "/api/send":
            subject = agent_bus._clean_text(data.get("subject"))
            body = agent_bus._clean_text(data.get("body"))
            if not body:
                self._json(400, {"error": "body required"})
                return
            msg = agent_bus.make_message(
                data.get("from") or "user",
                data.get("to") or "all",
                data.get("kind") or "note",
                subject,
                body,
                data.get("refs") or [],
                data.get("task_id") or "",
                data.get("reply_to") or "",
                data.get("sensitivity") or "",
                data.get("retention") or "",
            )
            agent_bus.append_message(self.bus_dir, msg)
            self._json(200, {"id": msg["id"]})
        elif path == "/a2a/rpc":
            from . import a2a

            params = data.get("params") if isinstance(data.get("params"), dict) else {}
            try:
                msg = a2a.inbound_message_to_bus(
                    self.bus_dir,
                    data,
                    params.get("tenant") or "all",
                    "a2a",
                )
            except ValueError as exc:
                self._json(200, a2a.error_response(data.get("id"), -32602, str(exc)))
                return
            self._json(200, a2a.inbound_success_response(data, msg))
        elif path == "/api/message-delete":
            mid = agent_bus._clean_text(data.get("id"))
            if not mid:
                self._json(400, {"error": "id required"})
                return
            try:
                agent_bus.delete_message(self.bus_dir, mid, data.get("by") or "user")
            except ValueError as exc:
                self._json(400, {"error": str(exc)})
                return
            self._json(200, {"ok": True})
        elif path == "/api/task-new":
            title = agent_bus._clean_text(data.get("title"))
            if not title:
                self._json(400, {"error": "title required"})
                return
            tid = agent_bus.create_task(
                self.bus_dir,
                title,
                data.get("by") or "user",
                data.get("assign"),
                data.get("id") or "",
                data.get("sensitivity") or "",
                data.get("retention") or "",
            )
            self._json(200, {"task_id": tid})
        elif path == "/api/task-state":
            tid = agent_bus._clean_text(data.get("id"))
            state = agent_bus._clean_text(data.get("state"))
            if not tid or state not in agent_bus.TASK_STATES:
                self._json(400, {"error": "valid id and state required"})
                return
            agent_bus.set_task_state(self.bus_dir, tid, state, data.get("by") or "user", data.get("note") or "")
            self._json(200, {"ok": True})
        elif path == "/api/task-delete":
            tid = agent_bus._clean_text(data.get("id"))
            if not tid:
                self._json(400, {"error": "id required"})
                return
            agent_bus.delete_task(self.bus_dir, tid, data.get("by") or "user")
            self._json(200, {"ok": True})
        elif path in ("/api/ticket-new", "/api/issue-new"):
            try:
                iid = agent_bus.create_issue(
                    self.bus_dir,
                    data.get("title"),
                    data.get("by") or "user",
                    data.get("body") or "",
                    data.get("refs") or [],
                    data.get("sensitivity") or "",
                    data.get("retention") or "",
                )
            except ValueError as exc:
                self._json(400, {"error": str(exc)})
                return
            self._json(200, {"ticket_id": iid, "issue_id": iid})
        elif path in ("/api/ticket-accept", "/api/issue-accept"):
            try:
                result = agent_bus.accept_issue(
                    self.bus_dir,
                    data.get("id"),
                    data.get("by") or "user",
                    data.get("to"),
                    data.get("note") or "",
                )
            except ValueError as exc:
                self._json(400, {"error": str(exc)})
                return
            self._json(200, result)
        elif path in ("/api/ticket-reject", "/api/issue-reject"):
            try:
                agent_bus.reject_issue(self.bus_dir, data.get("id"), data.get("by") or "user", data.get("note") or "")
            except ValueError as exc:
                self._json(400, {"error": str(exc)})
                return
            self._json(200, {"ok": True})
        elif path == "/api/stop":
            agent_bus.write_stop(
                self.bus_dir,
                data.get("by") or "user",
                data.get("reason") or "user_stop",
                data.get("detail") or "",
            )
            self._json(200, {"ok": True})
        elif path == "/api/clear-stop":
            ps["stop"].unlink(missing_ok=True)
            self._json(200, {"ok": True})
        elif path == "/api/agent-delete":
            name = agent_bus._clean_text(data.get("agent"))
            if not name:
                self._json(400, {"error": "agent required"})
                return
            agent_bus.delete_agent_status(self.bus_dir, name)
            self._json(200, {"ok": True})
        elif path == "/api/clear":
            agent_bus.clear_bus(self.bus_dir, bool(data.get("all")))
            self._json(200, {"ok": True})
        elif path == "/api/rotate":
            dest = agent_bus.rotate_log(self.bus_dir, "messages")
            self._json(200, {"ok": True, "archived": str(dest) if dest else None})
        else:
            self._json(404, {"error": "not found"})

    def log_message(self, fmt: str, *args) -> None:
        pass


def serve(bus_dir: Path, port: int = 8765, root: Path | None = None,
          cards_dir: Path | None = None) -> int:
    global FILE_INDEX_ROOT, CARDS_DIR
    agent_bus.ensure_bus(Path(bus_dir))
    if root is not None:
        FILE_INDEX_ROOT = Path(root)
    if cards_dir is not None:
        CARDS_DIR = Path(cards_dir)
    Handler.bus_dir = Path(bus_dir)
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"agent-bus dashboard: http://127.0.0.1:{port}  (bus: {bus_dir})")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


def main() -> int:
    # 기본값은 bus의 AGENTBUS_* 해석값이다.
    parser = argparse.ArgumentParser(prog="agentbus-dashboard")
    parser.add_argument("--bus-dir", type=Path, default=agent_bus.DEFAULT_BUS_DIR)
    parser.add_argument("--port", type=int, default=agent_bus.DEFAULT_PORT)
    parser.add_argument("--root", type=Path, default=agent_bus.DEFAULT_ROOT,
                        help="@ 파일 색인 루트 (기본 현재 디렉터리)")
    parser.add_argument("--cards-dir", dest="cards_dir", type=Path, default=agent_bus.CARDS_DIR)
    args = parser.parse_args()
    return serve(args.bus_dir, args.port, args.root, args.cards_dir)


if __name__ == "__main__":
    raise SystemExit(main())
