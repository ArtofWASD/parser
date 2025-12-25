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
    """Глубокий парсинг карточки товара"""
    page = await browser.new_page()
    try:
        # Устанавливаем долгий таймаут, так как карточки могут грузиться медленно
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        # Ждем именно заголовок карточки
        await page.wait_for_selector("h1.h2", timeout=10000)
        
        # 1. Полное название из карточки
        title_el = await page.query_selector("h1.h2")
        full_title = await title_el.inner_text() if title_el else "Без названия"
        
        # 2. Точная цена из карточки
        price_el = await page.query_selector(".c-product-info__price-block__price")
        full_price = await price_el.inner_text() if price_el else "Цена по запросу"
        
        # 3. Кросс-номера из таблицы характеристик
        cross_numbers = "Не указаны"
        # Селектор всех строк параметров
        params = await page.query_selector_all(".c-description__product-params__param")
        for p in params:
            name_text = await p.eval_on_selector(".c-description__product-params__param__name", "el => el.innerText")
            if "Кросс-номера" in name_text:
                cross_numbers = await p.eval_on_selector(".c-description__product-params__param__value", "el => el.innerText")
                break

        return {
            "name": full_title.strip(),
            "price": full_price.strip().replace('\xa0', ' '),
            "cross_numbers": cross_numbers.strip(),
            "url": url
        }
    except Exception as e:
        return {"name": "Ошибка загрузки карточки", "url": url, "error": str(e)}
    finally:
        await page.close()

@app.get("/search")
async def search(query: str):
    if not query:
        raise HTTPException(status_code=400, detail="Query is empty")
    
    # Поддержка нескольких артикулов через запятую
    queries = [q.strip() for q in query.split(",")]
    final_results = []

    for q in queries:
        page = await browser.new_page()
        search_url = f"https://skladmotorov.ru/search-by-string/?query={q}"
        
        try:
            await page.goto(search_url, wait_until="networkidle", timeout=30000)
            
            # Ждем появления списка товаров
            try:
                await page.wait_for_selector(".c-good-container", timeout=10000)
                items = await page.query_selector_all(".c-good-container")
            except:
                items = []

            for item in items:
                # Находим ссылку на карточку
                link_el = await item.query_selector("a[href*='/autopart-product/']")
                if link_el:
                    path = await link_el.get_attribute("href")
                    full_url = f"https://skladmotorov.ru{path}"
                    
                    # Заходим внутрь за деталями
                    await asyncio.sleep(1.5) # Пауза для стабильности
                    details = await scrape_card_details(browser, full_url)
                    details["searched_query"] = q
                    final_results.append(details)
            
        except Exception:
            continue
        finally:
            await page.close()
            await asyncio.sleep(1)

    return {"results": final_results, "count": len(final_results)}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)