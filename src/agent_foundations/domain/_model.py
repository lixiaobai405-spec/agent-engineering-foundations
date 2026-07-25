from collections.abc import Mapping
from typing import Any, Self

from pydantic import BaseModel


class ValidatedCopyModel(BaseModel):
    """Pydantic model whose update copies re-enter normal validation."""

    def model_copy(
        self,
        *,
        update: Mapping[str, Any] | None = None,
        deep: bool = False,
    ) -> Self:
        if update is None:
            return super().model_copy(deep=deep)

        payload = self.model_dump(round_trip=True)
        payload.update(update)
        validated = type(self).model_validate(payload)
        model_fields = type(self).model_fields
        validated_update = {
            field_name: getattr(validated, field_name)
            for field_name in update
            if field_name in model_fields
        }
        return super().model_copy(update=validated_update, deep=deep)
