# Invariants

1. EasyRemote does not parse runtime credentials directly.
2. EasyRemote uses `easynet_sdk.SdkEnvironment` for control-root scoped
   runtime identity projection.
3. Missing credentials still surface as `Unavailable(reason="not_paired")`.
4. Malformed credentials remain actionable and do not degrade into empty
   identities.
5. No private-key, keyring or signing material enters EasyRemote.
