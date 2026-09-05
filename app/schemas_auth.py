from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class LoginIn(BaseModel):
    username: str
    password: str


class UserCreate(BaseModel):
    username: str
    display_name: str
    password: str = Field(min_length=6)  # 内网口径:密码最短 6
    is_admin: bool = False


class UserUpdate(BaseModel):
    display_name: str | None = None
    password: str | None = Field(default=None, min_length=6)  # 可选,给了才重置
    is_active: bool | None = None


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


class UserSearchItem(BaseModel):
    id: int
    username: str
    display_name: str


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
