"""Runtime body validation and OpenAPI descriptions from the same input model."""
from copy import deepcopy
from fastapi import Request
from pydantic import BaseModel, ValidationError

from .errors import api_error


def request_schema(model: type[BaseModel]) -> dict:
    schema = model.model_json_schema()
    definitions = schema.pop('$defs', {})

    def expand(value):
        if isinstance(value, dict):
            if '$ref' in value:
                return expand(deepcopy(definitions[value['$ref'].rsplit('/', 1)[-1]]))
            return {key: expand(item) for key, item in value.items()}
        if isinstance(value, list):
            return [expand(item) for item in value]
        return value

    return {'requestBody': {'required': True, 'content': {'application/json': {'schema': expand(schema)}}}}


async def read_body(request: Request, model: type[BaseModel]) -> dict:
    try:
        value = model.model_validate(await request.json())
    except (ValidationError, ValueError) as exc:
        fields = [{'path': '.'.join(str(item) for item in error['loc']), 'message': error['msg']}
                  for error in exc.errors(include_input=False, include_context=False)] if isinstance(exc, ValidationError) else []
        raise api_error(422, 'validation_failed', '入力を確認してください。', errors=fields) from exc
    return value.model_dump(exclude_unset=True, by_alias=True)
