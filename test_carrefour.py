"""
Test rápido del scraper de Carrefour desde la máquina local.
Corre con: python test_carrefour.py
"""
import asyncio
import sys
sys.path.insert(0, "scrapers")

from carrefour import CarrefourScraper

async def main():
    scraper = CarrefourScraper()
    print("Buscando 'leche entera' en Carrefour...")
    result = await scraper.search_product("leche entera")
    if result:
        print(f"✅ Encontrado: {result.name} → {result.price}€ ({result.unit})")
        print(f"   URL: {result.url}")
    else:
        print("❌ No encontrado")

asyncio.run(main())
