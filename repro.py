import asyncio
from playwright.async_api import async_playwright
from parsers.manager import ParserManager

async def test_search():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        manager = ParserManager(browser, max_concurrent_pages=5)
        
        queries = ["1850921"]
        # Тестируем sites=None (эквивалентно "all")
        results = await manager.search_all(queries, None)
        
        print(f"Results keys (sites): {list(results.keys())}")
        for site, queries_res in results.items():
            for query, items in queries_res.items():
                print(f"Site: {site}, Query: {query}, Items count: {len(items)}")
                if items and "message" in items[0]:
                    print(f"  Message: {items[0]['message']}")
                elif items:
                    print(f"  First item name: {items[0].get('name')}")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(test_search())
