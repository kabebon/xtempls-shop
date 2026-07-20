import asyncio
import sys
sys.path.append('backend')
from backend.database import SessionLocal
from backend.models import ProductSize, Product
from sqlalchemy import select

async def main():
    async with SessionLocal() as db:
        res = await db.execute(select(ProductSize))
        sizes = res.scalars().all()
        print(f"Total sizes: {len(sizes)}")
        for s in sizes:
            print(f"Product {s.product_id}: Size {s.size} (Avail: {s.is_available})")
        
        # also print all products
        res = await db.execute(select(Product))
        products = res.scalars().all()
        for p in products:
            print(f"Product {p.id}: {p.name}")

if __name__ == '__main__':
    asyncio.run(main())
