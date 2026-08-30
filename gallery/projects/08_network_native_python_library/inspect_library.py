"""Prove that package metadata and signatures are available offline."""

import inspect
from pathlib import Path

from easyremote.silan import lotus

print("coordinate:", lotus.__easyremote_coordinate__)
print("realm:", lotus.__easyremote_realm__)
print("version:", lotus.__version__)
print("module:", lotus.__name__)
print("semantic_filter", inspect.signature(lotus.semantic_filter))
print("semantic_map", inspect.signature(lotus.semantic_map))
print("generated files:")
for path in sorted(Path(lotus.__file__).parent.iterdir()):
    if path.name != "__pycache__":
        print(" -", path.name)
