"""
main.py
=======

FastAPI 应用入口。

负责：
- 全局日志配置
- 挂载业务路由 (rules / desensitize)
- 提供根路径与健康检查接口
"""

import logging
import os

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from app.routers import rules as rules_router
from app.routers import desensitize as desensitize_router
from app.routers import models as models_router
from app.services.rule_store import rule_store
from app.services.ner_engine import ner_engine
from app.services.image_ocr import image_ocr_engine

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

logger = logging.getLogger("ictrek-desensitize")

logging.getLogger("httpx").setLevel(logging.WARNING)

app = FastAPI(
    title="ictrek-desensitize",
    description="数据脱敏服务 - 提供基于正则规则的敏感信息识别与脱敏 HTTP API",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def reject_invalid_image_content_type(request, call_next):
    """图片脱敏接口只接收 JSON，避免 multipart 二进制请求触发 500。"""
    if request.method == "POST" and request.url.path == "/api/v1/desensitize/image":
        content_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        if content_type != "application/json":
            return JSONResponse(
                status_code=415,
                content={
                    "detail": (
                        "POST /api/v1/desensitize/image expects application/json with "
                        "image_base64; multipart/form-data is not supported."
                    )
                },
            )
    return await call_next(request)


@app.on_event("startup")
async def on_startup():
    """应用启动钩子: 加载内置规则和自定义规则。"""
    rule_store.reload()
    ner_engine.startup()
    image_ocr_engine.startup()
    builtin_count = len(rule_store.get_builtin_rules())
    custom_count = len(rule_store.get_custom_rules())
    logger.info(
        "初始化完成，内置规则 %d 条，自定义规则 %d 条",
        builtin_count,
        custom_count,
    )


app.include_router(rules_router.router)
app.include_router(desensitize_router.router)
app.include_router(models_router.router)


@app.get("/health", summary="健康检查")
async def health_check():
    return {"status": "ok", "service": "ictrek-desensitize"}


@app.head("/health", include_in_schema=False)
async def health_check_head():
    return {"status": "ok", "service": "ictrek-desensitize"}


@app.get("/api/v1/system/about", summary="运行信息")
async def system_about():
    return {
        "service_id": "com.ictrek.desensitize",
        "service": "ictrek-desensitize",
        "app_version": os.getenv("DESENSITIZE_APP_VERSION", ""),
        "profile": os.getenv("DESENSITIZE_PROFILE", ""),
        "backend_image": os.getenv("DESENSITIZE_BACKEND_IMAGE", ""),
        "frontend_image": os.getenv("DESENSITIZE_FRONTEND_IMAGE", ""),
        "ner": ner_engine.info(),
        "image_ocr": image_ocr_engine.info(),
    }
