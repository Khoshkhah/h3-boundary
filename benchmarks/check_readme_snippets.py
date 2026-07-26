#!/usr/bin/env python3
"""
Executes every ```python block in README.md and the docs, in order, so a
snippet cannot ship broken or reference an undefined name.

Blocks in one file share a namespace, the way a reader reading top to bottom
would experience them. Lines that are obviously illustrative rather than
runnable (a bare `...`) are skipped.

    PYTHONPATH=src/python python benchmarks/check_readme_snippets.py
"""
import pathlib
import re
import sys
import traceback

FILES = ["README.md", "docs/index.md"]
BLOCK = re.compile(r"```python\n(.*?)```", re.DOTALL)


def check(path):
    text = pathlib.Path(path).read_text()
    blocks = BLOCK.findall(text)
    if not blocks:
        print(f"  {path}: no python blocks")
        return 0

    ns = {}
    failures = 0
    for i, block in enumerate(blocks, 1):
        if block.strip() in ("", "..."):
            continue
        try:
            exec(compile(block, f"{path}#block{i}", "exec"), ns)
        except Exception:
            failures += 1
            print(f"  {path} block {i} FAILED:")
            print("    " + "\n    ".join(block.strip().splitlines()))
            print("    " + traceback.format_exc().strip().replace("\n", "\n    "))
    status = "ok" if not failures else f"{failures} FAILED"
    print(f"  {path}: {len(blocks)} blocks — {status}")
    return failures


def main():
    print("checking documentation snippets")
    failures = sum(check(p) for p in FILES)
    if failures:
        print(f"\n{failures} snippet(s) failed")
        sys.exit(1)
    print("\nall snippets run")


if __name__ == "__main__":
    main()
