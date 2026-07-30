# Verification

- `uv run pytest -q tests/test_runtime_lifecycle_ownership.py tests/test_client.py -k 'functions or runtime_lifecycle_ownership'`
- `rg -n 'runtime://|backend_ura|user_ura|state_code|auth_binding|authority_binding' tests easyremote -S`
- `uv run pytest -q`
- `rg -n 'runtime://|backend_ura|user_ura|state_code|auth_binding' tests easyremote -S` returns no matches.
