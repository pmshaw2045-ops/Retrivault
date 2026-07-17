"""FastAPI 应用入口"""
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

# 加载 .env
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
env_path = PROJECT_ROOT / ".env"
load_dotenv(env_path)

from src.api.dependencies import get_components, init_components  # noqa: E402
from src.api.routes import eval, index, search, status  # noqa: E402
from src.api.routes.stream_search import router as stream_router  # noqa: E402

app = FastAPI(
    title="RAG Personal Knowledge Manager",
    version="0.1.0",
    description="Obsidian-first Personal Knowledge Management RAG System",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# API 路由
app.include_router(search.router, prefix="/api")
app.include_router(index.router, prefix="/api")
app.include_router(status.router, prefix="/api")
app.include_router(eval.router, prefix="/api")
app.include_router(stream_router, prefix="/api")

# 前端静态文件
frontend_dir = PROJECT_ROOT / "src" / "frontend"
app.mount("/static", StaticFiles(directory=str(frontend_dir)), name="static")


@app.get("/")
async def root():
    return FileResponse(str(frontend_dir / "index.html"))


@app.get("/eval")
async def eval_page():
    return FileResponse(str(frontend_dir / "eval.html"))


@app.on_event("startup")
async def startup():
    """应用启动：初始化所有组件"""
    try:
        init_components()
        print("✅ 所有组件初始化完成")
    except Exception as e:
        print(f"⚠️  组件初始化警告: {e}")


@app.on_event("shutdown")
async def shutdown():
    """应用关闭：清理资源"""
    try:
        comps = get_components()
        comps.db.close()
    except Exception:
        pass


@app.get("/api/health")
async def health():
    return {"status": "ok"}
