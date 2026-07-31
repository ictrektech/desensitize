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
│       ├── engine.py       # 脱敏引擎（正则 + 可选 NER）
│       ├── ner_engine.py   # 复用单个 ONNX Runtime NER 会话
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
│   ├── Dockerfile.cpu / Dockerfile.* # 各 profile 后端镜像
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
├── docs/
│   └── desensitize-service-comparison.md # 架构与接入方案
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

每次构建只对应一个 VOS profile，并只写入该 profile 的 Feishu sheet；打包也从同一张表取镜像。CPU tag 为 `<platform>_<YYYYMMDD>`，CUDA tag 带 CUDA 版本后缀：

| 构建机 | 参数 | 写入 sheet | tag 示例 |
| --- | --- | --- | --- |
| tc232 | `--sheet AMD_with_cuda` | `AMD_with_cuda` | `amd_cu128_20260731` |
| tc232 | `--sheet AMD_with_mxn100` | `AMD_with_mxn100` | `amd_20260731` |
| tc192 | `--sheet ARM_without_cuda` | `ARM_without_cuda` | `arm_20260731` |
| tc192 | `--sheet l4t` | `l4t` | `l4t_cu128_20260731` |
| tc81 | `--sheet ARM_with_cuda` | `ARM_with_cuda` | `arm_cu128_20260731` |
| tc81 | `--sheet thor_spark` | `thor_spark` | `thor_cu128_20260731` |

```bash
cd apps/desensitize

# 例：AMD CUDA；每个 profile 分别执行一次
./docker/build_image.sh --sheet AMD_with_cuda
```

不要跨 profile 写表，也不要使用任意功能后缀。**打包脚本不会跨 sheet 查找镜像**：
每个 profile 都只读取自己的表和该列第 2 行记录的镜像仓库。

只重建单个组件时：

```bash
./docker/build_image.sh --sheet ARM_with_cuda --component frontend
./docker/build_image.sh --sheet AMD_with_cuda --component backend
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

架构选型、调用方接入和后续语义脱敏演进见
[docs/desensitize-service-comparison.md](docs/desensitize-service-comparison.md)。

完整发布顺序：先在对应构建机逐个 profile 构建并确认镜像已写入其对应 sheet；再提交
代码，运行 `update_version.sh patch`。CI 只负责从每个 profile 自己的 sheet 读取 tag、
生成 pull 模式 VOS 包和发布应用商店，不重新构建镜像。

## 可选 NER（Model Hub）

NER 是显式开关，历史 API 不传 `ner` 时仍是纯正则。先在 Model Hub 安装
`huluxiaohuowa/bert4ner-base-chinese-onnx`，安装本应用时设置
`MODEL_HUB_SHARED_MODELS_PATH`（默认 `/data/vos_workspace/model_hub`）。容器只读挂载整个
目录到 `/modelhub`，从标准 ModelScope 导出路径加载模型。文本接口传 `{"ner": true}`，
批量接口在 `options` 中传 `{"ner": true}`；模型未就绪只影响 NER 请求，纯规则请求仍可用。

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
