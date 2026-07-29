# 数据脱敏服务 (Desensitize Service)

基于正则规则的敏感信息识别与脱敏 HTTP API 服务。

## 目录结构

```
apps/desensitize/
├── app/                    # FastAPI 后端
│   ├── main.py             # 应用入口
│   ├── models/             # Pydantic 数据模型
│   │   └── schemas.py
│   ├── routers/            # API 路由
│   │   ├── rules.py        # 规则管理 CRUD
│   │   └── desensitize.py  # 脱敏 API
│   └── services/           # 核心服务
│       ├── engine.py       # 脱敏引擎（正则匹配 + 中文数字归一化）
│       └── rule_store.py   # 规则存储（内置 + 自定义）
├── frontend/               # React + Vite 前端
│   ├── src/
│   │   ├── App.tsx
│   │   ├── api/client.ts   # API 客户端
│   │   └── pages/
│   │       ├── RulesPage.tsx       # 规则管理
│   │       ├── TestPage.tsx        # 脱敏测试
│   │       └── IntegrationPage.tsx # 接入指南
│   ├── Dockerfile
│   ├── nginx.conf
│   └── package.json
├── docker/
│   ├── Dockerfile          # 后端镜像
│   └── build_image.sh      # 构建推送脚本
├── ictrek.app/             # VOS 应用打包
│   ├── VERSION
│   ├── scripts/
│   │   ├── package.sh      # 打包脚本
│   │   └── update_version.sh
│   └── src/
│       ├── manifest.yml
│       ├── docker-compose.yml
│       ├── configs.yml
│       ├── routers.yml
│       ├── README.zh-CN.md
│       └── README.en.md
├── .github/workflows/
│   └── vos-release.yml     # CI 流水线
├── requirements.txt
└── README.md               # 本文件
```

## 开发

### 后端

```bash
pip install -r requirements.txt
cd app && python -m uvicorn main:app --host 0.0.0.0 --port 5000 --reload
```

### 前端

```bash
cd frontend
npm install
npm run dev
```

### 构建镜像

```bash
cd docker
./build_image.sh
```

### VOS 打包

```bash
cd ictrek.app
./scripts/package.sh
```

打包产物为 `dist/desensitize_<version>_pull.tar`，外层安装包只包含
`app.tar.gz`；镜像地址写在包内 `.env`，由 VOS 按所选 profile 拉取。

发布前先提交业务修改，再执行：

```bash
cd apps/desensitize
ictrek.app/scripts/update_version.sh patch
```

脚本只推送 `vos-desensitize-v<version>` 触发 tag。GitHub Actions 打包、创建
`v<version>` GitHub Release，并将安装包发布到已配置的 VOS App Store。

## 内置规则

| 规则 | 分类 | 占位符 |
|------|------|--------|
| OpenAI API Key | api_key | [API_KEY] |
| 阿里云 AccessKey | api_key | [ALIYUN_AK] |
| GitHub Token | api_key | [GITHUB_TOKEN] |
| AWS Access Key ID | api_key | [AWS_KEY_ID] |
| JWT Token | api_key | [JWT_TOKEN] |
| Bearer Token | api_key | [AUTH_HEADER] |
| 身份证号 (中国) | pii | [ID_CARD] |
| 银行卡号 | pii | [BANK_CARD] |
| 手机号 (中国) | pii | [PHONE_NUMBER] |
| 邮箱地址 | pii | [EMAIL_ADDRESS] |
| 密码/凭证关键词 | api_key | [CREDENTIAL] |
| IP 地址 (IPv4) | pii | [IP_ADDRESS] |
| URL 敏感参数 | api_key | [REDACTED_PARAM]=[FILTERED] |
