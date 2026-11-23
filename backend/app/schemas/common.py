"""Schema base shared by every feature: strict input handling."""
from pydantic import BaseModel, ConfigDict, field_validator


class Strict(BaseModel):
    # Unknown fields are rejected (typos fail loudly instead of being silently ignored).
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    @field_validator("*", mode="before")
    @classmethod
    def _blank_to_none(cls, v):
        # An empty text box from the UI means "no value", not an empty string in the DB.
        return None if isinstance(v, str) and v.strip() == "" else v
