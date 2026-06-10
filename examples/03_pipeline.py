"""Compose capabilities into an EAL mission.

Ordering is dataflow: passing `fetch.output` into a later step IS the
dependency edge. Inspect the generated source before running it.
"""

from easyremote import Client, Pipeline

pipe = Pipeline("hello-mission", client=Client())

fetch = pipe.step("er.ai_inference", prompt="step one", timeout=30)
pipe.step("er.ai_inference", prompt=fetch.output, on_failure="retry", retries=1)

print(pipe.to_eal())

if __name__ == "__main__":
    run = pipe.run()
    print("run_id:", run.run_id)
    print("status:", run.status)
