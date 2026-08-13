from sqlalchemy import (
    Column, Integer, String, Text, Boolean, Numeric,
    ForeignKey, DateTime, func, Enum as SAEnum, BigInteger, JSON,
    UniqueConstraint
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
    pending_ref_code = Column(String(32), nullable=True)

    orders = relationship("Order", back_populates="tg_user", lazy="selectin")


class OrderStatus(str, enum.Enum):
    new = "new"
    in_progress = "in_progress"
    done = "done"
    cancelled = "cancelled"


class BonusTxType(str, enum.Enum):
    accrual = "accrual"   # начисление бонусов (покупка, рефералка)
    spend = "spend"       # списание бонусов (оплата частью заказа)


class User(Base):
    """Зарегистрированный пользователь личного кабинета (email + пароль).

    Отдельная таблица от tg_users: те создаются автоматически из бота без email,
    а здесь — полноценные аккаунты магазина с верификацией, бонусами и рефералкой.
    Связь с заказами через Order.user_id (nullable — заказ может быть анонимным).
    """
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(200), nullable=False, unique=True, index=True)
    password_hash = Column(String(200), nullable=False)
    name = Column(String(150), nullable=True)
    phone = Column(String(30), nullable=True)
    is_verified = Column(Boolean, default=False, nullable=False, server_default="0")
    is_active = Column(Boolean, default=True, nullable=False, server_default="1")
    verification_token = Column(String(100), nullable=True, index=True)
    referred_by_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    referral_code = Column(String(32), nullable=False, unique=True, index=True)
    bonus_balance = Column(Numeric(10, 2), default=0, nullable=False, server_default="0")
    referral_signup_bonus_paid = Column(Boolean, default=False, nullable=False, server_default="0")
    notification_prefs = Column(JSON, nullable=True)  # {"order_updates": bool, "promo": bool}
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    referred_by = relationship("User", remote_side=[id], back_populates="referrals")
    orders = relationship("Order", back_populates="user", foreign_keys="[Order.user_id]", lazy="selectin")
    addresses = relationship("Address", back_populates="user", cascade="all, delete-orphan", lazy="selectin")
    favorites = relationship("Favorite", back_populates="user", cascade="all, delete-orphan", lazy="selectin")
    referrals = relationship("User", back_populates="referred_by")
    bonus_transactions = relationship("BonusTransaction", back_populates="user", cascade="all, delete-orphan", lazy="selectin")


class Address(Base):
    """Сохранённые адреса доставки пользователя личного кабинета."""
    __tablename__ = "addresses"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    label = Column(String(50), nullable=True)            # "Дом", "Работа"
    recipient = Column(String(150), nullable=True)
    phone = Column(String(30), nullable=True)
    city = Column(String(100), nullable=True)
    street = Column(String(200), nullable=True)
    house = Column(String(20), nullable=True)
    apt = Column(String(20), nullable=True)
    zip = Column(String(20), nullable=True)
    is_default = Column(Boolean, default=False, nullable=False, server_default="0")

    user = relationship("User", back_populates="addresses")


class Favorite(Base):
    """Избранные товары пользователя (wishlist)."""
    __tablename__ = "favorites"
    __table_args__ = (UniqueConstraint("user_id", "product_id", name="uq_favorite_user_product"),)

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="favorites")
    product = relationship("Product")


class BonusTransaction(Base):
    """История начислений/списаний бонусов пользователя.

    Шаблон: конкретная логика начисления (например, % от заказа или за
    реферальную покупку) допишется позже. Сейчас хранит аудит баланса.
    """
    __tablename__ = "bonus_transactions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    amount = Column(Numeric(10, 2), nullable=False)      # положительное число
    reason = Column(String(200), nullable=True)          # "Заказ #12", "Реферальный бонус"
    type = Column(SAEnum(BonusTxType), default=BonusTxType.accrual, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    order_id = Column(Integer, ForeignKey("orders.id", ondelete="SET NULL"), nullable=True, index=True)

    user = relationship("User", back_populates="bonus_transactions")


class PaymentStatus(str, enum.Enum):
    pending = "pending"    # ждём оплаты
    paid = "paid"          # ЮМани подтвердил
    failed = "failed"      # отменён / не оплачен


class OrderType(str, enum.Enum):
    catalog = "catalog"
    design = "design"


class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    tg_user_chat_id = Column(BigInteger, ForeignKey("tg_users.chat_id", ondelete="SET NULL"), nullable=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    customer_name = Column(String(150), nullable=False)
    customer_contact = Column(String(200), nullable=True)   # legacy: phone or @username (старые заказы)
    customer_phone = Column(String(30), nullable=True)      # новый формат: телефон
    customer_telegram = Column(String(100), nullable=True)  # новый формат: @username
    delivery_address = Column(Text, nullable=True)          # shipping address
    comment = Column(Text, nullable=True)
    admin_note = Column(Text, nullable=True)                # внутренние заметки менеджера
    # ── Soft-delete (корзина удалённых заказов) ───────────────────────────────
    is_deleted = Column(Boolean, default=False, nullable=False, server_default="0", index=True)
    deleted_at = Column(DateTime(timezone=True), nullable=True)
    # ─────────────────────────────────────────────────────────────────────────
    status = Column(SAEnum(OrderStatus), default=OrderStatus.new, nullable=False)
    order_type = Column(SAEnum(OrderType), default=OrderType.catalog, nullable=False)
    # ── ЮМани оплата ─────────────────────────────────────────────────────────
    payment_status = Column(SAEnum(PaymentStatus), default=PaymentStatus.pending, nullable=False)
    payment_label = Column(String(100), nullable=True, unique=True, index=True)  # наш ID в ЮМани
    amount = Column(Numeric(10, 2), nullable=True)          # итоговая сумма заказа
    bonus_spent = Column(Numeric(10, 2), default=0, nullable=False, server_default="0")
    referral_cashback_paid = Column(Boolean, default=False, nullable=False, server_default="0")
    bonus_refunded = Column(Boolean, default=False, nullable=False, server_default="0")
    # ─────────────────────────────────────────────────────────────────────────
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    tg_user = relationship("TgUser", back_populates="orders")
    user = relationship("User", back_populates="orders", foreign_keys=[user_id])
    items = relationship("OrderItem", back_populates="order", cascade="all, delete-orphan", lazy="selectin")


class PromoKind(str, enum.Enum):
    manual = "manual"
    referral = "referral"


class PromoCode(Base):
    """Promotional discount codes.

    kind=manual — обычный промокод из админки.
    kind=referral — персональный код пользователя (он же реферальный промокод).
    """
    __tablename__ = "promo_codes"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(50), nullable=False, unique=True, index=True)
    discount_percent = Column(Integer, nullable=False)  # e.g. 10 = 10%
    is_active = Column(Boolean, default=True)
    usage_limit = Column(Integer, nullable=True)       # None = unlimited
    used_count = Column(Integer, default=0)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    kind = Column(String(20), default=PromoKind.manual.value, nullable=False, server_default="manual")
    owner_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    cashback_percent = Column(Integer, nullable=True)  # override глобального кэшбэка держателю

    owner = relationship("User", foreign_keys=[owner_user_id])


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


class AppSetting(Base):
    """Ключ-значение для настроек, которые админ меняет без деплоя.

    Рефералка: referral.registration_bonus, referral.purchase_cashback_percent,
    referral.discount_percent, referral.max_bonus_spend_percent.
    """
    __tablename__ = "app_settings"

    key = Column(String(80), primary_key=True)
    value = Column(JSON, nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
