from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .database import Base, engine
from .routers import admin, articles, changes, inquiry, settings, sops, usage

Base.metadata.create_all(bind=engine)

app = FastAPI(title="AI SOP Admin", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(articles.router)
app.include_router(changes.router)
app.include_router(sops.router)
app.include_router(settings.router)
app.include_router(admin.router)
app.include_router(usage.router)
app.include_router(inquiry.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}
