from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from database import get_db
import crud
from schemas import ProductOut, ProductListResponse

router = APIRouter(prefix="/products", tags=["products"])


@router.get("/", response_model=ProductListResponse)
async def list_products(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    category_id: Optional[int] = Query(None),
    featured: bool = Query(False),
    search: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db)
):
    return await crud.get_products(
        db,
        page=page,
        per_page=per_page,
        category_id=category_id,
        featured_only=featured,
        active_only=True,
        search=search
    )


@router.get("/slug/{slug}", response_model=ProductOut)
async def get_product_by_slug(slug: str, db: AsyncSession = Depends(get_db)):
    product = await crud.get_product_by_slug(db, slug)
    if not product:
        raise HTTPException(status_code=404, detail="Товар не найден")
    return product


@router.get("/{product_id}", response_model=ProductOut)
async def get_product(product_id: int, db: AsyncSession = Depends(get_db)):
    product = await crud.get_product(db, product_id)
    if not product or not product.is_active:
        raise HTTPException(status_code=404, detail="Товар не найден")
    return product
