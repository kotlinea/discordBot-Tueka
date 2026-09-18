"""Command-line entrypoint for the social worker."""
from runtime.lifecycle import run
from social.worker import main


if __name__ == "__main__":
    run(main)
