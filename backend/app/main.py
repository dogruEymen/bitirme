from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.api.routes.chat import router as chat_router
from backend.app.api.routes.health import router as health_router
from backend.app.api.routes.analytics import router as analytics_router
from backend.app.api.routes.bulletin import router as bulletin_router
from backend.app.api.routes.auth import router as auth_router


app = FastAPI(
    title="Academic Literature Intelligence Platform API",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router, tags=["health"])
app.include_router(auth_router, tags=["auth"])
app.include_router(chat_router, tags=["chat"])
app.include_router(analytics_router, tags=["analytics"])
app.include_router(bulletin_router, tags=["bulletin"])
