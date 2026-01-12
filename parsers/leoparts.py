import asyncio
from playwright.async_api import Browser
from .base import BaseParser

class LeopartsParser(BaseParser):
    def __init__(self, browser: Browser, semaphore: asyncio.Semaphore):
        super().__init__(browser, semaphore)
        self.base_url = "https://leoparts.ru"

    async def search(self, query: str) -> list:
        async with self.semaphore:
            page = await self.browser.new_page()
            search_url = f"{self.base_url}/search-by-string/?query={query}"
            results = []
            
            try:
                await page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
                
                # Ждем появления списка товаров
                try:
                    await page.wait_for_selector(".c-good-container", timeout=15000)
                    items = await page.query_selector_all(".c-good-container")
                except:
                    items = []

                if not items:
                    return [{
                        "searched_query": query,
                        "message": f"По данному номеру ({query}) товары не найдены",
                        "site": "leoparts.ru"
                    }]
                else:
                    detail_tasks = []
                    for item in items:
                        # Находим ссылку на карточку
                        link_el = await item.query_selector("a[href*='/autopart-product/']")
                        if link_el:
                            path = await link_el.get_attribute("href")
                            full_url = f"{self.base_url}{path}"
                            detail_tasks.append(self.get_details(full_url))
                    
                    # Закрываем страницу поиска перед выполнением детальных задач
                    await page.close()
                    page = None

                    # Собираем детали параллельно
                    if detail_tasks:
                        details_list = await asyncio.gather(*detail_tasks, return_exceptions=True)
                        for detail in details_list:
                            if isinstance(detail, Exception):
                                continue # Или залогировать ошибку
                            if detail:
                                detail["searched_query"] = query
                                detail["site"] = "leoparts.ru"
                                results.append(detail)
                
            except Exception as e:
                results.append({
                    "searched_query": query,
                    "error": str(e),
                    "site": "leoparts.ru"
                })
            finally:
                if page:
                    await page.close()
                
            return results

    async def get_details(self, url: str) -> dict:
        async with self.semaphore:
            page = await self.browser.new_page()
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                await page.wait_for_selector("h1.h2", timeout=10000)
                
                title_el = await page.query_selector("h1.h2")
                full_title = await title_el.inner_text() if title_el else "Без названия"
                
                price_el = await page.query_selector(".c-product-info__price-block__price")
                full_price = await price_el.inner_text() if price_el else "Цена по запросу"
                
                cross_numbers = "Не указаны"
                params = await page.query_selector_all(".c-description__product-params__param")
                for p in params:
                    name_el = await p.query_selector(".c-description__product-params__param__name")
                    if name_el:
                        name_text = await name_el.inner_text()
                        if "Кросс-номера" in name_text or "Номер по производителю" in name_text:
                            value_el = await p.query_selector(".c-description__product-params__param__value")
                            if value_el:
                                value_text = await value_el.inner_text()
                                if cross_numbers == "Не указаны":
                                    cross_numbers = value_text
                                else:
                                    cross_numbers += f", {value_text}"

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
