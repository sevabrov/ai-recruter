"""
API schema conventions.

The frontend contract (`frontend/src/services/types.ts`) is camelCase, the Python
domain is snake_case. One alias generator bridges both directions:

* responses serialize by alias  → `scoreBreakdown`, `highQualityCount`
* requests accept either form   → `populate_by_name=True`
* field names match the domain models one-for-one, so `Schema.model_validate(entity)`
  needs no mapping code

Query *parameters* stay snake_case (`min_score`, `page_size`) — that is what the
frontend client sends and what reads naturally in a URL.
"""

from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

T = TypeVar("T")


class CamelModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
    )


class Paginated(CamelModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int
