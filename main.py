import uvicorn
import asyncio
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel
from playwright.async_api import async_playwright
from contextlib import asynccontextmanager
from parsers.manager import ParserManager
from typing import Optional

@asynccontextmanager
async def lifespan(app: FastAPI):
    global browser, playwright_context, parser_manager
    playwright_context = await async_playwright().start()
    browser = await playwright_context.chromium.launch(
        headless=True,
        args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
    )
    # Можно настроить лимит одновременно открытых страниц (например 15)
    parser_manager = ParserManager(browser, max_concurrent_pages=15)
    yield
    await browser.close()
    await playwright_context.stop()

app = FastAPI(lifespan=lifespan)

class SearchRequest(BaseModel):
    queries: list[str]
    sites: Optional[list[str]] = None

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.get("/sites")
async def get_sites():
    """Получить список доступных сайтов для парсинга"""
    return {"sites": parser_manager.get_sites()}

@app.get("/search")
async def search_get(
    query: str, 
    sites: Optional[str] = Query(None, description="Comma-separated list of sites")
):
    """Метод поиска через query параметры"""
    if not query:
        raise HTTPException(status_code=400, detail="Query is empty")
    
    queries = [q.strip() for q in query.split(",")]
    if sites and sites.lower() == "all":
        selected_sites = None
    else:
        selected_sites = sites.split(",") if sites else None
    
    results = await parser_manager.search_all(queries, selected_sites)
    return {"results": results}

@app.post("/search")
async def search_post(request: SearchRequest):
    """Метод поиска через POST тело запроса"""
    if not request.queries:
        raise HTTPException(status_code=400, detail="Queries list is empty")
    
    selected_sites = request.sites
    if selected_sites and len(selected_sites) == 1 and selected_sites[0].lower() == "all":
        selected_sites = None
        
    results = await parser_manager.search_all(request.queries, selected_sites)
    return {"results": results}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)