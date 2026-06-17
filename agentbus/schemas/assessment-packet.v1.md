# assessment-packet.v1

`assessment-packet.v1` carries operational data and assessment records in one JSON document. It is AAS-shaped for local exchange, with full AAS conformance handled by the surrounding integration layer.

The packet uses neutral external terms and avoids product names or project-coined terms.

## Shape

```json
{
  "schemaVersion": "assessment-packet.v1",
  "packetId": "pkt-...",
  "createdAt": "2026-06-15T00:00:00+00:00",
  "sensitivity": "confidential",
  "retention": "no_archive",
  "asset": {"assetId": "urn:example:asset:line-7-press-2"},
  "aasEnvironment": {
    "assetAdministrationShells": [],
    "submodels": [],
    "conceptDescriptions": []
  }
}
```

## Submodels

| `idShort` | Content |
| --- | --- |
| `OperationalData` | Manufacturing, process, sensor, or work data supplied by `--data`. |
| `AssessmentRecords` | Agent participants, lead synthesis, communication records, and review items. |
| `WorkItems` | Work item lifecycle state and assignment. |
| `Traceability` | Asset id, data source, event cursors, and change events. |

`OperationalData` and `AssessmentRecords` stay in the same packet when the receiver needs an auditable data-and-judgment bundle.

`sensitivity` and `retention` are optional handling signals. Outbound adapters use them to decide external transfer handling.

## Assessment summary

`AssessmentRecords.assessmentSummary` is always present. Supplying `--assessment-summary <json>` fills it with a lead-agent synthesis built from bus reports, evidence references, disagreements, and remaining decisions. agent-bus preserves and projects that synthesis; the lead agent owns the final judgment, user alignment, user-facing report, and follow-up interaction. `aas-packet` accepts object-shaped consensus entries with required fields, and `aas-packet-check` checks the projected AAS shape for the same minimum fields.

| Field | Content |
| --- | --- |
| `individualAssessments` | Per-participant objects with `participant`, `summary`, and optional evidence references. |
| `consensus` | Lead-synthesized agreement objects with `statement`, non-empty `participants`, and optional evidence or communication references. |
| `disagreements` | Objects with `topic` and participant `positions` that affect the decision. |
| `partialEvidence` | Evidence that is useful but still limited, partial, or agent-specific. |
| `uniqueFindings` | Objects with `finding` plus `participant` or `source`. |
| `evidenceGaps` | Missing observations, tests, fields, or verification links that the lead must account for. |
| `decisionsNeeded` | Choices the lead must resolve, ask the user about, or pass to the next workflow. |

## Field naming

| Raw source | Packet term |
| --- | --- |
| agent status | `participants` |
| judgment summary | `assessmentSummary` |
| messages | `communicationRecords` |
| tickets | `reviewItems` |
| tasks | `workItems` |
| refs | `evidenceReferences` |
| event stream | `changeEvents` |

## Check

```bash
agentbus aas-packet \
  --data agentbus/examples/aas/operational-data.sample.json \
  --asset-id urn:example:asset:line-7-press-2 \
  --assessment-summary agentbus/examples/aas/assessment-summary.sample.json \
  --out packet.json
agentbus aas-packet-check --file packet.json
```

The check verifies the packet version, asset id, AAS environment shape, required submodels, assessment summary fields, and required record lists. AAS conformance testing belongs to a dedicated AAS validator.
