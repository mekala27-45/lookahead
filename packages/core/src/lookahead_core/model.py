"""The base model every structured record in lookahead inherits from.

Unknown fields are an error rather than silently dropped, and instances are
immutable once built, so a figure cannot be edited after the query that made it.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class StrictModel(BaseModel):
    """Pydantic model that forbids extra fields and freezes on construction."""

    model_config = ConfigDict(extra="forbid", frozen=True, validate_default=True)


class MutableStrictModel(BaseModel):
    """Same validation as StrictModel for records that are assembled in steps."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True, validate_default=True)
