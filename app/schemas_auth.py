from typing import Literal

from pydantic import BaseModel, ConfigDict


class LoginIn(BaseModel):
    username: str
    password: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    display_name: str
    is_admin: bool
    is_active: bool


class LoginOut(BaseModel):
    token: str
    user: UserOut


class MemberAddIn(BaseModel):
    username: str
    role: Literal["owner", "editor", "viewer"]


class MemberRoleUpdate(BaseModel):
    role: Literal["owner", "editor", "viewer"]


class MemberOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    username: str
    display_name: str
    role: str
