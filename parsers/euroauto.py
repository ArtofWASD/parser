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
            # Устанавливаем реальный User-Agent
            await page.set_extra_http_headers({
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7"
            })
            
            results = []
            
            try:
                # Шаг 1: Идем на главную страницу
                response = await page.goto(self.base_url, wait_until="domcontentloaded", timeout=30000)
                
                if response and response.status == 403:
                    return [{
                        "searched_query": query,
                        "error": "Access Denied (403 Forbidden).",
                        "site": "euroauto.ru"
                    }]

                # Шаг 2: Ищем строку поиска и вбиваем артикул
                search_input_selector = "#header-search"
                try:
                    await page.wait_for_selector(search_input_selector, timeout=10000)
                    await page.fill(search_input_selector, query)
                    await page.press(search_input_selector, "Enter")
                except Exception as e:
                    # Если не нашли строку поиска на главной, возможно мы уже где-то не там
                    return [{
                        "searched_query": query,
                        "error": f"Search input not found: {str(e)}",
                        "site": "euroauto.ru"
                    }]

                # Шаг 3: Ждем результата
                # Сайт может редиректнуть или показать список
                await asyncio.sleep(3)
                
                try:
                    # Ждем либо карточку товара, либо список, либо сообщение "ничего не найдено"
                    await page.wait_for_selector("h1, .part-item, .product-card, .part-container-1, #product-new-block, .search-not-found", timeout=15000)
                except:
                    pass

                current_url = page.url
                
                # Проверяем, не на странице ли мы товара
                is_product_page = any(x in current_url for x in ["/firms/", "/parts/", "/part/"]) and "/filter/" not in current_url
                if not is_product_page:
                    product_container = await page.query_selector("#product-new-block, .part-container-1, .product-detail")
                    if product_container:
                        is_product_page = True
                
                if is_product_page:
                    detail = await self._extract_details(page, current_url)
                    if detail:
                        detail["searched_query"] = query
                        detail["site"] = "euroauto.ru"
                        results.append(detail)
                else:
                    # Проверяем список или "не найдено"
                    items = await page.query_selector_all(".part-item, .product-card, .item, .parts-list-item, .listing-item")
                    
                    if not items:
                        return [{
                            "searched_query": query,
                            "message": f"По данному номеру ({query}) товары не найдены",
                            "site": "euroauto.ru"
                        }]
                    
                    for item in items[:10]:
                        name_el = await item.query_selector(".name, h3, .title, .product-name")
                        price_el = await item.query_selector(".product_price, .price, .cost, .product-price")
                        link_el = await item.query_selector("a")
                        
                        if name_el and link_el:
                            name = await name_el.inner_text()
                            price = await price_el.inner_text() if price_el else "По запросу"
                            path = await link_el.get_attribute("href")
                            full_url = f"{self.base_url}{path}" if path.startswith("/") else path
                            
                            results.append({
                                "name": name.strip(),
                                "price": price.strip().replace('\xa0', ' '),
                                "url": full_url,
                                "searched_query": query,
                                "site": "euroauto.ru"
                            })

            except Exception as e:
                results.append({
                    "searched_query": query,
                    "error": str(e),
                    "site": "euroauto.ru"
                })
            finally:
                await page.close()
                
            return results

    async def get_details(self, url: str) -> dict:
        async with self.semaphore:
            page = await self.browser.new_page()
            await page.set_extra_http_headers({
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            })
            try:
                await page.goto(url, wait_until="networkidle", timeout=30000)
                return await self._extract_details(page, url)
            except Exception as e:
                return {"name": "Ошибка загрузки карточки", "url": url, "error": str(e)}
            finally:
                await page.close()

    async def _extract_details(self, page, url) -> dict:
        """Вспомогательный метод для извлечения данных со страницы товара."""
        try:
            await page.wait_for_selector("h1, .btn-soldout, .product_price, #product-new-block", timeout=10000)
        except:
            pass
            
        title_el = await page.query_selector("h1")
        full_title = await title_el.inner_text() if title_el else "Без названия"
        
        # Цена (.product_price)
        price_el = await page.query_selector(".product_price, .product-price, .item-price, .price")
        full_price = await price_el.inner_text() if price_el else "По запросу"
        
        # Кнопка "Товар продан"
        sold_out_el = await page.query_selector(".btn-soldout")
        if sold_out_el:
            sold_text = await sold_out_el.inner_text()
            if "продан" in sold_text.lower():
                full_price = "Продано"

        # Изображение
        img_el = await page.query_selector(".big-preview img, .main-img, .img-thumbnail, .product-photo img, #main-img")
        img_url = await img_el.get_attribute("src") if img_el else None
        if img_url and img_url.startswith("//"):
            img_url = f"https:{img_url}"
        elif img_url and img_url.startswith("/"):
            img_url = f"{self.base_url}{img_url}"

        # Наличие
        availability_el = await page.query_selector(".main-delivery-block, .availability, .stock, .part-price-container")
        availability = await availability_el.inner_text() if availability_el else "Нет данных"
        if availability:
            availability = " ".join(availability.split())

        return {
            "name": full_title.strip(),
            "price": full_price.strip().replace('\xa0', ' '),
            "image": img_url,
            "availability": availability.strip(),
            "url": url
        }
