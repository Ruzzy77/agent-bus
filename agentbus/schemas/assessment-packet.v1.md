# assessment-packet.v1

`assessment-packet.v1` carries operational data and assessment records in one JSON document. It is AAS-shaped and does not claim full AAS conformance.

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
| `AssessmentRecords` | Participants, assessment summary, communication records, and review items. |
| `WorkItems` | Work item lifecycle state and assignment. |
| `Traceability` | Asset id, data source, event cursors, and change events. |

`OperationalData` and `AssessmentRecords` stay in the same packet when the receiver needs an auditable data-and-judgment bundle.

`sensitivity` and `retention` are optional handling signals. Outbound adapters use them to block or allow external transfer.

## Assessment summary

`AssessmentRecords.assessmentSummary` is always present. It is empty unless `--assessment-summary <json>` is supplied.

| Field | Content |
| --- | --- |
| `individualAssessments` | Per-participant assessment notes and evidence references. |
| `consensus` | Points all or most participants agree on. |
| `disagreements` | Conflicting positions that affect the decision. |
| `partialEvidence` | Evidence only some participants considered, or evidence with limited coverage. |
| `uniqueFindings` | Findings raised by one participant or one source. |
| `blindSpots` | Missing observations, tests, or fields. |
| `decisionsNeeded` | Choices that need a human or next system action. |

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

The check verifies the packet version, asset id, AAS environment shape, required submodels, assessment summary fields, and required record lists. It is not an AAS conformance test.
