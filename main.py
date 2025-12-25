from fastapi import FastAPI, HTTPException
from playwright.async_api import async_playwright
from contextlib import asynccontextmanager

# Создаем lifespan-менеджер для управления браузером
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Код при запуске (startup)
    global browser, playwright_context
    playwright_context = await async_playwright().start()
    browser = await playwright_context.chromium.launch(
        headless=True,
        args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
    )
    yield
    # Код при выключении (shutdown)
    await browser.close()
    await playwright_context.stop()

app = FastAPI(lifespan=lifespan)

@app.get("/search")
async def search(query: str):
    if not query:
        raise HTTPException(status_code=400, detail="Query parameter is missing")
    
    page = await browser.new_page()
    url = f"https://skladmotorov.ru/search-by-string/?query={query}"
    
    try:
        # Увеличиваем таймаут до 20 сек, так как сайт может быть медленным
        await page.goto(url, wait_until="networkidle", timeout=20000)
        await page.wait_for_selector(".c-good-container", timeout=10000)
        
        items = await page.query_selector_all(".c-good-container")
        results = []

        for item in items:
            name_el = await item.query_selector(".c-good-container__category")
            price_el = await item.query_selector(".c-good-container__price__number")
            
            name = await name_el.inner_text() if name_el else "Без названия"
            price = await price_el.inner_text() if price_el else "Цена по запросу"
            
            results.append({
                "name": name.strip(),
                "price": price.strip()
            })
        
        return {"query": query, "results": results, "count": len(results)}

    except Exception:
        return {"query": query, "results": [], "count": 0}
    finally:
        await page.close()