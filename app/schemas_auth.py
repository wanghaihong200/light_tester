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
    role: str


class MemberRoleUpdate(BaseModel):
    role: str


class MemberOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    username: str
    display_name: str
    role: str
