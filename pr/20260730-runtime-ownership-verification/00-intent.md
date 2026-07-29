Goal
====

Verify and lock EasyRemote's convergence to the canonical EasyNet runtime model:

- descriptor refs are descriptor-bound and supplied by the EasyNet-Cli SDK path;
- receipt parsing and lifecycle state are SDK-owned;
- EasyRemote does not own daemon or Hub lifecycle authority.

Non-goals
=========

- Do not implement a second daemon launcher, Hub provisioner, receipt parser, or descriptor-ref builder in EasyRemote.
- Do not loosen tests to accept legacy `ability@version` descriptor refs.
- Do not change production invocation behavior unless a test or audit finds an actual ownership leak.
