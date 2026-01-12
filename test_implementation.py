import asyncio
import json
from playwright.async_api import async_playwright
from parsers.euroauto import EuroautoParser

async def test():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        semaphore = asyncio.Semaphore(5)
        parser = EuroautoParser(browser, semaphore)
        
        query = "1782109"
        print(f"Testing Euroauto search for query: {query}")
        
        results = await parser.search(query)
        
        print("\nSearch results:")
        print(json.dumps(results, indent=2, ensure_ascii=False))
        
        if len(results) > 1:
            print(f"\nSUCCESS: Found {len(results)} items (including analogues/replacements).")
        elif len(results) == 1:
            if "message" in results[0]:
                 print("\nINFO: No items found message received.")
            else:
                 print("\nWARNING: Only 1 item found. Check if analogues were present on the page.")
        else:
            print("\nFAILURE: No items found.")
            
        await browser.close()

if __name__ == "__main__":
    asyncio.run(test())
