from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


def _validate_tz(v: str) -> str:
    try:
        ZoneInfo(v)
    except (ZoneInfoNotFoundError, ValueError, OSError) as exc:
        raise ValueError("Unknown timezone (use an IANA name such as 'Asia/Kolkata')") from exc
    return v


class SetupRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=10, max_length=128)
    display_name: str = Field(min_length=1, max_length=120)
    timezone: str = "Asia/Kolkata"

    @field_validator("display_name")
    @classmethod
    def _strip(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Display name cannot be blank")
        return v

    @field_validator("password")
    @classmethod
    def _password_quality(cls, v: str) -> str:
        if v.strip() != v:
            raise ValueError("Password must not start or end with whitespace")
        if v.isdigit() or v.isalpha():
            raise ValueError("Password must mix letters with numbers or symbols")
        return v

    _tz = field_validator("timezone")(_validate_tz)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class UserOut(BaseModel):
    """Public user shape. Deliberately has no password hash, token or session fields."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    display_name: str
    timezone: str


class AuthStatus(BaseModel):
    setup_required: bool
    authenticated: bool
    user: UserOut | None = None
