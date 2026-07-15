import os
import uuid
import asyncio
import aiofiles
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status, Form
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from typing import List, Optional
from PIL import Image
import io

from database import get_db
from auth import get_current_admin, verify_password, create_access_token, get_password_hash
import crud
from schemas import (
    CategoryCreate, CategoryUpdate, CategoryOut,
    ProductCreate, ProductUpdate, ProductOut, ProductListResponse,
    StockUpdate, LoginRequest, TokenResponse, AdminUserOut,
    AdminUserCreate, AdminUserUpdate,
    OrderOut, OrderListResponse, OrderStatusUpdate, BroadcastRequest,
    PromoCodeCreate, PromoCodeOut, ImageReorderRequest
)
from models import AdminUser
from notifications import broadcast as tg_broadcast, get_broadcast_status

router = APIRouter(tags=["admin"])

UPLOAD_DIR = Path("/app/uploads")
UPLOAD_DIR.mkdir(exist_ok=True)
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
MAX_IMAGE_SIZE = 1920


# ─── Auth ─────────────────────────────────────────────────────────────────────

@router.post("/auth/login", response_model=TokenResponse)
async def login(data: LoginRequest, db: AsyncSession = Depends(get_db)):
    admin = await crud.get_admin_by_login(db, data.login)
    if not admin or not verify_password(data.password, admin.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid login or password"
        )
    if not admin.is_active:
        raise HTTPException(status_code=403, detail="Account disabled")
    await crud.update_last_login(db, admin.id)
    token = create_access_token({"sub": admin.login})
    return {"access_token": token}


@router.get("/admin/me", response_model=AdminUserOut)
async def me(current_admin: AdminUser = Depends(get_current_admin)):
    return current_admin


# ─── Admin: Categories ────────────────────────────────────────────────────────

@router.get("/admin/categories", response_model=List[CategoryOut])
async def admin_list_categories(
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(get_current_admin)
):
    cats = await crud.get_categories(db, active_only=False)
    result = []
    for cat in cats:
        result.append({
            "id": cat.id,
            "name": cat.name,
            "slug": cat.slug,
            "description": cat.description,
            "sort_order": cat.sort_order,
            "is_active": cat.is_active,
            "created_at": cat.created_at,
            "product_count": len(cat.products)
        })
    return result


@router.post("/admin/categories", response_model=CategoryOut, status_code=201)
async def admin_create_category(
    data: CategoryCreate,
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(get_current_admin)
):
    try:
        return await crud.create_category(db, data)
    except IntegrityError:
        raise HTTPException(status_code=409, detail="Категория с таким name/slug уже существует")


@router.put("/admin/categories/{category_id}", response_model=CategoryOut)
async def admin_update_category(
    category_id: int,
    data: CategoryUpdate,
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(get_current_admin)
):
    try:
        cat = await crud.update_category(db, category_id, data)
    except IntegrityError:
        raise HTTPException(status_code=409, detail="Категория с таким name/slug уже существует")
    if not cat:
        raise HTTPException(status_code=404, detail="Category not found")
    return cat


@router.delete("/admin/categories/{category_id}", status_code=204)
async def admin_delete_category(
    category_id: int,
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(get_current_admin)
):
    cat = await crud.get_category(db, category_id)
    if not cat:
        raise HTTPException(status_code=404, detail="Category not found")
    await crud.delete_category(db, category_id)


# ─── Admin: Products ──────────────────────────────────────────────────────────

@router.get("/admin/products", response_model=ProductListResponse)
async def admin_list_products(
    page: int = 1,
    per_page: int = 20,
    category_id: Optional[int] = None,
    search: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(get_current_admin)
):
    return await crud.get_products(
        db, page=page, per_page=per_page,
        category_id=category_id, active_only=False, search=search
    )


@router.post("/admin/products", response_model=ProductOut, status_code=201)
async def admin_create_product(
    data: ProductCreate,
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(get_current_admin)
):
    try:
        return await crud.create_product(db, data)
    except IntegrityError:
        raise HTTPException(status_code=409, detail="Товар с таким slug уже существует")


@router.get("/admin/products/{product_id}", response_model=ProductOut)
async def admin_get_product(
    product_id: int,
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(get_current_admin)
):
    product = await crud.get_product(db, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return product


@router.put("/admin/products/{product_id}", response_model=ProductOut)
async def admin_update_product(
    product_id: int,
    data: ProductUpdate,
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(get_current_admin)
):
    product = await crud.get_product(db, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    try:
        return await crud.update_product(db, product_id, data)
    except IntegrityError:
        raise HTTPException(status_code=409, detail="Товар с таким slug уже существует")


@router.delete("/admin/products/{product_id}", status_code=204)
async def admin_delete_product(
    product_id: int,
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(get_current_admin)
):
    product = await crud.get_product(db, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    # Delete image files
    for img in product.images:
        img_path = UPLOAD_DIR / img.url.split("/uploads/")[-1]
        if img_path.exists():
            img_path.unlink()
    await crud.delete_product(db, product_id)


@router.put("/admin/products/{product_id}/stock", response_model=ProductOut)
async def admin_update_stock(
    product_id: int,
    data: StockUpdate,
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(get_current_admin)
):
    product = await crud.get_product(db, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return await crud.update_stock(db, product_id, data.stock_status)


# ─── Admin: Images ────────────────────────────────────────────────────────────

@router.post("/admin/products/{product_id}/images", status_code=201)
async def admin_upload_image(
    product_id: int,
    file: UploadFile = File(...),
    is_primary: bool = Form(False),
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(get_current_admin)
):
    product = await crud.get_product(db, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"File type not allowed. Use: {ALLOWED_EXTENSIONS}")

    contents = await file.read()
    if len(contents) > 20 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large (max 20MB)")

    # Process & resize image
    img = Image.open(io.BytesIO(contents))
    img = img.convert("RGB")
    if img.width > MAX_IMAGE_SIZE or img.height > MAX_IMAGE_SIZE:
        img.thumbnail((MAX_IMAGE_SIZE, MAX_IMAGE_SIZE), Image.LANCZOS)

    filename = f"{product_id}_{uuid.uuid4().hex}.webp"
    save_path = UPLOAD_DIR / filename

    img.save(save_path, "WEBP", quality=85)

    url = f"/uploads/{filename}"
    image = await crud.add_product_image(db, product_id, url, is_primary)
    return {"id": image.id, "url": url, "is_primary": image.is_primary}


@router.delete("/admin/images/{image_id}", status_code=204)
async def admin_delete_image(
    image_id: int,
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(get_current_admin)
):
    from sqlalchemy import select
    from models import ProductImage
    result = await db.execute(select(ProductImage).where(ProductImage.id == image_id))
    img = result.scalar_one_or_none()
    if not img:
        raise HTTPException(status_code=404, detail="Image not found")
    # Delete file
    img_path = UPLOAD_DIR / img.url.split("/uploads/")[-1]
    if img_path.exists():
        img_path.unlink()
    await crud.delete_product_image(db, image_id)


@router.put("/admin/images/{image_id}/primary", status_code=200)
async def admin_set_primary_image(
    product_id: int,
    image_id: int,
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(get_current_admin)
):
    await crud.set_primary_image(db, product_id, image_id)
    return {"ok": True}


@router.put("/admin/products/{product_id}/images/reorder", status_code=200)
async def admin_reorder_images(
    product_id: int,
    data: ImageReorderRequest,
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(get_current_admin)
):
    """Update sort_order for product images (drag-and-drop reordering)."""
    product = await crud.get_product(db, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    await crud.reorder_product_images(db, product_id, [{"id": i.id, "sort_order": i.sort_order} for i in data.images])
    return {"ok": True}


# ── Admin: Orders ──────────────────────────────────────────────────────

@router.get("/admin/orders", response_model=OrderListResponse)
async def admin_list_orders(
    page: int = 1,
    per_page: int = 20,
    status: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(get_current_admin)
):
    return await crud.get_orders(db, page=page, per_page=per_page, status=status)


@router.get("/admin/orders/stats")
async def admin_orders_stats(
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(get_current_admin)
):
    orders_count = await crud.get_orders_count(db)
    users_count = await crud.get_tg_users_count(db)
    return {**orders_count, "tg_users": users_count}


@router.get("/admin/orders/{order_id}", response_model=OrderOut)
async def admin_get_order(
    order_id: int,
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(get_current_admin)
):
    order = await crud.get_order(db, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return order


@router.put("/admin/orders/{order_id}/status", response_model=OrderOut)
async def admin_update_order_status(
    order_id: int,
    data: OrderStatusUpdate,
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(get_current_admin)
):
    order = await crud.update_order_status(db, order_id, data.status)
    if not order:
        raise HTTPException(status_code=400, detail="Invalid status or order not found")
    return order


@router.delete("/admin/orders/{order_id}", status_code=204)
async def admin_delete_order(
    order_id: int,
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(get_current_admin)
):
    order = await crud.get_order(db, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    await crud.delete_order(db, order_id)


# ── Admin: Broadcast ─────────────────────────────────────────────────

@router.post("/admin/broadcast")
async def admin_broadcast(
    data: BroadcastRequest,
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(get_current_admin)
):
    """Queue a Telegram broadcast to all users who started the bot.

    Runs in the background so the HTTP request returns immediately; poll
    GET /admin/broadcast/status for progress.
    """
    chat_ids = await crud.get_all_tg_chat_ids(db)
    if not chat_ids:
        return {"queued": 0, "message": "No users found"}
    if get_broadcast_status().get("state") == "running":
        raise HTTPException(status_code=409, detail="A broadcast is already running")
    asyncio.create_task(tg_broadcast(chat_ids, data.text))
    return {"queued": len(chat_ids)}


@router.get("/admin/broadcast/status")
async def admin_broadcast_status(
    _: AdminUser = Depends(get_current_admin)
):
    """Progress of the current/last broadcast."""
    return get_broadcast_status()


# ── Admin: Promo Codes ──────────────────────────────────────────────────────

@router.get("/admin/promo-codes", response_model=List[PromoCodeOut])
async def admin_list_promo_codes(
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(get_current_admin)
):
    return await crud.get_all_promo_codes(db)


@router.post("/admin/promo-codes", response_model=PromoCodeOut, status_code=201)
async def admin_create_promo_code(
    data: PromoCodeCreate,
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(get_current_admin)
):
    try:
        return await crud.create_promo_code(
            db, data.code, data.discount_percent,
            data.is_active, data.usage_limit, data.expires_at
        )
    except Exception:
        raise HTTPException(status_code=409, detail="Промокод с таким названием уже существует")


@router.delete("/admin/promo-codes/{promo_id}", status_code=204)
async def admin_delete_promo_code(
    promo_id: int,
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(get_current_admin)
):
    await crud.delete_promo_code(db, promo_id)


@router.patch("/admin/promo-codes/{promo_id}/toggle", response_model=PromoCodeOut)
async def admin_toggle_promo_code(
    promo_id: int,
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(get_current_admin)
):
    promo = await crud.toggle_promo_code(db, promo_id)
    if not promo:
        raise HTTPException(status_code=404, detail="Promo code not found")
    return promo


# ── Admin: Users ──────────────────────────────────────────────────────

@router.get("/admin/users", response_model=List[AdminUserOut])
async def admin_list_users(
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(get_current_admin)
):
    return await crud.get_admins(db)


@router.post("/admin/users", response_model=AdminUserOut, status_code=201)
async def admin_create_user(
    data: AdminUserCreate,
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(get_current_admin)
):
    try:
        return await crud.create_admin(db, data.login, data.password)
    except IntegrityError:
        raise HTTPException(status_code=409, detail="Логин уже занят")


@router.put("/admin/users/{user_id}", response_model=AdminUserOut)
async def admin_update_user(
    user_id: int,
    data: AdminUserUpdate,
    db: AsyncSession = Depends(get_db),
    current_admin: AdminUser = Depends(get_current_admin)
):
    target = await crud.get_admin(db, user_id)
    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    # Cannot deactivate or delete yourself.
    if user_id == current_admin.id and data.is_active is False:
        raise HTTPException(status_code=400, detail="Нельзя деактивировать себя")

    values = data.model_dump(exclude_unset=True)
    password = values.pop("password", None)
    if password:
        values["password_hash"] = get_password_hash(password)

    try:
        updated = await crud.update_admin(db, user_id, values)
    except IntegrityError:
        raise HTTPException(status_code=409, detail="Логин уже занят")
    if not updated:
        raise HTTPException(status_code=404, detail="User not found")
    return updated


@router.delete("/admin/users/{user_id}", status_code=204)
async def admin_delete_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_admin: AdminUser = Depends(get_current_admin)
):
    if user_id == current_admin.id:
        raise HTTPException(status_code=400, detail="Нельзя удалить себя")
    target = await crud.get_admin(db, user_id)
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    await crud.delete_admin(db, user_id)
