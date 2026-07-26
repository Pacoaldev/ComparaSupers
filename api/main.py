"""
ComparaSupers API

Receives a shopping list and triggers scraping jobs for each supermarket.
The aggregator then compares totals and returns the cheapest option.

Endpoints:
  POST /compare   — submit a shopping list, get back prices per supermarket
  GET  /health    — liveness probe for Kubernetes
"""

import asyncio
import json
import os
import sys
from contextlib import asynccontextmanager

import redis.asyncio as aioredis
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

# Add scrapers directory to path so we can import scrapers directly
# In k8s this is handled by the container image layout
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "scrapers"))

from aggregator.main import aggregate_results  # noqa: E402  (imported after path fix)
from mercadona import MercadonaScraper  # noqa: E402
from dia import DiaScraper  # noqa: E402
from consum import ConsumScraper  # noqa: E402
from carrefour import CarrefourScraper  # noqa: E402
from lidl import LidlScraper  # noqa: E402
from family_cash import FamilyCashScraper  # noqa: E402
from alcampo import AlcampoScraper  # noqa: E402


# ---------------------------------------------------------------------------
# Config — read from environment variables (set via k8s ConfigMap / Secrets)
# ---------------------------------------------------------------------------

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
CACHE_TTL_SECONDS = int(os.getenv("CACHE_TTL_SECONDS", "3600"))  # 1 hour default


# ---------------------------------------------------------------------------
# Redis connection (shared across requests)
# ---------------------------------------------------------------------------

redis_client: aioredis.Redis | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Connect to Redis on startup, disconnect on shutdown."""
    global redis_client
    redis_client = aioredis.from_url(REDIS_URL, decode_responses=True)
    try:
        await redis_client.ping()
        print(f"[API] Connected to Redis at {REDIS_URL}")
    except Exception as e:
        print(f"[API] Warning: Redis not available ({e}). Caching disabled.")
        redis_client = None
    yield
    if redis_client:
        await redis_client.aclose()


app = FastAPI(
    title="ComparaSupers API",
    description="Compara precios de tu lista de la compra entre supermercados",
    version="1.0.0",
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class ShoppingList(BaseModel):
    items: list[str] = Field(
        min_length=1,
        max_length=50,
        examples=[["leche", "pan de molde", "huevos", "aceite de oliva"]],
    )


class ProductPrice(BaseModel):
    search_term: str
    found_name: str
    price: float
    unit: str
    url: str | None


class SupermarketResult(BaseModel):
    supermarket: str
    total: float
    products_found: int
    products_not_found: list[str]
    items: list[ProductPrice]


class CompareResponse(BaseModel):
    shopping_list: list[str]
    results: list[SupermarketResult]
    cheapest: str          # name of the cheapest supermarket
    savings: float         # difference between cheapest and most expensive


# ---------------------------------------------------------------------------
# Scrapers registry — add new supermarkets here
# ---------------------------------------------------------------------------

SCRAPERS = [
    MercadonaScraper(),
    DiaScraper(),
    ConsumScraper(),
    CarrefourScraper(),
    LidlScraper(),
    FamilyCashScraper(),
    AlcampoScraper(),
]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/health")
async def health():
    """Kubernetes liveness and readiness probe."""
    return {"status": "ok", "version": "1.0.0"}


@app.post("/compare", response_model=CompareResponse)
async def compare(shopping_list: ShoppingList):
    """
    Compare prices for a shopping list across all configured supermarkets.

    - Runs all scrapers concurrently
    - Caches results in Redis for CACHE_TTL_SECONDS to avoid hammering supermarket APIs
    - Returns ranked results with cheapest supermarket highlighted
    """
    items = [item.strip().lower() for item in shopping_list.items]
    cache_key = "compare:" + "|".join(sorted(items))

    # Try cache first
    if redis_client:
        cached = await redis_client.get(cache_key)
        if cached:
            print(f"[API] Cache hit for key: {cache_key}")
            return CompareResponse(**json.loads(cached))

    # Run all scrapers concurrently
    print(f"[API] Scraping {len(SCRAPERS)} supermarkets for {len(items)} items...")
    scraper_tasks = [scraper.search_products(items) for scraper in SCRAPERS]
    all_results = await asyncio.gather(*scraper_tasks, return_exceptions=True)

    # Build response
    supermarket_results: list[SupermarketResult] = []

    for scraper, results in zip(SCRAPERS, all_results):
        if isinstance(results, Exception):
            print(f"[API] Scraper {scraper.supermarket_name} failed: {results}")
            results = []

        found_terms = {r.search_term for r in results}
        not_found = [item for item in items if item not in found_terms]

        supermarket_results.append(SupermarketResult(
            supermarket=scraper.supermarket_name,
            total=scraper.total_price(results),
            products_found=len(results),
            products_not_found=not_found,
            items=[
                ProductPrice(
                    search_term=r.search_term,
                    found_name=r.name,
                    price=r.price,
                    unit=r.unit,
                    url=r.url,
                )
                for r in results
            ],
        ))

    valid_results = [r for r in supermarket_results if r.products_found > 0]
    if not valid_results:
        raise HTTPException(status_code=503, detail="No se pudo obtener precios de ningún supermercado")

    # Sort by total price (ascending), putting empty results at the end
    supermarket_results.sort(key=lambda x: (x.products_found == 0, x.total))

    cheapest = valid_results[0].supermarket
    cheapest_total = valid_results[0].total
    most_expensive_total = valid_results[-1].total
    savings = round(most_expensive_total - cheapest_total, 2)

    response = CompareResponse(
        shopping_list=items,
        results=supermarket_results,
        cheapest=cheapest,
        savings=savings,
    )

    # Cache result
    if redis_client:
        await redis_client.setex(cache_key, CACHE_TTL_SECONDS, response.model_dump_json())

    return response
