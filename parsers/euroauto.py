import asyncio
from playwright.async_api import Browser
from .base import BaseParser

class EuroautoParser(BaseParser):
    def __init__(self, browser: Browser, semaphore: asyncio.Semaphore):
        super().__init__(browser, semaphore)
        self.base_url = "https://euroauto.ru"
        self.headers = {}

    async def search(self, query: str) -> list:
        async with self.semaphore:
            # Используем контекст без ручной установки UA, чтобы Stealth работал корректно
            context = await self.browser.new_context(
                viewport={'width': 1920, 'height': 1080}
            )
            page = await context.new_page()
            
            # Применяем Stealth прямо здесь, так как парсер создает свой контекст
            try:
                from playwright_stealth import Stealth
                await Stealth().apply_stealth_async(page)
            except:
                pass

            results = []
            
            try:
                # ШАГ 1: Заходим на главную
                print(f"DEBUG: Заход на главную {self.base_url} для прохождения проверки Qrator...")
                response = await page.goto(self.base_url, wait_until="domcontentloaded", timeout=30000)
                
                if response and response.status in [401, 403]:
                    print(f"DEBUG: Получен статус {response.status} (проверка Qrator). Ждем 15 сек...")
                    await asyncio.sleep(15)
                    
                    # Попробуем зайти сразу на страницу поиска
                    search_url = f"{self.base_url}/search/?q={query}"
                    print(f"DEBUG: Пробуем прямой переход на поиск: {search_url}")
                    response = await page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
                    print(f"DEBUG: Статус после прямого перехода: {response.status if response else 'None'}")
                    
                    if response and response.status in [401, 403]:
                        print("DEBUG: Прямой переход тоже заблокирован. Пробуем финальную перезагрузку...")
                        await asyncio.sleep(5)
                        await page.reload(wait_until="networkidle")
                    
                    print(f"DEBUG: URL после всех попыток: {page.url}")
                    
                    # Если статус все еще 401 на той же странице - тогда ой.
                    # Но обычно Qrator редиректит или обновляет страницу.
                
                # ШАГ 2: Ищем поле поиска и вводим запрос
                # Селекторы для поиска: #header-search, input[name='q'], .hd_search-input
                search_selector = "input[name='q'], #header-search, .hd_search-input, input[placeholder*='номер запчасти']"
                try:
                    await page.wait_for_selector(search_selector, timeout=10000)
                    print("DEBUG: Поле поиска найдено, вводим артикул...")
                    
                    # Кликаем и очищаем поле (на всякий случай)
                    await page.click(search_selector)
                    await page.keyboard.press("Control+A")
                    await page.keyboard.press("Backspace")
                    
                    # Вводим по буквам с небольшим интервалом
                    await page.type(search_selector, query, delay=100)
                    await asyncio.sleep(1)
                    await page.keyboard.press("Enter")
                    
                    print(f"DEBUG: Ожидание результатов поиска для {query}...")
                    # Ждем смены URL или появления контента
                    await page.wait_for_load_state("networkidle", timeout=20000)
                    
                except Exception as e:
                    print(f"DEBUG: Ошибка при взаимодействии с поиском: {e}")
                    await page.screenshot(path="debug_search_interaction.png")
                    print("DEBUG: Скриншот ошибки сохранен в debug_search_interaction.png")

                status = response.status if response else "No Response"
                print(f"DEBUG: Текущий URL: {page.url}")

                # Костыль для отладки: сохраним HTML и скриншот если пусто (нет результатов)
                try:
                    await page.wait_for_selector(".search__item, .product_price, h1, .product-list, .search-result", timeout=15000)
                except Exception as e:
                    print(f"DEBUG: Искомые селекторы не найдены за 15с.")
                    content = await page.content()
                    with open("debug_euroauto.html", "w", encoding="utf-8") as f:
                        f.write(content)
                    await page.screenshot(path="debug_euroauto.png")
                    print("DEBUG: Дамп и скриншот сохранены для анализа (debug_euroauto.html / .png)")
                
                current_url = page.url
                
                # Если сайт сразу перекинул на товар (или мы уже там)
                if any(x in current_url for x in ["/part/new/", "/part/used/", "/part/"]):
                    print(f"DEBUG: Перенаправлено на страницу товара: {current_url}")
                    items = await self._extract_all_on_page(page, current_url, query)
                    results.extend(items)
                else:
                    # Ищем список результатов
                    items = await page.query_selector_all(".search__item")
                    print(f"DEBUG: Найдено элементов .search__item: {len(items)}")
                    
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
                await context.close()
                
            return results

    async def get_details(self, url: str) -> dict:
        async with self.semaphore:
            context = await self.browser.new_context(
                user_agent=self.user_agent,
                extra_http_headers=self.headers,
                viewport={'width': 1920, 'height': 1080}
            )
            page = await context.new_page()
            try:
                # Для деталей тоже желательно зайти через главную, если это первый запрос в сессии, 
                # но обычно search уже "прогрел" контекст. Но здесь мы создаем новый контекст.
                # Чтобы не плодить контексты, в будущем можно переиспользовать один.
                await page.goto(self.base_url, wait_until="networkidle", timeout=30000)
                await asyncio.sleep(1)

                response = await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                if response and response.status == 403:
                    return {"name": "Ошибка доступа (403)", "url": url, "error": "Forbidden"}
                
                # На странице товара нам может понадобиться собрать все варианты тоже?
                # Но обычно get_details вызывается из списка, где мы итерируемся по ссылкам.
                # Для Euroauto мы решили, что если мы попали на страницу товара, мы забираем ВСЕ что там есть.
                items = await self._extract_all_on_page(page, url, "")
                return items[0] if items else None
            except Exception as e:
                return {"name": "Ошибка загрузки карточки", "url": url, "error": str(e)}
            finally:
                await page.close()
                await context.close()

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
