from typing import Literal
from pydantic import BaseModel, Field, ConfigDict, field_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    @field_validator("reason", "content", "detail", check_fields=False)
    @classmethod
    def meaningful_text(cls, value):
        if not value.strip():
            raise ValueError("内容不能为空")
        return value.strip()


class RegisterRequest(StrictModel):
    email: str = Field(pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$", max_length=120)
    name: str = Field(min_length=1, max_length=30)
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(StrictModel):
    email: str = Field(min_length=3, max_length=120)
    password: str = Field(min_length=1, max_length=128)


class CartRequest(StrictModel):
    product_id: str = Field(min_length=1, max_length=40)
    quantity: int = Field(ge=1, le=99, strict=True)


class OrderRequest(StrictModel):
    address: str = Field(min_length=5, max_length=200)
    request_key: str = Field(min_length=8, max_length=100)


class TicketRequest(StrictModel):
    order_id: str | None = Field(default=None, max_length=40)
    reason: str = Field(min_length=3, max_length=1000)


class ChatRequest(StrictModel):
    message: str = Field(min_length=1, max_length=2000)
    conversation_id: str | None = Field(default=None, max_length=40)


class ConfirmRequest(StrictModel):
    confirmed: bool = Field(strict=True)


class StockRequest(StrictModel):
    stock: int = Field(ge=0, le=100000, strict=True)
    restock_at: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")

    @field_validator("restock_at")
    @classmethod
    def valid_date(cls, value):
        if value:
            from datetime import date

            date.fromisoformat(value)
        return value


class ProductChanges(StockRequest):
    stock: int | None = Field(default=None, ge=0, le=100000, strict=True)
    name: str | None = Field(default=None, min_length=1, max_length=120)
    category: Literal["audio", "workspace", "charging", "clothing"] | None = None
    description: str | None = Field(default=None, max_length=2000)
    price_cents: int | None = Field(default=None, ge=1, le=100000000, strict=True)
    image: (
        Literal["headphones", "keyboard", "charger", "speaker", "mouse", "hub", "shirt"]
        | None
    ) = None
    specs: dict[str, str] | None = None

    @field_validator(
        "name", "category", "description", "price_cents", "stock", "image", "specs"
    )
    @classmethod
    def non_null(cls, value):
        if value is None:
            raise ValueError("该字段不能为 null，请省略不修改的字段")
        if isinstance(value, str) and not value.strip() and value != "":
            raise ValueError("内容不能只包含空白")
        if isinstance(value, dict) and (
            len(value) > 30
            or any(
                not k.strip() or len(k) > 60 or len(v) > 300 for k, v in value.items()
            )
        ):
            raise ValueError("规格最多 30 项，名称最多 60 字，值最多 300 字")
        return value.strip() if isinstance(value, str) else value


class ProductCreate(ProductChanges):
    id: str = Field(pattern=r"^[A-Z0-9][A-Z0-9_-]{0,39}$")
    name: str = Field(min_length=1, max_length=120)
    category: Literal["audio", "workspace", "charging", "clothing"]
    description: str = Field(default="", max_length=2000)
    price_cents: int = Field(ge=1, le=100000000, strict=True)
    stock: int = Field(ge=0, le=100000, strict=True)
    image: Literal[
        "headphones", "keyboard", "charger", "speaker", "mouse", "hub", "shirt"
    ] = "hub"
    specs: dict[str, str] = Field(default_factory=dict)


class ProductEditArgs(StrictModel):
    product_id: str = Field(min_length=1, max_length=40)
    changes: ProductChanges = Field(default_factory=ProductChanges)
    stock_delta: int | None = Field(default=None, ge=-100000, le=100000, strict=True)


class ProductListingRequest(StrictModel):
    active: bool = Field(strict=True)


class ProductListingArgs(ProductListingRequest):
    product_id: str = Field(min_length=1, max_length=40)


class AdminProductQuery(StrictModel):
    query: str = Field(default="", max_length=200)
    status: Literal["all", "listed", "unlisted"] = "all"
    category: Literal["", "audio", "workspace", "charging", "clothing"] = ""


class TicketUpdate(StrictModel):
    status: Literal["processing", "resolved"]
    resolution: str = Field(default="", max_length=1000)


class SearchArgs(StrictModel):
    query: str = Field(default="", max_length=200)


class OrderArgs(StrictModel):
    order_id: str | None = Field(default=None, max_length=40)


class CancelArgs(StrictModel):
    order_id: str = Field(min_length=1, max_length=40)


class TicketArgs(TicketRequest):
    pass


class HandoffRequest(StrictModel):
    reason: str = Field(min_length=3, max_length=1000)
    order_id: str | None = Field(default=None, max_length=40)


class TicketQuery(StrictModel):
    ticket_id: str | None = Field(default=None, max_length=40)


class HumanReply(StrictModel):
    content: str = Field(min_length=1, max_length=2000)


class FulfillmentUpdate(StrictModel):
    stage: Literal["transit", "delivered"]
    detail: str = Field(min_length=3, max_length=300)
