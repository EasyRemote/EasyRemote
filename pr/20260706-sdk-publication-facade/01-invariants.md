# Invariants

- EasyRemote production code must keep depending on `easynet-sdk`, not
  `easynet-run-axon`, raw Axon modules, or raw C ABI symbols.
- Do not reintroduce an EasyRemote-local Resource URA grammar or descriptor
  grammar.
- The in-memory identity facade used by tests must expose the same method
  shape consumed by the SDK facade: `resource_ura(owner_ura, path)`.
- User-owned ability filtering must use `parse_ura` projection components, not
  owner string parsing in product code.
- EasyRemote runtime tests must pass with the sibling EasyNet-Cli SDK on
  `PYTHONPATH`.
