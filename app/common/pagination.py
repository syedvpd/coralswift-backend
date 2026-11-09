"""Offset pagination: a query-param dependency and the matching `meta` block."""

from typing import Annotated, Any

from fastapi import Depends, Query

from app.core.constants import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE


class PageParams:
    def __init__(
        self,
        page: Annotated[int, Query(ge=1)] = 1,
        page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
    ) -> None:
        self.page = page
        self.page_size = page_size

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


PageDep = Annotated[PageParams, Depends()]


def page_meta(params: PageParams, total: int) -> dict[str, Any]:
    pages = -(-total // params.page_size)  # ceil division
    return {"page": params.page, "page_size": params.page_size, "total": total, "pages": pages}
