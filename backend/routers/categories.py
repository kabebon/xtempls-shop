from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List

from database import get_db
import crud
from schemas import CategoryOut, CategoryCreate, CategoryUpdate

router = APIRouter(prefix="/categories", tags=["categories"])


@router.get("/", response_model=List[CategoryOut])
async def list_categories(db: AsyncSession = Depends(get_db)):
    cats = await crud.get_categories(db, active_only=True)
    result = []
    for cat in cats:
        cat_dict = {
            "id": cat.id,
            "name": cat.name,
            "slug": cat.slug,
            "description": cat.description,
            "sort_order": cat.sort_order,
            "is_active": cat.is_active,
            "created_at": cat.created_at,
            "product_count": len([p for p in cat.products if p.is_active])
        }
        result.append(cat_dict)
    return result


@router.get("/{category_id}", response_model=CategoryOut)
async def get_category(category_id: int, db: AsyncSession = Depends(get_db)):
    cat = await crud.get_category(db, category_id)
    if not cat:
        raise HTTPException(status_code=404, detail="Категория не найдена")
    return cat
