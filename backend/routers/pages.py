"""Публичные и админские эндпоинты текстовых блоков (оферта, лояльность…)."""
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from auth import get_current_admin
import crud
from schemas import SitePageOut, SitePageUpdate, ReferralClickIn

router = APIRouter(tags=["pages"])


@router.get("/pages", response_model=list[SitePageOut])
async def list_pages(db: AsyncSession = Depends(get_db)):
    return await crud.list_site_pages(db)


@router.get("/pages/{key}", response_model=SitePageOut)
async def get_page(key: str, db: AsyncSession = Depends(get_db)):
    page = await crud.get_site_page(db, key)
    if not page:
        raise HTTPException(status_code=404, detail="Страница не найдена")
    return page


@router.put("/admin/pages/{key}", response_model=SitePageOut)
async def admin_update_page(
    key: str,
    data: SitePageUpdate,
    db: AsyncSession = Depends(get_db),
    _admin=Depends(get_current_admin),
):
    values = data.model_dump(exclude_unset=True)
    page = await crud.update_site_page(db, key, values)
    if not page:
        raise HTTPException(status_code=404, detail="Страница не найдена")
    return page


@router.post("/ref/click")
async def ref_click(
    data: ReferralClickIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    forwarded = request.headers.get("x-forwarded-for") or ""
    ip = (forwarded.split(",")[0].strip() if forwarded else None) or (
        request.client.host if request.client else None
    )
    ua = request.headers.get("user-agent")
    recorded = await crud.track_referral_click(
        db, data.code, path=data.path, ip=ip, user_agent=ua,
    )
    return {"ok": True, "recorded": recorded}
