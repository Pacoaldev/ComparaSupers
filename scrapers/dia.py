"""
DIA scraper.

DIA devuelve todos los productos embebidos como JSON en el HTML
dentro de un tag <script id="vike_pageContext">.
No necesita Playwright ni autenticación.

URL: https://www.dia.es/search?q=<term>&format=json
"""

import json
import re
import httpx
from base_scraper import BaseScraper, ProductResult

DIA_SEARCH = "https://www.dia.es/search?q={query}&format=json"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-ES,es;q=0.9",
    "Referer": "https://www.dia.es/",
}


def _normalize(text: str) -> str:
    text = text.lower().strip()
    for a, b in {"á":"a","é":"e","í":"i","ó":"o","ú":"u","ü":"u","ñ":"n"}.items():
        text = text.replace(a, b)
    return text


def _matches(product_name: str, search_term: str) -> bool:
    name = _normalize(product_name)
    words = _normalize(search_term).split()
    return all(w in name for w in words)


class DiaScraper(BaseScraper):

    def __init__(self):
        super().__init__("DIA")

    async def search_product(self, product_name: str) -> ProductResult | None:
        url = DIA_SEARCH.format(query=product_name.replace(" ", "+"))

        async with httpx.AsyncClient(headers=HEADERS, timeout=20, follow_redirects=True) as client:
            try:
                response = await client.get(url)
                response.raise_for_status()
                html = response.text
            except Exception as e:
                print(f"[DIA] Error: {e}")
                return None

        return self._parse_html(product_name, html)

    def _parse_html(self, search_term: str, html: str) -> ProductResult | None:
        # DIA embeds all product data in a <script id="vike_pageContext"> tag
        match = re.search(
            r'<script[^>]+id=["\']vike_pageContext["\'][^>]*>(.*?)</script>',
            html,
            re.DOTALL,
        )
        if not match:
            # Fallback: buscar __NEXT_DATA__ o cualquier JSON grande
            match = re.search(r'<script[^>]*>\s*(\{.*?"searchProducts".*?\})\s*</script>', html, re.DOTALL)
            if not match:
                print(f"[DIA] No se encontró bloque de datos JSON en el HTML")
                return None

        try:
            data = json.loads(match.group(1))
        except json.JSONDecodeError:
            print(f"[DIA] Error parseando JSON")
            return None

        # Navegar el árbol de datos para encontrar los productos
        products = self._extract_products(data)
        if not products:
            print(f"[DIA] No se extrajeron productos del JSON")
            return None

        # Filtrar por relevancia con el término de búsqueda
        matching = [p for p in products if _matches(p.get("name", ""), search_term)]
        if not matching:
            # Si no hay match exacto, usar todos los resultados
            matching = products

        # Parsear precios y elegir el más barato (unidad, no pack)
        candidates = []
        for product in matching:
            price_str = product.get("price", "")
            if isinstance(price_str, (int, float)):
                price = float(price_str)
            else:
                # Formato "5,76 €" → 5.76
                price_clean = re.sub(r"[^\d,\.]", "", str(price_str)).replace(",", ".")
                try:
                    price = float(price_clean)
                except ValueError:
                    continue

            if price <= 0:
                continue

            name = product.get("name", "")
            url_path = product.get("url", "")
            full_url = f"https://www.dia.es{url_path}" if url_path and not url_path.startswith("http") else url_path

            # Evitar packs cuando sea posible
            is_pack = "pack" in name.lower() or "x " in name.lower()

            candidates.append({
                "name": name,
                "price": price,
                "unit": product.get("unit", "ud"),
                "url": full_url,
                "is_pack": is_pack,
            })

        if not candidates:
            return None

        # Preferir unidades sueltas, luego el más barato
        singles = [c for c in candidates if not c["is_pack"]]
        pool = singles if singles else candidates
        best = min(pool, key=lambda x: x["price"])

        return ProductResult(
            supermarket=self.supermarket_name,
            search_term=search_term,
            name=best["name"],
            price=best["price"],
            unit=best["unit"],
            url=best["url"],
        )

    def _extract_products(self, data: dict) -> list[dict]:
        """Navega el árbol JSON de DIA para encontrar la lista de productos."""
        results = []

        # 1. Intentar la nueva ruta: INITIAL_STATE -> header -> searchData -> search_items
        try:
            init_state = data.get("INITIAL_STATE", {})
            search_items = init_state.get("header", {}).get("searchData", {}).get("search_items", [])
            for item in search_items:
                parsed = self._parse_product_item(item)
                if parsed:
                    results.append(parsed)
        except Exception:
            pass

        # 2. Intentar la ruta antigua: pageContext -> pageProps -> initialState -> search -> searchProducts
        if not results:
            try:
                search_data = (
                    data.get("pageContext", data)
                        .get("pageProps", {})
                        .get("initialState", {})
                        .get("search", {})
                )
                search_products = search_data.get("searchProducts", [])
                for item in search_products:
                    parsed = self._parse_product_item(item)
                    if parsed:
                        results.append(parsed)
            except Exception:
                pass

        # 3. Fallback: buscar recursivamente
        if not results:
            self._recursive_search(data, results)

        return results

    def _parse_product_item(self, item: dict) -> dict | None:
        """Extrae nombre, precio y URL de un item de producto de DIA."""
        if not isinstance(item, dict):
            return None

        name = (
            item.get("display_name")
            or item.get("name")
            or item.get("displayName")
            or item.get("description", "")
        )
        if not name:
            return None

        # Precio — DIA lo guarda de varias formas
        price = None
        
        # Estructura nueva: item["prices"]["price"]
        prices_obj = item.get("prices")
        if isinstance(prices_obj, dict):
            price = prices_obj.get("price")

        if price is None:
            # Buscar en campos de nivel superior
            for field in ("price", "salePrice", "currentPrice", "priceFormatted"):
                val = item.get(field)
                if val is not None:
                    price = val
                    break

        if price is None:
            # Buscar en subestructuras anidadas
            if isinstance(prices_obj, dict):
                for field in ("value", "formattedValue", "price"):
                    val = prices_obj.get(field)
                    if val:
                        price = val
                        break

        url_path = item.get("url") or item.get("link") or item.get("slug") or ""
        unit = "ud"
        if isinstance(prices_obj, dict) and prices_obj.get("measure_unit"):
            unit = str(prices_obj.get("measure_unit")).lower()

        return {"name": name, "price": price or 0, "url": url_path, "unit": unit}

    def _recursive_search(self, obj, results: list, depth: int = 0):
        """Búsqueda recursiva de productos en el JSON."""
        if depth > 8:
            return
        if isinstance(obj, dict):
            name = obj.get("display_name") or obj.get("name") or obj.get("displayName", "")
            # Un producto tiene nombre Y precio
            prices = obj.get("prices")
            price_fields = [obj.get(f) for f in ("price", "salePrice", "currentPrice") if obj.get(f)]
            if name and (prices or price_fields) and len(obj) > 3:
                parsed = self._parse_product_item(obj)
                if parsed and parsed["price"]:
                    results.append(parsed)
            for v in obj.values():
                self._recursive_search(v, results, depth + 1)
        elif isinstance(obj, list):
            for item in obj:
                self._recursive_search(item, results, depth + 1)
