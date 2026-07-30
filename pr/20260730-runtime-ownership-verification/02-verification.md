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
- Passed:

```bash
PYTHONPATH=/Users/macbook.silan.tech/Documents/GitHub/EasyNet-Cli/sdk/python:/Users/macbook.silan.tech/Documents/GitHub/EasyNet-Axon/sdk/python \
  python -m pytest -q tests/test_invocation_ingress_ownership.py
```

  Result: `3 passed in 0.50s`.

- Passed:

```bash
PYTHONPATH=/Users/macbook.silan.tech/Documents/GitHub/EasyNet-Cli/sdk/python:/Users/macbook.silan.tech/Documents/GitHub/EasyNet-Axon/sdk/python \
  python -m pytest -q
```

  Result: `317 passed, 3 skipped, 2 warnings in 1.48s`.

- Passed:

```bash
python -m ruff check tests/test_invocation_ingress_ownership.py
```

  Result: `All checks passed!`.

Audit notes
-----------

- Production `gateway` handling only warns when it disagrees with paired daemon identity; it does not start or reroute Hub lifecycle.
- Production host context creates parent causal anchors through `easynet_sdk.RuntimeReceipt.from_required_mapping`.
- Static scan found no production `start_hub`, `start_daemon`, `DaemonHandle`, `backend_ura`, or `user_ura` usage in `easyremote/`.
- `tests/test_invocation_ingress_ownership.py` now also rejects any
  `runtime_root_context` call that is not an argument to one of the SDK-backed
  system adapters: `list_ability_descriptors`, `invoke_runtime_ability`, or
  `invocation_trace`.
