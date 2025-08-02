from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from api.v1.api import api_router
import uvicorn

app = FastAPI(title="Intent Analysis API", version="1.0.0")

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={"message": "Internal server error", "details": str(exc)},
    )

app.include_router(api_router, prefix="/api/v1")


if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)