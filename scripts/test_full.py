import subprocess
import sys
import time


FULL_COMMANDS = [
    [sys.executable, "-m", "unittest"],
    [sys.executable, "scripts/smoke.py"],
    [sys.executable, "scripts/health.py"],
]

OPTIONAL_RELEASE_CANDIDATE_COMMANDS = [
    [sys.executable, "scripts/readiness.py"],
]


def run_commands(commands=None) -> bool:
    started = time.time()
    ok = True
    for command in commands or FULL_COMMANDS:
        label = " ".join(command)
        step_started = time.time()
        print(f"\n==> {label}")
        result = subprocess.run(command, text=True)
        duration = time.time() - step_started
        print(f"<== exit {result.returncode} in {duration:.2f}s")
        if result.returncode != 0:
            ok = False
    total = time.time() - started
    print(f"\nFull regression summary: {'PASS' if ok else 'FAIL'} in {total:.2f}s")
    return ok


def main() -> int:
    ok = run_commands()
    print("\nManual release-candidate check:")
    for command in OPTIONAL_RELEASE_CANDIDATE_COMMANDS:
        print(f"- {' '.join(command)}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
