"""HTTP-only validation of routers produced by explicit feature factories."""
import re
from collections.abc import Callable, Iterable

from fastapi import APIRouter

from .context import ApiContext


def build_routers(factories: Iterable[Callable], context: ApiContext) -> tuple[APIRouter, ...]:
    routers = []
    paths, operation_ids = set(), set()
    for factory in factories:
        router = factory(context)
        if not isinstance(router, APIRouter):
            raise ValueError('API binding must return an APIRouter')
        for route in router.routes:
            # Parameter names do not distinguish URLs handled by the same method.
            shape = re.sub(r'\{[^}:]+(?=[:}])', '{_', route.path)
            for method in route.methods or ():
                key = (method, shape)
                if key in paths:
                    raise ValueError(f'Duplicate API route: {method} {route.path}')
                paths.add(key)
            operation_id = getattr(route, 'unique_id', None)
            if operation_id:
                if operation_id in operation_ids:
                    raise ValueError(f'Duplicate API operation ID: {operation_id}')
                operation_ids.add(operation_id)
        routers.append(router)
    return tuple(routers)
