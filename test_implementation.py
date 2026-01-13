from playwright.async_api import async_playwright
import playwright_stealth
from parsers.euroauto import EuroautoParser

async def test():
    async with async_playwright() as p:
        # Включаем видимый режим (headless=False), чтобы увидеть, что происходит
        try:
            browser = await p.chromium.launch(
                headless=False, 
                args=[
                    "--disable-blink-features=AutomationControlled",
                ]
            )
        except Exception as e:
            print(f"ОШИБКА: Не удалось запустить браузер.\n{e}")
            return

        semaphore = asyncio.Semaphore(5)
        parser = EuroautoParser(browser, semaphore)
        
        # Создаем контекст и применяем stealth-настройки
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        # Применяем stealth для маскировки
        try:
            await playwright_stealth.stealth_async(page)
        except Exception as e:
            print(f"DEBUG: Не удалось применить stealth: {e}")
        
        # Передаем уже созданную страницу в парсер (нужно немного изменить search)
        # Но для начала просто проверим, пустит ли нас на главную
        query = "1782109"
        print(f"--- Тестирование Euroauto (Stealth + Headless=False) для: {query} ---")
        
        try:
            results = await parser.search(query)
            
            print("\nРезультаты поиска:")
            if results:
                print(json.dumps(results, indent=2, ensure_ascii=False))
            else:
                print("Ничего не найдено (пустой список).")
            
            # Статистика
            analogs = [item for item in results if item.get("type") == "analog"]
            replacements = [item for item in results if item.get("type") == "replacement"]
            main = [item for item in results if "type" not in item and "message" not in item and "error" not in item]
            
            print(f"\nИТОГО:")
            print(f"- Основных товаров: {len(main)}")
            print(f"- Аналогов: {len(analogs)}")
            print(f"- Замен: {len(replacements)}")
            
            if not results or (len(results) == 1 and "message" in results[0]):
                print("\nПРЕДУПРЕЖДЕНИЕ: Товар не найден. Проверьте артикул вручную на сайте.")
            
        except Exception as e:
            print(f"\nКРИТИЧЕСКАЯ ОШИБКА при выполнении теста: {e}")
        finally:
            await browser.close()
            print("\n--- Тест завершен ---")

if __name__ == "__main__":
    asyncio.run(test())
