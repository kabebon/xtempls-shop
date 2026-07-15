from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from decimal import Decimal
from datetime import datetime
from models import StockStatus, OrderType


# ─── Category ────────────────────────────────────────────────────────────────

class CategoryBase(BaseModel):
    name: str = Field(..., max_length=100)
    slug: str = Field(..., max_length=100)
    description: Optional[str] = None
    sort_order: int = 0
    is_active: bool = True


class CategoryCreate(CategoryBase):
    pass


class CategoryUpdate(BaseModel):
    name: Optional[str] = None
    slug: Optional[str] = None
    description: Optional[str] = None
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None


class CategoryOut(CategoryBase):
    id: int
    created_at: datetime
    product_count: Optional[int] = 0

    class Config:
        from_attributes = True


# ─── Product Image ────────────────────────────────────────────────────────────

class ProductImageOut(BaseModel):
    id: int
    url: str
    is_primary: bool
    sort_order: int

    class Config:
        from_attributes = True


# ─── Product Size ─────────────────────────────────────────────────────────────

class ProductSizeBase(BaseModel):
    size: str = Field(..., max_length=20)
    is_available: bool = True
    sort_order: int = 0


class ProductSizeOut(ProductSizeBase):
    id: int

    class Config:
        from_attributes = True


# ─── Product ──────────────────────────────────────────────────────────────────

class ProductBase(BaseModel):
    name: str = Field(..., max_length=200)
    slug: str = Field(..., max_length=200)
    description: Optional[str] = None
    price: Decimal = Field(..., gt=0)
    old_price: Optional[Decimal] = None
    category_id: Optional[int] = None
    stock_status: StockStatus = StockStatus.in_stock
    is_active: bool = True
    is_featured: bool = False
    sort_order: int = 0
    size_chart: Optional[Dict[str, str]] = None  # e.g. {"S": "42-44", "M": "46-48"}


class ProductCreate(ProductBase):
    sizes: Optional[List[str]] = []


class ProductUpdate(BaseModel):
    name: Optional[str] = None
    slug: Optional[str] = None
    description: Optional[str] = None
    price: Optional[Decimal] = None
    old_price: Optional[Decimal] = None
    category_id: Optional[int] = None
    stock_status: Optional[StockStatus] = None
    is_active: Optional[bool] = None
    is_featured: Optional[bool] = None
    sort_order: Optional[int] = None
    sizes: Optional[List[str]] = None
    size_chart: Optional[Dict[str, str]] = None


class ProductOut(ProductBase):
    id: int
    images: List[ProductImageOut] = []
    sizes: List[ProductSizeOut] = []
    category: Optional[CategoryOut] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ProductListOut(BaseModel):
    id: int
    name: str
    slug: str
    price: Decimal
    old_price: Optional[Decimal] = None
    stock_status: StockStatus
    is_featured: bool
    primary_image: Optional[str] = None
    category_id: Optional[int] = None

    class Config:
        from_attributes = True


class ProductListResponse(BaseModel):
    items: List[ProductListOut]
    total: int
    page: int
    pages: int


# ─── Stock ────────────────────────────────────────────────────────────────────

class StockUpdate(BaseModel):
    stock_status: StockStatus


# ─── Auth ─────────────────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    login: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class AdminUserOut(BaseModel):
    id: int
    login: str
    is_active: bool
    created_at: datetime
    last_login: Optional[datetime] = None

    class Config:
        from_attributes = True


class AdminUserCreate(BaseModel):
    login: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=6, max_length=128)
    is_active: bool = True


class AdminUserUpdate(BaseModel):
    login: Optional[str] = Field(None, min_length=3, max_length=50)
    password: Optional[str] = Field(None, min_length=6, max_length=128)
    is_active: Optional[bool] = None


# ─── TgUser ───────────────────────────────────────────────────────────────────

class TgUserRegister(BaseModel):
    chat_id: int
    username: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None


class TgUserOut(BaseModel):
    id: int
    chat_id: int
    username: Optional[str] = None
    first_name: Optional[str] = None
    started_at: datetime

    class Config:
        from_attributes = True


# ─── Orders ───────────────────────────────────────────────────────────────────

class OrderItemCreate(BaseModel):
    product_id: int
    # product_name / product_price are resolved server-side from the DB
    # (never trust client-supplied prices). Kept optional for backwards compat.
    product_name: Optional[str] = None
    product_price: Optional[Decimal] = None
    size: Optional[str] = None
    quantity: int = Field(1, ge=1)


class OrderCreate(BaseModel):
    customer_name: str = Field(..., max_length=150)
    customer_contact: str = Field(..., max_length=200)
    comment: Optional[str] = None
    items: List[OrderItemCreate] = Field(default_factory=list)
    tg_user_chat_id: Optional[int] = None  # ignored from client; set from verified initData
    tg_init_data: Optional[str] = None
    order_type: OrderType = OrderType.catalog
    promo_code: Optional[str] = None  # promo code applied at checkout


class OrderItemOut(BaseModel):
    id: int
    product_id: Optional[int] = None
    product_name: str
    product_price: Decimal
    size: Optional[str] = None
    quantity: int

    class Config:
        from_attributes = True


class OrderOut(BaseModel):
    id: int
    customer_name: str
    customer_contact: str
    comment: Optional[str] = None
    status: str
    order_type: str
    tg_user_chat_id: Optional[int] = None
    items: List[OrderItemOut] = []
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class OrderStatusUpdate(BaseModel):
    status: str  # new | in_progress | done | cancelled


class OrderListResponse(BaseModel):
    items: List[OrderOut]
    total: int
    page: int
    pages: int


# ─── Broadcast ────────────────────────────────────────────────────────────────

class BroadcastRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=4096)


# ─── PromoCode ───────────────────────────────────────────────────────────────

class PromoCodeCreate(BaseModel):
    code: str = Field(..., min_length=2, max_length=50)
    discount_percent: int = Field(..., ge=1, le=100)
    is_active: bool = True
    usage_limit: Optional[int] = None
    expires_at: Optional[datetime] = None


class PromoCodeOut(BaseModel):
    id: int
    code: str
    discount_percent: int
    is_active: bool
    usage_limit: Optional[int] = None
    used_count: int
    expires_at: Optional[datetime] = None
    created_at: datetime

    class Config:
        from_attributes = True


class PromoValidateRequest(BaseModel):
    code: str


class PromoValidateResponse(BaseModel):
    valid: bool
    discount_percent: Optional[int] = None
    message: Optional[str] = None


# ─── Image reorder ───────────────────────────────────────────────────────────────

class ImageReorderItem(BaseModel):
    id: int
    sort_order: int


class ImageReorderRequest(BaseModel):
    images: List[ImageReorderItem]
