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

镜像构建只区分两种通用架构，tag 固定为 `<platform>_<YYYYMMDD>`：

| 构建参数 | 构建机 | 镜像 tag | 同步写入的飞书 sheet |
| --- | --- | --- | --- |
| `--platform amd` | `tc232` | `amd_20260729` | `AMD_with_cuda`、`AMD_with_mxn100` |
| `--platform arm` | `tc81` | `arm_20260729` | `ARM_with_cuda`、`ARM_without_cuda`、`l4t`、`thor_spark`、`SOPHON_bm1688` |

```bash
cd apps/desensitize

# AMD64：构建一次 backend + frontend，推送后写入全部 AMD sheet
./docker/build_image.sh --platform amd

# ARM64：构建一次 backend + frontend，推送后写入全部 ARM sheet
./docker/build_image.sh --platform arm
```

不要使用 `--sheet` 或自定义功能后缀 tag。当前各 ARM / AMD profile 共用通用镜像；
未来某个 profile 需要 CUDA、PyTorch 或设备专用运行时，再在构建脚本中为该 profile
增加专用构建映射。**打包脚本不会跨 sheet 查找镜像**：`l4t` 始终从 `l4t` sheet 读，
`arm` 始终从 `ARM_with_cuda` sheet 读，等专用镜像出现后无需修改打包逻辑。

只重建单个组件时：

```bash
./docker/build_image.sh --platform arm --component frontend
./docker/build_image.sh --platform amd --component backend
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

完整发布顺序：先在 tc232/tc81 构建并确认两个平台镜像已写入全部对应 sheet；再提交
代码，运行 `update_version.sh patch`。CI 只负责从每个 profile 自己的 sheet 读取 tag、
生成 pull 模式 VOS 包和发布应用商店，不重新构建镜像。

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
