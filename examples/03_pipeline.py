"""Chain two inference calls through EAL. Start 03_pipeline_node.py first.

The inference result is an object. An explicit projection ability extracts its
completion string for the next prompt, preserving the provider's public type.
"""

from easyremote import Client, FreshRoot, Pipeline, ResolvedTargetSubject


def main() -> None:
    client = Client(invocation_policy=FreshRoot(ResolvedTargetSubject()))
    abilities = {info.name: info for info in client.functions()}
    inference = abilities["ai_inference"]
    projection = abilities["completion_text"]
    pipe = Pipeline("hello-mission", client=client)
    fetch = pipe.step(
        "er.ai_inference",
        on=inference.owner_ura,
        descriptor_ref=inference.descriptor_ref,
        prompt="step one",
        timeout=30,
    )
    text = pipe.step(
        "er.completion_text",
        on=projection.owner_ura,
        descriptor_ref=projection.descriptor_ref,
        result=fetch.output,
        timeout=30,
    )
    pipe.step(
        "er.ai_inference",
        on=inference.owner_ura,
        descriptor_ref=inference.descriptor_ref,
        prompt=text.output,
        on_failure="retry",
        retries=1,
        timeout=30,
    )
    print(pipe.to_eal())
    run = pipe.run()
    status = run.status
    if status.get("running") is not False or status["meta"]["status"] != "ok":
        raise RuntimeError(f"Mission did not complete successfully: {status}")
    assert status["meta"]["steps_completed"] == 3
    assert run.outputs["ai_inference"]["completion"] == "echo(step one)"
    assert run.outputs["completion_text"] == "echo(step one)"
    assert run.outputs["ai_inference_2"]["completion"] == "echo(echo(step one))"
    print("run_id:", run.run_id)
    print("status:", status["meta"]["status"])
    print("outputs:", run.outputs)


if __name__ == "__main__":
    main()
