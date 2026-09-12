"""Companion for 03_pipeline.py: inference plus explicit completion projection.

Uses the same pretend-inference contract as 01_hello_node.py. Run only one
provider at a time in this Runtime environment.
"""

from easyremote import ComputeNode

node = ComputeNode()


@node.register
def ai_inference(prompt: str, max_tokens: int = 64) -> dict:
    if not prompt or len(prompt) > 16_384:
        raise ValueError("prompt must contain 1 to 16384 characters")
    if not 1 <= max_tokens <= 512:
        raise ValueError("max_tokens must be between 1 and 512")
    return {"completion": f"echo({prompt})", "max_tokens": max_tokens}


@node.register
def completion_text(result: dict) -> str:
    completion = result.get("completion")
    if not isinstance(completion, str):
        raise ValueError("inference result must contain a string completion")
    return completion


if __name__ == "__main__":
    node.serve()
