"""RF-8 gate for explicit public invocation-tuple derivation."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "easyremote"
CLIENT_MODULE = "easyremote/client.py"
POLICY_MODULE = "easyremote/invocation_policy.py"
CONTEXT_DISPATCH_MODULE = "easyremote/_context_dispatch.py"

FORBIDDEN_AUTHORITIES = {
    "DEFAULT_INVOCATION_POLICY",
    "default_subject_ura",
    "legacy_target_policy",
}
PUBLIC_DISPATCH_METHODS = {
    "call",
    "execute",
    "invoke",
    "prepare",
    "session",
    "stream",
}
RUNTIME_ROOT_CONTEXT_CONSUMERS = {
    "invocation_trace",
    "invoke_runtime_ability",
    "list_ability_descriptors",
}


def test_public_invocation_ingress_requires_explicit_policy() -> None:
    assert _invocation_ingress_violations(_production_sources()) == []


def test_runtime_root_context_is_confined_to_system_runtime_adapters() -> None:
    assert _runtime_root_context_violations(_production_sources()) == []


def test_invocation_ingress_gate_rejects_implicit_default_mutations() -> None:
    sources = _production_sources()

    client_default = _mutated(
        sources,
        CLIENT_MODULE,
        "invocation_policy: InvocationDerivationPolicy | None = None,",
        (
            "invocation_policy: InvocationDerivationPolicy | None = "
            "FreshRoot(ResolvedTargetSubject()),"
        ),
    )
    fail_open_prepare = _mutated(
        sources,
        CLIENT_MODULE,
        """        if policy is None:
            raise InvalidArgument(
                "public invocation requires an explicit derivation policy on"
                " Client or CallTarget",
                reason="missing_invocation_derivation_policy",
            )
""",
        """        if policy is None:
            policy = FreshRoot(ResolvedTargetSubject())
""",
    )
    hidden_subject_candidate = _mutated(
        sources,
        "easyremote/_addressing.py",
        "resolved_subject_ura: str",
        "default_subject_ura: str",
    )
    legacy_target_field = _mutated(
        sources,
        CLIENT_MODULE,
        "    sign: bool | None = None\n",
        "    subject: str | None = None\n    sign: bool | None = None\n",
    )
    direct_internal_ingress = dict(sources)
    direct_internal_ingress["easyremote/bad_control.py"] = """
def dispatch(client):
    return client.invoke("agent.start")
"""
    implicit_nonce_owner = dict(sources)
    implicit_nonce_owner["easyremote/bad_client.py"] = """
import easynet_sdk

def derive():
    return easynet_sdk.new_invocation_nonce_base64()
"""
    retired_default_authority = dict(sources)
    retired_default_authority[POLICY_MODULE] += """

DEFAULT_INVOCATION_POLICY = FreshRoot(ResolvedTargetSubject())
"""
    hidden_context_default = dict(sources)
    hidden_context_default[CONTEXT_DISPATCH_MODULE] += """

def _child_policy(parent):
    return ChildCausal(
        subject=ResolvedTargetSubject(),
        parent=parent,
    )
"""
    public_root_context = dict(sources)
    public_root_context["easyremote/bad_public.py"] = """
from .invocation_policy import runtime_root_context

def derive_public_tuple(client):
    local = client._who().device_ura
    return runtime_root_context(
        caller_ura=local,
        callee_ura=local,
        subject_ura=local,
    )
"""
    wrapped_wrong_consumer = dict(sources)
    wrapped_wrong_consumer["easyremote/bad_wrapper.py"] = """
from .invocation_policy import runtime_root_context

def dispatch(client):
    local = client._who().device_ura
    return client._connected().invoke(
        runtime_root_context(
            caller_ura=local,
            callee_ura=local,
            subject_ura=local,
        )
    )
"""

    assert _invocation_ingress_violations(client_default)
    assert _invocation_ingress_violations(fail_open_prepare)
    assert _invocation_ingress_violations(hidden_subject_candidate)
    assert _invocation_ingress_violations(legacy_target_field)
    assert _invocation_ingress_violations(direct_internal_ingress)
    assert _invocation_ingress_violations(implicit_nonce_owner)
    assert _invocation_ingress_violations(retired_default_authority)
    assert _invocation_ingress_violations(hidden_context_default)
    assert _runtime_root_context_violations(public_root_context)
    assert _runtime_root_context_violations(wrapped_wrong_consumer)


def _production_sources() -> dict[str, str]:
    return {
        str(path.relative_to(ROOT)): path.read_text(encoding="utf-8")
        for path in sorted(PACKAGE.rglob("*.py"))
    }


def _mutated(
    sources: dict[str, str],
    module: str,
    old: str,
    new: str,
) -> dict[str, str]:
    source = sources[module]
    assert old in source
    mutated = dict(sources)
    mutated[module] = source.replace(old, new, 1)
    return mutated


def _invocation_ingress_violations(sources: dict[str, str]) -> list[str]:
    violations: list[str] = []
    for name, source in sources.items():
        tree = ast.parse(source, filename=name)
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.FunctionDef)
                and name == CONTEXT_DISPATCH_MODULE
                and node.name == "_child_policy"
            ):
                violations.append(f"{name}: owns a hidden context derivation policy")
            elif isinstance(node, ast.Name) and node.id in FORBIDDEN_AUTHORITIES:
                violations.append(f"{name}: references retired authority {node.id}")
            elif (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and node.value in FORBIDDEN_AUTHORITIES
            ):
                violations.append(f"{name}: exports retired authority {node.value}")
            elif isinstance(node, ast.Attribute) and node.attr in FORBIDDEN_AUTHORITIES:
                violations.append(f"{name}: references retired authority {node.attr}")
            elif isinstance(node, ast.Call):
                call_name = _call_name(node.func)
                if (
                    name == CONTEXT_DISPATCH_MODULE
                    and call_name == "ResolvedTargetSubject"
                ):
                    violations.append(f"{name}: silently selects a context subject")
                if call_name == "new_invocation_nonce_base64" and name != POLICY_MODULE:
                    violations.append(f"{name}: owns implicit nonce derivation")
                if (
                    call_name in PUBLIC_DISPATCH_METHODS
                    and node.args
                    and isinstance(node.args[0], ast.Constant)
                    and isinstance(node.args[0].value, str)
                ):
                    violations.append(
                        f"{name}: dispatches a string target without explicit policy"
                    )
                if _qualified_call_name(node.func) == "Client.target" and not any(
                    keyword.arg == "invocation_policy" for keyword in node.keywords
                ):
                    violations.append(
                        f"{name}: constructs an internal target without explicit policy"
                    )

        if name == CLIENT_MODULE:
            violations.extend(_client_surface_violations(tree))
    return sorted(set(violations))


def _runtime_root_context_violations(sources: dict[str, str]) -> list[str]:
    violations: list[str] = []
    for name, source in sources.items():
        tree = ast.parse(source, filename=name)
        parents = _parent_index(tree)
        for node in ast.walk(tree):
            if (
                not isinstance(node, ast.Call)
                or _call_name(node.func) != "runtime_root_context"
            ):
                continue
            if not _is_runtime_root_context_adapter_argument(node, parents):
                violations.append(
                    f"{name}: runtime_root_context escapes system runtime "
                    "adapter boundary"
                )
    return sorted(set(violations))


def _is_runtime_root_context_adapter_argument(
    node: ast.AST,
    parents: dict[ast.AST, ast.AST],
) -> bool:
    current = node
    while parent := parents.get(current):
        if isinstance(parent, ast.Call):
            call_name = _call_name(parent.func)
            if call_name in RUNTIME_ROOT_CONTEXT_CONSUMERS:
                return True
            if call_name != "runtime_root_context":
                return False
        current = parent
    return False


def _parent_index(tree: ast.AST) -> dict[ast.AST, ast.AST]:
    parents: dict[ast.AST, ast.AST] = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parents[child] = parent
    return parents


def _client_surface_violations(tree: ast.Module) -> list[str]:
    violations: list[str] = []
    client = _class_node(tree, "Client")
    target = _class_node(tree, "CallTarget")
    init = _method_node(client, "__init__")
    prepare = _method_node(client, "_prepare_resolved")
    target_builder = _method_node(client, "target")

    init_defaults = _argument_defaults(init.args)
    policy_default = init_defaults.get("invocation_policy")
    if not (isinstance(policy_default, ast.Constant) and policy_default.value is None):
        violations.append(
            f"{CLIENT_MODULE}: Client invocation_policy is not fail-closed"
        )

    target_fields = {
        node.target.id
        for node in target.body
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name)
    }
    if target_fields & {"subject", "causal"}:
        violations.append(f"{CLIENT_MODULE}: CallTarget retains tuple defaults")

    target_parameters = {argument.arg for argument in target_builder.args.args}
    target_parameters.update(
        argument.arg for argument in target_builder.args.kwonlyargs
    )
    if target_parameters & {"subject", "causal"}:
        violations.append(f"{CLIENT_MODULE}: target builder retains tuple defaults")

    missing_policy_rejections = [
        node
        for node in ast.walk(prepare)
        if isinstance(node, ast.Call)
        and _call_name(node.func) == "InvalidArgument"
        and any(
            keyword.arg == "reason"
            and isinstance(keyword.value, ast.Constant)
            and keyword.value.value == "missing_invocation_derivation_policy"
            for keyword in node.keywords
        )
    ]
    if len(missing_policy_rejections) != 1:
        violations.append(
            f"{CLIENT_MODULE}: prepare lacks one explicit missing-policy rejection"
        )
    return violations


def _argument_defaults(arguments: ast.arguments) -> dict[str, ast.expr]:
    positional = [*arguments.posonlyargs, *arguments.args]
    positional_defaults = {
        argument.arg: default
        for argument, default in zip(
            positional[-len(arguments.defaults) :],
            arguments.defaults,
            strict=True,
        )
    }
    keyword_defaults = {
        argument.arg: default
        for argument, default in zip(
            arguments.kwonlyargs,
            arguments.kw_defaults,
            strict=True,
        )
        if default is not None
    }
    return positional_defaults | keyword_defaults


def _class_node(tree: ast.Module, name: str) -> ast.ClassDef:
    return next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == name
    )


def _method_node(owner: ast.ClassDef, name: str) -> ast.FunctionDef:
    return next(
        node
        for node in owner.body
        if isinstance(node, ast.FunctionDef) and node.name == name
    )


def _call_name(node: ast.expr) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return ""


def _qualified_call_name(node: ast.expr) -> str:
    if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
        return f"{node.value.id}.{node.attr}"
    return _call_name(node)
