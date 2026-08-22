# Notice

EasyRemote
Copyright (c) 2024-2026 Silan Hu

This product includes software developed by Silan Hu (silan.hu@u.nus.edu).

## Third-Party Runtime Components

EasyRemote is an MIT-licensed Python facade over the EasyNet runtime. The
following third-party or sibling-project components are relevant to normal
runtime use:

1. EasyNet-Axon
   - Role: protocol implementation consumed transitively by EasyNet CLI; it
     is not an EasyRemote package dependency.
   - License: Apache License 2.0.
   - Website: https://github.com/EasyRemote/EasyNet-Axon

2. EasyNet CLI / `easynet-sdk`
   - Role: the single EasyRemote SDK entrypoint for local daemon lifecycle,
     ability deployment, invocation, receipts, stream and bidi surfaces.
   - License: Apache License 2.0.
   - Website: https://github.com/EasyRemote/EasyNet-Cli
   - Note: not bundled in the pure Python wheel; users install EasyNet CLI or
     point `EASYNET_CLI_LIB` / `configure(library_path=...)` at an ABI v3
     library.

3. EasyNet
   - Role: backend/runtime family for EasyNet hubs and services that the
     EasyRemote facade is designed to work with.
   - License: Apache License 2.0.
   - Website: https://github.com/EasyRemote/EasyNet

4. pydantic (optional extra: `easyremote[pydantic]`)
   - Role: optional schema/model support when user function annotations use
     Pydantic models.
   - License: MIT License.
   - Website: https://github.com/pydantic/pydantic

5. cryptography (optional extra: `easyremote[gateway]`)
   - Role: optional self-signed TLS material generation for the hub wrapper.
   - License: Apache License 2.0 or BSD License.
   - Website: https://github.com/pyca/cryptography

Each component is provided under its own license terms. This notice is for
attribution and dependency clarity; it does not replace the license text in the
respective upstream projects.
