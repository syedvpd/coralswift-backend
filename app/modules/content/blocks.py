"""Structured CMS blocks (navigation tree) and their validation."""

import json
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field

from app.modules.content.constants import ContentType

# site-relative path or https URL; no javascript:, data: or protocol-relative links
_URL = r"^(/|/[^/\s<>\"'][^\s<>\"']*|https://[^\s<>\"']+)$"


class NavLink(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: Annotated[str, Field(min_length=1, max_length=100)]
    url: Annotated[str, Field(max_length=500, pattern=_URL)]
    children: list["NavLink"] = Field(default_factory=list, max_length=30)


class NavigationData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[NavLink] = Field(max_length=50)


def check_block_data(content_type: ContentType, data: dict[str, Any] | None) -> None:
    """Navigation must be a valid menu tree; other structured blocks only need to be small."""
    if data is None:
        return
    if len(json.dumps(data)) > 20_000:
        raise ValueError("data is limited to 20 KB")
    if content_type is ContentType.NAVIGATION:
        NavigationData.model_validate(data)
