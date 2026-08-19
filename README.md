# 数据脱敏服务 (Desensitize Service)

基于正则规则的敏感信息识别与脱敏 HTTP API 服务。

## 前置依赖

> ⚠️ **本服务的 NER 与图片 OCR 功能依赖 Model Hub**
>
> NER 模型（`huluxiaohuowa/bert4ner-base-chinese-onnx`）和图片 OCR 模型
>（`huluxiaohuowa/rapidocr-ppocrv4-onnx`）不随本应用镜像提供，需要通过 Model Hub 下载。
> 首次使用时，本服务会自动调用 Model Hub API 触发模型下载，也可在 Web 的“模型管理”页面手动触发下载、检查版本和更新。模型下载过程中：
> - 纯正则脱敏 API 始终可用，不受影响
> - `ner=true` 请求会返回 503 及"模型下载中，请稍后"提示
> - 图片接口会返回 503 及"图片 OCR 模型下载中，请稍后"提示
>
> 请确保 Model Hub 已安装且正常运行，且 `MODEL_HUB_SHARED_MODELS_PATH` 配置正确。

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

后端每次构建只对应一个 VOS profile，并只写入该 profile 的 Feishu sheet；前端不含 NER/ORT，始终只构建 AMD、ARM 两种镜像，并将同一个架构 tag 一对多写入对应 profile 表。打包从每个 profile 自己的表取镜像。CPU 后端 tag 为 `<platform>_<YYYYMMDD>`，AMD/ARM/Thor CUDA 后端 tag 带 CUDA 版本后缀；L4T 按 Jetson profile 命名为 `l4t_<YYYYMMDD>`：

| 构建机 | 参数 | 写入 sheet | tag 示例 |
| --- | --- | --- | --- |
| tc232 | `--sheet AMD_with_cuda` | `AMD_with_cuda`（后端） | `amd_cu128_20260731` |
| tc232 | `--sheet AMD_with_mxn100` | `AMD_with_mxn100` | `amd_20260731` |
| tc192 | `--sheet ARM_without_cuda` | `ARM_without_cuda` | `arm_20260731` |
| tc192 | `--sheet l4t` | `l4t` | `l4t_20260731` |
| tc81 | `--sheet ARM_with_cuda` | `ARM_with_cuda` | `arm_cu128_20260731` |
| tc81 | `--sheet thor_spark` | `thor_spark`（后端） | `thor_cu128_20260731` |
| tc232 | `--frontend-platform amd` | `AMD_with_cuda`、`AMD_with_mxn100`（前端） | `amd_20260731` |
| tc192 | `--frontend-platform arm` | `ARM_with_cuda`、`ARM_without_cuda`、`l4t`、`thor_spark`（前端） | `arm_20260731` |

```bash
cd apps/desensitize

# 六个 profile 后端分别执行
./docker/build_image.sh --sheet AMD_with_cuda
./docker/build_image.sh --sheet AMD_with_mxn100
./docker/build_image.sh --sheet ARM_with_cuda
./docker/build_image.sh --sheet ARM_without_cuda
./docker/build_image.sh --sheet l4t
./docker/build_image.sh --sheet thor_spark

# 前端只构建两次，再按架构一对多写入 Feishu
./docker/build_image.sh --frontend-platform amd
./docker/build_image.sh --frontend-platform arm
```

不要跨 profile 写表，也不要使用任意功能后缀。**打包脚本不会跨 sheet 查找镜像**：
每个 profile 都只读取自己的表和该列第 2 行记录的镜像仓库。

只重建单个组件时：

```bash
./docker/build_image.sh --sheet AMD_with_cuda --component backend
./docker/build_image.sh --frontend-platform arm
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

## 模型依赖（Model Hub）

NER 是显式开关，历史 API 不传 `ner` 时仍是纯正则。启动后服务通过 VOS alias
`model-hub-backend:5005` 查询 Model Hub，模型不存在时自动请求下载
`huluxiaohuowa/bert4ner-base-chinese-onnx`。安装本应用时设置
`MODEL_HUB_SHARED_MODELS_PATH`（默认 `/data/vos_workspace/model_hub`）。容器只读挂载整个
目录到 `/modelhub`，从标准 ModelScope 导出路径加载模型。文本接口传 `{"ner": true}`，
批量接口在 `options` 中传 `{"ner": true}`；模型下载过程不阻塞启动，未就绪时仅 NER 请求返回“模型下载中，请稍后”，纯规则请求仍可用。
NER 默认最多并发执行 4 个推理；超过时在安装参数 `DESENSITIZE_NER_QUEUE_TIMEOUT_SECONDS` 指定的时间内排队等待（默认 30 秒），超时才返回繁忙提示。

图片 OCR 模型也由 Model Hub 管理，模型 ID 为
`huluxiaohuowa/rapidocr-ppocrv4-onnx`，服务从
`/modelhub/export/ms/huluxiaohuowa/rapidocr-ppocrv4-onnx/current`
读取 RapidOCR 所需的 det/rec/cls 三个 ONNX 文件。OCR 模型未就绪时服务仍可启动，文本规则和
文本 NER 不受影响；只有图片脱敏接口会返回“图片 OCR 模型下载中，请稍后”。

Web 的“模型管理”页面提供 NER 与 OCR 两张模型卡片，可查看 Model Hub 状态、下载进度、当前版本、加载路径，并手动执行下载、版本检查和更新。

## 图片脱敏

图片接口为新增能力，不影响原有文本接口：

```bash
POST /api/v1/desensitize/image
Content-Type: application/json
```

请求体：

```json
{
  "image_base64": "<base64 或 data:image/...;base64,...>",
  "mime_type": "image/jpeg",
  "ner": false,
  "adaptive": false,
  "reversible": false,
  "return_coordinates": true,
  "max_side": 1600
}
```

该接口只接收 JSON base64 图片，不接收 `multipart/form-data` 文件上传；误用文件表单会返回
`415 Unsupported Media Type`。

返回值中的 `image_base64` 是已打码图片；`replaced` 给出命中规则统计；开启
`return_coordinates` 时会返回实际遮挡区域坐标（`quad` 为多边形顶点，倾斜文本时
顶点数可能大于 4）。图片脱敏流程先用 RapidOCR 识别文本块，再按行重建连续文本并
保留文本到图片框的映射；规则同时在原重建文本和去空白的紧凑文本上匹配，因此
手机号、身份证号、密钥等被 OCR 拆成多个文本框时仍可命中。`ner=true` 时会复用文本
NER 模型补充人名、地址遮挡。对于 RapidOCR 未返回文本框但图像上存在的长文本行，服务会
执行保守补偿遮挡，避免长 API Key、Token 等英文/符号混合串因 OCR 漏检而原样返回。
针对身份证、发票、物流面单等中文图片，服务还会识别“公民身份号码、手机号、地址、邮箱、
纳税人识别号、发票号码、订单号、运单号”等字段标签，并遮挡同一行或右侧相邻的字段值，
用于兜底 OCR 将数字拆断、漏识别或未形成完整正则匹配的情况。

### 多空间匹配与校验位门控

OCR 常把数字认成形近字母（`0→O`、`1→l/I`、`5→S`、`8→B` 等），导致手机号、身份证号
在原文和紧凑文本两个匹配空间都漏配。服务在紧凑文本之上构造可配置的等长派生空间：
默认正向混淆空间把形近字母映射回数字，仅对带校验器的规则（身份证 GB11643 校验位、
银行卡 Luhn、手机号号段、IBAN mod97、VIN ISO3779）启用；默认逆向混淆空间把数字
映射回字母，用于修复 `sk-l1ve` 这类密钥前缀 OCR 误读。自定义等长映射可通过
`DESENSITIZE_IMAGE_CONFUSION_MAPS_JSON` 配置。多空间命中按“原文 > 紧凑 > 派生空间”
的置信顺序去重，响应 `metadata.matched_via`、`metadata.suppressed_by_space` 与
`metadata.validator_rejected` 给出接受、抑制和校验失败审计。

校验失败候选会进入漏斗式审计：默认只计入 `validator_rejected`，不改变原输出；如部署要求
宁可过遮，可设置 `DESENSITIZE_IMAGE_GATE_FAILURE_POLICY=conservative`，将校验失败但可
回映射到 OCR 框的嫌疑区间按 `[SUSPECT_VALUE]` 遮挡。

### 四边形精确遮挡

遮挡区域不再使用轴对齐外接矩形，而是对各 OCR 文本框的实际四边形顶点沿远离质心方向
外扩后取凸包，倾斜文本（物流面单、拍照表单）得到贴合的多边形遮挡，显著减少对相邻
内容的过度遮挡；水平文本自动退化为矩形。

### 文档类型自适应（`adaptive: true`）

开启后服务基于 OCR 文本信号（字段标签、关键词）做轻量文档类型判定
（`id_document` / `invoice` / `shipping_label` / `config_screenshot` / `generic`，
不引入额外模型），按类型级联选择规则类别子集与兜底策略。例如配置截图只保留
api_key/pii 类规则并关闭字段标签兜底，降低长字母数字串的类别泛化误遮；信号不足或
并列时回退到全量规则的 `generic` 策略，保证不漏遮。响应 `metadata.scene` 返回判定
结果与所用策略。

### 分辨率自适应二次 OCR 兜底

当图片长边缩放或存在低置信 OCR 块时，服务可对少量疑似漏检区域做局部复核：检测被整行
兜底宽度规则剔除的窄文本带、以及低置信文本框邻域，从原图裁剪并放大后重新 OCR，坐标
逆变换后并回主流程，再统一执行行重建、多空间匹配和遮挡。默认 `auto` 模式仅在缩放场景
触发，最多复核 4 个区域，避免弱设备上开销失控。

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `DESENSITIZE_IMAGE_SECONDARY_OCR_ENABLED` | `auto` | `auto`/`true`/`false`，是否启用局部二次 OCR |
| `DESENSITIZE_IMAGE_SECONDARY_OCR_MAX_REGIONS` | `4` | 单张图片最多复核区域数 |
| `DESENSITIZE_IMAGE_SECONDARY_OCR_TARGET_SHORT` | `640` | 复核裁剪图短边目标像素 |

### 可逆脱敏与还原

请求带 `"reversible": true` 时，服务在遮挡前把每个遮挡区域的原始像素块裁剪、
PNG 序列化并用 AES-256-GCM 加密（每区域独立随机 nonce），随响应返回加密账本
`ledger`。密钥通过 `ledger_key`（64 位 hex，32 字节）传入，或设置环境变量
`DESENSITIZE_LEDGER_KEY`；两者都缺失时返回 400。持密钥方可调用还原接口逐区域
解密贴回：

```bash
POST /api/v1/desensitize/image/restore
```

```json
{
  "image_base64": "<已脱敏图片 base64>",
  "ledger": "<脱敏响应返回的 ledger 对象>",
  "ledger_key": "<64 位 hex 密钥>",
  "mime_type": "image/png"
}
```

单个区域解密失败只记录在 `report` 中，不中断其余区域还原。还原接口默认输出
`image/png`，避免 JPEG 重新压缩破坏已贴回像素。

图片 OCR 默认参数面向 tc192/L4T 这类弱性能设备保守设置：

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `DESENSITIZE_IMAGE_OCR_ENABLED` | `true` | 是否启用图片 OCR 脱敏接口 |
| `DESENSITIZE_IMAGE_OCR_MAX_CONCURRENCY` | `1` | 同时执行的 OCR 数量 |
| `DESENSITIZE_IMAGE_OCR_QUEUE_TIMEOUT_SECONDS` | `20` | OCR 并发满时的排队等待时间 |

## 运行信息

Web 界面右上角“关于”按钮会显示当前 VOS App 版本、安装 profile、前后端镜像，以及 NER
运行状态和实际 ONNX Runtime provider。后端只读接口为：

```bash
GET /api/v1/system/about
```

## 内置规则

规则管理页面支持对每条规则单独启用/停用。内置规则不可修改、不可删除，但启停状态会保存到持久化数据目录；自定义规则的内容和启停状态继续保存在同一数据目录。只要安装时的 `DESENSITIZE_DATA_PATH` 挂载不变，重启或下次登录后仍会保持上次状态。

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
| 纳税人识别号/统一社会信用代码 | document | [TAXPAYER_ID] |
| 发票代码/号码 | document | [INVOICE_NUMBER] |
| 订单号/运单号 | document | [ORDER_NUMBER] |
