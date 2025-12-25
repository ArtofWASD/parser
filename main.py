import uvicorn
from fastapi import FastAPI, HTTPException
from playwright.async_api import async_playwright
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Запуск браузера при старте контейнера
    global browser, playwright_context
    playwright_context = await async_playwright().start()
    browser = await playwright_context.chromium.launch(
        headless=True,
        args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
    )
    yield
    # Остановка при выключении
    await browser.close()
    await playwright_context.stop()

app = FastAPI(lifespan=lifespan)

@app.get("/")
async def root():
    return {"status": "ok", "message": "Parser is ready"}

@app.get("/search")
async def search(query: str):
    if not query:
        raise HTTPException(status_code=400, detail="Артикул не указан")
    
    page = await browser.new_page()
    url = f"https://skladmotorov.ru/search-by-string/?query={query}"
    
    try:
        # Увеличиваем таймаут до 30 секунд для стабильности
        await page.goto(url, wait_until="networkidle", timeout=30000)
        
        # Проверяем наличие товаров
        try:
            await page.wait_for_selector(".c-good-container", timeout=10000)
        except:
            return {"query": query, "results": [], "count": 0}

        items = await page.query_selector_all(".c-good-container")
        results = []

        for item in items:
            name_el = await item.query_selector(".c-good-container__category")
            price_el = await item.query_selector(".c-good-container__price__number")
            
            name = await name_el.inner_text() if name_el else "Нет названия"
            price = await price_el.inner_text() if price_el else "0"
            
            results.append({
                "name": name.strip(),
                "price": price.strip()
            })
        
        return {"query": query, "results": results, "count": len(results)}

    except Exception as e:
        return {"query": query, "results": [], "error": str(e)}
    finally:
        await page.close()

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)