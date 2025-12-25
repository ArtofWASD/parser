import uvicorn
import asyncio
from fastapi import FastAPI, HTTPException
from playwright.async_api import async_playwright
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    global browser, playwright_context
    playwright_context = await async_playwright().start()
    browser = await playwright_context.chromium.launch(
        headless=True,
        args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
    )
    yield
    await browser.close()
    await playwright_context.stop()

app = FastAPI(lifespan=lifespan)

async def scrape_card_details(browser, url):
    """Парсинг данных внутри карточки товара"""
    page = await browser.new_page()
    try:
        await page.goto(url, wait_until="networkidle", timeout=20000)
        
        # 1. Забираем H1 (Название)
        title_el = await page.query_selector("h1.h2")
        title = await title_el.inner_text() if title_el else "Без названия"
        
        # 2. Забираем Цену
        price_el = await page.query_selector(".c-product-info__price-block__price")
        price = await price_el.inner_text() if price_el else "Цена по запросу"
        
        # 3. Забираем Кросс-номера
        # Ищем блок, где текст названия параметра содержит "Кросс-номера"
        cross_numbers = "Не указаны"
        param_blocks = await page.query_selector_all(".c-description__product-params__param")
        for block in param_blocks:
            name_el = await block.query_selector(".c-description__product-params__param__name")
            if name_el and "Кросс-номера" in await name_el.inner_text():
                val_el = await block.query_selector(".c-description__product-params__param__value")
                if val_el:
                    cross_numbers = await val_el.inner_text()
                break

        return {
            "full_name": title.strip(),
            "full_price": price.strip().replace('\xa0', ' '), # Убираем неразрывные пробелы
            "cross_numbers": cross_numbers.strip(),
            "link": url
        }
    except Exception as e:
        return {"error": f"Ошибка парсинга карточки: {str(e)}", "link": url}
    finally:
        await page.close()

@app.get("/search")
async def search(query: str):
    if not query:
        raise HTTPException(status_code=400, detail="Запрос пуст")
    
    # Разбиваем запрос по запятой и убираем лишние пробелы
    queries = [q.strip() for q in query.split(",")]
    all_results = []

    for q in queries:
        page = await browser.new_page()
        search_url = f"https://skladmotorov.ru/search-by-string/?query={q}"
        
        try:
            await page.goto(search_url, wait_until="networkidle", timeout=30000)
            
            # Ждем появления контейнеров с товарами
            try:
                await page.wait_for_selector(".c-good-container", timeout=7000)
                items = await page.query_selector_all(".c-good-container")
            except:
                items = []

            for item in items:
                # Ищем ссылку на карточку
                link_el = await item.query_selector("a[href*='/autopart-product/']")
                if link_el:
                    path = await link_el.get_attribute("href")
                    full_card_url = f"https://skladmotorov.ru{path}"
                    
                    # Заходим в карточку (с задержкой, чтобы не забанили)
                    await asyncio.sleep(1) 
                    details = await scrape_card_details(browser, full_card_url)
                    details["searched_by"] = q
                    all_results.append(details)
            
        except Exception as e:
            continue # Пропускаем ошибки по конкретному номеру и идем дальше
        finally:
            await page.close()
            await asyncio.sleep(1) # Пауза между разными поисковыми запросами

    return {
        "total_found": len(all_results),
        "results": all_results
    }

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)