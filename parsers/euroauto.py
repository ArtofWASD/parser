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
                await page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
                
                try:
                    await page.wait_for_selector(".search__item, .product_price, h1", timeout=15000)
                except:
                    pass

                current_url = page.url
                
                # Если сайт сразу перекинул на товар (или мы уже там)
                if any(x in current_url for x in ["/part/new/", "/part/used/"]):
                    items = await self._extract_all_on_page(page, current_url, query)
                    results.extend(items)
                else:
                    # Ищем список результатов
                    items = await page.query_selector_all(".search__item")
                    
                    if not items:
                        content = await page.content()
                        if "не найдены" in content or "ничего не нашлось" in content.lower():
                            return [{
                                "searched_query": query,
                                "message": f"По данному номеру ({query}) товары не найдены",
                                "site": "euroauto.ru"
                            }]
                        return []
                    
                    detail_tasks = []
                    for item in items[:5]:
                        link_el = await item.query_selector("a.search__item_link")
                        if link_el:
                            path = await link_el.get_attribute("href")
                            full_url = self._fix_url(path, self.base_url)
                            detail_tasks.append(self.get_details(full_url))
                    
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
                # На странице товара нам может понадобиться собрать все варианты тоже?
                # Но обычно get_details вызывается из списка, где мы итерируемся по ссылкам.
                # Для Euroauto мы решили, что если мы попали на страницу товара, мы забираем ВСЕ что там есть.
                items = await self._extract_all_on_page(page, url, "")
                return items[0] if items else None
            except Exception as e:
                return {"name": "Ошибка загрузки карточки", "url": url, "error": str(e)}
            finally:
                await page.close()

    def _fix_url(self, url: str, base: str = "") -> str:
        if not url:
            return None
        if url.startswith("//"):
            return f"https:{url}"
        if url.startswith("/") and base:
            return f"{base}{url}"
        return url

    async def _extract_all_on_page(self, page, url: str, query: str) -> list:
        """Извлекает основной товар и все аналоги со страницы."""
        items = []
        
        # 1. Основной товар
        main_item = await self._extract_details(page, url)
        if main_item:
            main_item["searched_query"] = query
            main_item["site"] = "euroauto.ru"
            items.append(main_item)
            
        # 2. Аналоги из слайдеров (Новые и Б/У)
        cards = await page.query_selector_all(".slider-analog-card")
        for card in cards:
            try:
                brand_el = await card.query_selector(".slider-analog-card-content-brand")
                brand = await brand_el.inner_text() if brand_el else ""
                
                num_el = await card.query_selector(".slider-analog-card-content-num")
                number = await num_el.inner_text() if num_el else ""
                
                price_el = await card.query_selector(".slider-analog-card-content-price-num")
                price = await price_el.inner_text() if price_el else "По запросу"
                
                img_el = await card.query_selector("img")
                img_url = await img_el.get_attribute("src") if img_el else None
                
                items.append({
                    "name": f"{brand} {number}".strip() or "Аналог",
                    "price": price.strip().replace('\xa0', ' '),
                    "image": self._fix_url(img_url),
                    "url": url, # Ссылка та же, т.к. это варианты на текущей странице
                    "searched_query": query,
                    "site": "euroauto.ru",
                    "type": "analog"
                })
            except:
                continue

        # 3. Возможные замены
        replacements = await page.query_selector_all(".replacements__table-line")
        for rep in replacements:
            try:
                num_el = await rep.query_selector(".replacements__orig-num")
                rep_number = await num_el.inner_text() if num_el else ""
                rep_url = await num_el.get_attribute("href") if num_el else None
                
                name_el = await rep.query_selector(".replacements__name")
                name = await name_el.inner_text() if name_el else "Замена"
                
                items.append({
                    "name": f"{name} {rep_number}".strip(),
                    "price": "По запросу",
                    "url": self._fix_url(rep_url, self.base_url),
                    "searched_query": query,
                    "site": "euroauto.ru",
                    "type": "replacement"
                })
            except:
                continue
                
        return items

    async def _extract_details(self, page, url) -> dict:
        """Извлечение данных об основном товаре со страницы."""
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

        return {
            "name": full_title.strip(),
            "price": full_price.strip().replace('\xa0', ' '),
            "image": self._fix_url(img_url),
            "url": url
        }
