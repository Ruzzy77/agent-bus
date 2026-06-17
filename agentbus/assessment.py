"""Assessment packet projection."""
from __future__ import annotations

import re
import uuid
from pathlib import Path
from typing import Any

from . import bus as core

ASSESSMENT_PACKET_VERSION = "assessment-packet.v1"
ASSESSMENT_SUBMODELS = ("OperationalData", "AssessmentRecords", "WorkItems", "Traceability")
ASSESSMENT_ID_SHORTS = (
    "participants",
    "assessmentSummary",
    "individualAssessments",
    "consensus",
    "disagreements",
    "partialEvidence",
    "uniqueFindings",
    "evidenceGaps",
    "decisionsNeeded",
    "communicationRecords",
    "reviewItems",
    "workItems",
    "changeEvents",
)
ASSESSMENT_SUMMARY_KEYS = (
    "individualAssessments",
    "consensus",
    "disagreements",
    "partialEvidence",
    "uniqueFindings",
    "evidenceGaps",
    "decisionsNeeded",
)
SUMMARY_REFERENCE_KEYS = ("evidenceReferences", "communicationIds", "workItemIds")


def _id_short(value: object, default: str = "Item") -> str:
    text = re.sub(r"[^A-Za-z0-9_]+", "_", str(value or "").strip()).strip("_")
    if not text:
        text = default
    if not re.match(r"^[A-Za-z_]", text):
        text = f"{default}_{text}"
    return text[:128]


def _unique_id_short(value: object, used: set[str], default: str = "Item") -> str:
    base = _id_short(value, default)
    name = base
    i = 2
    while name in used:
        suffix = f"_{i}"
        name = (base[:128 - len(suffix)] + suffix) if len(base) + len(suffix) > 128 else base + suffix
        i += 1
    used.add(name)
    return name


def _aas_property(id_short: str, value: Any) -> dict[str, Any]:
    if isinstance(value, bool):
        value_type = "xs:boolean"
        text = "true" if value else "false"
    elif isinstance(value, int):
        value_type = "xs:long"
        text = str(value)
    elif isinstance(value, float):
        value_type = "xs:double"
        text = str(value)
    elif value is None:
        value_type = "xs:string"
        text = ""
    else:
        value_type = "xs:string"
        text = str(value)
    return {"modelType": "Property", "idShort": id_short, "valueType": value_type, "value": text}


def _aas_element(id_short: str, value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        used: set[str] = set()
        return {
            "modelType": "SubmodelElementCollection",
            "idShort": id_short,
            "value": [_aas_element(_unique_id_short(k, used), v) for k, v in value.items()],
        }
    if isinstance(value, list):
        return {
            "modelType": "SubmodelElementList",
            "idShort": id_short,
            "value": [_aas_element(f"Item{i + 1}", v) for i, v in enumerate(value)],
        }
    return _aas_property(id_short, value)


def _submodel_id(asset_id: str, id_short: str) -> str:
    safe = _id_short(asset_id, "Asset")
    if asset_id.startswith(("urn:", "http://", "https://")):
        return f"{asset_id.rstrip('/')}/submodels/{id_short}"
    return f"urn:assessment:{safe}:{id_short}"


def _aas_submodel(asset_id: str, id_short: str, payload: Any) -> dict[str, Any]:
    return {
        "modelType": "Submodel",
        "id": _submodel_id(asset_id, id_short),
        "idShort": id_short,
        "kind": "Instance",
        "submodelElements": [_aas_element("Records", payload)],
    }


def _message_record(row: dict[str, Any]) -> dict[str, Any]:
    record = {
        "id": row.get("id", ""),
        "time": row.get("time", ""),
        "sender": row.get("from", ""),
        "recipient": row.get("to", ""),
        "kind": row.get("kind", ""),
        "subject": row.get("subject", ""),
        "body": row.get("body", ""),
        "evidenceReferences": row.get("refs") or [],
        "workItemId": row.get("task_id", ""),
        "replyTo": row.get("reply_to", ""),
    }
    record.update(core.security_fields(core.effective_sensitivity(row), core.effective_retention(row)))
    return record


def _work_item_record(row: dict[str, Any]) -> dict[str, Any]:
    record = {
        "id": row.get("task_id", ""),
        "title": row.get("title", ""),
        "state": row.get("state", ""),
        "assignedTo": row.get("assign") or [],
        "createdAt": row.get("created_at", ""),
        "updatedAt": row.get("updated_at", ""),
        "note": row.get("note", ""),
    }
    record.update(core.security_fields(core.effective_sensitivity(row), core.effective_retention(row)))
    return record


def _review_item_record(row: dict[str, Any]) -> dict[str, Any]:
    record = {
        "id": row.get("issue_id", ""),
        "title": row.get("title", ""),
        "body": row.get("body", ""),
        "state": row.get("state", ""),
        "requestedBy": row.get("by", ""),
        "createdAt": row.get("created_at", ""),
        "updatedAt": row.get("updated_at", ""),
        "note": row.get("note", ""),
        "workItemId": row.get("task_id", ""),
        "communicationId": row.get("message_id", ""),
        "evidenceReferences": row.get("refs") or [],
    }
    record.update(core.security_fields(core.effective_sensitivity(row), core.effective_retention(row)))
    return record


def _summary_list(value: Any, key: str) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    raise ValueError(f"assessmentSummary.{key} must be a list")


def _has_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _has_text_item(value: Any) -> bool:
    return isinstance(value, list) and bool(value) and all(_has_text(item) for item in value)


def _require_summary_object(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{path} must be a JSON object")
    return value


def _require_text_field(row: dict[str, Any], path: str, field: str) -> None:
    if not _has_text(row.get(field)):
        raise ValueError(f"{path}.{field} must be a non-empty string")


def _require_text_list_field(row: dict[str, Any], path: str, field: str) -> None:
    if not _has_text_item(row.get(field)):
        raise ValueError(f"{path}.{field} must be a non-empty list of strings")


def _validate_reference_lists(row: dict[str, Any], path: str) -> None:
    for field in SUMMARY_REFERENCE_KEYS:
        value = row.get(field)
        if value is not None and not isinstance(value, list):
            raise ValueError(f"{path}.{field} must be a list")


def _validate_assessment_summary_source(summary: dict[str, list[Any]]) -> None:
    """Validate source summary claims before projecting them into AAS shape."""
    for i, item in enumerate(summary["individualAssessments"]):
        path = f"assessmentSummary.individualAssessments[{i}]"
        row = _require_summary_object(item, path)
        _require_text_field(row, path, "participant")
        _require_text_field(row, path, "summary")
        _validate_reference_lists(row, path)

    for i, item in enumerate(summary["consensus"]):
        path = f"assessmentSummary.consensus[{i}]"
        row = _require_summary_object(item, path)
        _require_text_field(row, path, "statement")
        _require_text_list_field(row, path, "participants")
        _validate_reference_lists(row, path)

    for i, item in enumerate(summary["disagreements"]):
        path = f"assessmentSummary.disagreements[{i}]"
        row = _require_summary_object(item, path)
        _require_text_field(row, path, "topic")
        positions = row.get("positions")
        if not isinstance(positions, list) or not positions:
            raise ValueError(f"{path}.positions must be a non-empty list")
        _validate_reference_lists(row, path)
        for j, position in enumerate(positions):
            position_path = f"{path}.positions[{j}]"
            position_row = _require_summary_object(position, position_path)
            _require_text_field(position_row, position_path, "participant")
            _require_text_field(position_row, position_path, "statement")
            _validate_reference_lists(position_row, position_path)

    for i, item in enumerate(summary["uniqueFindings"]):
        path = f"assessmentSummary.uniqueFindings[{i}]"
        row = _require_summary_object(item, path)
        _require_text_field(row, path, "finding")
        if not (_has_text(row.get("participant")) or _has_text(row.get("source"))):
            raise ValueError(f"{path} must include participant or source")
        _validate_reference_lists(row, path)


def normalize_assessment_summary(value: Any = None) -> dict[str, list[Any]]:
    if value in (None, ""):
        source: dict[str, Any] = {}
    elif isinstance(value, dict):
        source = value
    else:
        raise ValueError("assessmentSummary must be a JSON object")
    summary = {key: _summary_list(source.get(key), key) for key in ASSESSMENT_SUMMARY_KEYS}
    _validate_assessment_summary_source(summary)
    return summary


def _participant_records(bus_dir: Path) -> list[dict[str, Any]]:
    status = core.load_json(core.paths(bus_dir)["status"], {"agents": {}})
    agents = status.get("agents", {}) if isinstance(status, dict) else {}
    out = []
    for name, row in sorted(agents.items()):
        if not isinstance(row, dict):
            continue
        out.append({
            "name": name,
            "state": row.get("state", ""),
            "workItemId": row.get("task", ""),
            "note": row.get("note", ""),
            "updatedAt": row.get("updated_at", ""),
            "lastActivity": row.get("heartbeat", ""),
        })
    return out


def _change_event_record(event: dict[str, Any]) -> dict[str, Any]:
    return {
        "cursor": event.get("cursor", ""),
        "time": event.get("time", ""),
        "type": event.get("type", ""),
        "actor": event.get("actor", ""),
        "target": event.get("target", ""),
        "object": event.get("object") or {},
    }


def assessment_packet(
    bus_dir: Path,
    operational_data: Any,
    asset_id: str,
    asset_name: str = "",
    data_source: str = "",
    event_cursor: str = "",
    include_messages: int = 50,
    assessment_summary: Any = None,
    sensitivity: str = "",
    retention: str = "",
) -> dict[str, Any]:
    core.ensure_bus(bus_dir)
    asset = {
        "assetId": core._required_text(asset_id, "asset_id"),
        "idShort": _id_short(asset_name or asset_id, "Asset"),
    }
    if asset_name:
        asset["name"] = asset_name
    message_rows = [] if include_messages <= 0 else core.live_messages(bus_dir)[-include_messages:]
    messages = [_message_record(row) for row in message_rows]
    work_items = [_work_item_record(row) for row in core.fold_tasks(bus_dir)]
    review_items = [_review_item_record(row) for row in core.fold_issues(bus_dir, include_closed=True)]
    change_events = [_change_event_record(event) for event in core.bus_events(bus_dir, after=event_cursor)]
    assessment_records = {
        "participants": _participant_records(bus_dir),
        "assessmentSummary": normalize_assessment_summary(assessment_summary),
        "communicationRecords": messages,
        "reviewItems": review_items,
    }
    traceability = {
        "assetId": asset["assetId"],
        "dataSource": data_source,
        "eventCursor": event_cursor,
        "latestEventCursor": change_events[-1]["cursor"] if change_events else event_cursor,
        "changeEvents": change_events,
    }
    submodels = [
        _aas_submodel(asset["assetId"], "OperationalData", operational_data),
        _aas_submodel(asset["assetId"], "AssessmentRecords", assessment_records),
        _aas_submodel(asset["assetId"], "WorkItems", {"workItems": work_items}),
        _aas_submodel(asset["assetId"], "Traceability", traceability),
    ]
    shell_id = f"{asset['assetId'].rstrip('/')}/assessment" if asset["assetId"].startswith(("urn:", "http://", "https://")) else f"urn:assessment:{asset['idShort']}:shell"
    packet = {
        "schemaVersion": ASSESSMENT_PACKET_VERSION,
        "packetId": "pkt-" + uuid.uuid4().hex[:12],
        "createdAt": core.now_iso(),
        "asset": asset,
        "aasEnvironment": {
            "assetAdministrationShells": [{
                "modelType": "AssetAdministrationShell",
                "id": shell_id,
                "idShort": "AssessmentPacket",
                "assetInformation": {
                    "assetKind": "Instance",
                    "globalAssetId": asset["assetId"],
                },
                "submodels": [
                    {"type": "ModelReference", "keys": [{"type": "Submodel", "value": submodel["id"]}]}
                    for submodel in submodels
                ],
            }],
            "submodels": submodels,
            "conceptDescriptions": [],
        },
    }
    packet.update(core.security_fields(sensitivity, retention))
    return packet


def _json_id_shorts(value: Any) -> set[str]:
    id_shorts: set[str] = set()
    stack = [value]
    while stack:
        item = stack.pop()
        if isinstance(item, dict):
            id_short = item.get("idShort")
            if isinstance(id_short, str) and id_short:
                id_shorts.add(id_short)
            stack.extend(item.values())
        elif isinstance(item, list):
            stack.extend(item)
    return id_shorts


def _aas_child(element: dict[str, Any], id_short: str) -> dict[str, Any] | None:
    value = element.get("value")
    if not isinstance(value, list):
        return None
    for child in value:
        if isinstance(child, dict) and child.get("idShort") == id_short:
            return child
    return None


def _aas_child_text(element: dict[str, Any], id_short: str) -> bool:
    child = _aas_child(element, id_short)
    return isinstance(child, dict) and _has_text(child.get("value"))


def _aas_child_nonempty_list(element: dict[str, Any], id_short: str) -> bool:
    child = _aas_child(element, id_short)
    return isinstance(child, dict) and isinstance(child.get("value"), list) and bool(child["value"])


def _assessment_summary_elements(packet: dict[str, Any]) -> list[dict[str, Any]]:
    env = packet.get("aasEnvironment")
    submodels = env.get("submodels") if isinstance(env, dict) else None
    if not isinstance(submodels, list):
        return []
    out: list[dict[str, Any]] = []
    for submodel in submodels:
        if not isinstance(submodel, dict) or submodel.get("idShort") != "AssessmentRecords":
            continue
        for element in submodel.get("submodelElements") or []:
            if not isinstance(element, dict) or element.get("idShort") != "Records":
                continue
            summary = _aas_child(element, "assessmentSummary")
            if isinstance(summary, dict):
                out.append(summary)
    return out


def _validate_aas_consensus(summary_elements: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    for summary in summary_elements:
        consensus = _aas_child(summary, "consensus")
        if not isinstance(consensus, dict):
            errors.append("assessmentSummary.consensus required")
            continue
        items = consensus.get("value")
        if not isinstance(items, list):
            errors.append("assessmentSummary.consensus must be a list")
            continue
        for i, item in enumerate(items):
            if not isinstance(item, dict) or item.get("modelType") != "SubmodelElementCollection":
                errors.append(f"assessmentSummary.consensus[{i}] must be a collection with statement and participants")
                continue
            if not _aas_child_text(item, "statement"):
                errors.append(f"assessmentSummary.consensus[{i}].statement required")
            if not _aas_child_nonempty_list(item, "participants"):
                errors.append(f"assessmentSummary.consensus[{i}].participants required")
    return errors


def validate_assessment_packet(packet: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(packet, dict):
        return ["packet must be a JSON object"]
    if packet.get("schemaVersion") != ASSESSMENT_PACKET_VERSION:
        errors.append(f"schemaVersion must be {ASSESSMENT_PACKET_VERSION}")
    asset = packet.get("asset")
    if not isinstance(asset, dict) or not asset.get("assetId"):
        errors.append("asset.assetId required")
    env = packet.get("aasEnvironment")
    if not isinstance(env, dict):
        errors.append("aasEnvironment required")
        return errors
    shells = env.get("assetAdministrationShells")
    if not isinstance(shells, list) or not shells:
        errors.append("aasEnvironment.assetAdministrationShells required")
    submodels = env.get("submodels")
    if not isinstance(submodels, list):
        errors.append("aasEnvironment.submodels must be a list")
        return errors
    present = {row.get("idShort") for row in submodels if isinstance(row, dict)}
    for name in ASSESSMENT_SUBMODELS:
        if name not in present:
            errors.append(f"missing submodel: {name}")
    id_shorts = _json_id_shorts(packet)
    for name in ASSESSMENT_ID_SHORTS:
        if name not in id_shorts:
            errors.append(f"missing field idShort: {name}")
    summary_elements = _assessment_summary_elements(packet)
    if not summary_elements and "AssessmentRecords" in present:
        errors.append("AssessmentRecords.assessmentSummary required")
    errors.extend(_validate_aas_consensus(summary_elements))
    return errors
