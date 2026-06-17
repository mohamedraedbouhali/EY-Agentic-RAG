from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class UserCreate(BaseModel):
    email:      str
    password:   str
    first_name: str
    last_name:  str
    role_title: str = ""


class UserUpdate(BaseModel):
    email:      Optional[str] = None
    password:   Optional[str] = None
    first_name: Optional[str] = None
    last_name:  Optional[str] = None
    role_title: Optional[str] = None


class UserOut(BaseModel):
    id:          str
    email:       str
    first_name:  str
    last_name:   str
    role_title:  str
    role:        str
    is_approved: bool
    created_at:  datetime
    avatar:      Optional[str] = None


class ProfileUpdate(BaseModel):
    first_name: Optional[str] = None
    last_name:  Optional[str] = None
    avatar:     Optional[str] = None


class LoginRequest(BaseModel):
    email:    str
    password: str


class Token(BaseModel):
    access_token: str
    token_type:   str
    user:         UserOut
