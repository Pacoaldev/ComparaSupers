"""
Lidl scraper.

Uses Lidl's internal search API:
https://www.lidl.es/q/api/search?q={query}&assortment=ES&locale=es_ES&version=2.0
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
}


def _normalize(text: str) -> str:
    """Lowercase, remove accents, collapse spaces."""
    text = text.lower().strip()
    replacements = {"á": "a", "é": "e", "í": "i", "ó": "o", "ú": "u", "ü": "u", "ñ": "n"}
    for a, b in replacements.items():
        text = text.replace(a, b)
    return re.sub(r"\s+", " ", text)


def _matches(product_name: str, search_term: str) -> bool:
    """Check if all search words appear in the product name."""
    name = _normalize(product_name)
    words = _normalize(search_term).split()
    return all(w in name for w in words)


class LidlScraper(BaseScraper):

    def __init__(self):
        super().__init__("Lidl")

    async def search_product(self, product_name: str) -> ProductResult | None:
        url = f"https://www.lidl.es/q/api/search?q={product_name.replace(' ', '+')}&assortment=ES&locale=es_ES&version=2.0"

        async with httpx.AsyncClient(headers=HEADERS, timeout=20) as client:
            try:
                resp = await client.get(url)
                if resp.status_code != 200:
                    print(f"[Lidl] Error HTTP {resp.status_code} buscando '{product_name}'")
                    return None
                data = resp.json()
            except Exception as e:
                print(f"[Lidl] Error de red/JSON buscando '{product_name}': {e}")
                return None

        items = data.get("items", [])
        if not items:
            return None

        # Filter by match relevance
        candidates = []
        for item in items:
            g_data = item.get("gridbox", {}).get("data", {})
            title = g_data.get("title") or g_data.get("fullTitle") or ""
            if not title or not _matches(title, product_name):
                continue

            price_info = g_data.get("price", {})
            price_val = price_info.get("price")
            if price_val is None:
                continue

            try:
                price = float(price_val)
            except (ValueError, TypeError):
                continue

            if price <= 0:
                continue

            unit = price_info.get("packaging", {}).get("text") or "ud"
            canonical_url = g_data.get("canonicalUrl")
            full_url = f"https://www.lidl.es{canonical_url}" if canonical_url else None

            # Check if it's a pack
            is_pack = "pack" in title.lower() or "x " in title.lower()

            candidates.append({
                "name": title,
                "price": price,
                "unit": unit,
                "url": full_url,
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
