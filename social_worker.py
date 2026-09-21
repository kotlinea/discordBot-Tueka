"""Command-line entrypoint for the social worker."""
from runtime.lifecycle import run
from asyncio import TaskGroup
from features.loading import resolve_bindings
from features.registry import REGISTRY


async def main() -> None:
    factories = resolve_bindings(REGISTRY.for_process('worker'))
    async with TaskGroup() as group:
        for factory in factories:
            group.create_task(factory())


if __name__ == "__main__":
    run(main)
