import math
from datetime import datetime, timezone
from typing import Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, update, delete
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from models import Category, Product, ProductImage, ProductSize, AdminUser, StockStatus, TgUser, Order, OrderItem, OrderStatus, PromoCode
from schemas import (
    CategoryCreate, CategoryUpdate,
    ProductCreate, ProductUpdate,
    ProductListOut, StockStatus,
    OrderCreate,
)
from auth import get_password_hash


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
                         first_name: str = None, last_name: str = None):
    result = await db.execute(select(TgUser).where(TgUser.chat_id == chat_id))
    user = result.scalar_one_or_none()
    if user:
        user.username = username
        user.first_name = first_name
        user.last_name = last_name
        user.last_seen = datetime.now(timezone.utc)
    else:
        user = TgUser(chat_id=chat_id, username=username,
                      first_name=first_name, last_name=last_name)
        db.add(user)
    await db.commit()
    return user


async def get_all_tg_chat_ids(db: AsyncSession) -> list[int]:
    result = await db.execute(select(TgUser.chat_id))
    return [row[0] for row in result.all()]


async def get_tg_users_count(db: AsyncSession) -> int:
    result = await db.execute(select(func.count()).select_from(TgUser))
    return result.scalar()


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
        raise ValueError(f"Products not found or inactive: {missing}")

    order = Order(
        tg_user_chat_id=data.tg_user_chat_id,
        customer_name=data.customer_name,
        customer_contact=data.customer_contact,
        delivery_address=getattr(data, "delivery_address", None),
        comment=data.comment,
        order_type=getattr(data, "order_type", None),
    )
    db.add(order)
    await db.flush()

    # Resolve promo code discount if provided
    discount_percent = 0
    applied_promo = None
    if getattr(data, "promo_code", None):
        promo = await validate_promo_code(db, data.promo_code)
        if promo:
            discount_percent = promo.discount_percent
            applied_promo = promo.code
            # Increment usage count
            await db.execute(
                update(PromoCode)
                .where(PromoCode.id == promo.id)
                .values(used_count=PromoCode.used_count + 1)
            )

    for item_data in data.items:
        product = products_by_id[item_data.product_id]
        price = product.price
        disc_amount = None
        if discount_percent:
            from decimal import Decimal
            disc_amount = (price * Decimal(discount_percent) / Decimal(100)).quantize(Decimal('0.01'))
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

    await db.commit()
    return await get_order(db, order.id)


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
    await db.execute(update(Order).where(Order.id == order_id).values(status=s))
    await db.commit()
    return await get_order(db, order_id)


async def delete_order(db: AsyncSession, order_id: int):
    await db.execute(delete(Order).where(Order.id == order_id))
    await db.commit()


async def get_orders_count(db: AsyncSession) -> dict:
    total = (await db.execute(select(func.count()).select_from(Order))).scalar()
    new_count = (await db.execute(
        select(func.count()).select_from(Order).where(Order.status == OrderStatus.new)
    )).scalar()
    return {"total": total, "new": new_count}


# ── Promo Codes ────────────────────────────────────────────────────────────────────────────────

async def validate_promo_code(db: AsyncSession, code: str) -> Optional[PromoCode]:
    """Check if promo code is valid and return it, or None if invalid."""
    from datetime import datetime, timezone
    result = await db.execute(select(PromoCode).where(PromoCode.code == code.upper()))
    promo = result.scalar_one_or_none()
    if not promo:
        return None
    if not promo.is_active:
        return None
    if promo.usage_limit is not None and promo.used_count >= promo.usage_limit:
        return None
    if promo.expires_at and promo.expires_at < datetime.now(timezone.utc):
        return None
    return promo


async def get_all_promo_codes(db: AsyncSession) -> list:
    result = await db.execute(select(PromoCode).order_by(PromoCode.created_at.desc()))
    return list(result.scalars().all())


async def create_promo_code(db: AsyncSession, code: str, discount_percent: int,
                            is_active: bool = True, usage_limit=None, expires_at=None):
    promo = PromoCode(
        code=code.upper(),
        discount_percent=discount_percent,
        is_active=is_active,
        usage_limit=usage_limit,
        expires_at=expires_at,
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
