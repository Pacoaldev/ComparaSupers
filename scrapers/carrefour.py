"""
Carrefour scraper — usa Playwright (browser real) para evitar Cloudflare.

La tienda de Carrefour España intercepta las llamadas XHR a su API interna
que devuelven JSON limpio con precios y productos.
"""

import json
import re
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout
from base_scraper import BaseScraper, ProductResult


CARREFOUR_SEARCH = "https://www.carrefour.es/supermercado/search?query={query}"


class CarrefourScraper(BaseScraper):

    def __init__(self):
        super().__init__("Carrefour")

    async def search_product(self, product_name: str) -> ProductResult | None:
        url = CARREFOUR_SEARCH.format(query=product_name.replace(" ", "+"))
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

            # Interceptar respuestas JSON de la API interna de Carrefour
            api_data = []

            async def handle_response(response):
                if (
                    "api-product" in response.url
                    or "search" in response.url
                ) and response.status == 200:
                    try:
                        ct = response.headers.get("content-type", "")
                        if "json" in ct:
                            body = await response.json()
                            api_data.append(body)
                    except Exception:
                        pass

            page = await context.new_page()
            page.on("response", handle_response)

            try:
                await page.goto(url, wait_until="networkidle", timeout=30000)
            except PlaywrightTimeout:
                # Incluso con timeout parcial puede haber datos
                pass
            except Exception as e:
                print(f"[Carrefour] Error navegando: {e}")
                await browser.close()
                return None

            # Intentar extraer productos del DOM si la intercepción no funcionó
            if not api_data:
                products = await self._extract_from_dom(page, product_name)
            else:
                for data in api_data:
                    products.extend(self._parse_api_response(product_name, data))

            await browser.close()

        if not products:
            return None

        best = min(products, key=lambda x: x.price)
        return best

    async def _extract_from_dom(self, page, product_name: str) -> list[ProductResult]:
        """Extrae productos directamente del DOM renderizado."""
        results = []
        try:
            # Esperar a que aparezcan tarjetas de producto
            await page.wait_for_selector(
                "[data-testid='product-card'], .product-card, [class*='ProductCard']",
                timeout=10000,
            )
        except PlaywrightTimeout:
            pass

        try:
            # Extraer via JavaScript del DOM
            raw = await page.evaluate("""
                () => {
                    const cards = document.querySelectorAll(
                        '[data-testid="product-card"], .product-card, [class*="ProductCard"]'
                    );
                    return Array.from(cards).slice(0, 10).map(card => {
                        const nameEl = card.querySelector(
                            '[data-testid="product-name"], .product-card__title, h3, h2, [class*="name"]'
                        );
                        const priceEl = card.querySelector(
                            '[data-testid="product-price"], [class*="price"], .price'
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
            print(f"[Carrefour] Error extrayendo DOM: {e}")

        return results

    def _parse_api_response(self, search_term: str, data: dict) -> list[ProductResult]:
        """Parsea la respuesta JSON de la API interna de Carrefour."""
        results = []
        products = data.get("products", data.get("results", []))

        for product in products:
            pricing = product.get("priceData", product.get("price", {}))
            price = None
            for field in ("price", "finalPrice", "retailPrice", "value"):
                raw = pricing.get(field) if isinstance(pricing, dict) else None
                if raw is not None:
                    try:
                        price = float(raw)
                        break
                    except (ValueError, TypeError):
                        pass

            if price is None or price <= 0:
                continue

            name = (
                product.get("name")
                or product.get("displayName")
                or product.get("title", "")
            )
            slug = product.get("slug", "")
            url = f"https://www.carrefour.es/supermercado/{slug}/p" if slug else None

            results.append(ProductResult(
                supermarket=self.supermarket_name,
                search_term=search_term,
                name=name,
                price=price,
                unit="ud",
                url=url,
            ))

        return results
