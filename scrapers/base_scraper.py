"""
Base scraper class.
All supermarket scrapers inherit from this and implement `search_product`.
"""

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class ProductResult:
    """Represents a single product found in a supermarket."""
    supermarket: str
    search_term: str
    name: str
    price: float
    unit: str          # e.g. "1kg", "500ml", "ud"
    price_per_unit: float | None = None
    url: str | None = None
    available: bool = True


class BaseScraper(ABC):
    """
    Abstract base class for all supermarket scrapers.

    Each scraper is responsible for:
    - Searching a product by name
    - Returning the cheapest matching result
    """

    def __init__(self, supermarket_name: str):
        self.supermarket_name = supermarket_name

    @abstractmethod
    async def search_product(self, product_name: str) -> ProductResult | None:
        """
        Search for a product and return the best (cheapest) match.
        Returns None if product is not found.
        """
        raise NotImplementedError

    async def search_products(self, product_list: list[str]) -> list[ProductResult]:
        """
        Search all products in the list concurrently.
        Returns only the products that were found.
        """
        tasks = [self.search_product(p) for p in product_list]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        found = []
        for product, result in zip(product_list, results):
            if isinstance(result, Exception):
                print(f"[{self.supermarket_name}] Error buscando '{product}': {result}")
            elif result is not None:
                found.append(result)
            else:
                print(f"[{self.supermarket_name}] '{product}' no encontrado")

        return found

    def total_price(self, results: list[ProductResult]) -> float:
        """Sum of all product prices in a result list."""
        return round(sum(r.price for r in results), 2)
