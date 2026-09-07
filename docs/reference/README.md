# industrial-ai-platform-aws — Phase 0 Forensic Analysis

This directory is the **specification** for the AWS-native port of the
current `industrial-ai-platform` (Azure) repository. It was produced by
inspecting the actual current source code — not from memory — and is the
authoritative reference the AWS implementation must satisfy.

## Reading order

1. `EVENT_CONTRACT.md` — the Generic Envelope (Phase 0D)
2. `CONFIGURATION_CONTRACT.md` — settings + config-driven asset types (0C)
3. `CURRENT_AZURE_DATA_FLOW.md` — end-to-end flow, corrected (0B)
4. `CONSUMER_BEHAVIOUR.md` — ingestion + P0-01 checkpoint ordering (0E)
5. `DATABRICKS_BEHAVIOUR.md` — bundle, DLT, jobs, UC (0F)
6. `ML_BEHAVIOUR.md` — leakage-safe ML methodology (0G)
7. `TERRAFORM_COMPONENT_MAPPING.md` — infra modules (0H)
8. `CICD_BEHAVIOUR.md` — GitHub Actions workflows (0I)
9. `TEST_COVERAGE_MAP.md` — port/adapt/replace decisions (0J)
10. `AZURE_COMPONENT_INVENTORY.md` — every component classified (0A)

Then `../aws/AZURE_TO_AWS_MAPPING.md` (0K) and `../aws/AWS_PARITY_MATRIX.md`
(Phase 1).

## Governing principles (from the task spec)

- Faithful AWS translation of the CURRENT platform — not a redesign, demo, or
  generic template.
- **Cloud agnosticism abandoned**: AWS-native services used directly, no
  abstraction layer / provider factory.
- **Domain agnosticism preserved**: one envelope, one ingestion path, one
  Bronze/Silver path, config-driven asset types, one production DLT pipeline.
- Do not regress hardening: checkpoint ordering, lazy credential init,
  config-driven onboarding, single DLT path, deterministic ML.
