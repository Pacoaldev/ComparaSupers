"""
Debug v5: cerrar popup "Compra más rápido" y navegar a búsqueda.
"""
import asyncio
import json
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="es-ES",
            viewport={"width": 1280, "height": 800},
        )

        json_responses = []

        async def on_response(response):
            url = response.url
            ct = response.headers.get("content-type", "")
            if response.status == 200 and "json" in ct:
                try:
                    body = await response.json()
                    if isinstance(body, dict):
                        for key in ('products', 'results', 'items', 'hits'):
                            if key in body and isinstance(body[key], list) and len(body[key]) > 2:
                                json_responses.append({"url": url[:150], "key": key, "data": body[key]})
                                print(f"  [PRODUCTOS JSON] {url[:100]} → {len(body[key])} items")
                                break
                except Exception:
                    pass

        page = await context.new_page()
        page.on("response", on_response)

        # 1. Ir a la home del supermercado primero
        print("Cargando home de Carrefour supermercado...")
        await page.goto("https://www.carrefour.es/supermercado", wait_until="domcontentloaded", timeout=20000)
        await asyncio.sleep(2)

        # 2. Aceptar cookies si aparece
        try:
            await page.click("#onetrust-accept-btn-handler", timeout=3000)
            print("  Cookies aceptadas")
            await asyncio.sleep(1)
        except Exception:
            pass

        # 3. Cerrar el popup "Compra más rápido" — botón X
        print("Cerrando popup...")
        popup_closed = False
        for sel in [
            "button.modal__close",
            "button[aria-label='Cerrar']",
            "button[aria-label='cerrar']",
            ".modal__close",
            "button.close",
            # El botón × suele ser el primer botón dentro del modal
            ".modal button:first-of-type",
            "[class*='modal'] [class*='close']",
            "[class*='dialog'] [class*='close']",
            # Por texto
            "button:has-text('×')",
            "button:has-text('✕')",
        ]:
            try:
                await page.click(sel, timeout=1500)
                print(f"  Popup cerrado con: {sel}")
                popup_closed = True
                await asyncio.sleep(0.5)
                break
            except Exception:
                pass

        if not popup_closed:
            # Intentar con Escape
            await page.keyboard.press("Escape")
            print("  Enviado Escape para cerrar popup")
            await asyncio.sleep(1)

        # 4. Ahora navegar a la búsqueda
        print("Navegando a búsqueda de leche entera...")
        await page.goto(
            "https://www.carrefour.es/supermercado?query=leche+entera",
            wait_until="domcontentloaded",
            timeout=20000,
        )
        await asyncio.sleep(4)

        # 5. Esperar productos
        print("Esperando productos...")
        try:
            await page.wait_for_selector(
                "[data-testid='product-card'], [class*='product-card'], [class*='ProductCard']",
                timeout=10000
            )
            print("  ✅ Productos en DOM")
        except Exception:
            print("  ⚠️ No aparecen tarjetas de producto")

        await asyncio.sleep(2)
        current_url = page.url
        print(f"URL actual: {current_url}")

        # 6. Extraer productos del DOM
        print("\nExtrayendo productos del DOM...")
        items = await page.evaluate("""
            () => {
                const selectors = [
                    '[data-testid="product-card"]',
                    '[class*="product-card"]',
                    '[class*="ProductCard"]',
                    'article[class*="product"]',
                    '[class*="product-cell"]'
                ];
                let cards = [];
                for (const sel of selectors) {
                    cards = [...document.querySelectorAll(sel)];
                    if (cards.length > 0) break;
                }
                return cards.slice(0, 5).map(c => ({
                    text: c.innerText.slice(0, 300),
                    tag: c.tagName,
                    cls: c.className.slice(0, 80)
                }));
            }
        """)

        print(f"Tarjetas encontradas: {len(items)}")
        for item in items:
            print(f"\n[{item['tag']} / {item['cls'][:50]}]")
            print(item['text'][:200])

        # 7. Ver resultados JSON
        print(f"\nJSON de productos capturados: {len(json_responses)}")
        for r in json_responses[:2]:
            print(f"\nURL: {r['url']}")
            prod = r['data'][0]
            print(json.dumps(prod, ensure_ascii=False, indent=2)[:600])

        input("\nPresiona ENTER para cerrar...")
        await browser.close()

asyncio.run(main())
