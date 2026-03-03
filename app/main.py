from fastapi import FastAPI
from app.api.endpoints import router as api_router
from app.middleware import AdminImpersonationMiddleware

app = FastAPI(title="EgoWealth AI Investment API", version="1.0.0")

# 註冊 Middlewares
app.add_middleware(AdminImpersonationMiddleware)

# 註冊 API Routers
app.include_router(api_router, prefix="/api")

@app.get("/health")
def health_check():
    return {"status": "ok"}
