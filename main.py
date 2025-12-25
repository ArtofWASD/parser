import uvicorn
from fastapi import FastAPI

app = FastAPI()

@app.get("/")
async def root():
    return {"status": "ok", "message": "Server is alive"}

if __name__ == "__main__":
    # Важно: 0.0.0.0 позволяет видеть сервер вне контейнера
    uvicorn.run(app, host="0.0.0.0", port=8000)