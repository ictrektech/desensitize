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

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import rules as rules_router
from app.routers import desensitize as desensitize_router
from app.services.rule_store import rule_store

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


@app.on_event("startup")
async def on_startup():
    """应用启动钩子: 加载内置规则和自定义规则。"""
    rule_store.reload()
    builtin_count = len(rule_store.get_builtin_rules())
    custom_count = len(rule_store.get_custom_rules())
    logger.info(
        "初始化完成，内置规则 %d 条，自定义规则 %d 条",
        builtin_count,
        custom_count,
    )


app.include_router(rules_router.router)
app.include_router(desensitize_router.router)


@app.get("/health", summary="健康检查")
async def health_check():
    return {"status": "ok", "service": "ictrek-desensitize"}


@app.head("/health", include_in_schema=False)
async def health_check_head():
    return {"status": "ok", "service": "ictrek-desensitize"}
