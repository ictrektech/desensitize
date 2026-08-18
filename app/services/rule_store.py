"""
rule_store.py
=============

规则存储管理。

- 内置规则: 硬编码在 BUILTIN_RULES 中，不可修改/删除，启停状态可持久化
- 自定义规则: 持久化到 JSON 文件，支持增删改查
"""

import json
import logging
import os
import re
from pathlib import Path
from typing import Optional

logger = logging.getLogger("ictrek-desensitize.rule_store")

DATA_DIR = Path(os.environ.get("DESENSITIZE_DATA_DIR", "/data"))
RULES_FILE = DATA_DIR / "custom_rules.json"
BUILTIN_STATE_FILE = DATA_DIR / "builtin_rule_state.json"


# ──────────────────────────────────────
# 内置规则
# ──────────────────────────────────────

BUILTIN_RULES = [
    {
        "id": "api_key_openai",
        "name": "OpenAI API Key",
        "description": "匹配 sk- / pk- / rk- 开头的 OpenAI API Key",
        "pattern": r"(?<![A-Za-z0-9])(?:sk|pk|rk)[_-](?:live|test)[_-][A-Za-z0-9]{24,}(?![A-Za-z0-9])",
        "placeholder": "[API_KEY]",
        "priority": 10,
        "enabled": True,
        "builtin": True,
        "category": "api_key",
    },
    {
        "id": "api_key_aliyun",
        "name": "阿里云 AccessKey",
        "description": "匹配 AKLT 开头的阿里云 AccessKey",
        "pattern": r"(?<![A-Za-z0-9])(AKLT[A-Za-z0-9]{18})(?![A-Za-z0-9])",
        "placeholder": "[ALIYUN_AK]",
        "priority": 10,
        "enabled": True,
        "builtin": True,
        "category": "api_key",
    },
    {
        "id": "api_key_github",
        "name": "GitHub Token",
        "description": "匹配 ghp_ / github_pat_ 开头的 GitHub Token",
        "pattern": r"(?<![A-Za-z0-9])(ghp|github_pat)_[A-Za-z0-9]{36,}(?![A-Za-z0-9])",
        "placeholder": "[GITHUB_TOKEN]",
        "priority": 10,
        "enabled": True,
        "builtin": True,
        "category": "api_key",
    },
    {
        "id": "api_key_aws",
        "name": "AWS Access Key ID",
        "description": "匹配 AKIA 开头的 AWS Access Key ID",
        "pattern": r"(?<![A-Za-z0-9])(AKIA[0-9A-Z]{16})(?![A-Za-z0-9])",
        "placeholder": "[AWS_KEY_ID]",
        "priority": 10,
        "enabled": True,
        "builtin": True,
        "category": "api_key",
    },
    {
        "id": "jwt_token",
        "name": "JWT Token",
        "description": "匹配三段式 JWT Token (eyJ...)",
        "pattern": r"(?<![A-Za-z0-9_-])(eyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,})(?![A-Za-z0-9_-])",
        "placeholder": "[JWT_TOKEN]",
        "priority": 10,
        "enabled": True,
        "builtin": True,
        "category": "api_key",
    },
    {
        "id": "bearer_token",
        "name": "Bearer Token",
        "description": "匹配 Authorization Header 中的 Bearer Token",
        "pattern": r"(?<![A-Za-z0-9])(Bearer\s+[A-Za-z0-9_\-\.=]+)(?![A-Za-z0-9_\-\.=])",
        "placeholder": "[AUTH_HEADER]",
        "priority": 8,
        "enabled": True,
        "builtin": True,
        "category": "api_key",
    },
    {
        "id": "id_card_cn",
        "name": "身份证号 (中国)",
        "description": "匹配 18 位中国身份证号",
        "pattern": r"(?<!\d)(\d{17}[\dXx])(?!\d)",
        "placeholder": "[ID_CARD]",
        "priority": 9,
        "enabled": True,
        "builtin": True,
        "category": "pii",
        "validator": "china_id",
    },
    {
        "id": "bank_card",
        "name": "银行卡号",
        "description": "匹配 15-19 位银行卡号",
        "pattern": r"(?<!\d)([1-9]\d{14,18})(?!\d)",
        "placeholder": "[BANK_CARD]",
        "priority": 8,
        "enabled": True,
        "builtin": True,
        "category": "pii",
        "validator": "luhn",
    },
    {
        "id": "phone_cn",
        "name": "手机号 (中国)",
        "description": "匹配 11 位中国手机号，支持 +86 前缀",
        "pattern": r"(?<!\d)(?:\+?86)?(1[3-9]\d{9})(?!\d)",
        "placeholder": "[PHONE_NUMBER]",
        "priority": 8,
        "enabled": True,
        "builtin": True,
        "category": "pii",
        "validator": "cn_mobile",
    },
    {
        "id": "email",
        "name": "邮箱地址",
        "description": "匹配标准邮箱格式",
        "pattern": r"(?<![A-Za-z0-9._%+-])([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})(?![A-Za-z0-9._%+-])",
        "placeholder": "[EMAIL_ADDRESS]",
        "priority": 7,
        "enabled": True,
        "builtin": True,
        "category": "pii",
    },
    {
        "id": "credential_keyword",
        "name": "密码/凭证关键词",
        "description": "匹配 password=xxx, secret: xxx, token='xxx' 等格式",
        "pattern": r"(?<![A-Za-z0-9_])(password|passwd|pwd|secret|token|api[_-]?key|credential)\s*[:=]\s*[\"']?([^\s\"',}]{4,})[\"']?",
        "placeholder": "[CREDENTIAL]",
        "priority": 6,
        "enabled": True,
        "builtin": True,
        "category": "api_key",
    },
    {
        "id": "ip_address",
        "name": "IP 地址 (IPv4)",
        "description": "匹配 IPv4 地址",
        "pattern": r"(?<![\d.])((?:\d{1,3}\.){3}\d{1,3})(?![\d.])",
        "placeholder": "[IP_ADDRESS]",
        "priority": 5,
        "enabled": True,
        "builtin": True,
        "category": "pii",
    },
    {
        "id": "url_sensitive_param",
        "name": "URL 敏感参数",
        "description": "匹配 URL 中 password/token/key/secret 参数值",
        "pattern": r"([?&])(password|token|key|secret|api[_-]?key)=([^&\s]+)",
        "placeholder": r"\1[REDACTED_PARAM]=[FILTERED]",
        "priority": 7,
        "enabled": True,
        "builtin": True,
        "category": "api_key",
    },
    {
        "id": "cn_taxpayer_id",
        "name": "纳税人识别号/统一社会信用代码",
        "description": "匹配 15-20 位纳税人识别号或统一社会信用代码",
        "pattern": r"(?<![A-Z0-9])([0-9A-Z]{15,20})(?![A-Z0-9])",
        "placeholder": "[TAXPAYER_ID]",
        "priority": 6,
        "enabled": True,
        "builtin": True,
        "category": "document",
    },
    {
        "id": "cn_invoice_number",
        "name": "发票代码/号码",
        "description": "匹配发票代码、发票号码等 8-20 位票据编号",
        "pattern": r"(?<!\d)(?:发票(?:代码|号码)|票据号码|机打号码|校验码)\s*[:：]?\s*(\d[\d\s-]{7,24}\d)(?!\d)",
        "placeholder": "[INVOICE_NUMBER]",
        "priority": 6,
        "enabled": True,
        "builtin": True,
        "category": "document",
    },
    {
        "id": "cn_logistics_order",
        "name": "订单号/运单号",
        "description": "匹配订单号、运单号、快递单号等物流/交易编号",
        "pattern": r"(?<![A-Za-z0-9])(?:订单号|运单号|快递单号|物流单号|单号)\s*[:：]?\s*([A-Za-z0-9][A-Za-z0-9\s-]{7,31})(?![A-Za-z0-9])",
        "placeholder": "[ORDER_NUMBER]",
        "priority": 6,
        "enabled": True,
        "builtin": True,
        "category": "document",
    },
]


class RuleStore:
    """规则存储管理器。"""

    def __init__(self):
        self._builtin: list[dict] = []
        self._custom: list[dict] = []
        self._compiled: dict[str, re.Pattern] = {}
        self._loaded = False

    def reload(self):
        """重新加载内置规则和自定义规则。"""
        self._builtin = [dict(r) for r in BUILTIN_RULES]
        self._apply_builtin_state()
        self._custom = self._load_custom()
        self._compile_all()
        self._loaded = True

    def _ensure_loaded(self):
        """保证所有请求都能使用内置规则，即使启动钩子未被执行。"""
        if not self._loaded:
            self.reload()

    def _load_custom(self) -> list[dict]:
        if not RULES_FILE.exists():
            return []
        try:
            with open(RULES_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                return data
        except Exception as e:
            logger.error("加载自定义规则失败: %s", e)
        return []

    def _load_builtin_state(self) -> dict[str, bool]:
        if not BUILTIN_STATE_FILE.exists():
            return {}
        try:
            with open(BUILTIN_STATE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return {str(k): bool(v) for k, v in data.items()}
        except Exception as e:
            logger.error("加载内置规则状态失败: %s", e)
        return {}

    def _apply_builtin_state(self):
        state = self._load_builtin_state()
        if not state:
            return
        for rule in self._builtin:
            if rule["id"] in state:
                rule["enabled"] = state[rule["id"]]

    def _save_builtin_state(self):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        state = {rule["id"]: bool(rule.get("enabled", True)) for rule in self._builtin}
        with open(BUILTIN_STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)

    def _save_custom(self):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        with open(RULES_FILE, "w", encoding="utf-8") as f:
            json.dump(self._custom, f, ensure_ascii=False, indent=2)

    def _compile_all(self):
        self._compiled.clear()
        for rule in self._builtin + self._custom:
            try:
                self._compiled[rule["id"]] = re.compile(rule["pattern"])
            except re.error as e:
                logger.error("规则 %s 正则编译失败: %s", rule["id"], e)

    def get_builtin_rules(self) -> list[dict]:
        self._ensure_loaded()
        return [r for r in self._builtin]

    def get_custom_rules(self) -> list[dict]:
        self._ensure_loaded()
        return [r for r in self._custom]

    def get_all_rules(self, enabled_only: bool = False) -> list[dict]:
        self._ensure_loaded()
        rules = self._builtin + self._custom
        if enabled_only:
            rules = [r for r in rules if r.get("enabled", True)]
        return rules

    def get_rule(self, rule_id: str) -> Optional[dict]:
        self._ensure_loaded()
        for r in self._builtin + self._custom:
            if r["id"] == rule_id:
                return r
        return None

    def get_compiled(self, rule_id: str) -> Optional[re.Pattern]:
        self._ensure_loaded()
        return self._compiled.get(rule_id)

    def add_custom_rule(self, rule: dict) -> dict:
        self._ensure_loaded()
        rule_id = rule.get("id") or self._gen_id(rule["name"])
        while self.get_rule(rule_id) is not None:
            rule_id = self._gen_id(rule["name"], suffix=True)
        rule["id"] = rule_id
        rule["builtin"] = False
        rule["enabled"] = rule.get("enabled", True)
        self._custom.append(rule)
        try:
            self._compiled[rule_id] = re.compile(rule["pattern"])
        except re.error as e:
            logger.error("新规则 %s 正则编译失败: %s", rule_id, e)
        self._save_custom()
        return rule

    def update_custom_rule(self, rule_id: str, updates: dict) -> Optional[dict]:
        self._ensure_loaded()
        for i, r in enumerate(self._custom):
            if r["id"] == rule_id:
                r.update(updates)
                if "pattern" in updates:
                    try:
                        self._compiled[rule_id] = re.compile(updates["pattern"])
                    except re.error as e:
                        logger.error("规则 %s 正则编译失败: %s", rule_id, e)
                self._save_custom()
                return r
        return None

    def update_builtin_enabled(self, rule_id: str, enabled: bool) -> Optional[dict]:
        self._ensure_loaded()
        for rule in self._builtin:
            if rule["id"] == rule_id:
                rule["enabled"] = enabled
                self._save_builtin_state()
                return rule
        return None

    def delete_custom_rule(self, rule_id: str) -> bool:
        self._ensure_loaded()
        before = len(self._custom)
        self._custom = [r for r in self._custom if r["id"] != rule_id]
        if len(self._custom) < before:
            self._compiled.pop(rule_id, None)
            self._save_custom()
            return True
        return False

    @staticmethod
    def _gen_id(name: str, suffix: bool = False) -> str:
        import unicodedata
        import hashlib

        normalized = unicodedata.normalize("NFKD", name)
        ascii_name = normalized.encode("ascii", "ignore").decode("ascii")
        slug = "".join(c.lower() if c.isalnum() else "_" for c in ascii_name).strip("_")
        slug = slug or "rule"
        if suffix:
            short_hash = hashlib.md5(name.encode()).hexdigest()[:4]
            return f"{slug}_{short_hash}"
        return f"custom_{slug}"


rule_store = RuleStore()
