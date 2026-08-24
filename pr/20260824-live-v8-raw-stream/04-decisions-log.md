# Decisions

## 2026-08-24 — Opt-in mutating integration case

Keep the ordinary integration suite read-only. Require an explicit environment
flag for ability installation, and place generated packages under the daemon
state root so the device-local resource mapping is independent of the daemon's
process working directory.
