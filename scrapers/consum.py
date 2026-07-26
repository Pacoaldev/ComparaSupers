"""
Consum scraper — uses Consum's public REST API directly.

URL: https://tienda.consum.es/api/rest/V1.0/catalog/product?page=1&limit=20&offset=0&orderById=13&showProducts=true&q={query}
"""

import httpx
import re
from base_scraper import BaseScraper, ProductResult

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Referer": "https://tienda.consum.es/",
}


def _normalize(text: str) -> str:
    text = text.lower().strip()
    replacements = {"á": "a", "é": "e", "í": "i", "ó": "o", "ú": "u", "ü": "u", "ñ": "n"}
    for a, b in replacements.items():
        text = text.replace(a, b)
    return re.sub(r"\s+", " ", text)


def _matches(product_name: str, search_term: str) -> bool:
    name = _normalize(product_name)
    words = _normalize(search_term).split()
    return all(w in name for w in words)


class ConsumScraper(BaseScraper):

    def __init__(self):
        super().__init__("Consum")

    async def search_product(self, product_name: str) -> ProductResult | None:
        url = f"https://tienda.consum.es/api/rest/V1.0/catalog/product?page=1&limit=20&offset=0&orderById=13&showProducts=true&q={product_name.replace(' ', '+')}"

        async with httpx.AsyncClient(headers=HEADERS, timeout=20) as client:
            try:
                resp = await client.get(url)
                if resp.status_code != 200:
                    print(f"[Consum] Error HTTP {resp.status_code} buscando '{product_name}'")
                    return None
                data = resp.json()
            except Exception as e:
                print(f"[Consum] Error buscando '{product_name}': {e}")
                return None

        # Parse products from JSON response
        products = data.get("products", [])
        if not products:
            return None

        candidates = []
        for product in products:
            prod_data = product.get("productData", {})
            name = prod_data.get("name") or prod_data.get("description") or ""
            if not name or not _matches(name, product_name):
                continue

            # Verify category is food/supermarket
            is_ignored = False
            for cat in product.get("categories", []):
                cat_name = cat.get("name", "").lower()
                if any(ig in cat_name for ig in ["mascota", "limpieza", "perfumeri", "drogueri", "bebe", "cosmetic", "higiene"]):
                    is_ignored = True
                    break
            if is_ignored:
                continue

            price_data = product.get("priceData", {})
            prices = price_data.get("prices", [])
            price_val = None
            for p in prices:
                if p.get("id") == "PRICE":
                    val = p.get("value", {})
                    price_val = val.get("centAmount") or val.get("centUnitAmount")
                    break

            if price_val is None:
                continue

            try:
                price = float(price_val)
            except (ValueError, TypeError):
                continue

            if price <= 0:
                continue

            unit = price_data.get("unitPriceUnitType") or "ud"
            product_url = prod_data.get("url")

            # Check if it's a pack
            is_pack = "pack" in name.lower() or "x " in name.lower()

            candidates.append({
                "name": name,
                "price": price,
                "unit": unit,
                "url": product_url,
                "is_pack": is_pack,
            })

        if not candidates:
            return None

        # Prefer non-packs, then cheapest
        singles = [c for c in candidates if not c["is_pack"]]
        pool = singles if singles else candidates
        best = min(pool, key=lambda x: x["price"])

        return ProductResult(
            supermarket=self.supermarket_name,
            search_term=product_name,
            name=best["name"],
            price=best["price"],
            unit=best["unit"],
            url=best["url"],
        )
