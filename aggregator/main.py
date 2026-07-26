"""
Aggregator module.

Takes results from all scrapers and produces a ranked comparison:
- Which supermarket is cheapest for the full list
- Which products couldn't be found in each supermarket
- Savings compared to the most expensive option

This runs inside the API process (not a separate service) for simplicity.
In a future iteration it could become its own microservice reading from Redis.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SupermarketSummary:
    supermarket: str
    total: float
    products_found: int
    products_missing: list[str]
    rank: int  # 1 = cheapest


def aggregate_results(results_by_supermarket: dict[str, list]) -> list[SupermarketSummary]:
    """
    Rank supermarkets by total price for the given shopping list results.

    Args:
        results_by_supermarket: dict mapping supermarket name → list of ProductResult

    Returns:
        List of SupermarketSummary sorted by total price ascending (cheapest first).
    """
    summaries = []

    for supermarket, products in results_by_supermarket.items():
        total = round(sum(p.price for p in products), 2)
        found_terms = {p.search_term for p in products}
        summaries.append({
            "supermarket": supermarket,
            "total": total,
            "products_found": len(products),
            "found_terms": found_terms,
            "products": products,
        })

    # Sort by total ascending
    summaries.sort(key=lambda x: x["total"])

    ranked = []
    for rank, s in enumerate(summaries, start=1):
        ranked.append(SupermarketSummary(
            supermarket=s["supermarket"],
            total=s["total"],
            products_found=s["products_found"],
            products_missing=[],  # populated by caller who knows the full list
            rank=rank,
        ))

    return ranked


def format_comparison_report(
    shopping_list: list[str],
    summaries: list[SupermarketSummary],
) -> str:
    """
    Generate a human-readable text comparison report.
    Useful for CLI mode or logging.
    """
    if not summaries:
        return "No se obtuvieron resultados de ningún supermercado."

    lines = [
        "=" * 50,
        "  COMPARACIÓN DE PRECIOS — LISTA DE LA COMPRA",
        "=" * 50,
        f"Productos buscados: {', '.join(shopping_list)}",
        "",
    ]

    for s in summaries:
        medal = "🥇" if s.rank == 1 else ("🥈" if s.rank == 2 else "🥉")
        lines.append(f"{medal} {s.rank}. {s.supermarket:<15} → {s.total:.2f} €  ({s.products_found}/{len(shopping_list)} productos)")

    if len(summaries) >= 2:
        cheapest = summaries[0]
        priciest = summaries[-1]
        savings = round(priciest.total - cheapest.total, 2)
        lines += [
            "",
            f"💰 Ahorro comprando en {cheapest.supermarket} vs {priciest.supermarket}: {savings:.2f} €",
        ]

    lines.append("=" * 50)
    return "\n".join(lines)
