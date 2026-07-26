"""
Mercadona scraper.

Strategy: the /api/search/ endpoint no longer exists.
We use /api/categories/ to load all products grouped by category,
then do keyword matching locally.

The full catalog is ~4000 products and loads fast (under 1s per category).
We cache the category→subcategory map so repeated calls don't re-fetch it.
"""

import asyncio
import re
import httpx
from base_scraper import BaseScraper, ProductResult

MERCADONA_BASE = "https://tienda.mercadona.es/api"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Referer": "https://tienda.mercadona.es/",
}


def _normalize(text: str) -> str:
    """Lowercase, remove accents, collapse spaces."""
    text = text.lower().strip()
    replacements = {"á": "a", "é": "e", "í": "i", "ó": "o", "ú": "u", "ü": "u", "ñ": "n"}
    for a, b in replacements.items():
        text = text.replace(a, b)
    return re.sub(r"\s+", " ", text)


def _matches(product_name: str, search_term: str) -> bool:
    """
    Check if a product name matches a search term.
    Splits the search term into words and checks if ALL of them appear in the product name.
    """
    name = _normalize(product_name)
    words = _normalize(search_term).split()
    return all(w in name for w in words)


class MercadonaScraper(BaseScraper):

    def __init__(self):
        super().__init__("Mercadona")
        # Cache: subcategory_id -> list of products (loaded lazily)
        self._category_map: dict[int, list[dict]] | None = None
        self._catalog: list[dict] | None = None
        self._lock = asyncio.Lock()

    async def _load_all_subcategory_ids(self, client: httpx.AsyncClient) -> list[int]:
        """Fetch top-level categories and collect all subcategory IDs."""
        resp = await client.get(f"{MERCADONA_BASE}/categories/")
        resp.raise_for_status()
        data = resp.json()

        ids = []
        for cat in data.get("results", []):
            for subcat in cat.get("categories", []):
                ids.append(subcat["id"])
        return ids

    async def _load_subcategory(self, client: httpx.AsyncClient, subcat_id: int) -> list[dict]:
        """Load all products for a given subcategory."""
        try:
            resp = await client.get(f"{MERCADONA_BASE}/categories/{subcat_id}/")
            resp.raise_for_status()
            data = resp.json()
            products = []
            for section in data.get("categories", []):
                products.extend(section.get("products", []))
            return products
        except Exception:
            return []

    async def _build_catalog(self, client: httpx.AsyncClient) -> list[dict]:
        """Load the full product catalog (all subcategories in parallel)."""
        subcat_ids = await self._load_all_subcategory_ids(client)
        tasks = [self._load_subcategory(client, sid) for sid in subcat_ids]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        all_products = []
        for r in results:
            if isinstance(r, list):
                all_products.extend(r)
        return all_products

    async def search_product(self, product_name: str) -> ProductResult | None:
        if self._catalog is None:
            async with self._lock:
                if self._catalog is None:
                    async with httpx.AsyncClient(headers=HEADERS, timeout=30) as client:
                        try:
                            self._catalog = await self._build_catalog(client)
                            print(f"[Mercadona] Catálogo cargado con éxito: {len(self._catalog)} productos.")
                        except Exception as e:
                            print(f"[Mercadona] Error cargando catálogo: {e}")
                            return None

        catalog = self._catalog or []

        # Find all matching products
        matches = [p for p in catalog if _matches(p.get("display_name", ""), product_name)]

        if not matches:
            return None

        # Parse prices and pick cheapest (single unit, not pack)
        candidates = []
        for product in matches:
            pi = product.get("price_instructions", {})
            try:
                # Prefer unit_price of a single item (not pack)
                is_pack = pi.get("is_pack", False)
                if is_pack:
                    price = float(pi.get("bulk_price", 0))  # price per base unit
                else:
                    price = float(pi.get("unit_price", 0))
            except (ValueError, TypeError):
                continue

            if price <= 0:
                continue

            unit_size = pi.get("unit_size", 1)
            size_format = pi.get("size_format", "ud")

            candidates.append({
                "name": product.get("display_name", ""),
                "price": price,
                "unit": f"{unit_size}{size_format}",
                "url": product.get("share_url"),
                "is_pack": is_pack,
            })

        if not candidates:
            return None

        # Prefer non-pack items, then cheapest
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
