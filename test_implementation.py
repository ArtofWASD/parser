import asyncio
import json
import os
from playwright.async_api import async_playwright
import playwright_stealth
from parsers.euroauto import EuroautoParser

async def test():
    async with async_playwright() as p:
        # Используем глубокий перехват (Deep Hooking) с эмуляцией Windows
        try:
            from playwright_stealth import Stealth
            # Явно просим Stealth косить под Windows, так как мы в Linux/WSL
            stealth = Stealth(
                navigator_platform_override="Win32",
                navigator_user_agent_override="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            stealth.hook_playwright_context(p)
            
            browser = await p.chromium.launch(
                headless=False,  # Включаем окно! Так Qrator нас не найдет
                args=[
                    "--disable-blink-features=AutomationControlled",
                ]
            )
        except Exception as e:
            print(f"ОШИБКА: Не удалось запустить браузер с маскировкой.\n{e}")
            return

        semaphore = asyncio.Semaphore(5)
        parser = EuroautoParser(browser, semaphore)
        
        # Парсер сам применит Stealth к своему контексту, так как мы пропатчили 'browser' через 'p'
        print("DEBUG: Запуск теста. Используется Deep Stealth Hooking.")
        
        query = "1782109"
        print(f"--- Тестирование Euroauto (Stealth + Headless=True) для: {query} ---")
        # Проверим IP еще раз
        try:
            import subprocess
            res = subprocess.run(['curl', '-s', 'ipinfo.io'], capture_output=True, text=True)
            print(f"DEBUG: Текущий IP/Провайдер:\n{res.stdout}")
        except:
            pass
        
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
