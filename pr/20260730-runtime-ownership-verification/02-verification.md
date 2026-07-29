Verification
============

Commands
--------

Run with local EasyNet-Cli and EasyNet-Axon SDK sources on `PYTHONPATH`:

```bash
PYTHONPATH=/Users/macbook.silan.tech/Documents/GitHub/EasyNet-Cli/sdk/python:/Users/macbook.silan.tech/Documents/GitHub/EasyNet-Axon/sdk/python:$PYTHONPATH \
  python -m pytest \
    tests/test_runtime_lifecycle_ownership.py \
    tests/test_invocation.py \
    tests/test_client.py \
    tests/test_control.py \
    tests/test_mission.py \
    tests/test_pipeline.py \
    -q
```

Result
------

- Passed: `143 passed in 0.81s`.

Audit notes
-----------

- Production `gateway` handling only warns when it disagrees with paired daemon identity; it does not start or reroute Hub lifecycle.
- Production host context creates parent causal anchors through `easynet_sdk.RuntimeReceipt.from_required_mapping`.
- Static scan found no production `start_hub`, `start_daemon`, `DaemonHandle`, `backend_ura`, or `user_ura` usage in `easyremote/`.
