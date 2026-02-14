# EasyRemote Documentation Center

Author: Silan Hu (silan.hu@u.nus.edu)

## Recommended reading order

1. [Quick Start](user-guide/quick-start.md)
2. [Installation](user-guide/installation.md)
3. [Examples](user-guide/examples.md)
4. [Whitepaper](research/whitepaper.md)
5. [Research Proposal](research/research-proposal.md)
6. [Pitch](research/pitch.md)
7. [Killer Apps Gallery](../../gallery/README.md)
8. [Gallery Projects](../../gallery/projects/README.md)

## Document structure

```text
docs/en/
├── README.md
├── user-guide/
│   ├── quick-start.md
│   ├── installation.md
│   └── examples.md
└── research/
    ├── whitepaper.md
    ├── research-proposal.md
    └── pitch.md
```

## Protocol references

- MCP implemented scope: `docs/ai/mcp-integration.md`
- A2A implemented scope: `docs/ai/a2a-integration.md`
- Agent-side gateway proxy runtime: `EasyRemoteClientRuntime` (see MCP/A2A guides section 2.3)
- Capability Management Protocol (CMP): `docs/CAPABILITY_MANAGEMENT_PROTOCOL.md`
- Protocol conformance tests: `tests/test_protocol_adapters.py`
- Killer-app catalog: `gallery/README.md` and `gallery/killer_apps.md`
- Quickstart projects: `gallery/projects/README.md`
