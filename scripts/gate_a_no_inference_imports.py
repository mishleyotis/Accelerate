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

# ── the three ways past a literal-import regex ──────────────────────────
#
# AUD-0047: invariant 1 says the serving path performs no inference, and the
# gate that asserts it matched the LITERAL TEXT of an import statement. Three
# evasions reach a live inference endpoint and pass it, and none of them is
# exotic — each is ordinary Python that happens not to spell the import:
#
#   1. `importlib.import_module("anthr" + "opic")` — the module name is never
#      a literal, so no import regex can see it.
#   2. `httpx.post("https://api.anthropic.com/v1/messages", ...)` — no import
#      of a client library at all; the endpoint is called directly.
#   3. `__import__(os.environ["LLM_SDK"])` — the name arrives at runtime.
#
# So the gate now looks for the BEHAVIOUR as well as the spelling: a dynamic
# import whose argument is not a plain literal, and any inference endpoint
# host in a string. Both are reported with the line, because a false positive
# here is cheap to read and a false negative is a model call on the serving
# path.
DYNAMIC_IMPORT = re.compile(
    r"""(?:importlib\.import_module|__import__)\s*\(\s*(?!['"][\w.]+['"]\s*[,)])""")

INFERENCE_HOST = re.compile(
    r"""["'`]https?://[^"'`\s]*\b("""
    r"api\.anthropic\.com|api\.openai\.com|api\.cohere\.(?:ai|com)|"
    r"api\.mistral\.ai|api\.groq\.com|api\.together\.xyz|"
    r"generativelanguage\.googleapis\.com|"
    r"[\w.-]*aiplatform\.googleapis\.com|"
    r"bedrock[\w.-]*\.amazonaws\.com|api\.replicate\.com|"
    r"openrouter\.ai|api\.deepseek\.com"
    r""")[^"'`]*["'`]""")

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
            # The two behavioural checks are about the SERVING PATH. A test
            # that walks an AST and imports what it finds (worker
            # test_enrichment_loop) is doing the OPPOSITE of evading the
            # gate, and a fixture naming an endpoint is a string in an
            # assertion. Both would be false positives, and a gate that
            # cries wolf on its own test suite gets switched off.
            in_tests = "tests" in path.parts or path.name.startswith("test_")
            if in_tests:
                continue
            for m in INFERENCE_HOST.finditer(text):
                line = text.count("\n", 0, m.start()) + 1
                violations.append(
                    f"{path.relative_to(ROOT)}:{line}: names an inference "
                    f"endpoint ({m.group(1)}) — invariant 1 is about the CALL, "
                    f"not about which library makes it")
            for m in DYNAMIC_IMPORT.finditer(text):
                line = text.count("\n", 0, m.start()) + 1
                violations.append(
                    f"{path.relative_to(ROOT)}:{line}: a dynamic import whose "
                    f"module name is not a literal — no import gate can see "
                    f"what this loads. Import it by name, or move it out of "
                    f"the serving path")
    if violations:
        print("GATE A FAILED — inference imports are forbidden in backend modules:")
        print("\n".join(violations))
        return 1
    print("Gate A passed: no inference client imports.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
