"""Contract checks for independently runnable concrete-use-case projects."""

from __future__ import annotations

import importlib
import runpy
import sys
import tomllib
from pathlib import Path

import pytest

import easyremote.config as config
from easyremote import Context, StreamFrame

PROJECT_ROOT = Path(__file__).parents[1] / "gallery" / "projects"
PROJECTS = (
    "00_basic_remote_math",
    "01_team_gpu_pool_load_balancing",
    "02_mcp_tool_mesh",
    "03_a2a_incident_copilot",
    "04_function_marketplace",
    "05_local_data_residency_ai",
    "06_runtime_device_capability_injection",
    "07_claude_code_robot_commander_mcp",
    "08_network_native_python_library",
)
REQUIRED_FILES = ("README.md", "pyproject.toml", "uv.lock", "node.py", "client.py")
REQUIRED_SECTIONS = (
    "## Concrete use case",
    "## Requirements",
    "## Existing approach",
    "## EasyRemote approach",
    "## Effect",
    "## Run",
)


def test_gallery_projects_are_independent_uv_applications() -> None:
    assert (
        tuple(path.name for path in sorted(PROJECT_ROOT.iterdir()) if path.is_dir())
        == PROJECTS
    )

    for project_name in PROJECTS:
        project = PROJECT_ROOT / project_name
        for filename in REQUIRED_FILES:
            assert (project / filename).is_file(), f"{project_name}/{filename}"

        manifest = tomllib.loads((project / "pyproject.toml").read_text())
        dependencies = set(manifest["project"]["dependencies"])
        sources = manifest["tool"]["uv"]["sources"]
        assert "easyremote" in dependencies
        assert "easynet-sdk>=0.142.22,<0.143" in dependencies
        assert sources["easyremote"] == {"path": "../../..", "editable": True}
        assert sources["easynet-sdk"] == {
            "path": "../../../../EasyNet-Cli/sdk/python",
            "editable": True,
        }
        lock = tomllib.loads((project / "uv.lock").read_text())
        assert lock["version"] >= 1


def test_gallery_readmes_are_concise_use_case_papers() -> None:
    for project_name in PROJECTS:
        readme = (PROJECT_ROOT / project_name / "README.md").read_text()
        positions = [readme.index(section) for section in REQUIRED_SECTIONS]
        assert positions == sorted(positions), project_name
        assert 250 <= len(readme.split()) <= 700, project_name


def test_gallery_code_uses_only_the_public_decorator_boundary() -> None:
    for project_name in PROJECTS:
        project = PROJECT_ROOT / project_name
        node_source = (project / "node.py").read_text()
        client_source = (project / "client.py").read_text()

        compile(node_source, str(project / "node.py"), "exec")
        compile(client_source, str(project / "client.py"), "exec")
        assert "@node.register" in node_source, project_name
        if project_name == "08_network_native_python_library":
            assert "from easyremote.silan.lotus import" in client_source
        else:
            assert "@remote(" in client_source, project_name
        assert "subprocess" not in node_source, project_name
        assert "os.system" not in node_source, project_name


def test_gallery_modules_initialize_without_external_services(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(config, "_settings", None)
    config.configure(control=tmp_path / "control.json")

    for project_name in PROJECTS:
        project = PROJECT_ROOT / project_name
        provider = runpy.run_path(str(project / "node.py"))
        if project_name == "08_network_native_python_library":
            from easyremote import install_library

            monkeypatch.setenv("EASYREMOTE_LIBRARY_ROOT", str(tmp_path / "libraries"))
            install_library(project / "library.json", root=tmp_path / "libraries")
            importlib.invalidate_caches()
            sys.modules.pop("easyremote.silan.lotus", None)
            sys.modules.pop("easyremote.silan", None)
            caller = runpy.run_path(str(project / "client.py"))
            assert callable(caller["semantic_filter"])
            assert callable(caller["semantic_map"])
            assert provider["node"].abilities
            continue
        caller = runpy.run_path(str(project / "client.py"))

        assert provider["node"].abilities, project_name
        caller["client"].close()


def test_gallery_provider_behaviors_are_bounded(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(config, "_settings", None)
    config.configure(control=tmp_path / "control.json")
    caller = "easynet:///r/acme/user/00000000-0000-0000-0000-000000000001"

    quote = runpy.run_path(str(PROJECT_ROOT / PROJECTS[0] / "node.py"))
    assert quote["calculate_quote"](10)["total_cents"] == 397_800
    with pytest.raises(ValueError, match="between 1 and 5,000"):
        quote["calculate_quote"](0)

    model = runpy.run_path(str(PROJECT_ROOT / PROJECTS[1] / "node.py"))
    embedding = model["embed_text"]("bounded model call")
    assert embedding == model["embed_text"]("bounded model call")
    assert len(embedding) == 8
    assert model["embed_text"]("Capability sharing keeps model custody local.") == [
        0.362116,
        0.664379,
        0.475839,
        0.092774,
        0.242409,
        0.194525,
        0.152628,
        0.269343,
    ]
    with pytest.raises(ValueError, match="must not be empty"):
        model["embed_text"]("   ")

    tools = runpy.run_path(str(PROJECT_ROOT / PROJECTS[2] / "node.py"))
    assert tools["lookup_account"]("acme")["health"] == 82
    assert tools["revenue_trend"]("acme", 2) == [151_000, 159_000]
    context = Context(invocation_id="inv-followup-1", caller=caller)
    first_task = tools["create_followup"](context, "acme", "alex", 5)
    assert tools["create_followup"](context, "acme", "alex", 5) == first_task
    with pytest.raises(ValueError, match="between 1 and 30"):
        tools["create_followup"](context, "acme", "alex", 31)
    bounded_store = tools["FollowupStore"](capacity=1)
    bounded_store.create(
        invocation_id="inv-a",
        requested_by=caller,
        account_id="acme",
        owner="alex",
        due_in_days=5,
    )
    with pytest.raises(ValueError, match="capacity reached"):
        bounded_store.create(
            invocation_id="inv-b",
            requested_by=caller,
            account_id="acme",
            owner="alex",
            due_in_days=5,
        )

    incident = runpy.run_path(str(PROJECT_ROOT / PROJECTS[3] / "node.py"))
    diagnosis = incident["diagnose_service"](
        Context(invocation_id="inv-incident-1", caller=caller), "api", 15
    )
    assert diagnosis["status"] == "degraded"
    evidence = list(incident["stream_evidence"]("api", 2))
    assert [sample["sequence"] for sample in evidence] == [1, 2]
    with pytest.raises(ValueError, match="service must be one of"):
        list(incident["stream_evidence"]("unknown", 1))

    marketplace = runpy.run_path(str(PROJECT_ROOT / PROJECTS[4] / "node.py"))
    assert marketplace["normalize_invoice"](12_500, "EUR")["usd_cents"] == 13_500
    assert marketplace["classify_ticket"]("Duplicate invoice charge") == "billing"
    assert marketplace["score_customer_health"](91, 1, 14) == 77
    with pytest.raises(ValueError, match="currency must be one of"):
        marketplace["normalize_invoice"](100, "GBP")

    residency = runpy.run_path(str(PROJECT_ROOT / PROJECTS[5] / "node.py"))
    summary = residency["summarize_patient_record"](
        Context(invocation_id="inv-record-1", caller=caller), "case-1042"
    )
    assert "Synthetic Alice" not in summary["summary"]
    assert summary["risk_labels"] == ["respiratory", "fever"]
    no_risk = residency["summarize_patient_record"](
        Context(invocation_id="inv-record-2", caller=caller), "case-2088"
    )
    assert no_risk["risk_labels"] == []

    camera = runpy.run_path(str(PROJECT_ROOT / PROJECTS[6] / "node.py"))
    frames = list(camera["camera_frames"](2, 16, 16))
    assert len(frames) == 2
    assert all(isinstance(frame, StreamFrame) for frame in frames)
    assert frames[0].content_type == "image/x-portable-graymap"
    assert frames[0].payload.startswith(b"P5\n16 16\n255\n")
    assert frames[0].payload != frames[1].payload
    with pytest.raises(ValueError, match="between 16 and 256"):
        list(camera["camera_frames"](1, 15, 16))

    robot = runpy.run_path(str(PROJECT_ROOT / PROJECTS[7] / "node.py"))
    state = robot["move_robot"](
        Context(invocation_id="inv-robot-1", caller=caller), 100
    )
    assert state["position_cm"] == 100
    assert state["battery_percent"] == 90
    assert [sample["sequence"] for sample in robot["robot_telemetry"](2)] == [1, 2]
    with pytest.raises(ValueError, match="excluding 0"):
        robot["move_robot"](Context(invocation_id="inv-robot-2", caller=caller), 0)

    library = runpy.run_path(str(PROJECT_ROOT / PROJECTS[8] / "node.py"))
    records = ["Invoice refund pending", "API latency normal"]
    assert library["semantic_filter"](records, "invoice billing") == [records[0]]
    assert library["semantic_map"](records, "lowercase") == [
        "invoice refund pending",
        "api latency normal",
    ]
    with pytest.raises(ValueError, match="instruction must be"):
        library["semantic_map"](records, "write a poem")
    with pytest.raises(ValueError, match="between 1 and 1,000 items"):
        library["semantic_filter"]([], "invoice")
    with pytest.raises(ValueError, match="between 1 and 500 characters"):
        library["semantic_filter"](records, "x" * 501)
    with pytest.raises(ValueError, match="searchable letters or numbers"):
        library["semantic_filter"](records, "---")
