"""
Generic response envelopes shared across every endpoint.

Keeping these in one place is what lets the frontend rely on a predictable
shape everywhere: list endpoints always return {items, page, limit, total},
and every error always returns {error: {code, message}}.
"""
from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class PaginatedResponse(BaseModel, Generic[T]):
    items: list[T]
    page: int
    limit: int
    total: int


class ErrorDetail(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorDetail
