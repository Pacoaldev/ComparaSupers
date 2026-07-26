import asyncio
import sys
sys.path.insert(0, "scrapers")
from dia import DiaScraper

async def main():
    scraper = DiaScraper()
    for term in ["leche entera", "pan de molde", "huevos"]:
        result = await scraper.search_product(term)
        if result:
            print(f"✅ {term}: {result.name} → {result.price}€")
        else:
            print(f"❌ {term}: no encontrado")

asyncio.run(main())
