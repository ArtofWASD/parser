from abc import ABC, abstractmethod
from playwright.async_api import Browser

class BaseParser(ABC):
    def __init__(self, browser: Browser, semaphore: asyncio.Semaphore):
        self.browser = browser
        self.semaphore = semaphore

    @abstractmethod
    async def search(self, query: str) -> list:
        """Method to search for a query and return a list of items."""
        pass

    @abstractmethod
    async def get_details(self, url: str) -> dict:
        """Method to get details for a specific item URL."""
        pass
