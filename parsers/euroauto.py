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
            await page.set_extra_http_headers({
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7"
            })
            
            results = []
            search_url = f"{self.base_url}/search/text/{query}/"
            
            try:
                # Шаг 1: Переход по прямой ссылке поиска
                # Используем networkidle для уверенности, что все JS-блоки прогрузились
                response = await page.goto(search_url, wait_until="networkidle", timeout=30000)
                
                if response and response.status == 403:
                    return [{
                        "searched_query": query,
                        "error": "Access Denied (403 Forbidden).",
                        "site": "euroauto.ru"
                    }]

                # Дополнительное ожидание для тяжелых скриптов сайта
                await asyncio.sleep(3)
                
                try:
                    # Ждем базовые элементы
                    await page.wait_for_selector(".search__item, .search__item_link, h1, .product_price, .search-not-found", timeout=10000)
                except:
                    pass

                current_url = page.url
                
                # Проверяем на страницу товара (редирект)
                is_product_page = any(x in current_url for x in ["/firms/", "/parts/", "/part/"]) and "/filter/" not in current_url
                if not is_product_page:
                    product_container = await page.query_selector("#product-new-block, .part-container-1, .product-detail, .part-page")
                    if product_container:
                        is_product_page = True
                
                if is_product_page:
                    detail = await self._extract_details(page, current_url)
                    if detail:
                        detail["searched_query"] = query
                        detail["site"] = "euroauto.ru"
                        results.append(detail)
                else:
                    # Мы на странице списка или поиска
                    # Ищем любые ссылки или блоки, похожие на результаты
                    items = await page.query_selector_all(".search__item, .search__item_link, .part-item, .product-card, .listing-item")
                    
                    if not items:
                        # Если не нашли по селекторам, попробуем найти текстом в ссылках (на всякий случай)
                        links = await page.query_selector_all("a")
                        for l in links:
                            txt = await l.inner_text()
                            if query in txt:
                                items = [l]
                                break

                    if not items:
                        content = await page.content()
                        title = await page.title()
                        if "не найдены" in content or "ничего не нашлось" in content.lower():
                            return [{
                                "searched_query": query,
                                "message": f"По данному номеру ({query}) товары не найдены",
                                "site": "euroauto.ru"
                            }]
                        
                        # Если пусто и не "не найден", выдаем ошибку с заголовком страницы
                        return [{
                            "searched_query": query,
                            "error": f"Результаты не загружены (Page Title: {title}). Возможно, требуется проверка 'Я не робот' или формат страницы изменился.",
                            "site": "euroauto.ru"
                        }]
                    
                    # Обрабатываем список товаров
                    # В .search__item_link часто уже лежит ссылка на товар
                    processed_urls = set()
                    for item in items[:5]:
                        # Пытаемся достать ссылку
                        href = await item.get_attribute("href")
                        if not href:
                            link_el = await item.query_selector("a")
                            if link_el:
                                href = await link_el.get_attribute("href")
                        
                        if href and href not in processed_urls:
                            processed_urls.add(href)
                            full_url = f"{self.base_url}{href}" if href.startswith("/") else href
                            
                            # Заходим в товар для получения цены и фото
                            detail = await self.get_details(full_url)
                            if detail:
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
            await page.wait_for_selector("h1, .product_price, #product-new-block", timeout=10000)
        except:
            pass
            
        title_el = await page.query_selector(".part-h1 h1, h1")
        full_title = await title_el.inner_text() if title_el else "Без названия"
        
        # Цена (приоритет на розничную)
        price_el = await page.query_selector(".product_price-retail .product_price, .product_price, .price")
        full_price = await price_el.inner_text() if price_el else "По запросу"
        
        # Кнопка "Товар продан"
        sold_out_el = await page.query_selector(".btn-soldout")
        if sold_out_el:
            sold_text = await sold_out_el.inner_text()
            if "продан" in sold_text.lower():
                full_price = "Продано"

        # Изображение
        img_el = await page.query_selector(".big-preview img, .main-img, #main-img, .product-photo img")
        img_url = await img_el.get_attribute("src") if img_el else None
        if img_url and img_url.startswith("//"):
            img_url = f"https:{img_url}"
        elif img_url and img_url.startswith("/"):
            img_url = f"{self.base_url}{img_url}"

        # Наличие
        availability_el = await page.query_selector(".main-delivery-block, .availability, .part-price-container")
        availability = await availability_el.inner_text() if availability_el else "В наличии"
        if availability:
            availability = " ".join(availability.split())

        return {
            "name": full_title.strip(),
            "price": full_price.strip().replace('\xa0', ' '),
            "image": img_url,
            "availability": availability.strip(),
            "url": url
        }
