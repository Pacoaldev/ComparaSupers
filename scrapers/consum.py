"""
Consum scraper — usa Playwright para navegar la SPA Angular.

Consum carga los productos via XHR desde su backend (aktiosdigitalservices).
Interceptamos esas llamadas para obtener el JSON con precios directamente.
"""

import re
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout
from base_scraper import BaseScraper, ProductResult


CONSUM_SEARCH = "https://tienda.consum.es/search?q={query}"


class ConsumScraper(BaseScraper):

    def __init__(self):
        super().__init__("Consum")

    async def search_product(self, product_name: str) -> ProductResult | None:
        url = CONSUM_SEARCH.format(query=product_name.replace(" ", "+"))
        products = []

        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                ],
            )
            context = await browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                locale="es-ES",
                viewport={"width": 1280, "height": 800},
            )

            api_responses = []

            async def handle_response(response):
                """Intercepta las llamadas JSON al backend de Consum."""
                url_r = response.url
                if response.status == 200 and (
                    "aktiosdigitalservices" in url_r
                    or "catalog" in url_r
                    or "search" in url_r
                ):
                    try:
                        ct = response.headers.get("content-type", "")
                        if "json" in ct:
                            body = await response.json()
                            api_responses.append(body)
                    except Exception:
                        pass

            page = await context.new_page()
            page.on("response", handle_response)

            try:
                await page.goto(url, wait_until="networkidle", timeout=35000)
            except PlaywrightTimeout:
                pass
            except Exception as e:
                print(f"[Consum] Error navegando: {e}")
                await browser.close()
                return None

            # Parsear respuestas interceptadas
            for response_data in api_responses:
                products.extend(self._parse_response(product_name, response_data))

            # Fallback: extraer del DOM si no hay respuestas API
            if not products:
                products = await self._extract_from_dom(page, product_name)

            await browser.close()

        if not products:
            return None

        best = min(products, key=lambda x: x.price)
        return best

    def _parse_response(self, search_term: str, data) -> list[ProductResult]:
        """Parsea respuesta JSON del backend de Consum."""
        results = []

        # El backend de Consum puede devolver distintas estructuras
        items = []
        if isinstance(data, list):
            items = data
        elif isinstance(data, dict):
            # Buscar lista de productos en distintos campos
            for key in ("products", "results", "items", "data", "content"):
                if key in data and isinstance(data[key], list):
                    items = data[key]
                    break

        for item in items:
            if not isinstance(item, dict):
                continue

            name = (
                item.get("name")
                or item.get("displayName")
                or item.get("description", "")
            )
            if not name:
                continue

            # Buscar precio en distintos campos
            price = None
            for field in ("price", "priceValue", "unitPrice", "salePrice", "finalPrice"):
                val = item.get(field)
                if val is not None:
                    try:
                        price = float(val)
                        break
                    except (ValueError, TypeError):
                        pass

            # A veces el precio está anidado
            if price is None:
                pricing = item.get("pricing") or item.get("priceData") or {}
                if isinstance(pricing, dict):
                    for field in ("price", "value", "amount"):
                        val = pricing.get(field)
                        if val is not None:
                            try:
                                price = float(val)
                                break
                            except (ValueError, TypeError):
                                pass

            if price is None or price <= 0:
                continue

            unit = item.get("unit") or item.get("unitMeasure") or "ud"
            url = item.get("url") or item.get("link")

            results.append(ProductResult(
                supermarket=self.supermarket_name,
                search_term=search_term,
                name=name,
                price=price,
                unit=str(unit),
                url=url,
            ))

        return results

    async def _extract_from_dom(self, page, product_name: str) -> list[ProductResult]:
        """Extrae productos del DOM renderizado cuando no hay intercepción API."""
        results = []

        try:
            # Esperar tarjetas de producto de Consum
            await page.wait_for_selector(
                "tol-product-widget, [class*='product-widget'], [class*='ProductCard']",
                timeout=10000,
            )
        except PlaywrightTimeout:
            pass

        try:
            raw = await page.evaluate("""
                () => {
                    // Selectores comunes en Angular/Ionic apps de supermercados
                    const selectors = [
                        'tol-product-widget',
                        '[class*="product-widget"]',
                        '[class*="ProductCard"]',
                        '.product-card',
                        'article[class*="product"]'
                    ];

                    let cards = [];
                    for (const sel of selectors) {
                        cards = document.querySelectorAll(sel);
                        if (cards.length > 0) break;
                    }

                    return Array.from(cards).slice(0, 10).map(card => {
                        const nameEl = card.querySelector(
                            '[class*="name"], [class*="title"], h2, h3, p'
                        );
                        const priceEl = card.querySelector(
                            '[class*="price"], [class*="Price"]'
                        );
                        const linkEl = card.querySelector('a[href]');
                        return {
                            name: nameEl ? nameEl.textContent.trim() : '',
                            price: priceEl ? priceEl.textContent.trim() : '',
                            url: linkEl ? linkEl.href : ''
                        };
                    }).filter(p => p.name && p.price);
                }
            """)

            for item in raw:
                price_str = re.sub(r"[^\d,\.]", "", item["price"]).replace(",", ".")
                try:
                    price = float(price_str)
                    if price > 0:
                        results.append(ProductResult(
                            supermarket=self.supermarket_name,
                            search_term=product_name,
                            name=item["name"],
                            price=price,
                            unit="ud",
                            url=item.get("url"),
                        ))
                except ValueError:
                    continue
        except Exception as e:
            print(f"[Consum] Error extrayendo DOM: {e}")

        return results
