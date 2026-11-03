#!/usr/bin/env python3
"""Build and exercise all lmcode sample ports against one pinned corpus."""

import argparse
import hashlib
import json
import os
import runpy
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import time


ROOT = Path(__file__).resolve().parent
LANGS = ("c", "cpp", "rust", "go", "csharp", "java", "kotlin", "scala")


def load_env_file(path):
    if not path:
        return {}
    data = json.loads(path.read_text()) if path.suffix == ".json" else {}
    if not data:
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            key, sep, value = line.partition("=")
            if not sep or not key.isidentifier() or any(x in value for x in ("$", "`", ";")):
                raise ValueError(f"unsafe environment file line: {line}")
            data[key] = value.strip().strip('"\'')
    if not isinstance(data, dict):
        raise ValueError("environment file must contain an object")
    return {str(k): (json.dumps(v) if isinstance(v, list) else str(v)) for k, v in data.items()}


def command_for(env, lang, repo):
    key = f"SAMPLE_{lang.upper()}_COMMAND"
    if key in env:
        value = json.loads(env[key])
        if not isinstance(value, list) or not all(isinstance(x, str) for x in value):
            raise ValueError(f"{key} must be a JSON argv array")
        return value
    if lang == "rust" and (repo / "Cargo.toml").is_file():
        return [str(repo / "target/release/lmcode-rust-sample")]
    if lang == "csharp" and (repo / "src/LmCode.Sample.csproj").is_file():
        return ["dotnet", str(repo / "src/bin/Release/net8.0/lmcode-csharp-sample.dll")]
    if lang == "kotlin" and (repo / "pom.xml").is_file():
        return ["java", "-jar", str(repo / "target/lmcode-kotlin-sample.jar")]
    if lang == "scala" and (repo / "build.sbt").is_file():
        classpath = (repo / "target/runtime-classpath.txt").read_text().strip()
        if not classpath:
            raise ValueError("scala: empty runtime classpath")
        return ["java", "-cp", classpath, "shop.Main"]
    return [str(repo / "build" / f"lmcode-{lang}-sample")]


def build_for(lang, repo, env):
    key = f"SAMPLE_{lang.upper()}_BUILD"
    if key in env:
        value = json.loads(env[key])
        if not isinstance(value, list) or not all(isinstance(x, str) for x in value):
            raise ValueError(f"{key} must be a JSON argv array")
        return value
    if lang == "rust" and (repo / "Cargo.toml").is_file():
        return ["cargo", "build", "--release", "--locked"]
    if lang == "csharp" and (repo / "src/LmCode.Sample.csproj").is_file():
        return ["dotnet", "build", "src/LmCode.Sample.csproj", "--configuration", "Release", "--nologo"]
    if lang == "kotlin" and (repo / "pom.xml").is_file():
        return ["mvn", "--batch-mode", "package", "-DskipTests"]
    if lang == "scala" and (repo / "build.sbt").is_file():
        return [env.get("SBT", "sbt"), "-batch", "compile", "writeRuntimeClasspath"]
    if lang == "go" and (repo / "go.mod").is_file():
        return ["go", "build", "-o", str(repo / "build/lmcode-go-sample"), "."]
    if (repo / "build.sh").is_file():
        return ["./build.sh"]
    if (repo / "Makefile").is_file():
        return ["make", "all"]
    raise ValueError(f"{lang}: no build.sh or Makefile")


def execute(argv, cwd, log, env):
    started = time.monotonic()
    with log.open("w") as output:
        try:
            result = subprocess.run(argv, cwd=cwd, env=env, stdout=output,
                                    stderr=subprocess.STDOUT, timeout=int(env.get("SAMPLE_TIMEOUT", 600)))
            code = result.returncode
        except (OSError, subprocess.TimeoutExpired) as error:
            output.write(str(error) + "\n")
            code = 124
    return code, round(time.monotonic() - started, 2)


def run_case(command, bytecode, expected_out, expected_exit, scratch, env, timeout=30, cwd=None):
    started = time.monotonic()
    child_env = dict(env, SAMPLE_TMP=str(scratch))
    try:
        result = subprocess.run([*command, "--lmcode", str(bytecode)], env=child_env, cwd=cwd,
                                capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired as error:
        return {"exit": 124, "stdout": error.stdout or b"", "stderr": b"timeout", "seconds": round(time.monotonic()-started, 4),
                "expected_exit": expected_exit, "expected_stdout": expected_out}
    return {
        "exit": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "expected_exit": expected_exit,
        "expected_stdout": expected_out,
        "seconds": round(time.monotonic()-started, 4),
    }


# Immutable released v1 digest, retained solely to identify unported SDKs.
LEGACY_STD_SHA256 = "cfe31e8b34fdcc33a13e456e80fa9d05a5e6c8fed5b98988abd24ac8570e65e0"

def pinned_std_digest(repo):
    lock = repo / "sdk.lock"
    if not lock.exists():
        return None
    data = json.loads(lock.read_text())
    return data.get("sha256", {}).get("std/lmcode-std.schema.json")


def legacy_signature_set():
    audit = runpy.run_path(str(ROOT / "audit.py"))
    data = (ROOT / "legacy-std-v1.schema.json").read_bytes()
    if hashlib.sha256(data).hexdigest() != LEGACY_STD_SHA256:
        raise ValueError("legacy std fixture digest mismatch")
    return audit["signatures"](json.loads(data))


def selected_ports(value):
    selected = tuple(value.split(","))
    if "cpp" not in selected or len(set(selected)) != len(selected) or set(selected) - set(LANGS):
        raise ValueError("ports must be unique known names and include cpp")
    return selected


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--all", action="store_true", help="run all eight configured ports")
    selection.add_argument("--ports", help="explicit comma-separated subset; must include cpp reference")
    parser.add_argument("--env-file", type=Path, default=None)
    args = parser.parse_args()
    try:
        selected = LANGS if args.all else selected_ports(args.ports)
    except ValueError as error:
        parser.error(str(error))

    try:
        file_env = load_env_file(args.env_file or (Path(os.environ["SAMPLE_ENV_FILE"]) if os.environ.get("SAMPLE_ENV_FILE") else None))
        env = dict(os.environ, **file_env)
        root = Path(env.get("SAMPLE_REPO_ROOT", Path.home() / "repos" / "dsl"))
        state = Path(env.get("SAMPLE_STATE", Path.home() / ".local/state/lmctl/sample-matrix"))
        state.mkdir(parents=True, exist_ok=True)
        corpus = Path(env.get("SAMPLE_CORPUS", ROOT)).expanduser().resolve()
        manifest = json.loads((corpus / "manifest.json").read_text())
        hooks = runpy.run_path(str(corpus / "run-suite.py"))
        hooks['check_files'](manifest)
        hooks['check_compiler']()
        cases = []
        for item in manifest["cases"]:
            cases.append((item["name"], item, corpus / item["bytecode"],
                          (corpus / "expected" / (item["name"] + ".out")).read_bytes(),
                          int((corpus / "expected" / (item["name"] + ".exit")).read_text())))
        if not cases:
            raise ValueError("manifest contains no sample cases")
    except Exception as error:
        print(f"FAIL setup: {error}", file=sys.stderr)
        return 2

    report = {"ports": {}, "cases": len(cases), "ok": True, "pending": [], "excluded": [lang for lang in LANGS if lang not in selected]}
    std_path = Path(env.get("SAMPLE_STD_SCHEMA", ROOT.parent / "std/lmcode-std.schema.json"))
    target_digest = hashlib.sha256(std_path.read_bytes()).hexdigest() if std_path.exists() else None
    audit = runpy.run_path(str(corpus / "audit.py"))
    target_std = audit["signatures"](json.loads(std_path.read_text())) if std_path.exists() else set()
    legacy_std = legacy_signature_set() if target_std else set()

    def pending_port(lang, entry):
        entry.update(pending=True, reason="released v1 SDK catalog; v2 port pending", ok=False)
        report["pending"].append(lang)
        report["ok"] = False
        print(f"FAIL {lang}: {entry['reason']}")
    actual_by_case = {}
    for lang in selected:
        repo = Path(env.get(f"SAMPLE_{lang.upper()}_DIR", root / f"lmcode-{lang}-sample")).expanduser().resolve()
        entry = report["ports"][lang] = {"repo": str(repo), "build": None, "cases": [], "ok": False}
        if not repo.is_dir():
            entry["error"] = "missing repository"
            print(f"FAIL {lang}: missing repository")
            report["ok"] = False
            continue
        try:
            pinned_digest = pinned_std_digest(repo)
        except (OSError, ValueError, TypeError, AttributeError) as error:
            entry["error"] = "invalid SDK lock: " + str(error)
            report["ok"] = False
            print(f"FAIL {lang}: {entry['error']}")
            continue
        if target_digest and target_digest != LEGACY_STD_SHA256 and pinned_digest == LEGACY_STD_SHA256:
            pending_port(lang, entry)
        try:
            build = build_for(lang, repo, env)
            entry["build"] = shlex.join(build)
        except Exception as error:
            entry["error"] = str(error)
            print(f"FAIL {lang}: {error}")
            report["ok"] = False
            continue
        code, seconds = execute(build, repo, state / f"{lang}-build.log", env)
        entry["build_exit"] = code
        entry["build_seconds"] = seconds
        if code:
            entry["error"] = "build failed"
            print(f"FAIL {lang}: build exited {code}")
            report["ok"] = False
            continue
        try:
            command = command_for(env, lang, repo)
            if pinned_digest is None and legacy_std and target_std - legacy_std:
                probe = subprocess.run([*command, "--lmcode-signatures"], env=env, cwd=repo, capture_output=True, text=True, timeout=30)
                observed = set(probe.stdout.splitlines())
                if probe.returncode == 0 and legacy_std <= observed and not ((target_std - legacy_std) & observed):
                    pending_port(lang, entry)
            # The port's own protocol and canonical runner are mandatory checks.
            checker = corpus / "protocol.py"
            protocol = subprocess.run([sys.executable, str(checker), *command], env=env, cwd=repo,
                                       capture_output=True, text=True, timeout=120)
            entry["protocol_suite_exit"] = protocol.returncode
            if protocol.returncode:
                entry["error"] = "canonical suite failed"
                print(f"FAIL {lang}: canonical suite exited {protocol.returncode}")
                report["ok"] = False
            for name, item, bytecode, expected_out, expected_exit in cases:
                with tempfile.TemporaryDirectory(prefix=f"sample-{lang}-") as scratch:
                    hooks['prepare_tmp'](scratch)
                    for fixture, content in item.get("fixtures", {}).items():
                        path = Path(scratch) / fixture
                        path.parent.mkdir(parents=True, exist_ok=True)
                        path.write_bytes(bytes.fromhex(content))
                    observed = run_case(command, bytecode, expected_out, expected_exit, scratch, env, int(item.get("timeout_seconds", 30)), cwd=repo)
                raw_stdout = observed["stdout"]
                raw_stderr = observed["stderr"]
                observed.update({"name": name, "stdout": raw_stdout.decode(errors="replace"),
                                 "stderr": raw_stderr.decode(errors="replace"),
                                 "stdout_hex": raw_stdout.hex(), "stderr_hex": raw_stderr.hex(),
                                 "expected_stdout": expected_out.decode(errors="replace")})
                good = (observed["exit"] == expected_exit and raw_stdout == expected_out and not raw_stderr)
                observed["ok"] = good
                entry["cases"].append(observed)
                actual_by_case.setdefault(name, {})[lang] = observed
                if not good:
                    print(f"FAIL {lang}/{name}: output or exit mismatch")
                    report["ok"] = False
            entry["ok"] = all(item["ok"] for item in entry["cases"]) and not protocol.returncode and not entry.get("pending", False)
        except Exception as error:
            entry["error"] = str(error)
            print(f"FAIL {lang}: {error}")
            report["ok"] = False

    if not report["ports"].get("cpp", {}).get("ok"):
        report["ok"] = False
        report["reference_error"] = "a current passing C++ reference is required; all-skipped is not success"
    for name, ports in actual_by_case.items():
        values = {(item["exit"], item["stdout_hex"], item["stderr_hex"]) for item in ports.values()}
        if len(values) != 1:
            report["ok"] = False
            report.setdefault("cross_mismatches", []).append(name)
    (state / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print("\nPROGRAM x SAMPLE MATRIX")
    print(f'{"program":<38} ' + ' '.join(f'{lang:>7}' for lang in selected))
    for name, _, _, _, _ in cases:
        row = actual_by_case.get(name, {})
        values = []
        for lang in selected:
            good = row.get(lang, {}).get('ok', False) and not report['ports'][lang].get('protocol_suite_exit', 1)
            values.append('FAIL' if report['ports'][lang].get('pending') else 'PASS' if good else 'FAIL')
        print(f'{name:<38} ' + ' '.join(f'{value:>7}' for value in values))
    print("\nPORT MATRIX")
    print("port     build  suite  cases")
    for lang, item in report["ports"].items():
        status = "FAIL" if item.get("pending") else "PASS" if item["ok"] else "FAIL"
        print(f"{lang:<8} {item.get('build_exit', 'FAIL')!s:<6} {item.get('protocol_suite_exit', 'FAIL')!s:<6} {status}")
    if report["pending"]:
        print("Cross-port v2 interoperability pending: " + ", ".join(report["pending"]))
    print(json.dumps(report, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
