import asyncio
from playwright.async_api import Browser
from .skladmotorov import SkladMotorovParser
from .leoparts import LeopartsParser

class ParserManager:
    def __init__(self, browser: Browser, max_concurrent_pages: int = 10):
        self.browser = browser
        self.semaphore = asyncio.Semaphore(max_concurrent_pages)
        self.parsers = {
            "skladmotorov.ru": SkladMotorovParser(browser, self.semaphore),
            "leoparts.ru": LeopartsParser(browser, self.semaphore),
        }

    def get_sites(self) -> list[str]:
        """Возвращает список поддерживаемых сайтов."""
        return list(self.parsers.keys())

    async def search_all(self, queries: list[str], selected_sites: list[str] = None):
        """
        Ищет по всем или выбранным сайтам одновременно.
        Возвращает структурированный словарь: { сайт: { запрос: [результаты] } }
        """
        tasks = []

        # Определяем по каким парсерам искать
        if selected_sites:
            target_parser_items = [(name, p) for name, p in self.parsers.items() if name in selected_sites]
        else:
            target_parser_items = list(self.parsers.items())

        if not target_parser_items:
            return {}

        async def buffered_search(site_name, parser, query):
            res = await parser.search(query)
            return site_name, query, res

        for query in queries:
            for site_name, parser in target_parser_items:
                tasks.append(buffered_search(site_name, parser, query))

        # Запускаем все задачи одновременно
        raw_results = await asyncio.gather(*tasks)

        # Группируем результаты
        grouped_results = {}
        for site_name, query, items in raw_results:
            if site_name not in grouped_results:
                grouped_results[site_name] = {}
            grouped_results[site_name][query] = items

        return grouped_results
