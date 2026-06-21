"""A2A projection and local transport helpers."""
from __future__ import annotations

import json
import os
import re
import uuid
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from . import bus as core

A2A_PROTOCOL_VERSION = "1.0"
A2A_RPC_METHOD = "SendMessage"
A2A_ROLES = ("ROLE_USER", "ROLE_AGENT")
A2A_TASK_STATES = {
    "submitted": "TASK_STATE_SUBMITTED",
    "working": "TASK_STATE_WORKING",
    "input_required": "TASK_STATE_INPUT_REQUIRED",
    "completed": "TASK_STATE_COMPLETED",
    "failed": "TASK_STATE_FAILED",
    "canceled": "TASK_STATE_CANCELED",
}
A2A_STATE_TO_TASK = {value: key for key, value in A2A_TASK_STATES.items()}
A2A_STATE_TO_TASK["TASK_STATE_REJECTED"] = "failed"
A2A_STATE_TO_TASK["TASK_STATE_AUTH_REQUIRED"] = "input_required"


def find_message(bus_dir: Path, message_id: str) -> dict[str, Any]:
    mid = core._required_text(message_id, "message_id")
    for row in core.live_messages(bus_dir):
        if row.get("id") == mid:
            return row
    raise ValueError("message not found")


def _text_part(text: object) -> dict[str, Any]:
    return {
        "text": core._required_text(text, "message body"),
        "mediaType": "text/plain",
    }


def _data_part(data: Any, source: str = "") -> dict[str, Any]:
    level = core.effective_sensitivity(data) if isinstance(data, dict) else "normal"
    projected = core.redact_payload(data, level) if level in core.EXTERNAL_RAW_BLOCK_LEVELS else data
    part: dict[str, Any] = {
        "data": projected,
        "mediaType": "application/json",
    }
    metadata: dict[str, Any] = {}
    if source:
        metadata["source"] = source
    if isinstance(data, dict) and data.get("schemaVersion"):
        metadata["schemaVersion"] = data["schemaVersion"]
    if isinstance(data, dict):
        metadata.update(core.security_fields(level))
    if isinstance(projected, dict) and projected.get("redacted"):
        metadata["redacted"] = True
    if metadata:
        part["metadata"] = metadata
    return part


def _message_metadata(row: dict[str, Any]) -> dict[str, Any]:
    metadata = {
        "communicationId": row.get("id", ""),
        "createdAt": row.get("time", ""),
        "sender": row.get("from", ""),
        "recipient": row.get("to", ""),
        "kind": row.get("kind", ""),
        "subject": row.get("subject", ""),
        "evidenceReferences": row.get("refs") or [],
    }
    metadata.update(core.security_fields(core.effective_sensitivity(row)))
    if row.get("redacted"):
        metadata["redacted"] = True
        metadata["redactedFields"] = row.get("redactedFields") or []
    reply = row.get("reply_to")
    if reply:
        metadata["replyTo"] = reply
    return metadata


def send_message_request(
    row: dict[str, Any],
    request_id: str = "",
    role: str = "ROLE_USER",
    context_id: str = "",
    tenant: str = "",
    data_parts: list[tuple[Any, str]] | None = None,
    accepted_output_modes: list[str] | None = None,
    return_immediately: bool = True,
) -> dict[str, Any]:
    row = core.redact_record(row, "external")
    role = core._choice(role, "role", list(A2A_ROLES))
    parts = [_text_part(row.get("body", ""))]
    for data, source in data_parts or []:
        parts.append(_data_part(data, source))
    message: dict[str, Any] = {
        "messageId": core._required_text(row.get("id"), "message_id"),
        "role": role,
        "parts": parts,
        "metadata": _message_metadata(row),
    }
    if context_id:
        message["contextId"] = context_id
    task_id = core._clean_text(row.get("task_id"))
    if task_id:
        message["taskId"] = task_id
        message["referenceTaskIds"] = [task_id]
    params: dict[str, Any] = {
        "message": message,
        "configuration": {
            "acceptedOutputModes": accepted_output_modes or ["text/plain", "application/json"],
            "returnImmediately": return_immediately,
        },
        "metadata": {
            "protocolVersion": A2A_PROTOCOL_VERSION,
        },
    }
    if tenant:
        params["tenant"] = tenant
    return {
        "jsonrpc": "2.0",
        "id": request_id or ("rpc-" + uuid.uuid4().hex[:12]),
        "method": A2A_RPC_METHOD,
        "params": params,
    }


def _validate_part(part: Any, index: int) -> list[str]:
    if not isinstance(part, dict):
        return [f"message.parts[{index}] must be an object"]
    keys = [key for key in ("text", "raw", "url", "data") if key in part]
    if len(keys) != 1:
        return [f"message.parts[{index}] must contain exactly one of text, raw, url, data"]
    if "mediaType" in part and not isinstance(part["mediaType"], str):
        return [f"message.parts[{index}].mediaType must be a string"]
    if "metadata" in part and not isinstance(part["metadata"], dict):
        return [f"message.parts[{index}].metadata must be an object"]
    return []


def validate_rpc(request: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(request, dict):
        return ["request must be a JSON object"]
    if request.get("jsonrpc") != "2.0":
        errors.append("jsonrpc must be 2.0")
    if not request.get("id"):
        errors.append("id required")
    if request.get("method") != A2A_RPC_METHOD:
        errors.append(f"method must be {A2A_RPC_METHOD}")
    params = request.get("params")
    if not isinstance(params, dict):
        errors.append("params must be an object")
        return errors
    message = params.get("message")
    if not isinstance(message, dict):
        errors.append("params.message required")
        return errors
    if not message.get("messageId"):
        errors.append("message.messageId required")
    if message.get("role") not in A2A_ROLES:
        errors.append("message.role must be ROLE_USER or ROLE_AGENT")
    parts = message.get("parts")
    if not isinstance(parts, list) or not parts:
        errors.append("message.parts must be a non-empty list")
    else:
        for i, part in enumerate(parts):
            errors.extend(_validate_part(part, i))
    metadata = message.get("metadata")
    if metadata is not None and not isinstance(metadata, dict):
        errors.append("message.metadata must be an object")
    config = params.get("configuration")
    if config is not None:
        if not isinstance(config, dict):
            errors.append("params.configuration must be an object")
        else:
            output_modes = config.get("acceptedOutputModes")
            if output_modes is not None and not isinstance(output_modes, list):
                errors.append("configuration.acceptedOutputModes must be a list")
            if "returnImmediately" in config and not isinstance(config["returnImmediately"], bool):
                errors.append("configuration.returnImmediately must be a boolean")
    return errors


def _media_type(value: object) -> str:
    text = str(value or "").strip()
    if "/" in text:
        return text
    mapping = {
        "text": "text/plain",
        "plain": "text/plain",
        "json": "application/json",
        "data": "application/json",
        "file": "text/uri-list",
        "file-ref": "text/uri-list",
        "uri": "text/uri-list",
    }
    return mapping.get(text, text or "text/plain")


def _media_types(values: object, fallback: list[str]) -> list[str]:
    items = core._flat_string_list(values)
    out = [_media_type(item) for item in items]
    return out or fallback


def _skill_tags(skill: dict[str, Any]) -> list[str]:
    tags = core._flat_string_list(skill.get("tags"))
    if tags:
        return tags
    raw = [skill.get("id", ""), skill.get("name", "")]
    tags = []
    for value in raw:
        text = re.sub(r"[^A-Za-z0-9_]+", "-", str(value or "").strip()).strip("-").lower()
        if text and text not in tags:
            tags.append(text)
    return tags or ["general"]


def agent_card(local_card: dict[str, Any], url: str, tenant: str = "") -> dict[str, Any]:
    if not isinstance(local_card, dict):
        raise ValueError("agent card must be an object")
    name = core._required_text(local_card.get("name") or local_card.get("idShort"), "card.name")
    description = core._required_text(local_card.get("description"), "card.description")
    tenant = core._clean_text(tenant, core._clean_text(local_card.get("idShort"), name))
    skills = []
    for row in local_card.get("skills") or []:
        if not isinstance(row, dict):
            continue
        skills.append({
            "id": core._required_text(row.get("id") or row.get("name"), "skill.id"),
            "name": core._required_text(row.get("name") or row.get("id"), "skill.name"),
            "description": core._required_text(row.get("description"), "skill.description"),
            "tags": _skill_tags(row),
            "inputModes": _media_types(row.get("inputModes"), ["text/plain", "application/json"]),
            "outputModes": _media_types(row.get("outputModes"), ["text/plain", "application/json"]),
        })
    if not skills:
        skills.append({
            "id": "general",
            "name": "General request handling",
            "description": description,
            "tags": ["general"],
            "inputModes": ["text/plain", "application/json"],
            "outputModes": ["text/plain", "application/json"],
        })
    caps = local_card.get("capabilities") if isinstance(local_card.get("capabilities"), dict) else {}
    interface = {
        "url": core._required_text(url, "url"),
        "protocolBinding": "JSONRPC",
        "protocolVersion": A2A_PROTOCOL_VERSION,
    }
    if tenant:
        interface["tenant"] = tenant
    return {
        "name": name,
        "description": description,
        "supportedInterfaces": [interface],
        "version": str(local_card.get("version") or "0.1.0"),
        "capabilities": {
            "streaming": bool(caps.get("streaming", False)),
            "pushNotifications": bool(caps.get("pushNotifications", False)),
            "extendedAgentCard": False,
        },
        "defaultInputModes": sorted({mode for skill in skills for mode in skill.get("inputModes", [])}) or ["text/plain"],
        "defaultOutputModes": sorted({mode for skill in skills for mode in skill.get("outputModes", [])}) or ["text/plain"],
        "skills": skills,
    }


def validate_agent_card(card: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(card, dict):
        return ["card must be a JSON object"]
    for key in ["name", "description", "version"]:
        if not isinstance(card.get(key), str) or not card.get(key):
            errors.append(f"{key} required")
    interfaces = card.get("supportedInterfaces")
    if not isinstance(interfaces, list) or not interfaces:
        errors.append("supportedInterfaces required")
    else:
        for i, row in enumerate(interfaces):
            if not isinstance(row, dict):
                errors.append(f"supportedInterfaces[{i}] must be an object")
                continue
            for key in ["url", "protocolBinding", "protocolVersion"]:
                if not isinstance(row.get(key), str) or not row.get(key):
                    errors.append(f"supportedInterfaces[{i}].{key} required")
    if not isinstance(card.get("capabilities"), dict):
        errors.append("capabilities required")
    for key in ["defaultInputModes", "defaultOutputModes"]:
        if not isinstance(card.get(key), list) or not card.get(key):
            errors.append(f"{key} required")
    skills = card.get("skills")
    if not isinstance(skills, list) or not skills:
        errors.append("skills required")
    else:
        for i, skill in enumerate(skills):
            if not isinstance(skill, dict):
                errors.append(f"skills[{i}] must be an object")
                continue
            for key in ["id", "name", "description"]:
                if not isinstance(skill.get(key), str) or not skill.get(key):
                    errors.append(f"skills[{i}].{key} required")
            if not isinstance(skill.get("tags"), list) or not skill.get("tags"):
                errors.append(f"skills[{i}].tags required")
    return errors


def validate_rpc_response(response: Any, request_id: object = "") -> list[str]:
    errors: list[str] = []
    if not isinstance(response, dict):
        return ["response must be a JSON object"]
    if response.get("jsonrpc") != "2.0":
        errors.append("response.jsonrpc must be 2.0")
    if "id" not in response:
        errors.append("response.id required")
    elif request_id and response.get("id") != request_id:
        errors.append("response.id must match request id")
    has_result = "result" in response
    has_error = "error" in response
    if has_result == has_error:
        errors.append("response must contain exactly one of result or error")
    if has_error:
        error = response.get("error")
        if not isinstance(error, dict):
            errors.append("response.error must be an object")
        else:
            if "code" not in error:
                errors.append("response.error.code required")
            if not isinstance(error.get("message"), str) or not error.get("message"):
                errors.append("response.error.message required")
    return errors


def header_pairs(values: object) -> dict[str, str]:
    headers: dict[str, str] = {}
    for raw in values or []:
        text = str(raw)
        name, sep, value = text.partition(":")
        if not sep or not name.strip():
            raise ValueError(f"invalid header: {text}")
        headers[name.strip()] = value.strip()
    return headers


def read_token(token_env: str = "") -> str:
    if token_env:
        value = os.environ.get(token_env, "")
        if not value:
            raise ValueError(f"{token_env} not set")
        return value
    return ""


def _validate_http_endpoint(endpoint: str) -> str:
    text = core._required_text(endpoint, "endpoint")
    parsed = urlparse(text)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError("endpoint must be http or https URL")
    return text


def _response_text(body: bytes, headers: dict[str, str]) -> str:
    content_type = headers.get("Content-Type") or headers.get("content-type") or ""
    match = re.search(r"charset=([^;]+)", content_type)
    encoding = match.group(1).strip() if match else "utf-8"
    try:
        return body.decode(encoding)
    except (LookupError, UnicodeDecodeError):
        return body.decode("utf-8", errors="replace")


def post_rpc(
    request_body: dict[str, Any],
    endpoint: str,
    bearer_token: str = "",
    headers: dict[str, str] | None = None,
    timeout: float = 30.0,
) -> dict[str, Any]:
    endpoint = _validate_http_endpoint(endpoint)
    errors = validate_rpc(request_body)
    if errors:
        raise ValueError("; ".join(errors))
    body = json.dumps(request_body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    request_headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "A2A-Version": A2A_PROTOCOL_VERSION,
    }
    if bearer_token:
        request_headers["Authorization"] = f"Bearer {bearer_token}"
    request_headers.update(headers or {})
    req = Request(endpoint, data=body, headers=request_headers, method="POST")
    try:
        with urlopen(req, timeout=timeout) as resp:
            response_body = resp.read()
            response_headers = dict(resp.headers.items())
            status = resp.status
    except HTTPError as exc:
        response_body = exc.read()
        response_headers = dict(exc.headers.items()) if exc.headers else {}
        text = _response_text(response_body, response_headers)
        return {"ok": False, "status": exc.code, "headers": response_headers, "body": text, "error": f"HTTP {exc.code}"}
    except URLError as exc:
        return {"ok": False, "status": 0, "headers": {}, "body": "", "error": str(exc.reason)}
    text = _response_text(response_body, response_headers)
    parsed: Any = None
    parse_error = ""
    if text.strip():
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            parse_error = str(exc)
    if parse_error:
        return {"ok": False, "status": status, "headers": response_headers, "body": text, "error": f"invalid JSON response: {parse_error}"}
    response_errors = validate_rpc_response(parsed, request_body.get("id")) if parsed is not None else ["empty response body"]
    if response_errors:
        return {"ok": False, "status": status, "headers": response_headers, "body": text, "response": parsed, "error": "; ".join(response_errors)}
    if isinstance(parsed, dict) and "error" in parsed:
        error = parsed["error"]
        message = error.get("message", "") if isinstance(error, dict) else ""
        code = error.get("code", "") if isinstance(error, dict) else ""
        return {"ok": False, "status": status, "headers": response_headers, "body": text, "response": parsed, "error": f"rpc error {code}: {message}".strip()}
    return {"ok": 200 <= status < 300, "status": status, "headers": response_headers, "body": text, "response": parsed, "error": "" if 200 <= status < 300 else f"HTTP {status}"}


def log_bridge_failure(path: Path | None, record: dict[str, Any]) -> None:
    if path:
        core.append_jsonl(path, record)


def _part_text(parts: object) -> str:
    if not isinstance(parts, list):
        return ""
    chunks: list[str] = []
    for part in parts:
        if not isinstance(part, dict):
            continue
        if isinstance(part.get("text"), str):
            chunks.append(part["text"])
        elif "data" in part:
            chunks.append(json.dumps(part["data"], ensure_ascii=False, sort_keys=True))
    return "\n\n".join(chunk for chunk in chunks if chunk)


def _response_message_record(message: dict[str, Any], sender: str, recipient: str, fallback_task: str = "") -> dict[str, Any]:
    body = _part_text(message.get("parts")) or json.dumps(message, ensure_ascii=False, indent=2, sort_keys=True)
    task_id = core._clean_text(message.get("taskId"), fallback_task)
    metadata = message.get("metadata") if isinstance(message.get("metadata"), dict) else {}
    subject = core._clean_text(metadata.get("subject"), "A2A message")
    return core.make_message(
        sender,
        recipient,
        "report",
        subject,
        body,
        [],
        task_id,
        "",
        metadata.get("sensitivity"),
    )


def _remote_task_state(task: dict[str, Any]) -> str:
    status = task.get("status") if isinstance(task.get("status"), dict) else {}
    return A2A_STATE_TO_TASK.get(str(status.get("state") or ""), "")


def record_rpc_result(
    bus_dir: Path,
    request_body: dict[str, Any],
    result: dict[str, Any],
    recipient: str,
    sender: str = "a2a",
    by: str = "a2a",
) -> dict[str, str]:
    response = result.get("response")
    params = request_body.get("params", {}) if isinstance(request_body, dict) else {}
    request_message = params.get("message", {}) if isinstance(params, dict) else {}
    request_metadata = request_message.get("metadata") if isinstance(request_message.get("metadata"), dict) else {}
    fallback_task = core._clean_text(request_message.get("taskId")) if isinstance(request_message, dict) else ""
    out = {"messageId": "", "taskId": "", "taskState": ""}
    if not isinstance(response, dict):
        body = json.dumps({"status": result.get("status"), "error": result.get("error"), "body": result.get("body")}, ensure_ascii=False, indent=2, sort_keys=True)
        msg = core.make_message(
            sender,
            recipient,
            "error",
            f"A2A response {request_body.get('id', '')}".strip(),
            body,
            [],
            fallback_task,
            "",
            request_metadata.get("sensitivity"),
        )
        core.append_message(bus_dir, msg)
        out["messageId"] = msg["id"]
        return out
    payload = response.get("result") if result.get("ok") else response.get("error")
    if isinstance(payload, dict) and isinstance(payload.get("message"), dict):
        message_obj = payload["message"]
        task_obj = None
    elif isinstance(payload, dict) and isinstance(payload.get("task"), dict):
        message_obj = None
        task_obj = payload["task"]
    elif isinstance(payload, dict) and isinstance(payload.get("parts"), list):
        message_obj = payload
        task_obj = None
    elif isinstance(payload, dict) and isinstance(payload.get("status"), dict):
        message_obj = None
        task_obj = payload
    else:
        message_obj = None
        task_obj = None

    if isinstance(message_obj, dict):
        msg = _response_message_record(message_obj, sender, recipient, fallback_task)
        core.append_message(bus_dir, msg)
        out["messageId"] = msg["id"]
    elif isinstance(task_obj, dict):
        local_task = fallback_task or core._clean_text(task_obj.get("metadata", {}).get("workItemId") if isinstance(task_obj.get("metadata"), dict) else "")
        state = _remote_task_state(task_obj)
        if local_task and state:
            core.set_task_state(bus_dir, local_task, state, by, f"remote task {task_obj.get('id', '')}")
            out["taskId"] = local_task
            out["taskState"] = state
        status = task_obj.get("status") if isinstance(task_obj.get("status"), dict) else {}
        if isinstance(status.get("message"), dict):
            msg = _response_message_record(status["message"], sender, recipient, local_task)
            core.append_message(bus_dir, msg)
            out["messageId"] = msg["id"]
    else:
        kind = "report" if result.get("ok") else "error"
        body = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
        msg = core.make_message(
            sender,
            recipient,
            kind,
            f"A2A response {request_body.get('id', '')}".strip(),
            body,
            [],
            fallback_task,
            "",
            request_metadata.get("sensitivity"),
        )
        core.append_message(bus_dir, msg)
        out["messageId"] = msg["id"]
    return out


def inbound_message_to_bus(bus_dir: Path, request: dict[str, Any], recipient: str = "all", sender: str = "a2a") -> dict[str, Any]:
    errors = validate_rpc(request)
    if errors:
        raise ValueError("; ".join(errors))
    message = request["params"]["message"]
    metadata = message.get("metadata") if isinstance(message.get("metadata"), dict) else {}
    from_name = core._clean_text(metadata.get("sender"), sender)
    to_name = core._clean_text(metadata.get("recipient"), recipient)
    subject = core._clean_text(metadata.get("subject"), "A2A message")
    refs = metadata.get("evidenceReferences") or []
    task_id = core._clean_text(message.get("taskId"))
    body = _part_text(message.get("parts"))
    msg = core.make_message(
        from_name,
        to_name,
        "request",
        subject,
        body,
        refs,
        task_id,
        "",
        metadata.get("sensitivity"),
    )
    core.append_message(bus_dir, msg)
    return msg


def inbound_success_response(request: dict[str, Any], local_message: dict[str, Any]) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": request.get("id"),
        "result": {
            "message": {
                "messageId": local_message["id"],
                "role": "ROLE_AGENT",
                "parts": [{"text": "accepted", "mediaType": "text/plain"}],
                "metadata": {
                    "communicationId": local_message["id"],
                    "recipient": local_message.get("to", ""),
                },
            }
        },
    }


def error_response(request_id: object, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}
