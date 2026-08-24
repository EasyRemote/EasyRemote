# Invariants

- EasyRemote consumes only public `easynet_sdk` APIs and never binds a C symbol.
- The base ABI remains 7; v8 raw streaming is feature negotiated.
- Payload bytes and media type must survive exactly, including NUL, `0xff`, and
  an empty data frame.
- The smoke is opt-in because it installs an ability; cleanup always uninstalls
  the deployment and removes its package directory.
- Invocation authority, ordering, receipts, terminal state, and backpressure
  remain owned below the EasyRemote facade.
