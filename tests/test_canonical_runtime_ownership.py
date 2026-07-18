"""Architecture gates for canonical SDK ownership in EasyRemote."""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "easyremote"
POLICY_PATH = PACKAGE / "edge-adapter-policy.v1.json"

RESERVED_ADAPTER_NAMES = {
    "Arguments",
    "CausalRef",
    "DescriptorProjection",
    "IdentityFacade",
    "InvocationTuple",
    "MerkleAnchor",
    "Receipt",
    "ReceiptChain",
    "UraProjection",
}
FORBIDDEN_INVOCATION_FUNCTIONS = {
    "_encode_causal",
    "canonical_bytes",
    "encode_invocation",
    "fresh_nonce",
}
CANONICAL_INVOCATION_FIELDS = {
    "ability",
    "arguments",
    "args",
    "callee",
    "callee_ura",
    "caller",
    "caller_ura",
    "causal",
    "causal_context",
    "descriptor_ref",
    "nonce",
    "nonce_base64",
    "subject",
    "subject_ura",
}
CANONICAL_RECEIPT_FIELDS = {
    "index",
    "invocation_id",
    "prev_receipt_hash",
    "prev_receipt_hash_hex",
    "receipt_type",
    "receipt_ura",
    "self_hash",
    "self_hash_hex",
    "state",
    "timestamp_unix_ms",
}
URA_GRAMMAR_VERBS = re.compile(
    r"(?:canonicali[sz]e|decode|encode|normalize|parse|project|split|tokenize)"
)
RETIRED_ADDRESS_TERM = "".join(("u", "r", "i"))
NON_URA_ADDRESS_TOKEN = re.compile(
    rf"(?i)(?:\b{RETIRED_ADDRESS_TERM}\b|"
    rf"\b{RETIRED_ADDRESS_TERM}_[a-z0-9_]*\b|"
    rf"\b[a-z0-9_]*_{RETIRED_ADDRESS_TERM}\b)"
)


def test_edge_adapter_policy_is_versioned_and_matches_package() -> None:
    policy = _policy()
    version_source = (PACKAGE / "_version.py").read_text(encoding="utf-8")
    version_tree = ast.parse(version_source)
    assignment = next(
        node
        for node in version_tree.body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "__version__"
            for target in node.targets
        )
    )
    assert isinstance(assignment.value, ast.Constant)

    assert policy["schema_version"] == 1
    assert policy["package"] == {
        "name": "easyremote",
        "current_version": assignment.value.value,
    }
    assert policy["removal_version"] == "3.0.0"
    assert int(policy["removal_version"].split(".", maxsplit=1)[0]) > int(
        policy["package"]["current_version"].split(".", maxsplit=1)[0]
    )
    assert policy["zero_new_internal_callers"] is True


def test_only_policy_enumerated_delegation_adapters_are_present() -> None:
    sources = _production_sources()
    policy = _policy()
    adapters = _adapter_records(policy)

    assert _canonical_model_violations(sources, adapters) == []
    assert _adapter_shape_violations(sources, adapters) == []


def test_policy_adapters_have_zero_new_internal_callers() -> None:
    sources = _production_sources()
    policy = _policy()

    assert _internal_adapter_callers(sources, policy) == []


def test_receipt_chain_adapter_contains_no_local_chain_rule() -> None:
    source = (PACKAGE / "receipts.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    receipt_chain = _class_node(tree, "ReceiptChain")
    verify = _method_node(receipt_chain, "verify_continuity")
    attributes = {
        node.attr for node in ast.walk(verify) if isinstance(node, ast.Attribute)
    }

    assert "prev_receipt_hash" not in attributes
    assert "self_hash" not in attributes
    assert any(isinstance(node, ast.Raise) for node in ast.walk(verify))
    assert "easynet_sdk.ReceiptClient.verify_chain" in source


def test_receipt_lifecycle_is_fail_closed_by_the_sdk_type() -> None:
    source = (PACKAGE / "receipts.py").read_text(encoding="utf-8")

    assert _receipt_lifecycle_authority_violations(source) == []


def test_edge_adapter_warning_matches_policy_removal_version() -> None:
    client = (PACKAGE / "client.py").read_text(encoding="utf-8")
    removal_version = _policy()["removal_version"]

    assert f"in EasyRemote {removal_version}; use invocation_policy" in client


def test_production_has_no_local_ura_grammar_or_retired_address_term() -> None:
    assert not (PACKAGE / "_sdk_identity.py").exists()
    assert _ura_violations(_production_sources()) == []


def test_sdk_provider_path_is_load_bearing() -> None:
    client = (PACKAGE / "client.py").read_text(encoding="utf-8")
    transport = (PACKAGE / "_sdk_transport" / "__init__.py").read_text(encoding="utf-8")
    invocation = (PACKAGE / "invocation.py").read_text(encoding="utf-8")
    receipts = (PACKAGE / "receipts.py").read_text(encoding="utf-8")
    addressing = (PACKAGE / "_addressing.py").read_text(encoding="utf-8")
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")

    assert "build_target_invocation(request)" in client
    assert 'candidate.get("ability_ura")' in client
    assert "info.ability_ura" in addressing
    assert "easynet_sdk.AbilityInvocationClient" in transport
    assert "class InvocationTuple:" in invocation
    assert "easynet_sdk.InvocationWireProjector" in invocation
    assert 'state_code = response.get("state")' in invocation
    assert 'frame.get("terminal")' not in transport
    assert "hasattr(config" not in transport
    assert "easynet_sdk.RuntimeReceipt.from_required_mapping" in receipts
    assert '"edge-adapter-policy.v1.json"' in pyproject
    assert "../EasyNet-Axon/sdk/python" not in pyproject


def test_negative_fixtures_detect_second_authorities() -> None:
    adapters = _adapter_records(_policy())
    renamed_invocation = {
        "bad_invocation.py": """
class RuntimeEnvelope:
    caller_ura: str
    callee_ura: str
    descriptor_ref: str
    subject_ura: str
    nonce_base64: str
    causal_context: dict
    args: object
""",
    }
    renamed_receipt = {
        "bad_receipt.py": """
class RuntimeProof:
    receipt_ura: str
    invocation_id: str
    receipt_type: str
    state: str
    prev_receipt_hash_hex: str
    self_hash_hex: str
""",
    }
    unauthorized_named_adapter = {
        "bad_named.py": """
class InvocationTuple:
    caller: str
    callee: str
    ability: str
    subject: str
    nonce: bytes
    causal: object
    arguments: object
""",
    }
    renamed_ura_parser = {
        "bad_identity.py": """
def decode_ability_ura(ability_ura):
    return ability_ura.split("/")
""",
    }
    embedded_grammar = {
        "bad_literal.py": 'PREFIX = "easynet:///"\n',
    }
    retired_address_term = {
        "bad_term.py": f"{RETIRED_ADDRESS_TERM}_value = 'legacy'\n",
    }
    fail_open_receipt_lifecycle = """
def _decode_runtime_receipt(value):
    receipt = easynet_sdk.RuntimeReceipt.from_required_mapping(value)
    normalized = receipt.state.replace("_", "").lower()
    for state in InvocationState:
        if state.name.lower() == normalized:
            return receipt, state
    return receipt, InvocationState.UNSPECIFIED
"""

    assert _canonical_model_violations(renamed_invocation, adapters)
    assert _canonical_model_violations(renamed_receipt, adapters)
    assert _canonical_model_violations(unauthorized_named_adapter, adapters)
    assert _ura_violations(renamed_ura_parser)
    assert _ura_violations(embedded_grammar)
    assert _ura_violations(retired_address_term)
    assert _receipt_lifecycle_authority_violations(fail_open_receipt_lifecycle)


def _policy() -> dict[str, Any]:
    value = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _adapter_records(
    policy: dict[str, Any],
) -> dict[tuple[str, str], dict[str, Any]]:
    records: dict[tuple[str, str], dict[str, Any]] = {}
    for adapter in policy["adapters"]:
        key = (adapter["module"], adapter["symbol"])
        assert key not in records
        records[key] = adapter
    return records


def _production_sources() -> dict[str, str]:
    return {
        str(path.relative_to(ROOT)): path.read_text(encoding="utf-8")
        for path in sorted(PACKAGE.rglob("*.py"))
    }


def _canonical_model_violations(
    sources: dict[str, str],
    adapters: dict[tuple[str, str], dict[str, Any]],
) -> list[str]:
    violations: list[str] = []
    for name, source in sources.items():
        tree = ast.parse(source, filename=name)
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                fields = _public_class_fields(node)
                adapter = adapters.get((name, node.name))
                if node.name in RESERVED_ADAPTER_NAMES and adapter is None:
                    violations.append(f"{name}: unlisted adapter class {node.name}")
                if len(fields & CANONICAL_INVOCATION_FIELDS) >= 6 and adapter is None:
                    violations.append(
                        f"{name}: structurally complete local Invocation model"
                    )
                if len(fields & CANONICAL_RECEIPT_FIELDS) >= 5 and adapter is None:
                    violations.append(
                        f"{name}: structurally complete local receipt model"
                    )
            if (
                isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
                and node.name in FORBIDDEN_INVOCATION_FUNCTIONS
            ):
                violations.append(f"{name}: local canonical function {node.name}")
    return violations


def _adapter_shape_violations(
    sources: dict[str, str],
    adapters: dict[tuple[str, str], dict[str, Any]],
) -> list[str]:
    violations: list[str] = []
    for (module, symbol), adapter in adapters.items():
        if "." in symbol:
            continue
        tree = ast.parse(sources[module], filename=module)
        matches = [
            node
            for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name == symbol
        ]
        if len(matches) != 1:
            violations.append(f"{module}: expected exactly one class {symbol}")
            continue
        expected = set(adapter["public_fields"])
        actual = _public_class_fields(matches[0])
        if actual != expected:
            violations.append(
                f"{module}: {symbol} fields {sorted(actual)} != {sorted(expected)}"
            )
    return violations


def _internal_adapter_callers(
    sources: dict[str, str],
    policy: dict[str, Any],
) -> list[str]:
    violations: list[str] = []
    reexports = set(policy["reexport_modules"])
    for adapter in policy["adapters"]:
        symbol = adapter["symbol"]
        module = adapter["module"]
        if symbol == "CallTarget.subject/causal":
            for name, source in sources.items():
                if name == module:
                    continue
                if re.search(
                    r"\b(?:Client\.target|CallTarget)\s*"
                    r"\([^)]*\b(?:subject|causal)\s*=",
                    source,
                ):
                    violations.append(
                        f"{name}: internal released target adapter caller"
                    )
            continue
        if symbol == "PreparedInvocation.with_causal":
            for name, source in sources.items():
                if name == module:
                    continue
                tree = ast.parse(source, filename=name)
                if any(
                    isinstance(node, ast.Attribute) and node.attr == "with_causal"
                    for node in ast.walk(tree)
                ):
                    violations.append(f"{name}: internal with_causal adapter caller")
            continue
        for name, source in sources.items():
            if name == module or name in reexports:
                continue
            tree = ast.parse(source, filename=name)
            if any(
                isinstance(node, ast.Name) and node.id == symbol
                for node in ast.walk(tree)
            ):
                violations.append(f"{name}: internal {symbol} adapter caller")
    return violations


def _ura_violations(sources: dict[str, str]) -> list[str]:
    violations: list[str] = []
    for name, source in sources.items():
        tree = ast.parse(source, filename=name)
        if NON_URA_ADDRESS_TOKEN.search(source):
            violations.append(f"{name}: retired non-URA address terminology")
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                normalized = node.name.lower()
                if node.name in {
                    "DescriptorProjection",
                    "IdentityFacade",
                    "UraProjection",
                } or ("ura" in normalized and URA_GRAMMAR_VERBS.search(normalized)):
                    violations.append(f"{name}: local URA projection {node.name}")
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                normalized = node.name.lower()
                if "ura" in normalized and URA_GRAMMAR_VERBS.search(normalized):
                    violations.append(f"{name}: local URA parser {node.name}")
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in {"partition", "removeprefix", "rsplit", "split"}
                and _expression_mentions_ura(node.func.value)
            ):
                violations.append(f"{name}: local URA tokenization")
        if "easynet:///" in source:
            violations.append(f"{name}: embedded URA grammar literal")
    return violations


def _receipt_lifecycle_authority_violations(source: str) -> list[str]:
    violations: list[str] = []
    tree = ast.parse(source)
    decoders = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "_decode_runtime_receipt"
    ]
    if len(decoders) != 1:
        return ["receipt lifecycle must have exactly one canonical decoder"]
    decoder = decoders[0]
    sdk_lookups = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Subscript)
        and isinstance(node.value, ast.Attribute)
        and isinstance(node.value.value, ast.Name)
        and node.value.value.id == "easynet_sdk"
        and node.value.attr == "InvocationLifecycleState"
    ]
    if len(sdk_lookups) != 1:
        violations.append(
            "receipt lifecycle projection must use exactly one SDK enum lookup"
        )
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
            and node.name == "_lifecycle_state"
        ):
            violations.append("local receipt lifecycle decoder")
        if isinstance(node, ast.Call) and (
            (isinstance(node.func, ast.Name) and node.func.id == "InvocationState")
            or (
                isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "easynet_sdk"
                and node.func.attr == "InvocationLifecycleState"
            )
        ):
            violations.append("numeric receipt lifecycle interpretation")
        if (
            isinstance(node, ast.For)
            and isinstance(node.iter, ast.Name)
            and node.iter.id == "InvocationState"
        ):
            violations.append("local receipt lifecycle enumeration")
        if (
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id == "InvocationState"
            and node.attr == "UNSPECIFIED"
        ):
            violations.append("fail-open unspecified receipt lifecycle fallback")
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr
            in {
                "casefold",
                "lower",
                "removeprefix",
                "removesuffix",
                "replace",
                "strip",
            }
        ):
            violations.append("local receipt lifecycle normalization")
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "int"
        ):
            violations.append("numeric receipt lifecycle normalization")
    for lookup in sdk_lookups:
        guarded = next(
            (
                node
                for node in ast.walk(decoder)
                if isinstance(node, ast.Try)
                and any(lookup is child for child in ast.walk(node))
            ),
            None,
        )
        if guarded is None or not any(
            isinstance(handler.type, ast.Name)
            and handler.type.id == "KeyError"
            and any(isinstance(child, ast.Raise) for child in ast.walk(handler))
            for handler in guarded.handlers
        ):
            violations.append("SDK receipt lifecycle lookup is not fail closed")
    return violations


def _public_class_fields(node: ast.ClassDef) -> set[str]:
    return {
        child.target.id
        for child in node.body
        if isinstance(child, ast.AnnAssign)
        and isinstance(child.target, ast.Name)
        and not child.target.id.startswith("_")
    }


def _class_node(tree: ast.Module, name: str) -> ast.ClassDef:
    return next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == name
    )


def _method_node(node: ast.ClassDef, name: str) -> ast.FunctionDef:
    return next(
        child
        for child in node.body
        if isinstance(child, ast.FunctionDef) and child.name == name
    )


def _expression_mentions_ura(node: ast.AST) -> bool:
    return any(
        (isinstance(child, ast.Name) and "ura" in child.id.lower())
        or (isinstance(child, ast.Attribute) and "ura" in child.attr.lower())
        for child in ast.walk(node)
    )
