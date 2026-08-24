# Invariants

- ResourceRef owner is the selected Device, never the caller process.
- Bundle bytes enter the target tmp plane only through `fs.transfer` bidi.
- Upload chunks use the FileTransfer binary wire profile and canonical EOF.
- Deployment starts only after a verified completed terminal receipt proves
  byte count, SHA-256, and cleanup completion.
- `ability.deploy` receives only fields in its committed input schema.
- Local and remote targets use the same staging state transition.
