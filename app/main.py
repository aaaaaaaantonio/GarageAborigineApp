from fastapi import FastAPI

app = FastAPI(title="CRM Backend")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
