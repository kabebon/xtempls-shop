from sqlalchemy import (
    Column, Integer, String, Text, Boolean, Numeric,
    ForeignKey, DateTime, func, Enum as SAEnum, BigInteger, JSON
)
from sqlalchemy.orm import relationship
import enum
from database import Base


class StockStatus(str, enum.Enum):
    in_stock = "in_stock"
    out_of_stock = "out_of_stock"
    preorder = "preorder"


class Category(Base):
    __tablename__ = "categories"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False, unique=True)
    slug = Column(String(100), nullable=False, unique=True, index=True)
    description = Column(Text, nullable=True)
    sort_order = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    products = relationship("Product", back_populates="category", lazy="selectin")


class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False)
    slug = Column(String(200), nullable=False, unique=True, index=True)
    description = Column(Text, nullable=True)
    price = Column(Numeric(10, 2), nullable=False)
    old_price = Column(Numeric(10, 2), nullable=True)
    category_id = Column(Integer, ForeignKey("categories.id", ondelete="SET NULL"), nullable=True)
    stock_status = Column(SAEnum(StockStatus), default=StockStatus.in_stock, nullable=False)
    is_active = Column(Boolean, default=True)
    is_featured = Column(Boolean, default=False)
    sort_order = Column(Integer, default=0)
    size_chart = Column(JSON, nullable=True)  # {"S": "42-44 см", "M": "46-48 см", ...}
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    category = relationship("Category", back_populates="products")
    images = relationship("ProductImage", back_populates="product", cascade="all, delete-orphan", lazy="selectin")
    sizes = relationship("ProductSize", back_populates="product", cascade="all, delete-orphan", lazy="selectin")


class ProductImage(Base):
    __tablename__ = "product_images"

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
    url = Column(String(500), nullable=False)
    is_primary = Column(Boolean, default=False)
    sort_order = Column(Integer, default=0)

    product = relationship("Product", back_populates="images")


class ProductSize(Base):
    __tablename__ = "product_sizes"

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
    size = Column(String(20), nullable=False)
    is_available = Column(Boolean, default=True)
    sort_order = Column(Integer, default=0)

    product = relationship("Product", back_populates="sizes")


class AdminUser(Base):
    __tablename__ = "admin_users"

    id = Column(Integer, primary_key=True, index=True)
    login = Column(String(50), nullable=False, unique=True, index=True)
    password_hash = Column(String(200), nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    last_login = Column(DateTime(timezone=True), nullable=True)


class TgUser(Base):
    """Telegram users who started the bot — for broadcast notifications."""
    __tablename__ = "tg_users"

    id = Column(Integer, primary_key=True, index=True)
    chat_id = Column(BigInteger, nullable=False, unique=True, index=True)
    username = Column(String(100), nullable=True)
    first_name = Column(String(100), nullable=True)
    last_name = Column(String(100), nullable=True)
    started_at = Column(DateTime(timezone=True), server_default=func.now())
    last_seen = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    orders = relationship("Order", back_populates="tg_user", lazy="selectin")


class OrderStatus(str, enum.Enum):
    new = "new"
    in_progress = "in_progress"
    done = "done"
    cancelled = "cancelled"


class OrderType(str, enum.Enum):
    catalog = "catalog"
    design = "design"


class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    tg_user_chat_id = Column(BigInteger, ForeignKey("tg_users.chat_id", ondelete="SET NULL"), nullable=True)
    customer_name = Column(String(150), nullable=False)
    customer_contact = Column(String(200), nullable=False)  # phone or @username
    delivery_address = Column(Text, nullable=True)          # shipping address
    comment = Column(Text, nullable=True)
    status = Column(SAEnum(OrderStatus), default=OrderStatus.new, nullable=False)
    order_type = Column(SAEnum(OrderType), default=OrderType.catalog, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    tg_user = relationship("TgUser", back_populates="orders")
    items = relationship("OrderItem", back_populates="order", cascade="all, delete-orphan", lazy="selectin")


class PromoCode(Base):
    """Promotional discount codes."""
    __tablename__ = "promo_codes"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(50), nullable=False, unique=True, index=True)
    discount_percent = Column(Integer, nullable=False)  # e.g. 10 = 10%
    is_active = Column(Boolean, default=True)
    usage_limit = Column(Integer, nullable=True)       # None = unlimited
    used_count = Column(Integer, default=0)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class OrderItem(Base):
    __tablename__ = "order_items"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id", ondelete="CASCADE"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="SET NULL"), nullable=True)
    product_name = Column(String(200), nullable=False)   # snapshot at order time
    product_price = Column(Numeric(10, 2), nullable=False)
    size = Column(String(20), nullable=True)
    quantity = Column(Integer, default=1)

    order = relationship("Order", back_populates="items")
    product = relationship("Product")
    promo_code = Column(String(50), nullable=True)       # snapshot of applied promo code
    discount_amount = Column(Numeric(10, 2), nullable=True)  # saved discount amount
