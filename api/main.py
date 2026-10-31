from fastapi import FastAPI
app = FastAPI(title="ReliefRoute API", version="0.1.0")

@app.get("/health")
async def health():
    return {"status": "ok", "service": "reliefroute-api"}
