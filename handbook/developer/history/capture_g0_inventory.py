"""Capture the G0 source inventory; run with the repository's Python tools image.

This is historical capture tooling, not an application registration mechanism.
Output goes to artifacts; review before preserving a dated baseline beside it.
No application imports, database access, or environment secrets are required.
"""
from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[3]
OUTPUT = ROOT / "artifacts/g0-inventory.json"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def digest(value: str) -> str:
    return hashlib.sha256(value.replace("\r\n", "\n").encode()).hexdigest()


def relative(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def python_record(path: Path) -> dict:
    tree = ast.parse(read(path))
    imports = sorted({ast.unparse(n) for n in ast.walk(tree)
                      if isinstance(n, (ast.Import, ast.ImportFrom))})
    entries = []
    for n in ast.walk(tree):
        if not isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        decorators = [ast.unparse(d) for d in n.decorator_list]
        if decorators or n.name in {"setup", "main", "run", "cog_load", "cog_unload", "setup_hook", "close",
                                     "poll_loop", "x_stream_loop", "heartbeat_loop", "_process_target"}:
            guards = sorted({ast.unparse(c.func) for c in ast.walk(n)
                             if isinstance(c, ast.Call) and any(s in ast.unparse(c.func)
                             for s in ("auth.", "access", "csrf", "permission", "_enabled", "require_", "run_batch"))})
            entries.append({"name": n.name, "line": n.lineno, "decorators": decorators,
                            "arguments": ast.unparse(n.args), "guards_and_dispatch": guards})
    tests = [n.name for n in ast.walk(tree)
             if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name.startswith("test_")]
    return {"imports": imports, "entries": entries, "tests": tests}


def capture() -> dict:
    directories = ("cogs", "dashboard/api", "guild_settings", "community", "engagement",
                   "moderation", "ticketing", "reaction_roles", "suggestions", "social",
                   "database", "jobs", "discord_io", "observability", "runtime", "recovery",
                   "deploy", "scripts", "tests")
    python_paths = set(ROOT.glob("*.py")) | set((ROOT / "dashboard").glob("*.py"))
    for directory in directories:
        python_paths.update((ROOT / directory).rglob("*.py"))
    python_paths = sorted(p for p in python_paths if "__pycache__" not in p.parts)
    python = {relative(p): python_record(p) for p in python_paths}
    frontend_paths = sorted(p for p in (ROOT / "dashboard/frontend/src").rglob("*")
                            if p.suffix in {".ts", ".tsx", ".css"})
    frontend_paths += sorted((ROOT / "dashboard/frontend/e2e").glob("*.ts"))
    frontend = {}
    for path in frontend_paths:
        source = read(path)
        frontend[relative(path)] = {
            "imports": sorted(set(re.findall(r'(?:from\s*|import\s*\()([\x22\x27][^\x22\x27]+[\x22\x27])', source))),
            "routes": re.findall(r'<Route\b[^>]*', source),
            "api_operations": sorted(set(re.findall(r'[\x22\x27]((?:GET|POST|PUT|DELETE|PATCH) /api/v1/[^\x22\x27]+)', source))),
        }
    registry = ast.parse(read(ROOT / "feature_registry.py"))
    features = []
    keys = ("id", "category", "title_key", "description_key", "icon", "docs_path",
            "fields", "required_fields", "required_bot_permissions", "parent")
    for n in ast.walk(registry):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "Feature":
            feature = dict(zip(keys, (ast.literal_eval(arg) for arg in n.args)))
            docs = feature["docs_path"].removeprefix("/docs/")
            feature["docs_files"] = [f"docs/{docs}.md", f"docs/en/{docs}.md"]
            for doc in feature["docs_files"]:
                if not (ROOT / doc).is_file():
                    raise ValueError(f"Missing feature documentation: {doc}")
            features.append(feature)
    config = ast.parse(read(ROOT / "config.py"))
    extensions = next(ast.literal_eval(n.value) for n in ast.walk(config)
                      if isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name)
                      and n.target.id == "extensions")
    commands = json.loads(read(ROOT / "docs/reference/commands.json"))
    commands = {name: {"contract": value["contract"], "permissions": value["ja"]["permissions"]}
                for name, value in commands.items()}
    openapi = json.loads(read(ROOT / "dashboard/api/openapi.json"))
    operations = []
    for path, methods in openapi["paths"].items():
        for method, operation in methods.items():
            if method not in {"get", "post", "put", "patch", "delete", "head", "options"}:
                continue
            operations.append({"path": path, "method": method.upper(),
                               "operationId": operation.get("operationId"),
                               "parameters": operation.get("parameters", []),
                               "statuses": sorted(operation.get("responses", {})),
                               "contract_sha256": digest(json.dumps(operation, sort_keys=True))})
    contract = json.loads(read(ROOT / "tests/fixtures/api_v1_contract.json"))
    queues = [ast.unparse(n) for n in ast.walk(ast.parse(read(ROOT / "jobs/catalog.py")))
              if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "QueueSpec"]
    extra = [ROOT / p for p in ("feature_registry.py", "dashboard/api/openapi.json",
             "dashboard/frontend/src/generated/api.ts", "tests/fixtures/api_v1_contract.json",
             "docs/reference/commands.json", "compose.tools.yaml", "Dockerfile", "Dockerfile.tools",
             "requirements.lock", "dashboard/frontend/package-lock.json")]
    docs = [ROOT / doc for feature in features for doc in feature["docs_files"]]
    files = sorted(set(python_paths + frontend_paths + extra + docs))
    hashes = {relative(path): digest(read(path)) for path in files}
    return {
        "captured_date": "2026-09-21",
        "source_commit": "2b7050cb26acc85ea6edba080d5bf2af55458a18",
        "hash_normalization": "UTF-8 without BOM; CRLF normalized to LF",
        "scope": "Current application sources, direct/static imports (including test-only imports), declared entry decorators, UI routes, generated API operations and command contracts. Runtime registration is checked separately by commands-check/api-check/test-python.",
        "features": features, "extensions": extensions, "queues": queues,
        "commands": commands, "api_operations": operations,
        "openapi_components_sha256": digest(json.dumps(openapi.get("components", {}), sort_keys=True)),
        "historical_auth_boundaries": [{"mode": row["mode"], "path": row["path"],
                                        "method": row["method"], "status": row["status"],
                                        "body_sha256": digest(json.dumps(row["body"], sort_keys=True))}
                                       for row in contract["boundaries"]],
        "auth_boundary_note": "Historical fixture bodies are normalized by test_api_contract.py:error_detail and next:null before comparing current responses; the fixture is not a current-body snapshot.",
        "python": python, "frontend": frontend, "source_sha256": hashes,
        "counts": {"features": len(features), "extensions": len(extensions), "queues": len(queues),
                   "commands": len(commands), "api_paths": len(openapi["paths"]), "api_operations": len(operations),
                   "auth_cases": len(contract["boundaries"]), "python_files": len(python),
                   "frontend_files": len(frontend), "hashed_files": len(hashes)},
    }


if __name__ == "__main__":
    result = capture()
    OUTPUT.parent.mkdir(exist_ok=True)
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result["counts"], ensure_ascii=False))
    print(f"Inventory: {OUTPUT}")
