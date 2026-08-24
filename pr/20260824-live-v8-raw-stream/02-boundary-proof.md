# Boundary Proof

The test publishes a finite `Iterator[StreamFrame]` through `ComputeNode`, whose
resident host uses `binary_v1`. The daemon admits and executes the committed
`host_stream` descriptor, Axon carries typed bytes, and the Python SDK selects
the advertised v8 callback. EasyRemote sees only SDK `FrameStream` values and
reconstructs public `StreamFrame` objects.

No C ABI probing, route selection, receipt interpretation, or terminal
inference is added to EasyRemote.
