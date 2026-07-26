"""Inspeccionar la estructura exacta del JSON de DIA."""
import httpx
import re
import json
import asyncio

async def main():
    url = "https://www.dia.es/search?q=leche+entera&format=json"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "text/html",
        "Referer": "https://www.dia.es/",
    }
    async with httpx.AsyncClient(headers=headers, timeout=15, follow_redirects=True) as client:
        r = await client.get(url)
        html = r.text

    print(f"HTML size: {len(html)}")

    # Buscar el script con los datos
    # DIA usa vike (Vite SSR framework) — buscar el script correcto
    scripts = re.findall(r'<script[^>]*id=["\']([^"\']+)["\'][^>]*>(.*?)</script>', html, re.DOTALL)
    print(f"Scripts con id: {[(s[0], len(s[1])) for s in scripts]}")

    # Buscar el bloque más grande de JSON
    all_scripts = re.findall(r'<script[^>]*>(.*?)</script>', html, re.DOTALL)
    json_blocks = []
    for s in all_scripts:
        s = s.strip()
        if s.startswith('{') or s.startswith('window.'):
            json_blocks.append((len(s), s[:100]))
    print(f"\nBloques JSON: {sorted(json_blocks, reverse=True)[:5]}")

    # Buscar searchProducts específicamente
    idx = html.find('searchProducts')
    if idx >= 0:
        print(f"\n'searchProducts' encontrado en posición {idx}")
        # Extraer contexto
        chunk = html[max(0,idx-200):idx+500]
        print(chunk[:600])
    else:
        print("\n'searchProducts' NO encontrado")
        # Buscar otros patrones de productos
        for pattern in ['product-card', 'data-test-id="product-card"', '"price":', 'search-product']:
            idx2 = html.find(pattern)
            if idx2 >= 0:
                print(f"'{pattern}' encontrado en posición {idx2}")
                print(html[idx2:idx2+300])
                break

asyncio.run(main())
