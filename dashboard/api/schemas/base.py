"""HTTP wire models; domain validation remains independent of FastAPI."""
from pydantic import BaseModel, ConfigDict


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="allow", coerce_numbers_to_str=True)


from copy import deepcopy
from functools import lru_cache
from typing import get_args, get_origin, Union, Any
from types import UnionType
from pydantic import create_model


def _partial_type(annotation):
    if isinstance(annotation, type) and issubclass(annotation, ApiModel):
        return input_model(annotation)
    origin = get_origin(annotation)
    args = get_args(annotation)
    if origin is list:
        return list[_partial_type(args[0])]
    if origin is dict:
        return dict[args[0], _partial_type(args[1])]
    if origin in (Union, UnionType):
        return Union[tuple(_partial_type(item) for item in args)]
    return annotation


@lru_cache(maxsize=None)
def input_model(model: type[ApiModel]) -> type[ApiModel]:
    """Use the same field constraints for partial input and complete responses.

    Omitted fields remain omitted when passed to the domain normalizer, which
    owns defaults and cross-field rules. Supplying a field validates its type
    and bounds. No response identity is required in a creation request.
    """
    fields = {}
    for name, field in model.model_fields.items():
        info = deepcopy(field)
        info.default = None
        info.default_factory = None
        fields[name] = (_partial_type(field.annotation), info)
    return create_model(model.__name__ + 'Input', __base__=ApiModel, **fields)
