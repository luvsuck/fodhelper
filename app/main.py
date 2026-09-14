from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.routers import order_router, product_router, generate_router, finished_goods_router

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(order_router.router)
app.include_router(product_router.router)
app.include_router(generate_router.router, prefix="/api")
app.include_router(finished_goods_router.router)


@app.get("/cfg", include_in_schema=False)
def cfg_page():
    """隐藏的配置管理页（StaticFiles html=True 不会把 /cfg 映射到 cfg.html，需显式路由）"""
    return FileResponse("web/cfg.html")


app.mount("/", StaticFiles(directory="web", html=True), name="web")
