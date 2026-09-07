# hybrid-mode-evidence.md
Edge/cloud/hybrid modes are carried by config-driven asset types (orchestrator_mode,
context_snapshot, bearing_inference, cloud_validation) — identical to Azure.
- Generator correctness (offline): test_generate_bearing_events (7) asserts Scenario B
  (agreement=0.5, cloud_accuracy=1.0), Scenario F confusion matrix, deterministic ids.
- NATS translate (mode transitions, context breach/heartbeat sampling): test_nats_bearing_bridge (14).
- CloudForest async second-opinion contract: test_train_..._contract + ml-evidence.
Reproducing mode_history / escalation_efficacy THROUGH deployed Gold tables: NOT EXECUTED
(needs live pipeline). The generator + translate assertions verify the input+routing contract.
