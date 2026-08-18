#!/usr/bin/env python3
"""CI Gate A — no inference import (Implementation Plan S.3).

The build fails if any backend module imports an inference client. The
serving path performs no inference (invariant 1); the ONLY permitted
model use is the local sentence-embedding model inside the connector and
worker (`sentence_transformers` / ONNX runtime), which is deliberately
NOT on the blocklist.

Scans the four deployables and shared packages. Excludes docs/, the
prototype, the legacy snapshot, tests' fixture text, and dependency dirs.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCAN_DIRS = ["apps/api", "apps/mcp", "apps/worker", "apps/web", "packages"]
EXCLUDE_PARTS = {"node_modules", ".venv", "venv", "__pycache__", ".next", "dist"}

# Inference API clients. sentence_transformers / onnxruntime are allowed by
# design (local, deterministic, submit-time only — TRD vector tier).
BLOCKLIST = [
    "anthropic", "openai", "cohere", "mistralai", "litellm", "groq",
    "together", "replicate", "google.generativeai", "google.genai",
    "vertexai", "boto3.bedrock", "langchain",
]
PY_IMPORT = re.compile(
    r"^\s*(?:import|from)\s+(" + "|".join(re.escape(b) for b in BLOCKLIST) + r")\b",
    re.M,
)
JS_IMPORT = re.compile(
    r"""(?:from\s+|require\(\s*)['"](@anthropic-ai/[^'"]+|@google/generative-ai|openai|cohere-ai|groq-sdk|together-ai)['"]""",
)

def main() -> int:
    violations = []
    for d in SCAN_DIRS:
        base = ROOT / d
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if path.suffix not in {".py", ".ts", ".tsx", ".js", ".jsx", ".mjs"}:
                continue
            if EXCLUDE_PARTS.intersection(path.parts):
                continue
            if "dma-insights" in path.parts:  # legacy snapshot, reference only
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            for rx in (PY_IMPORT, JS_IMPORT):
                for m in rx.finditer(text):
                    line = text.count("\n", 0, m.start()) + 1
                    violations.append(f"{path.relative_to(ROOT)}:{line}: imports inference client '{m.group(1)}'")
    if violations:
        print("GATE A FAILED — inference imports are forbidden in backend modules:")
        print("\n".join(violations))
        return 1
    print("Gate A passed: no inference client imports.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
