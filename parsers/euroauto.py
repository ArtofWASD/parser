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
            # Устанавливаем реальный User-Agent для обхода простых проверок
            await page.set_extra_http_headers({
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7"
            })
            
            search_url = f"{self.base_url}/search/?q={query}"
            results = []
            
            try:
                # Переход на страницу поиска
                response = await page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
                
                # Проверяем на 403 Forbidden
                if response.status == 403:
                    return [{
                        "searched_query": query,
                        "error": "Access Denied (403 Forbidden). Qrator protection detected.",
                        "site": "euroauto.ru"
                    }]

                # Ждем немного для отработки JS
                await asyncio.sleep(2)

                # Проверяем, не перенаправило ли нас сразу на страницу товара
                current_url = page.url
                # Улучшенная проверка на страницу товара (firms, parts, part, catalog/part)
                is_product_page = any(x in current_url for x in ["/firms/", "/parts/", "/part/"]) and "/filter/" not in current_url
                
                if is_product_page:
                    detail = await self._extract_details(page, current_url)
                    if detail:
                        detail["searched_query"] = query
                        detail["site"] = "euroauto.ru"
                        results.append(detail)
                else:
                    # Мы на странице списка результатов или фильтров
                    # Попробуем найти элементы в списке
                    # На euroauto.ru список товаров часто в .part-item, .product-card, .item, .parts-list-item
                    items = await page.query_selector_all(".part-item, .product-card, .item, .parts-list-item, .listing-item")
                    
                    if not items:
                        # Если совсем ничего не нашли, попробуем еще раз подождать
                        await asyncio.sleep(3)
                        items = await page.query_selector_all(".part-item, .product-card, .item, .parts-list-item, .listing-item")

                    if not items:
                        return [{
                            "searched_query": query,
                            "message": f"По данному номеру ({query}) товары не найдены",
                            "site": "euroauto.ru"
                        }]
                    
                    for item in items[:10]: # Ограничим до 10 для быстроты
                        name_el = await item.query_selector(".name, h3, .title, .product-name")
                        # Селектор цены поменяли на .product_price + старые варианты
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
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                await asyncio.sleep(1) # Ждем прогрузки JS
                return await self._extract_details(page, url)
            except Exception as e:
                return {"name": "Ошибка загрузки карточки", "url": url, "error": str(e)}
            finally:
                await page.close()

    async def _extract_details(self, page, url) -> dict:
        """Вспомогательный метод для извлечения данных со страницы товара."""
        # Ждем заголовка или признака проданного товара
        try:
            await page.wait_for_selector("h1, .btn-soldout, .product_price", timeout=7000)
        except:
            pass
            
        title_el = await page.query_selector("h1")
        full_title = await title_el.inner_text() if title_el else "Без названия"
        
        # Цена (.product_price с подчеркиванием!)
        price_el = await page.query_selector(".product_price, .product-price, .item-price, .price")
        full_price = await price_el.inner_text() if price_el else "По запросу"
        
        # Если есть кнопка "Товар продан", помечаем это
        sold_out_el = await page.query_selector(".btn-soldout")
        if sold_out_el:
            sold_text = await sold_out_el.inner_text()
            if "продан" in sold_text.lower():
                full_price = "Продано"

        # Изображение (.big-preview img, .main-img, .img-thumbnail)
        img_el = await page.query_selector(".big-preview img, .main-img, .img-thumbnail, .product-photo img")
        img_url = await img_el.get_attribute("src") if img_el else None
        if img_url and img_url.startswith("//"):
            img_url = f"https:{img_url}"
        elif img_url and img_url.startswith("/"):
            img_url = f"{self.base_url}{img_url}"

        # Наличие (.main-delivery-block)
        availability_el = await page.query_selector(".main-delivery-block, .availability, .stock")
        availability = await availability_el.inner_text() if availability_el else "Нет данных"
        if availability:
            # Очистим от лишних пробелов и переносов
            availability = " ".join(availability.split())

        return {
            "name": full_title.strip(),
            "price": full_price.strip().replace('\xa0', ' '),
            "image": img_url,
            "availability": availability.strip(),
            "url": url
        }
