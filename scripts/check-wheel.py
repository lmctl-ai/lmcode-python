#!/usr/bin/env python3
"""Check that the built artifact is a pure Python wheel with runtime data."""
from pathlib import Path
from zipfile import ZipFile
import sys
root=Path(sys.argv[1]) if len(sys.argv)>1 else Path(".build/wheels")
wheels=sorted(root.glob("*.whl"))
if len(wheels)!=1:raise SystemExit("expected one wheel artifact")
wheel=wheels[0]
if not wheel.name.startswith("lmcode_python-") or not wheel.name.endswith("py3-none-any.whl"):
    raise SystemExit("wheel is not a py3-none-any Python artifact: "+wheel.name)
with ZipFile(wheel) as archive:
    names=archive.namelist()
    wheel_info=next(name for name in names if name.endswith(".dist-info/WHEEL"))
    metadata=next(name for name in names if name.endswith(".dist-info/METADATA"))
    info=archive.read(wheel_info).decode("utf8")
    meta=archive.read(metadata).decode("utf8")
    if "Root-Is-Purelib: true" not in info or "Tag: py3-none-any" not in info:raise SystemExit("wheel metadata does not mark a pure Python wheel")
    if "Name: lmcode-python" not in meta or "Requires-Dist:" in meta:raise SystemExit("wheel metadata has unexpected package/dependency declarations")
    for path in ("lmcode/loader.py","lmcode/data/lmcode-std.schema.json","sample/main.py","sample/data/sample.dsl.json"):
        if path not in names:raise SystemExit("wheel missing "+path)
print("verified pure Python wheel: "+wheel.name)
