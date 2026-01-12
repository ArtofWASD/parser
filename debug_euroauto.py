import asyncio
from playwright.async_api import async_playwright

async def run():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        
        url = "https://euroauto.ru/"
        print(f"Opening {url}...")
        try:
            response = await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            print(f"Status: {response.status}")
            
            await asyncio.sleep(3)
            
            content = await page.content()
            with open("page_dump.html", "w", encoding="utf-8") as f:
                f.write(content)
            
            await page.screenshot(path="debug_homepage.png")
            print("Screenshot saved to debug_homepage.png")
            
            # Check for selectors
            selectors = ["#header-search", "input[name='q']", "input[placeholder*='номер запчасти']", ".hd_search-input"]
            for s in selectors:
                el = await page.query_selector(s)
                print(f"Selector '{s}': {'FOUND' if el else 'NOT FOUND'}")
                if el:
                    is_vis = await el.is_visible()
                    print(f"Selector '{s}' visible: {is_vis}")

        except Exception as e:
            print(f"Error: {e}")
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(run())
