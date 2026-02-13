# Gallery Smoke Test Report

Author: Silan Hu (silan.hu@u.nus.edu)

Generated at (UTC): 2026-02-13T11:44:23.573946+00:00

| Case | Route | Status | Duration(s) | Detail |
|---|---|---:|---:|---|
| P1 MCP Tool Mesh | agent | PASS | 0.11 | ok |
| P2 A2A Incident Copilot | agent | PASS | 0.09 | ok |
| P3 Function Marketplace Agent Route | agent | PASS | 0.09 | ok |
| P4 Local Data Residency Agent Route | agent | PASS | 0.11 | ok |
| H1 Basic Remote Math | human | PASS | 4.51 | 19:44:07 INFO ℹ️ Initialized DistributedComputingClient 'client-macbook-air--46d499c6' targeting 127.0.0.1:18080 19:44:07 INFO ℹ️ Successfully connected to gateway at 127.0.0.1:18080 add_numbers => 42 process_payload ... |
| H2 Team GPU Pool | human | PASS | 6.91 | 19:44:11 INFO ℹ️ Initialized DistributedComputingClient 'client-macbook-air--6bdd7460' targeting 127.0.0.1:18081 19:44:11 INFO ℹ️ Successfully connected to gateway at 127.0.0.1:18081 {'node_id': 'gpu-beta', 'model_nam... |
| H3 Function Marketplace Human Route | human | PASS | 4.62 | 19:44:18 INFO ℹ️ Initialized DistributedComputingClient 'client-macbook-air--0e4b4c94' targeting 127.0.0.1:18082 19:44:18 INFO ℹ️ Successfully connected to gateway at 127.0.0.1:18082 calculate_margin => {'margin': 340... |
| H4 Local Data Residency Human Route | human | PASS | 4.52 | 19:44:23 INFO ℹ️ Initialized DistributedComputingClient 'client-macbook-air--6eb08ee3' targeting 127.0.0.1:18083 19:44:23 INFO ℹ️ Successfully connected to gateway at 127.0.0.1:18083 sanitize_claim_record => {'patient... |

## Conclusion

All smoke cases passed.
