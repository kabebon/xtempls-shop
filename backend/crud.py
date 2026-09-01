import math
import hashlib
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, update, delete, String, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from models import (
    Category, Product, ProductImage, ProductSize, AdminUser, StockStatus, TgUser,
    Order, OrderItem, OrderStatus, OrderType, PaymentStatus, PromoCode, PromoKind,
    User, Address, Favorite, BonusTransaction, BonusTxType, AppSetting,
    SitePage, ReferralClick,
)
from schemas import (
    CategoryCreate, CategoryUpdate,
    ProductCreate, ProductUpdate,
    ProductListOut, StockStatus,
    OrderCreate,
)
from auth import get_password_hash
from database import settings


# ─── Categories ───────────────────────────────────────────────────────────────

async def get_categories(db: AsyncSession, active_only: bool = True):
    q = select(Category)
    if active_only:
        q = q.where(Category.is_active == True)
    q = q.order_by(Category.sort_order, Category.name)
    result = await db.execute(q)
    categories = result.scalars().all()
    return categories


async def get_category(db: AsyncSession, category_id: int):
    result = await db.execute(select(Category).where(Category.id == category_id))
    return result.scalar_one_or_none()


async def create_category(db: AsyncSession, data: CategoryCreate):
    cat = Category(**data.model_dump())
    db.add(cat)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise
    await db.refresh(cat)
    return cat


async def update_category(db: AsyncSession, category_id: int, data: CategoryUpdate):
    values = {k: v for k, v in data.model_dump(exclude_unset=True).items()}
    if not values:
        return await get_category(db, category_id)
    await db.execute(update(Category).where(Category.id == category_id).values(**values))
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise
    return await get_category(db, category_id)


async def delete_category(db: AsyncSession, category_id: int):
    await db.execute(delete(Category).where(Category.id == category_id))
    await db.commit()


# ─── Products ─────────────────────────────────────────────────────────────────

async def get_products(
    db: AsyncSession,
    page: int = 1,
    per_page: int = 20,
    category_id: Optional[int] = None,
    featured_only: bool = False,
    active_only: bool = True,
    search: Optional[str] = None
):
    q = select(Product).options(
        selectinload(Product.images),
        selectinload(Product.sizes),
        selectinload(Product.category)
    )
    if active_only:
        q = q.where(Product.is_active == True)
    if category_id:
        q = q.where(Product.category_id == category_id)
    if featured_only:
        q = q.where(Product.is_featured == True)
    if search:
        q = q.where(Product.name.ilike(f"%{search}%"))

    count_q = select(func.count()).select_from(q.subquery())
    total_result = await db.execute(count_q)
    total = total_result.scalar()

    q = q.order_by(Product.sort_order, Product.created_at.desc())
    q = q.offset((page - 1) * per_page).limit(per_page)
    result = await db.execute(q)
    products = result.scalars().all()

    items = []
    for p in products:
        primary_img = next((img.url for img in p.images if img.is_primary), None)
        if not primary_img and p.images:
            primary_img = p.images[0].url
        items.append(ProductListOut(
            id=p.id,
            name=p.name,
            slug=p.slug,
            price=p.price,
            old_price=p.old_price,
            stock_status=p.stock_status,
            is_featured=p.is_featured,
            primary_image=primary_img,
            category_id=p.category_id
        ))

    return {
        "items": items,
        "total": total,
        "page": page,
        "pages": max(1, math.ceil(total / per_page))
    }


async def get_product(db: AsyncSession, product_id: int):
    result = await db.execute(
        select(Product)
        .options(
            selectinload(Product.images),
            selectinload(Product.sizes),
            selectinload(Product.category)
        )
        .where(Product.id == product_id)
    )
    return result.scalar_one_or_none()


async def get_product_by_slug(db: AsyncSession, slug: str):
    result = await db.execute(
        select(Product)
        .options(
            selectinload(Product.images),
            selectinload(Product.sizes),
            selectinload(Product.category)
        )
        .where(Product.slug == slug, Product.is_active == True)
    )
    return result.scalar_one_or_none()


async def create_product(db: AsyncSession, data: ProductCreate):
    sizes = data.sizes or []
    product_data = data.model_dump(exclude={"sizes"})
    product = Product(**product_data)
    db.add(product)
    await db.flush()

    for i, size_val in enumerate(sizes):
        size = ProductSize(product_id=product.id, size=size_val, sort_order=i)
        db.add(size)

    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise
    return await get_product(db, product.id)


async def update_product(db: AsyncSession, product_id: int, data: ProductUpdate):
    sizes = data.sizes
    values = {k: v for k, v in data.model_dump(exclude_unset=True, exclude={"sizes"}).items()}

    if values:
        await db.execute(update(Product).where(Product.id == product_id).values(**values))

    if sizes is not None:
        await db.execute(delete(ProductSize).where(ProductSize.product_id == product_id))
        for i, size_val in enumerate(sizes):
            size = ProductSize(product_id=product_id, size=size_val, sort_order=i)
            db.add(size)

    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise
    return await get_product(db, product_id)


async def delete_product(db: AsyncSession, product_id: int):
    await db.execute(delete(Product).where(Product.id == product_id))
    await db.commit()


async def update_stock(db: AsyncSession, product_id: int, stock_status: StockStatus):
    await db.execute(
        update(Product).where(Product.id == product_id).values(stock_status=stock_status)
    )
    await db.commit()
    return await get_product(db, product_id)


async def add_product_image(db: AsyncSession, product_id: int, url: str, is_primary: bool = False):
    if is_primary:
        await db.execute(
            update(ProductImage)
            .where(ProductImage.product_id == product_id)
            .values(is_primary=False)
        )
    img = ProductImage(product_id=product_id, url=url, is_primary=is_primary)
    db.add(img)
    await db.commit()
    await db.refresh(img)
    return img


async def delete_product_image(db: AsyncSession, image_id: int):
    await db.execute(delete(ProductImage).where(ProductImage.id == image_id))
    await db.commit()


async def set_primary_image(db: AsyncSession, product_id: int, image_id: int):
    await db.execute(
        update(ProductImage)
        .where(ProductImage.product_id == product_id)
        .values(is_primary=False)
    )
    await db.execute(
        update(ProductImage)
        .where(ProductImage.id == image_id)
        .values(is_primary=True)
    )
    await db.commit()


async def reorder_product_images(db: AsyncSession, product_id: int, order: list):
    """Update sort_order for product images. order = [{id, sort_order}, ...]"""
    for item in order:
        await db.execute(
            update(ProductImage)
            .where(ProductImage.id == item["id"], ProductImage.product_id == product_id)
            .values(sort_order=item["sort_order"])
        )
    await db.commit()


# ─── Admin Users ──────────────────────────────────────────────────────────────

async def get_admin_by_login(db: AsyncSession, login: str):
    result = await db.execute(select(AdminUser).where(AdminUser.login == login))
    return result.scalar_one_or_none()


async def create_admin(db: AsyncSession, login: str, password: str):
    admin = AdminUser(login=login, password_hash=get_password_hash(password))
    db.add(admin)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise
    await db.refresh(admin)
    return admin


async def get_admins(db: AsyncSession) -> list[AdminUser]:
    result = await db.execute(select(AdminUser).order_by(AdminUser.id))
    return list(result.scalars().all())


async def get_admin(db: AsyncSession, admin_id: int) -> Optional[AdminUser]:
    result = await db.execute(select(AdminUser).where(AdminUser.id == admin_id))
    return result.scalar_one_or_none()


async def update_admin(db: AsyncSession, admin_id: int, values: dict) -> Optional[AdminUser]:
    if not values:
        return await get_admin(db, admin_id)
    await db.execute(update(AdminUser).where(AdminUser.id == admin_id).values(**values))
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise
    return await get_admin(db, admin_id)


async def delete_admin(db: AsyncSession, admin_id: int) -> bool:
    result = await db.execute(delete(AdminUser).where(AdminUser.id == admin_id))
    await db.commit()
    return (result.rowcount or 0) > 0


async def update_last_login(db: AsyncSession, admin_id: int):
    await db.execute(
        update(AdminUser).where(AdminUser.id == admin_id).values(last_login=datetime.now(timezone.utc))
    )
    await db.commit()


# ── TgUsers ────────────────────────────────────────────────────────────────────────────

async def upsert_tg_user(db: AsyncSession, chat_id: int, username: str = None,
                         first_name: str = None, last_name: str = None,
                         pending_ref_code: str = None):
    result = await db.execute(select(TgUser).where(TgUser.chat_id == chat_id))
    user = result.scalar_one_or_none()
    ref = (pending_ref_code or "").strip().upper() or None
    if user:
        user.username = username
        user.first_name = first_name
        user.last_name = last_name
        user.last_seen = datetime.now(timezone.utc)
        # Не затираем уже сохранённый реферал повторным /start без кода.
        if ref:
            user.pending_ref_code = ref
    else:
        user = TgUser(
            chat_id=chat_id, username=username,
            first_name=first_name, last_name=last_name,
            pending_ref_code=ref,
        )
        db.add(user)
    await db.commit()
    return user


async def get_all_tg_chat_ids(db: AsyncSession) -> list[int]:
    result = await db.execute(select(TgUser.chat_id))
    return [row[0] for row in result.all()]


async def get_tg_users_count(db: AsyncSession) -> int:
    result = await db.execute(select(func.count()).select_from(TgUser))
    return result.scalar()


async def get_subscribers(
    db: AsyncSession,
    page: int = 1,
    per_page: int = 20,
    search: Optional[str] = None,
) -> dict:
    """Список подписчиков бота со сводкой по заказам.

    Для каждого пользователя из tg_users считаем агрегаты по заказам
    (считаем только активные заказы, без корзины):
      - orders_count — сколько заказов оформлено
      - total_spent — суммарная стоимость всех заказов
      - last_order_at — дата последнего заказа
      - last_phone / last_telegram — контакты из последнего заказа

    search ищет по username, имени и фамилии (без учёта регистра).
    """
    # Агрегаты по заказам — отдельным подзапросом, потом джойним к TgUser.
    # DISTINCT в count нужен потому, что JOIN с OrderItem разворачивает
    # многопозиционные заказы в несколько строк (иначе заказ с 3 позициями
    # посчитался бы как 3 заказа).
    order_agg = (
        select(
            Order.tg_user_chat_id.label("chat_id"),
            func.count(Order.id.distinct()).label("orders_count"),
            func.sum(OrderItem.product_price * OrderItem.quantity).label("total_spent"),
            func.max(Order.created_at).label("last_order_at"),
        )
        .join(OrderItem, OrderItem.order_id == Order.id, isouter=True)
        .where(Order.is_deleted == False)
        .group_by(Order.tg_user_chat_id)
        .subquery()
    )

    # Подзапрос: контакты последнего заказа каждого пользователя.
    # DISTINCT ON даёт одну строку на chat_id — самую свежую по created_at.
    last_contacts = (
        select(
            Order.tg_user_chat_id.label("chat_id"),
            Order.customer_phone.label("last_phone"),
            Order.customer_telegram.label("last_telegram"),
        )
        .select_from(Order)
        .where(Order.is_deleted == False, Order.tg_user_chat_id.isnot(None))
        .distinct(Order.tg_user_chat_id)
        .order_by(Order.tg_user_chat_id, Order.created_at.desc())
        .subquery()
    )

    base = (
        select(
            TgUser,
            func.coalesce(order_agg.c.orders_count, 0).label("orders_count"),
            order_agg.c.total_spent.label("total_spent"),
            order_agg.c.last_order_at.label("last_order_at"),
            last_contacts.c.last_phone.label("last_phone"),
            last_contacts.c.last_telegram.label("last_telegram"),
        )
        .select_from(TgUser)
        .outerjoin(order_agg, order_agg.c.chat_id == TgUser.chat_id)
        .outerjoin(last_contacts, last_contacts.c.chat_id == TgUser.chat_id)
    )

    if search:
        like = f"%{search.lower()}%"
        base = base.where(
            func.lower(func.coalesce(TgUser.username, "")).like(like)
            | func.lower(func.coalesce(TgUser.first_name, "")).like(like)
            | func.lower(func.coalesce(TgUser.last_name, "")).like(like)
            | func.cast(TgUser.chat_id, String).like(like)
        )

    total = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar()

    rows = (
        await db.execute(
            base.order_by(TgUser.started_at.desc())
            .offset((page - 1) * per_page)
            .limit(per_page)
        )
    ).all()

    items = []
    for user, orders_count, total_spent, last_order_at, last_phone, last_telegram in rows:
        items.append(
            {
                "id": user.id,
                "chat_id": user.chat_id,
                "username": user.username,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "started_at": user.started_at,
                "last_seen": user.last_seen,
                "orders_count": orders_count or 0,
                "total_spent": total_spent,
                "last_order_at": last_order_at,
                "last_phone": last_phone,
                "last_telegram": last_telegram,
            }
        )

    return {
        "items": items,
        "total": total,
        "page": page,
        "pages": max(1, math.ceil(total / per_page)),
    }


# ── Orders ──────────────────────────────────────────────────────────────────────────

async def create_order(db: AsyncSession, data: OrderCreate) -> Order:
    # Resolve every item from the DB: we never trust client-supplied prices.
    # Fetch all referenced products in one query.
    product_ids = [item.product_id for item in data.items]
    products_by_id: dict[int, Product] = {}
    if product_ids:
        result = await db.execute(select(Product).where(Product.id.in_(product_ids)))
        for p in result.scalars().all():
            products_by_id[p.id] = p

    missing = [pid for pid in product_ids if pid not in products_by_id]
    if missing:
        raise ValueError(f"Указанные товары не найдены или неактивны: {missing}")

    # Гарантируем что Telegram-пользователь существует в tg_users, иначе FK
    # orders_tg_user_chat_id_fkey падает (если юзер открыл миниапп напрямую,
    # не запустив /start и не зарегистрировавшись через бота).
    if data.tg_user_chat_id:
        existing = await db.execute(
            select(TgUser).where(TgUser.chat_id == data.tg_user_chat_id)
        )
        if not existing.scalar_one_or_none():
            db.add(TgUser(chat_id=data.tg_user_chat_id))
            try:
                await db.flush()
            except IntegrityError:
                # Кто-то другой только что добавил — ничего страшного.
                await db.rollback()

    order = Order(
        tg_user_chat_id=data.tg_user_chat_id,
        customer_name=data.customer_name,
        customer_phone=getattr(data, "customer_phone", None),
        customer_telegram=getattr(data, "customer_telegram", None),
        customer_contact=getattr(data, "customer_contact", None),
        delivery_address=getattr(data, "delivery_address", None),
        comment=data.comment,
        order_type=getattr(data, "order_type", None),
        user_id=getattr(data, "user_id", None),
    )
    db.add(order)
    await db.flush()

    buyer_id = getattr(data, "user_id", None)
    discount_percent = 0
    applied_promo = None
    promo_row = None
    if getattr(data, "promo_code", None):
        promo_row, promo_err = await resolve_promo_code(
            db, data.promo_code, buyer_user_id=buyer_id
        )
        if promo_err:
            raise ValueError(promo_err)
        if promo_row:
            discount_percent = int(promo_row.discount_percent or 0)
            is_ref = (promo_row.kind == PromoKind.referral.value) or bool(promo_row.owner_user_id)
            if is_ref:
                _rs = await get_referral_settings(db)
                if not _rs.get("buyer_discount_enabled", True) or not _rs.get("program_enabled", True):
                    discount_percent = 0
            applied_promo = promo_row.code
            await db.execute(
                update(PromoCode)
                .where(PromoCode.id == promo_row.id)
                .values(used_count=PromoCode.used_count + 1)
            )

    subtotal = Decimal("0")
    for item_data in data.items:
        product = products_by_id[item_data.product_id]
        price = product.price
        disc_amount = None
        if discount_percent:
            disc_amount = (price * Decimal(discount_percent) / Decimal(100)).quantize(Decimal("0.01"))
            price = price - disc_amount
        item = OrderItem(
            order_id=order.id,
            product_id=item_data.product_id,
            product_name=product.name,
            product_price=price,
            size=item_data.size,
            quantity=item_data.quantity,
            promo_code=applied_promo,
            discount_amount=disc_amount,
        )
        db.add(item)
        subtotal += price * item_data.quantity

    bonus_spent = Decimal("0")
    requested_bonus = Decimal(getattr(data, "bonus_spend", None) or 0)
    if requested_bonus < 0:
        requested_bonus = Decimal("0")
    if requested_bonus > 0:
        if not buyer_id:
            raise ValueError("Чтобы списать бонусы, войдите в личный кабинет")
        ref_settings = await get_referral_settings(db)
        max_pct = Decimal(ref_settings["max_bonus_spend_percent"])
        max_by_percent = (subtotal * max_pct / Decimal(100)).quantize(Decimal("0.01"))
        buyer = (
            await db.execute(select(User).where(User.id == buyer_id).with_for_update())
        ).scalar_one_or_none()
        if not buyer:
            raise ValueError("Пользователь не найден")
        bonus_spent = min(requested_bonus, Decimal(buyer.bonus_balance or 0), max_by_percent, subtotal)
        bonus_spent = bonus_spent.quantize(Decimal("0.01"))
        if bonus_spent > 0:
            await add_bonus_transaction(
                db, buyer_id, bonus_spent,
                reason=f"Списание на заказ #{order.id}",
                tx_type=BonusTxType.spend,
                order_id=order.id,
                commit=False,
            )

    total_amount = (subtotal - bonus_spent).quantize(Decimal("0.01"))
    order.bonus_spent = bonus_spent
    order.amount = total_amount
    # Заказ полностью закрыт бонусами — оплаты картой нет.
    if total_amount <= 0 and getattr(data, "order_type", None) != OrderType.design:
        order.payment_status = PaymentStatus.paid
        order.status = OrderStatus.in_progress

    await db.commit()
    order = await get_order(db, order.id)
    if order and order.payment_status == PaymentStatus.paid:
        await grant_referral_purchase_cashback(db, order)
        order = await get_order(db, order.id)
    return order


async def get_order(db: AsyncSession, order_id: int) -> Optional[Order]:
    result = await db.execute(
        select(Order)
        .options(selectinload(Order.items))
        .where(Order.id == order_id)
    )
    return result.scalar_one_or_none()


async def get_orders(db: AsyncSession, page: int = 1, per_page: int = 20,
                     status: str = None) -> dict:
    q = select(Order).options(selectinload(Order.items))
    # Soft-delete: активные заказы имеют is_deleted == False
    q = q.where(Order.is_deleted == False)
    if status:
        try:
            q = q.where(Order.status == OrderStatus(status))
        except ValueError:
            pass
    count_q = select(func.count()).select_from(q.subquery())
    total = (await db.execute(count_q)).scalar()
    q = q.order_by(Order.created_at.desc()).offset((page - 1) * per_page).limit(per_page)
    result = await db.execute(q)
    return {
        "items": result.scalars().all(),
        "total": total,
        "page": page,
        "pages": max(1, math.ceil(total / per_page))
    }


async def update_order_status(db: AsyncSession, order_id: int, status: str) -> Optional[Order]:
    try:
        s = OrderStatus(status)
    except ValueError:
        return None
    order = await get_order(db, order_id)
    if not order:
        return None
    prev = order.status
    order.status = s
    if s == OrderStatus.cancelled and prev != OrderStatus.cancelled:
        await refund_order_bonuses(db, order, commit=False)
        await reverse_referral_cashback(db, order, commit=False)
    await db.commit()
    return await get_order(db, order_id)


async def update_order_note(db: AsyncSession, order_id: int,
                            admin_note: Optional[str]) -> Optional[Order]:
    """Сохраняет/обновляет внутренние заметки менеджера по заказу."""
    note = (admin_note or "").strip() or None
    result = await db.execute(
        update(Order).where(Order.id == order_id).values(admin_note=note)
    )
    if result.rowcount == 0:
        return None
    await db.commit()
    return await get_order(db, order_id)


async def update_order_admin(db: AsyncSession, order_id: int, data) -> Optional[Order]:
    """Полное редактирование заказа из админки. Принимает схему OrderAdminUpdate,
    применяет только переданные поля (exclude_unset). Статусы валидируются через
    enum'ы. Возвращает обновлённый заказ или None, если заказ не найден."""
    payload = data.model_dump(exclude_unset=True)
    if not payload:
        return await get_order(db, order_id)

    # Валидируем значения статусов, если они переданы
    if "status" in payload and payload["status"] is not None:
        try:
            payload["status"] = OrderStatus(payload["status"])
        except ValueError:
            raise ValueError(f"Неверный status: {payload['status']}")
    if "payment_status" in payload and payload["payment_status"] is not None:
        try:
            payload["payment_status"] = PaymentStatus(payload["payment_status"])
        except ValueError:
            raise ValueError(f"Неверный payment_status: {payload['payment_status']}")

    # Тримим строки
    for k in ("customer_name", "customer_phone", "customer_telegram"):
        if k in payload and payload[k]:
            payload[k] = str(payload[k]).strip()

    order = await get_order(db, order_id)
    if not order:
        return None
    prev_status = order.status
    prev_pay = order.payment_status
    result = await db.execute(
        update(Order).where(Order.id == order_id).values(**payload)
    )
    if result.rowcount == 0:
        return None
    await db.commit()
    order = await get_order(db, order_id)
    new_status = payload.get("status", prev_status)
    new_pay = payload.get("payment_status", prev_pay)
    if new_status == OrderStatus.cancelled and prev_status != OrderStatus.cancelled:
        await refund_order_bonuses(db, order, commit=True)
        order = await get_order(db, order_id)
        await reverse_referral_cashback(db, order, commit=True)
        order = await get_order(db, order_id)
    if new_pay == PaymentStatus.paid and prev_pay != PaymentStatus.paid:
        await grant_referral_purchase_cashback(db, order)
        order = await get_order(db, order_id)
    return order


async def delete_order(db: AsyncSession, order_id: int) -> bool:
    """Soft-delete: помечаем заказ как удалённый (попадает в корзину админки).
    Возвращает True если заказ существовал и был удалён."""
    from datetime import datetime, timezone
    result = await db.execute(
        update(Order)
        .where(Order.id == order_id)
        .where(Order.is_deleted == False)
        .values(is_deleted=True, deleted_at=datetime.now(timezone.utc))
    )
    if result.rowcount == 0:
        return False
    await db.commit()
    return True


async def get_trashed_orders(db: AsyncSession, page: int = 1,
                             per_page: int = 20) -> dict:
    """Список заказов, удалённых в корзину (is_deleted == True)."""
    q = select(Order).options(selectinload(Order.items)).where(Order.is_deleted == True)
    count_q = select(func.count()).select_from(q.subquery())
    total = (await db.execute(count_q)).scalar()
    q = q.order_by(Order.deleted_at.desc().nullslast()).offset((page - 1) * per_page).limit(per_page)
    result = await db.execute(q)
    return {
        "items": result.scalars().all(),
        "total": total,
        "page": page,
        "pages": max(1, math.ceil(total / per_page)),
    }


async def restore_order(db: AsyncSession, order_id: int) -> Optional[Order]:
    """Восстанавливает заказ из корзины (снимает флаг soft-delete)."""
    result = await db.execute(
        update(Order)
        .where(Order.id == order_id)
        .where(Order.is_deleted == True)
        .values(is_deleted=False, deleted_at=None)
    )
    if result.rowcount == 0:
        return None
    await db.commit()
    return await get_order(db, order_id)


async def get_orders_count(db: AsyncSession) -> dict:
    active = select(Order).where(Order.is_deleted == False)
    total = (await db.execute(select(func.count()).select_from(active.subquery()))).scalar()
    new_q = active.where(Order.status == OrderStatus.new)
    new_count = (await db.execute(select(func.count()).select_from(new_q.subquery()))).scalar()
    return {"total": total, "new": new_count}


# ── Promo Codes ────────────────────────────────────────────────────────────────────────────────

async def resolve_promo_code(
    db: AsyncSession, code: str, buyer_user_id: Optional[int] = None
) -> tuple[Optional[PromoCode], Optional[str]]:
    """Найти промокод и проверить, можно ли его применить.

    Возвращает (promo, None) если ок, (None, сообщение) если нельзя.
    Свой реферальный промокод держатель использовать не может.
    """
    raw = (code or "").strip().upper()
    if not raw:
        return None, "Введите промокод"
    result = await db.execute(select(PromoCode).where(PromoCode.code == raw))
    promo = result.scalar_one_or_none()
    if not promo:
        return None, "Промокод недействителен или истёк"
    if not promo.is_active:
        return None, "Промокод отключён"
    if promo.usage_limit is not None and promo.used_count >= promo.usage_limit:
        return None, "Промокод больше нельзя использовать"
    if promo.expires_at and promo.expires_at < datetime.now(timezone.utc):
        return None, "Промокод истёк"
    is_referral = (promo.kind == PromoKind.referral.value) or bool(promo.owner_user_id)
    if is_referral:
        ref_settings = await get_referral_settings(db)
        if not ref_settings.get("program_enabled", True):
            return None, "Реферальная программа временно отключена"
        allow_self = bool(ref_settings.get("allow_self_promo"))
        if not allow_self and buyer_user_id and promo.owner_user_id == buyer_user_id:
            return None, "Нельзя использовать свой реферальный промокод"
    return promo, None


async def validate_promo_code(db: AsyncSession, code: str) -> Optional[PromoCode]:
    """Обратная совместимость: валидный промокод или None."""
    promo, err = await resolve_promo_code(db, code, buyer_user_id=None)
    return promo if not err else None


async def get_all_promo_codes(db: AsyncSession, kind: Optional[str] = None) -> list:
    q = select(PromoCode).options(selectinload(PromoCode.owner)).order_by(PromoCode.created_at.desc())
    if kind:
        q = q.where(PromoCode.kind == kind)
    result = await db.execute(q)
    return list(result.scalars().all())


async def create_promo_code(db: AsyncSession, code: str, discount_percent: int,
                            is_active: bool = True, usage_limit=None, expires_at=None,
                            kind: str = PromoKind.manual.value,
                            owner_user_id: Optional[int] = None,
                            cashback_percent: Optional[int] = None):
    promo = PromoCode(
        code=code.upper(),
        discount_percent=discount_percent,
        is_active=is_active,
        usage_limit=usage_limit,
        expires_at=expires_at,
        kind=kind,
        owner_user_id=owner_user_id,
        cashback_percent=cashback_percent,
    )
    db.add(promo)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise
    await db.refresh(promo)
    return promo


async def delete_promo_code(db: AsyncSession, promo_id: int):
    result = await db.execute(select(PromoCode).where(PromoCode.id == promo_id))
    promo = result.scalar_one_or_none()
    if not promo:
        return
    if promo.kind == PromoKind.referral.value:
        raise ValueError("Реферальный промокод нельзя удалить — его можно только отключить")
    await db.execute(delete(PromoCode).where(PromoCode.id == promo_id))
    await db.commit()


async def toggle_promo_code(db: AsyncSession, promo_id: int) -> Optional[PromoCode]:
    result = await db.execute(select(PromoCode).where(PromoCode.id == promo_id))
    promo = result.scalar_one_or_none()
    if not promo:
        return None
    promo.is_active = not promo.is_active
    await db.commit()
    await db.refresh(promo)
    return promo


# ─── Пользователи личного кабинета (users) ───────────────────────────────────

import secrets
import string

_REF_ALPHABET = string.ascii_uppercase + string.digits  # без неоднозначных символов
# убираем похожие 0/O, 1/I чтобы коды читались легче
_REF_ALPHABET = _REF_ALPHABET.replace("O", "").replace("0", "").replace("I", "").replace("1", "")


def _generate_referral_code(length: int = 8) -> str:
    """Короткий читаемый код (X7KQ-стиль). Уникальность проверяет вызывающий код."""
    return "".join(secrets.choice(_REF_ALPHABET) for _ in range(length))


def _generate_token() -> str:
    """Длинный непредсказуемый токен подтверждения email."""
    return secrets.token_urlsafe(32)


async def _unique_referral_code(db: AsyncSession) -> str:
    """Подбирает уникальный реферальный код (коллизии крайне редки)."""
    for _ in range(10):
        code = _generate_referral_code()
        exists = await db.execute(select(User.id).where(User.referral_code == code))
        if not exists.scalar_one_or_none():
            return code
    # Запасной вариант — с большей энтропией.
    return _generate_referral_code(16)


async def create_user(db: AsyncSession, email: str, password: str,
                      name: str = None, phone: str = None,
                      ref_code: str = None) -> User:
    """Создать аккаунт. email приводим к нижнему регистру, генерим referral_code
    и verification_token. Если ref_code валиден — привязываем пригласившего."""
    referral_code = await _unique_referral_code(db)
    user = User(
        email=email.lower().strip(),
        password_hash=get_password_hash(password),
        name=(name or "").strip() or None,
        phone=phone,
        referral_code=referral_code,
        verification_token=_generate_token(),
        notification_prefs={"order_updates": True, "promo": True},
    )

    # Привязка реферала: ищем пригласившего по коду (нельзя приглашать самого себя).
    if ref_code:
        referrer = await db.execute(
            select(User).where(User.referral_code == ref_code.strip().upper())
        )
        referrer = referrer.scalar_one_or_none()
        if referrer:
            user.referred_by_id = referrer.id

    db.add(user)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise

    ref_settings = await get_referral_settings(db)
    db.add(PromoCode(
        code=referral_code,
        discount_percent=int(ref_settings["discount_percent"]),
        is_active=True,
        kind=PromoKind.referral.value,
        owner_user_id=user.id,
        # cashback_percent=None → берётся из глобальных настроек админки
    ))
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise
    await db.refresh(user)
    return user


async def get_user_by_email(db: AsyncSession, email: str) -> Optional[User]:
    result = await db.execute(select(User).where(User.email == email.lower().strip()))
    return result.scalar_one_or_none()


async def get_user(db: AsyncSession, user_id: int) -> Optional[User]:
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


async def verify_user(db: AsyncSession, token: str) -> Optional[User]:
    """Подтвердить email по токену. Возвращает пользователя или None."""
    if not token:
        return None
    result = await db.execute(select(User).where(User.verification_token == token))
    user = result.scalar_one_or_none()
    if not user:
        return None
    user.is_verified = True
    user.verification_token = None
    await db.flush()
    await grant_welcome_bonus(db, user)
    await grant_referral_signup_bonus(db, user)
    await db.commit()
    await db.refresh(user)
    return user


async def update_user(db: AsyncSession, user_id: int, values: dict) -> Optional[User]:
    if not values:
        user = await get_user(db, user_id)
        return user
    await db.execute(update(User).where(User.id == user_id).values(**values))
    await db.commit()
    return await get_user(db, user_id)


async def change_user_password(db: AsyncSession, user_id: int, new_password: str) -> None:
    await db.execute(
        update(User).where(User.id == user_id)
        .values(password_hash=get_password_hash(new_password))
    )
    await db.commit()


# ─── Админка: заказчики (User) ───────────────────────────────────────────────

async def _customer_orders_count(db: AsyncSession, user_id: int) -> int:
    """Кол-во «видимых» заказов пользователя (тот же фильтр, что в ЛК):
    дизайн-заказы + оплаченные + обработанные. Брошенные pending не считаем."""
    visible = or_(
        Order.order_type == OrderType.design,
        Order.payment_status == PaymentStatus.paid,
        Order.status != OrderStatus.new,
    )
    result = await db.execute(
        select(func.count(Order.id)).where(
            Order.user_id == user_id, Order.is_deleted == False, visible
        )
    )
    return result.scalar() or 0


async def get_customers(db: AsyncSession, page: int = 1, per_page: int = 20,
                        search: Optional[str] = None) -> dict:
    """Список заказчиков (User) для админки. Поиск по email/имени/телефону.
    Возвращает total/pages для пагинации."""
    q = select(User)
    if search:
        like = f"%{search}%"
        q = q.where(
            or_(User.email.ilike(like), User.name.ilike(like), User.phone.ilike(like))
        )
    q = q.order_by(User.created_at.desc())
    total = (await db.execute(select(func.count()).select_from(q.subquery()))).scalar() or 0
    users = (await db.execute(q.offset((page - 1) * per_page).limit(per_page))).scalars().all()

    items = []
    for u in users:
        cnt = await _customer_orders_count(db, u.id)
        invited = (
            await db.execute(select(func.count()).select_from(User).where(User.referred_by_id == u.id))
        ).scalar() or 0
        items.append({
            "id": u.id, "email": u.email, "name": u.name, "phone": u.phone,
            "is_verified": u.is_verified, "is_active": u.is_active,
            "bonus_balance": u.bonus_balance, "referral_code": u.referral_code,
            "referred_by_id": u.referred_by_id, "invited_count": invited,
            "created_at": u.created_at, "orders_count": cnt,
        })
    return {
        "items": items, "total": total, "page": page,
        "pages": max(1, math.ceil(total / per_page)),
    }


async def get_customer(db: AsyncSession, user_id: int) -> Optional[dict]:
    u = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if not u:
        return None
    cnt = await _customer_orders_count(db, u.id)
    invited = (
        await db.execute(select(func.count()).select_from(User).where(User.referred_by_id == u.id))
    ).scalar() or 0
    referrer_email = None
    if u.referred_by_id:
        ref = await get_user(db, u.referred_by_id)
        referrer_email = ref.email if ref else None
    return {
        "id": u.id, "email": u.email, "name": u.name, "phone": u.phone,
        "is_verified": u.is_verified, "is_active": u.is_active,
        "bonus_balance": u.bonus_balance, "referral_code": u.referral_code,
        "referred_by_id": u.referred_by_id, "referred_by_email": referrer_email,
        "invited_count": invited,
        "created_at": u.created_at, "orders_count": cnt,
    }


async def update_customer(db: AsyncSession, user_id: int, data) -> Optional[User]:
    """Ручное редактирование заказчика из админки. apply только переданные поля.

    Изменение bonus_balance пишется как транзакция (аудит), а не «тихое» присвоение.
    """
    payload = data.model_dump(exclude_unset=True)
    new_balance = payload.pop("bonus_balance", None)
    if "name" in payload and payload["name"] is not None:
        payload["name"] = str(payload["name"]).strip() or None
    if "phone" in payload and payload["phone"] is not None:
        payload["phone"] = str(payload["phone"]).strip() or None
    user = await db.get(User, user_id)
    if not user:
        return None
    was_verified = bool(user.is_verified)
    if payload:
        await db.execute(update(User).where(User.id == user_id).values(**payload))
        await db.commit()
        user = await db.get(User, user_id)
        if user and user.is_verified and not was_verified:
            await grant_welcome_bonus(db, user)
            await grant_referral_signup_bonus(db, user)
            await db.commit()
            user = await db.get(User, user_id)
    if new_balance is not None:
        current = Decimal(user.bonus_balance or 0)
        target = Decimal(new_balance)
        delta = (target - current).quantize(Decimal("0.01"))
        if delta != 0:
            await add_bonus_transaction(
                db, user_id, abs(delta),
                reason="Корректировка баланса из админки",
                tx_type=BonusTxType.accrual if delta > 0 else BonusTxType.spend,
            )
            user = await db.get(User, user_id)
    return user


async def deactivate_customer(db: AsyncSession, user_id: int) -> bool:
    """«Удаление» заказчика — безопасно деактивируем аккаунт (is_active=False),
    заказы и история сохраняются. Hard-delete не делаем, чтобы не ломать ссылки
    заказов (Order.user_id ON DELETE SET NULL) и аудит."""
    result = await db.execute(
        update(User).where(User.id == user_id).values(is_active=False)
    )
    if result.rowcount == 0:
        return False
    await db.commit()
    return True


# ─── Адреса ──────────────────────────────────────────────────────────────────

async def list_addresses(db: AsyncSession, user_id: int) -> list[Address]:
    result = await db.execute(
        select(Address)
        .where(Address.user_id == user_id)
        .order_by(Address.is_default.desc(), Address.id.desc())
    )
    return list(result.scalars().all())


async def create_address(db: AsyncSession, user_id: int, data) -> Address:
    values = data.model_dump(exclude_unset=False)
    # Снимаем is_default из значений, чтобы обработать логику «только один дефолт».
    make_default = values.pop("is_default", False)
    address = Address(user_id=user_id, **values)
    db.add(address)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise
    await db.refresh(address)
    if make_default:
        await set_default_address(db, user_id, address.id)
    return address


async def get_address(db: AsyncSession, user_id: int, address_id: int) -> Optional[Address]:
    result = await db.execute(
        select(Address).where(Address.id == address_id, Address.user_id == user_id)
    )
    return result.scalar_one_or_none()


async def update_address(db: AsyncSession, user_id: int, address_id: int, data) -> Optional[Address]:
    values = data.model_dump(exclude_unset=True)
    make_default = values.pop("is_default", None)
    if values:
        await db.execute(
            update(Address).where(Address.id == address_id, Address.user_id == user_id).values(**values)
        )
        await db.commit()
    if make_default:
        await set_default_address(db, user_id, address_id)
    return await get_address(db, user_id, address_id)


async def set_default_address(db: AsyncSession, user_id: int, address_id: int) -> None:
    """Сначала снимаем флаг у всех адресов пользователя, потом ставим одному."""
    await db.execute(
        update(Address).where(Address.user_id == user_id).values(is_default=False)
    )
    await db.execute(
        update(Address).where(Address.id == address_id, Address.user_id == user_id).values(is_default=True)
    )
    await db.commit()


async def delete_address(db: AsyncSession, user_id: int, address_id: int) -> bool:
    result = await db.execute(
        delete(Address).where(Address.id == address_id, Address.user_id == user_id)
    )
    await db.commit()
    return (result.rowcount or 0) > 0


# ─── Избранное ───────────────────────────────────────────────────────────────

async def list_favorites(db: AsyncSession, user_id: int) -> list[Favorite]:
    result = await db.execute(
        select(Favorite)
        .options(selectinload(Favorite.product).selectinload(Product.images))
        .where(Favorite.user_id == user_id)
        .order_by(Favorite.created_at.desc())
    )
    return list(result.scalars().all())


async def add_favorite(db: AsyncSession, user_id: int, product_id: int) -> Favorite:
    # Проверяем существование товара.
    product = await db.execute(select(Product).where(Product.id == product_id, Product.is_active == True))
    if not product.scalar_one_or_none():
        raise ValueError("Товар не найден")
    fav = Favorite(user_id=user_id, product_id=product_id)
    db.add(fav)
    try:
        await db.commit()
    except IntegrityError:
        # Уже в избранном — возвращаем существующую запись.
        await db.rollback()
        existing = await db.execute(
            select(Favorite).where(Favorite.user_id == user_id, Favorite.product_id == product_id)
        )
        return existing.scalar_one()
    await db.refresh(fav)
    return fav


async def remove_favorite(db: AsyncSession, user_id: int, product_id: int) -> bool:
    result = await db.execute(
        delete(Favorite).where(Favorite.user_id == user_id, Favorite.product_id == product_id)
    )
    await db.commit()
    return (result.rowcount or 0) > 0


# ─── Рефералка ───────────────────────────────────────────────────────────────

async def get_referral_stats(db: AsyncSession, user_id: int) -> dict:
    """Код, ссылки (сайт + бот), число приглашённых и правила программы."""
    user = await get_user(db, user_id)
    if not user:
        return {
            "referral_code": "",
            "promo_code": "",
            "referral_link": "/register.html",
            "bot_link": None,
            "invited_count": 0,
            "link_clicks": 0,
            "earned_total": 0,
        }
    base_url = (settings.webapp_url or "").rstrip("/")
    code = (user.referral_code or "").upper()
    invited_count = (
        await db.execute(select(func.count()).select_from(User).where(User.referred_by_id == user_id))
    ).scalar() or 0
    earned_q = await db.execute(
        select(func.coalesce(func.sum(BonusTransaction.amount), 0)).where(
            BonusTransaction.user_id == user_id,
            BonusTransaction.type == BonusTxType.accrual,
            or_(
                BonusTransaction.reason.ilike("%регистрац%"),
                BonusTransaction.reason.ilike("%кэшбэк%"),
                BonusTransaction.reason.ilike("%кешбэк%"),
            ),
        )
    )
    earned = earned_q.scalar() or 0
    ref_settings = await get_referral_settings(db)
    site_link = f"{base_url}/register.html?ref={code}" if base_url else f"/register.html?ref={code}"
    bot_name = (settings.telegram_bot_username or "").lstrip("@")
    bot_link = f"https://t.me/{bot_name}?start={code}" if bot_name else None
    return {
        "referral_code": code,
        "promo_code": code,
        "referral_link": site_link,
        "bot_link": bot_link,
        "invited_count": invited_count,
        "link_clicks": await count_referral_clicks(db, code),
        "earned_total": earned,
        "registration_bonus": ref_settings["registration_bonus"],
        "purchase_cashback_percent": ref_settings["purchase_cashback_percent"],
        "discount_percent": ref_settings["discount_percent"],
        "program_enabled": ref_settings.get("program_enabled", True),
        "signup_bonus_enabled": ref_settings.get("signup_bonus_enabled", True),
        "invitee_bonus_enabled": ref_settings.get("invitee_bonus_enabled", False),
        "invitee_bonus": ref_settings.get("invitee_bonus", 0),
        "welcome_bonus_enabled": ref_settings.get("welcome_bonus_enabled", False),
        "welcome_bonus": ref_settings.get("welcome_bonus", 0),
        "purchase_cashback_enabled": ref_settings.get("purchase_cashback_enabled", True),
        "buyer_discount_enabled": ref_settings.get("buyer_discount_enabled", True),
        "min_order_amount": ref_settings.get("min_order_amount", 0),
    }


# ─── Бонусы ──────────────────────────────────────────────────────────────────

async def get_bonus_balance(db: AsyncSession, user_id: int) -> Decimal:
    user = await get_user(db, user_id)
    return user.bonus_balance if user else Decimal("0")


async def list_bonus_transactions(db: AsyncSession, user_id: int) -> list[BonusTransaction]:
    result = await db.execute(
        select(BonusTransaction)
        .where(BonusTransaction.user_id == user_id)
        .order_by(BonusTransaction.created_at.desc())
    )
    return list(result.scalars().all())


async def add_bonus_transaction(db: AsyncSession, user_id: int, amount,
                                reason: str = None,
                                tx_type: BonusTxType = BonusTxType.accrual,
                                order_id: Optional[int] = None,
                                commit: bool = True) -> BonusTransaction:
    """Начислить/списать бонусы и обновить баланс пользователя.

    commit=False — чтобы вложить операцию в чужую транзакцию (создание заказа).
    """
    amount = Decimal(amount).quantize(Decimal("0.01"))
    if amount <= 0:
        raise ValueError("Сумма бонусов должна быть больше нуля")
    locked = (
        await db.execute(select(User).where(User.id == user_id).with_for_update())
    ).scalar_one_or_none()
    if not locked:
        raise ValueError("Пользователь не найден")
    if tx_type == BonusTxType.spend and Decimal(locked.bonus_balance or 0) < amount:
        raise ValueError("Недостаточно бонусов на счёте")
    tx = BonusTransaction(
        user_id=user_id, amount=amount, reason=reason, type=tx_type, order_id=order_id,
    )
    db.add(tx)
    delta = amount if tx_type == BonusTxType.accrual else -amount
    await db.execute(
        update(User).where(User.id == user_id)
        .values(bonus_balance=User.bonus_balance + delta)
    )
    if commit:
        await db.commit()
        await db.refresh(tx)
    return tx


# ─── Заказы пользователя ─────────────────────────────────────────────────────

async def get_user_orders(db: AsyncSession, user_id: int,
                          page: int = 1, per_page: int = 10) -> dict:
    # В личном кабинете показываем только «реальные» заказы:
    #   • дизайн-заказы (order_type=design) — всегда (оплата не требуется);
    #   • каталог-заказы, которые оплачены (paid) ИЛИ уже обработаны админом
    #     (status != new — in_progress/done/cancelled).
    # «Брошенные» корзины (pending/failed + status=new) — не показываем и не считаем,
    # иначе счётчик «заказов» раздувается неоплаченными попытками на ЮМани.
    visible = or_(
        Order.order_type == OrderType.design,
        Order.payment_status == PaymentStatus.paid,
        Order.status != OrderStatus.new,
    )
    q = (
        select(Order)
        .options(selectinload(Order.items))
        .where(Order.user_id == user_id, Order.is_deleted == False, visible)
        .order_by(Order.created_at.desc())
    )
    total = (await db.execute(select(func.count()).select_from(q.subquery()))).scalar()
    rows = (
        await db.execute(q.offset((page - 1) * per_page).limit(per_page))
    ).scalars().all()
    return {
        "items": list(rows),
        "total": total,
        "page": page,
        "pages": max(1, math.ceil(total / per_page)),
    }


async def get_user_order(db: AsyncSession, user_id: int, order_id: int) -> Optional[Order]:
    visible = or_(
        Order.order_type == OrderType.design,
        Order.payment_status == PaymentStatus.paid,
        Order.status != OrderStatus.new,
    )
    result = await db.execute(
        select(Order)
        .options(selectinload(Order.items))
        .where(Order.id == order_id, Order.user_id == user_id,
               Order.is_deleted == False, visible)
    )
    return result.scalar_one_or_none()


async def cancel_stale_pending_orders(db: AsyncSession,
                                       older_than_hours: int = 24) -> int:
    """Автоотмена «брошенных» заказов: каталог-заказам, которые висят в
    payment_status=pending + status=new дольше older_than часов, выставляем
    payment_status=failed + status=cancelled.

    Списанные при оформлении бонусы возвращаем на счёт.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=older_than_hours)
    result = await db.execute(
        select(Order).where(
            Order.payment_status == PaymentStatus.pending,
            Order.status == OrderStatus.new,
            Order.is_deleted == False,
            Order.created_at < cutoff,
        )
    )
    orders = list(result.scalars().all())
    for order in orders:
        await refund_order_bonuses(db, order, commit=False)
        order.payment_status = PaymentStatus.failed
        order.status = OrderStatus.cancelled
    if orders:
        await db.commit()
    return len(orders)


# ─── Настройки реферальной программы ─────────────────────────────────────────

REFERRAL_SETTING_DEFAULTS = {
    "program_enabled": True,                       # мастер-выключатель
    "signup_bonus_enabled": True,                  # бонус держателю за регистрацию друга
    "registration_bonus": Decimal("100"),          # ₽ держателю
    "invitee_bonus_enabled": False,                # бонус самому приглашённому
    "invitee_bonus": Decimal("0"),                 # ₽ приглашённому
    "welcome_bonus_enabled": False,                # бонус каждому новому аккаунту (не только по реф. ссылке)
    "welcome_bonus": Decimal("0"),                 # ₽ новому клиенту
    "purchase_cashback_enabled": True,             # кэшбэк держателю с покупки по промо
    "purchase_cashback_percent": Decimal("5"),     # %
    "buyer_discount_enabled": True,                # скидка покупателю по реф. промокоду
    "discount_percent": Decimal("5"),              # %
    "max_bonus_spend_percent": Decimal("100"),     # сколько % заказа можно закрыть бонусами
    "min_order_amount": Decimal("0"),              # мин. сумма оплаты для кэшбэка
    "allow_self_promo": False,                     # свой код на свои покупки
    "cashback_base": "paid",                       # paid | subtotal
}

_REF_SETTING_KEYS = {name: f"referral.{name}" for name in REFERRAL_SETTING_DEFAULTS}
_BOOL_SETTINGS = {
    "program_enabled", "signup_bonus_enabled", "invitee_bonus_enabled",
    "welcome_bonus_enabled",
    "purchase_cashback_enabled", "buyer_discount_enabled", "allow_self_promo",
}
_STR_SETTINGS = {"cashback_base"}
_PERCENT_SETTINGS = {
    "purchase_cashback_percent", "discount_percent", "max_bonus_spend_percent",
}


def _as_decimal(value, default: Decimal) -> Decimal:
    try:
        return Decimal(str(value))
    except Exception:
        return default


def _coerce_setting(name: str, raw, default):
    if name in _BOOL_SETTINGS:
        if isinstance(raw, bool):
            return raw
        if isinstance(raw, (int, float)):
            return bool(raw)
        if isinstance(raw, str):
            return raw.strip().lower() in ("1", "true", "yes", "on")
        return bool(default)
    if name in _STR_SETTINGS:
        val = str(raw if raw is not None else default).strip().lower()
        if name == "cashback_base" and val not in ("paid", "subtotal"):
            return default
        return val
    return _as_decimal(raw, default)


def _json_setting(name: str, value):
    if name in _BOOL_SETTINGS:
        return bool(value)
    if name in _STR_SETTINGS:
        return str(value)
    value = Decimal(value)
    if value == value.to_integral_value():
        return int(value)
    return float(value)


async def get_referral_settings(db: AsyncSession) -> dict:
    result = await db.execute(select(AppSetting))
    stored = {row.key: row.value for row in result.scalars().all()}
    out = {}
    for name, default in REFERRAL_SETTING_DEFAULTS.items():
        key = _REF_SETTING_KEYS[name]
        raw = stored[key] if key in stored else default
        out[name] = _coerce_setting(name, raw, default)
    return out


async def set_referral_settings(db: AsyncSession, data: dict) -> dict:
    current = await get_referral_settings(db)
    for name, default in REFERRAL_SETTING_DEFAULTS.items():
        if name not in data or data[name] is None:
            continue
        value = _coerce_setting(name, data[name], default)
        if name in _PERCENT_SETTINGS:
            if value < 0 or value > 100:
                raise ValueError(f"{name}: процент должен быть от 0 до 100")
        elif name not in _BOOL_SETTINGS and name not in _STR_SETTINGS:
            if value < 0:
                raise ValueError(f"{name}: значение не может быть отрицательным")
        current[name] = value
        key = _REF_SETTING_KEYS[name]
        existing = await db.execute(select(AppSetting).where(AppSetting.key == key))
        row = existing.scalar_one_or_none()
        json_val = _json_setting(name, value)
        if row:
            row.value = json_val
        else:
            db.add(AppSetting(key=key, value=json_val))
    await db.commit()

    # Скидка на реферальных промокодах следует глобальной настройке.
    disc = int(current["discount_percent"]) if current.get("buyer_discount_enabled") else 0
    await db.execute(
        update(PromoCode)
        .where(PromoCode.kind == PromoKind.referral.value)
        .values(discount_percent=disc)
    )
    await db.commit()
    return current


async def grant_welcome_bonus(db: AsyncSession, user: User) -> None:
    """Бонус за регистрацию любому новому аккаунту (не только по реф. ссылке)."""
    if not user or user.welcome_bonus_paid:
        return
    ref_settings = await get_referral_settings(db)
    user.welcome_bonus_paid = True
    if not ref_settings.get("welcome_bonus_enabled"):
        return
    amount = Decimal(ref_settings.get("welcome_bonus") or 0)
    if amount <= 0:
        return
    await add_bonus_transaction(
        db, user.id, amount,
        reason="Бонус за регистрацию",
        tx_type=BonusTxType.accrual,
        commit=False,
    )


async def grant_referral_signup_bonus(db: AsyncSession, invitee: User) -> None:
    """Бонус держателю (и опционально приглашённому) после подтверждения email."""
    if not invitee.referred_by_id or invitee.referral_signup_bonus_paid:
        return
    ref_settings = await get_referral_settings(db)
    invitee.referral_signup_bonus_paid = True
    if not ref_settings.get("program_enabled", True):
        return
    referrer = await get_user(db, invitee.referred_by_id)
    if referrer and referrer.id != invitee.id and ref_settings.get("signup_bonus_enabled", True):
        amount = Decimal(ref_settings["registration_bonus"])
        if amount > 0:
            await add_bonus_transaction(
                db, referrer.id, amount,
                reason=f"Бонус за регистрацию реферала {invitee.email}",
                tx_type=BonusTxType.accrual,
                commit=False,
            )
    if ref_settings.get("invitee_bonus_enabled") and Decimal(ref_settings.get("invitee_bonus") or 0) > 0:
        welcome = Decimal(ref_settings["invitee_bonus"])
        await add_bonus_transaction(
            db, invitee.id, welcome,
            reason="Приветственный бонус за регистрацию по реферальной ссылке",
            tx_type=BonusTxType.accrual,
            commit=False,
        )


async def grant_referral_purchase_cashback(db: AsyncSession, order: Order) -> None:
    """Кэшбэк держателю промокода после оплаты заказа. Идемпотентно."""
    if not order or order.referral_cashback_paid:
        return
    if order.payment_status != PaymentStatus.paid:
        return
    ref_settings = await get_referral_settings(db)
    if not ref_settings.get("program_enabled", True) or not ref_settings.get("purchase_cashback_enabled", True):
        order.referral_cashback_paid = True
        await db.commit()
        return
    promo_code = None
    if order.items:
        promo_code = next((i.promo_code for i in order.items if i.promo_code), None)
    if not promo_code:
        order.referral_cashback_paid = True
        await db.commit()
        return

    promo, _ = await resolve_promo_code(db, promo_code, buyer_user_id=None)
    owner_id = promo.owner_user_id if promo else None
    if not owner_id:
        owner = (
            await db.execute(select(User).where(User.referral_code == promo_code.upper()))
        ).scalar_one_or_none()
        owner_id = owner.id if owner else None
    if not owner_id or owner_id == order.user_id:
        order.referral_cashback_paid = True
        await db.commit()
        return

    percent = Decimal(promo.cashback_percent) if promo and promo.cashback_percent is not None \
        else Decimal(ref_settings["purchase_cashback_percent"])
    if ref_settings.get("cashback_base") == "subtotal":
        base_amount = sum(
            (Decimal(i.product_price) * int(i.quantity or 1) for i in (order.items or [])),
            Decimal("0"),
        )
    else:
        base_amount = Decimal(order.amount or 0)
    min_amt = Decimal(ref_settings.get("min_order_amount") or 0)
    if base_amount < min_amt:
        order.referral_cashback_paid = True
        await db.commit()
        return
    cashback = (base_amount * percent / Decimal(100)).quantize(Decimal("0.01"))
    order.referral_cashback_paid = True
    if cashback > 0:
        await add_bonus_transaction(
            db, owner_id, cashback,
            reason=f"Кэшбэк за заказ #{order.id} по промокоду {promo_code}",
            tx_type=BonusTxType.accrual,
            order_id=order.id,
            commit=False,
        )
    await db.commit()


async def refund_order_bonuses(db: AsyncSession, order: Order, commit: bool = True) -> None:
    """Вернуть списанные при оформлении бонусы (отмена / брошенный заказ)."""
    if not order or order.bonus_refunded:
        return
    spent = Decimal(order.bonus_spent or 0)
    if spent <= 0 or not order.user_id:
        order.bonus_refunded = True
        if commit:
            await db.commit()
        return
    await add_bonus_transaction(
        db, order.user_id, spent,
        reason=f"Возврат бонусов за заказ #{order.id}",
        tx_type=BonusTxType.accrual,
        order_id=order.id,
        commit=False,
    )
    order.bonus_refunded = True
    if commit:
        await db.commit()


async def reverse_referral_cashback(db: AsyncSession, order: Order, commit: bool = True) -> None:
    """Забрать кэшбэк у держателя, если оплаченный заказ отменили."""
    if not order or not order.referral_cashback_paid:
        return
    txs = (
        await db.execute(
            select(BonusTransaction).where(
                BonusTransaction.order_id == order.id,
                BonusTransaction.type == BonusTxType.accrual,
                BonusTransaction.reason.ilike("%кэшбэк%"),
            )
        )
    ).scalars().all()
    for tx in txs:
        try:
            await add_bonus_transaction(
                db, tx.user_id, tx.amount,
                reason=f"Отмена кэшбэка по заказу #{order.id}",
                tx_type=BonusTxType.spend,
                order_id=order.id,
                commit=False,
            )
        except ValueError:
            # Если на счёте уже нет денег — уходим в минус нельзя; пишем 0-баланс.
            locked = (
                await db.execute(select(User).where(User.id == tx.user_id).with_for_update())
            ).scalar_one_or_none()
            available = Decimal(locked.bonus_balance or 0) if locked else Decimal("0")
            if available > 0:
                await add_bonus_transaction(
                    db, tx.user_id, available,
                    reason=f"Отмена кэшбэка по заказу #{order.id} (частично)",
                    tx_type=BonusTxType.spend,
                    order_id=order.id,
                    commit=False,
                )
    if commit:
        await db.commit()


async def list_customer_referrals(db: AsyncSession, user_id: int) -> list[dict]:
    rows = (
        await db.execute(
            select(User).where(User.referred_by_id == user_id).order_by(User.created_at.desc())
        )
    ).scalars().all()
    return [
        {
            "id": u.id,
            "email": u.email,
            "name": u.name,
            "is_verified": u.is_verified,
            "created_at": u.created_at,
            "signup_bonus_paid": u.referral_signup_bonus_paid,
        }
        for u in rows
    ]


# ─── Переходы по реферальной ссылке ──────────────────────────────────────────

def _hash_ip(ip: Optional[str]) -> Optional[str]:
    if not ip:
        return None
    raw = f"{ip}|{settings.secret_key}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


async def count_referral_clicks(db: AsyncSession, code: str) -> int:
    if not code:
        return 0
    result = await db.execute(
        select(func.count()).select_from(ReferralClick).where(
            ReferralClick.referral_code == code.strip().upper()
        )
    )
    return result.scalar() or 0


async def track_referral_click(
    db: AsyncSession,
    code: str,
    path: Optional[str] = None,
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> bool:
    """Записать переход. Повтор с того же IP по тому же коду в течение часа не дублируется."""
    code = (code or "").strip().upper()
    if not code or len(code) < 2:
        return False
    ip_hash = _hash_ip(ip)
    if ip_hash:
        since = datetime.now(timezone.utc) - timedelta(hours=1)
        exists = await db.execute(
            select(ReferralClick.id).where(
                ReferralClick.referral_code == code,
                ReferralClick.ip_hash == ip_hash,
                ReferralClick.created_at >= since,
            ).limit(1)
        )
        if exists.scalar_one_or_none():
            return False
    db.add(ReferralClick(
        referral_code=code,
        landing_path=(path or "")[:300] or None,
        ip_hash=ip_hash,
        user_agent=(user_agent or "")[:300] or None,
    ))
    await db.commit()
    return True


# ─── Текстовые блоки сайта ───────────────────────────────────────────────────

async def seed_site_pages(db: AsyncSession) -> None:
    from page_defaults import PAGE_DEFAULTS
    existing = await db.execute(select(SitePage.key))
    have = {row[0] for row in existing.all()}
    added = False
    for page in PAGE_DEFAULTS:
        if page["key"] in have:
            continue
        db.add(SitePage(
            key=page["key"],
            title=page["title"],
            content=page["content"],
            sort_order=page.get("sort_order") or 0,
        ))
        added = True
    if added:
        await db.commit()


async def list_site_pages(db: AsyncSession) -> list[SitePage]:
    await seed_site_pages(db)
    result = await db.execute(select(SitePage).order_by(SitePage.sort_order, SitePage.key))
    return list(result.scalars().all())


async def get_site_page(db: AsyncSession, key: str) -> Optional[SitePage]:
    await seed_site_pages(db)
    result = await db.execute(select(SitePage).where(SitePage.key == key))
    return result.scalar_one_or_none()


async def update_site_page(db: AsyncSession, key: str, values: dict) -> Optional[SitePage]:
    page = await get_site_page(db, key)
    if not page:
        return None
    if "title" in values and values["title"] is not None:
        page.title = values["title"].strip()
    if "content" in values and values["content"] is not None:
        page.content = values["content"]
    if "sort_order" in values and values["sort_order"] is not None:
        page.sort_order = int(values["sort_order"])
    await db.commit()
    await db.refresh(page)
    return page


# ─── Яндекс Метрика ──────────────────────────────────────────────────────────

async def _get_app_setting_raw(db: AsyncSession, key: str):
    result = await db.execute(select(AppSetting).where(AppSetting.key == key))
    row = result.scalar_one_or_none()
    return None if row is None else row.value


async def _set_app_setting_raw(db: AsyncSession, key: str, value) -> None:
    existing = await db.execute(select(AppSetting).where(AppSetting.key == key))
    row = existing.scalar_one_or_none()
    if row:
        row.value = value
    else:
        db.add(AppSetting(key=key, value=value))


async def get_metrika_settings(db: AsyncSession) -> dict:
    counter = await _get_app_setting_raw(db, "metrika.counter_id")
    token = await _get_app_setting_raw(db, "metrika.oauth_token")
    counter_id = "" if counter is None else str(counter).strip()
    oauth = "" if token is None else str(token).strip()
    return {"counter_id": counter_id, "oauth_token": oauth}


async def set_metrika_settings(db: AsyncSession, data: dict) -> dict:
    current = await get_metrika_settings(db)
    if "counter_id" in data and data["counter_id"] is not None:
        current["counter_id"] = str(data["counter_id"]).strip()
        await _set_app_setting_raw(db, "metrika.counter_id", current["counter_id"])
    if "oauth_token" in data and data["oauth_token"]:
        current["oauth_token"] = str(data["oauth_token"]).strip()
        await _set_app_setting_raw(db, "metrika.oauth_token", current["oauth_token"])
    await db.commit()
    return current
