from fastapi import FastAPI, HTTPException
from playwright.async_api import async_playwright
import uvicorn

app = FastAPI()

# Глобальные переменные для браузера
browser = None
playwright_context = None

@app.on_event("startup")
async def startup():
    global browser, playwright_context
    playwright_context = await async_playwright().start()
    # Запускаем chromium с нужными флагами для работы в Docker
    browser = await playwright_context.chromium.launch(
        headless=True,
        args=["--no-sandbox", "--disable-setuid-sandbox"]
    )

@app.on_event("shutdown")
async def shutdown():
    await browser.close()
    await playwright_context.stop()

@app.get("/search")
async def search(query: str):
    if not query:
        raise HTTPException(status_code=400, detail="Query parameter is missing")
    
    page = await browser.new_page()
    url = f"https://skladmotorov.ru/search-by-string/?query={query}"
    
    try:
        await page.goto(url, wait_until="networkidle", timeout=15000)
        
        # Ждем появления товаров или сообщения, что ничего не найдено
        await page.wait_for_selector(".c-good-container", timeout=5000)
        
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

    except Exception as e:
        # Если ничего не найдено (timeout), возвращаем пустой список
        return {"query": query, "results": [], "count": 0}
    finally:
        await page.close()

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)