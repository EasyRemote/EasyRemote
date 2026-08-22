# Share a Warm Model, Not a GPU Login

## Concrete use case

An ML team has useful models resident on personal workstations and lab GPU
boxes. An evaluation engineer needs embeddings for short text batches, while
the model owner wants to keep weights, CUDA dependencies, and machine access
local. The minimum task accepts one non-empty UTF-8 string of at most 4,096
characters and returns a fixed-size vector from a model that was initialized
once when the provider process started.

`node.py` uses a deterministic standard-library model adapter so the project is
immediately runnable. Replacing `WarmEmbeddingModel.embed` with a real local
model does not change the remote contract.

## Requirements

- Initialize model state once and reuse it across invocations.
- Reject empty or oversized text before inference.
- Keep weights and accelerator dependencies on the provider.
- Allow the caller to select a paired GPU device without receiving SSH access.
- Return a bounded JSON vector; batch scheduling is outside this MVP.

## Existing approach

Teams usually copy the model into every environment, ask the owner to run a
batch manually over SSH, or create a model-specific HTTP endpoint. Copying
wastes storage and VRAM, SSH grants machine-level authority for a function-level
need, and one-off endpoints repeat authentication, schema, routing, and logging
work for every model.

## EasyRemote approach

The model owner exposes `embed_text` with `@node.register`. The evaluation
script uses an `@remote` stub and may set `EASYREMOTE_GPU_NODE` to target a
specific paired device. The function stays warm in the provider process;
EasyNet handles the invocation boundary rather than turning the workstation
into a generally accessible server.

## Effect

The team can validate shared inference with one model and one caller before
adopting a scheduler. Model custody and machine control remain local, while the
consumer sees a typed team capability. Pool-wide load balancing, quotas, and
accelerator admission are deliberate follow-on layers, not behavior simulated
by this example.

## Run

```bash
uv sync
uv run python node.py
EASYREMOTE_GPU_NODE=gpu-1 uv run python client.py
```
