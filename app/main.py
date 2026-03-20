from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.routers import order_router, product_router, generate_router

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

app.mount("/", StaticFiles(directory="web", html=True), name="web")
