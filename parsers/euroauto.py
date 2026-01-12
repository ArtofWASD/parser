import asyncio
from playwright.async_api import Browser
from .base import BaseParser

class EuroautoParser(BaseParser):
    def __init__(self, browser: Browser, semaphore: asyncio.Semaphore):
        super().__init__(browser, semaphore)
        self.base_url = "https://euroauto.ru"

    async def search(self, query: str) -> list:
        async with self.semaphore:
            page = await self.browser.new_page()
            search_url = f"{self.base_url}/search/text/{query}/"
            results = []
            
            try:
                # Навигация как в SkladMotorov
                await page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
                
                # Ждем либо список либо карточку
                try:
                    await page.wait_for_selector(".search__item, .product_price", timeout=15000)
                except:
                    pass

                current_url = page.url
                
                # Если сайт сразу перекинул на товар
                if any(x in current_url for x in ["/part/new/", "/part/used/"]):
                    detail = await self._extract_details(page, current_url)
                    if detail:
                        detail["searched_query"] = query
                        detail["site"] = "euroauto.ru"
                        results.append(detail)
                else:
                    # Ищем список результатов
                    items = await page.query_selector_all(".search__item")
                    
                    if not items:
                        # Проверяем "не найдено"
                        content = await page.content()
                        if "не найдены" in content or "ничего не нашлось" in content.lower():
                            return [{
                                "searched_query": query,
                                "message": f"По данному номеру ({query}) товары не найдены",
                                "site": "euroauto.ru"
                            }]
                        
                        # Если пусто, но не "не найдено", возвращаем пустой список или ошибку
                        return []
                    
                    detail_tasks = []
                    # Берем первые 5 ссылок для деталей
                    for item in items[:5]:
                        link_el = await item.query_selector("a.search__item_link")
                        if link_el:
                            path = await link_el.get_attribute("href")
                            full_url = f"{self.base_url}{path}" if path.startswith("/") else path
                            detail_tasks.append(self.get_details(full_url))
                    
                    # Закрываем страницу поиска как в SkladMotorov
                    await page.close()
                    page = None

                    if detail_tasks:
                        details_list = await asyncio.gather(*detail_tasks, return_exceptions=True)
                        for detail in details_list:
                            if isinstance(detail, Exception) or not detail:
                                continue
                            detail["searched_query"] = query
                            detail["site"] = "euroauto.ru"
                            results.append(detail)
                
            except Exception as e:
                results.append({
                    "searched_query": query,
                    "error": str(e),
                    "site": "euroauto.ru"
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
                return await self._extract_details(page, url)
            except Exception as e:
                return {"name": "Ошибка загрузки карточки", "url": url, "error": str(e)}
            finally:
                await page.close()

    async def _extract_details(self, page, url) -> dict:
        """Извлечение данных со страницы товара."""
        try:
            await page.wait_for_selector("h1, .product_price", timeout=10000)
        except:
            pass
            
        title_el = await page.query_selector("h1")
        full_title = await title_el.inner_text() if title_el else "Без названия"
        
        price_el = await page.query_selector(".product_price-retail .product_price, .product_price")
        full_price = await price_el.inner_text() if price_el else "По запросу"
        
        # Обработка проданного товара
        sold_out_el = await page.query_selector(".btn-soldout")
        if sold_out_el:
            sold_text = await sold_out_el.inner_text()
            if "продан" in sold_text.lower():
                full_price = "Продано"

        img_el = await page.query_selector(".big-preview img, #main-img")
        img_url = await img_el.get_attribute("src") if img_el else None
        if img_url and img_url.startswith("//"):
            img_url = f"https:{img_url}"

        return {
            "name": full_title.strip(),
            "price": full_price.strip().replace('\xa0', ' '),
            "image": img_url,
            "url": url
        }
