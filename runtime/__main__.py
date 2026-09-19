"""Select one foreground process, preserving signals and exit status with exec."""
import os
import sys


COMMANDS = {
    "bot": ["python", "bot.py"],
    "dashboard": ["python", "-m", "uvicorn", "dashboard.app:app", "--host", "0.0.0.0", "--port", "8000", "--log-config", "observability/logging.json", "--no-access-log"],
    "social-worker": ["python", "social_worker.py"],
    "migrate": ["python", "migrate.py"],
    "test": ["python", "-m", "unittest", "discover", "-s", "tests", "-p", "test_*.py"],
}


def main() -> None:
    args = sys.argv[1:]
    if not args or args[0] in {"-h", "--help"}:
        print("Usage: tueka {" + "|".join(COMMANDS) + "} [arguments]")
        return
    if args[0] not in COMMANDS:
        print("Unknown command. Use --help for available commands.", file=sys.stderr)
        raise SystemExit(2)
    command = [*COMMANDS[args[0]], *args[1:]]
    os.execvp(command[0], command)


if __name__ == "__main__":
    main()
