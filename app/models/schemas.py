"""
schemas.py
==========

Pydantic 数据模型定义。
"""

from typing import Optional

from pydantic import BaseModel, Field


# ──────────────────────────────────────
# 规则相关
# ──────────────────────────────────────

class RuleOut(BaseModel):
    id: str
    name: str
    description: str
    pattern: str
    placeholder: str
    priority: int = 0
    enabled: bool = True
    builtin: bool = False
    category: str = "custom"


class RuleCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: str = Field(default="", max_length=500)
    pattern: str = Field(..., min_length=1)
    placeholder: str = Field(..., min_length=1)
    priority: int = Field(default=0, ge=0, le=100)
    enabled: bool = True
    category: str = "custom"


class RuleUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    pattern: Optional[str] = None
    placeholder: Optional[str] = None
    priority: Optional[int] = Field(default=None, ge=0, le=100)
    enabled: Optional[bool] = None
    category: Optional[str] = None


# ──────────────────────────────────────
# 脱敏请求/响应
# ──────────────────────────────────────

class Message(BaseModel):
    role: str = "user"
    content: str = ""


class DesensitizeOptions(BaseModel):
    level: str = "standard"
    rules: Optional[list[str]] = None
    preserve_length: bool = False
    skip_roles: list[str] = Field(default_factory=lambda: ["assistant"])
    audit: bool = False
    ner: bool = False


class DesensitizeRequest(BaseModel):
    messages: list[Message]
    options: DesensitizeOptions = Field(default_factory=DesensitizeOptions)


class DesensitizeTextRequest(BaseModel):
    text: str
    level: str = "standard"
    rules: Optional[list[str]] = None
    ner: bool = False


class ReplacedItem(BaseModel):
    rule: str
    placeholder: str
    occurrences: int


class DesensitizeResponse(BaseModel):
    messages: list[Message]
    replaced: list[ReplacedItem]
    metadata: dict


class DesensitizeTextResponse(BaseModel):
    text: str
    replaced: list[ReplacedItem]
    latency_ms: float


class ImageDesensitizeRequest(BaseModel):
    image_base64: str
    mime_type: str = "image/jpeg"
    level: str = "standard"
    rules: Optional[list[str]] = None
    ner: bool = False
    return_coordinates: bool = False
    max_side: int = Field(default=1600, ge=256, le=4096)


class ImageDesensitizeResponse(BaseModel):
    image_base64: str
    mime_type: str
    replaced: list[ReplacedItem]
    metadata: dict
    latency_ms: float
    coordinates: Optional[list[dict]] = None
