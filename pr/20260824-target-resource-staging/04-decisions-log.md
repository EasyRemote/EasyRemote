# Decisions log

- Rejected reordering `home` before `workspace`: it masks one local layout but
  keeps client-authored daemon mappings and cannot support remote Devices.
- Reused `fs.transfer` rather than adding an upload ABI or hidden filesystem
  endpoint.
- Used binary chunks, not JSON/base64 file frames, because the daemon's
  FileTransfer wire profile performs the canonical chunk mapping.
- Read completion from the terminal receipt because Runtime Core deliberately
  suppresses the duplicate provider completion data frame.
