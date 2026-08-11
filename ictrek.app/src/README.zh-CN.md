# 数据脱敏服务 用户使用说明

数据脱敏服务（Desensitize Service）提供基于正则规则的敏感信息识别与脱敏 HTTP API，供 WeKnora、agent-room 等应用在调用云模型前统一脱敏，防止个人隐私和密钥泄露到云端。

> ⚠️ **前置依赖：Model Hub**
>
> 本应用的 NER（语义脱敏）和图片 OCR 功能依赖 Model Hub 服务，请在安装本应用前确保 Model Hub 已安装且正常运行。
>
> NER 模型 `huluxiaohuowa/bert4ner-base-chinese-onnx` 与图片 OCR 模型 `huluxiaohuowa/rapidocr-ppocrv4-onnx` 不随本应用提供。首次使用时本服务会自动调用 Model Hub 触发模型下载，也可在 Web 的“模型管理”页面手动下载、检查版本和更新。下载过程中纯正则脱敏 API 不受影响，`ner=true` 请求会暂时返回"模型下载中，请稍后"，图片接口会暂时返回"图片 OCR 模型下载中，请稍后"。

## 安装时需要选择的内容

上传安装包后，安装界面会展示安装位置、计算平台 profile 和运行参数。

### 计算平台 profile

| 安装界面显示 | VOS profile id | 适用场景 |
| --- | --- | --- |
| AMD64 | `amd` | tc232 等 AMD64 主机 |
| ARM64 | `arm` | tc81 等 ARM64 主机 |

### 主要运行参数

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `DESENSITIZE_DATA_PATH` | `/data/vos_workspace/desensitize` | 持久化数据目录（存储自定义规则） |
| `MODEL_HUB_SHARED_MODELS_PATH` | `/data/vos_workspace/model_hub` | Model Hub 共享模型根目录；后端会将总目录只读挂载为 `/modelhub` |
| `DESENSITIZE_NER_ENABLED` | `true` | 是否允许请求通过 `ner=true` 启用语义脱敏 |
| `DESENSITIZE_IMAGE_OCR_ENABLED` | `true` | 是否启用图片 OCR 脱敏接口 |
| `DESENSITIZE_IMAGE_OCR_MAX_CONCURRENCY` | `1` | 同时执行的图片 OCR 数量；tc192/L4T 建议保持默认 |
| `DESENSITIZE_IMAGE_OCR_QUEUE_TIMEOUT_SECONDS` | `20` | 图片 OCR 并发满时的最长排队等待时间 |

## 访问入口

安装完成后，在 VOS 左侧导航进入：

```text
数据脱敏 -> 脱敏管理
```

VOS 内部 iframe 页面入口为：

```text
/app/com.ictrek.desensitize/
```

## 功能说明

### 规则管理

- **内置规则**：预置 13 条常用脱敏规则，覆盖手机号、身份证号、邮箱、银行卡号、API Key（OpenAI / 阿里云 / GitHub / AWS / JWT）、Bearer Token、密码/凭证关键词、IP 地址、URL 敏感参数等。
- **自定义规则**：支持通过界面或 API 添加自定义正则规则，规则持久化存储。
- **规则测试**：在添加规则前可测试正则表达式是否匹配预期文本。

### 脱敏测试

在"脱敏测试"页面可以输入文本，实时查看脱敏效果、命中规则和耗时。启用 NER 复选框后，服务还会识别人名和地址。

### 模型依赖（Model Hub）

NER 权重不包含在本应用镜像中。启动后服务会通过 VOS 网络 alias
`model-hub-backend:5005` 查询 Model Hub；模型不存在或下载失败时会自动触发 ModelScope
模型 `huluxiaohuowa/bert4ner-base-chinese-onnx` 的下载。本服务从只读挂载的
`/modelhub/export/ms/huluxiaohuowa/bert4ner-base-chinese-onnx/current` 加载它。
该过程不阻塞服务启动：原有正则 API 始终可用；模型下载中时只有 `ner=true` 请求返回 503
及“模型下载中，请稍后”。

图片 OCR 模型也由 Model Hub 管理，模型 ID 为
`huluxiaohuowa/rapidocr-ppocrv4-onnx`。服务从只读挂载的
`/modelhub/export/ms/huluxiaohuowa/rapidocr-ppocrv4-onnx/current` 加载 RapidOCR
所需的 det/rec/cls 三个 ONNX 文件。OCR 模型下载期间不影响文本规则和文本 NER；只有图片接口返回 503 及“图片 OCR 模型下载中，请稍后”。

NER 最大并发数和队列等待时间可在安装界面分别通过
`DESENSITIZE_NER_MAX_CONCURRENCY`（默认 4）与
`DESENSITIZE_NER_QUEUE_TIMEOUT_SECONDS`（默认 30 秒）调整。达到并发上限时请求排队等待，只有超时才返回繁忙提示。

Web 的“模型管理”页面会分别显示 NER 与 OCR 模型的 Model Hub 状态、任务进度、当前版本和加载路径，并提供“下载模型”“检查版本”“更新模型”按钮。

### 图片脱敏

图片脱敏接口会先使用 Model Hub 提供的 RapidOCR 模型识别文本框，再按行重建连续文本并执行规则匹配。规则会同时在原重建文本和去空白的紧凑文本上匹配，因此一段手机号、身份证号或密钥被 OCR 拆成多个文本框时仍可命中并遮挡对应区域。对于 RapidOCR 未返回文本框但图像上存在的长文本行，服务会执行保守补偿遮挡，避免长 API Key、Token 等英文/符号混合串因 OCR 漏检而原样返回。传入 `ner=true` 时会复用文本 NER 模型补充识别人名和地址。

### 接入指南

"接入指南"页面提供了其他应用接入的完整示例代码和配置说明。

右上角"关于"按钮会显示当前 VOS App 版本、安装 profile、前后端镜像版本，以及 NER 运行状态和实际 ONNX Runtime provider。

## VOS 网络内连接方式

| 目标 | 地址 |
| --- | --- |
| 同一 VOS 实例的应用 | `http://desensitize-backend:5000`（调用方必须加入外部 `vos_default` 网络） |
| VOS 内部网关 | `http://${VOS_HOST_GW_IP}:${VOS_API_GW_PORT_INTERNAL}/api/com.ictrek.desensitize` |

两种地址都是 API 基地址；请求单文本脱敏时追加
`/api/v1/desensitize/text`。网关路径会由 Traefik 移除
`/api/com.ictrek.desensitize` 前缀后再转发。

## API 接口

| 接口 | 方法 | 说明 |
| --- | --- | --- |
| `/api/v1/rules` | GET | 列出所有规则 |
| `/api/v1/rules/builtin` | GET | 列出内置规则 |
| `/api/v1/rules/custom` | GET | 列出自定义规则 |
| `/api/v1/rules/{id}` | GET | 查看单个规则 |
| `/api/v1/rules` | POST | 创建自定义规则 |
| `/api/v1/rules/{id}` | PUT | 更新自定义规则 |
| `/api/v1/rules/{id}` | DELETE | 删除自定义规则 |
| `/api/v1/rules/test` | POST | 测试正则表达式 |
| `/api/v1/desensitize` | POST | 批量脱敏消息列表 |
| `/api/v1/desensitize/text` | POST | 单文本脱敏 |
| `/api/v1/desensitize/image` | POST | 图片 OCR 脱敏 |
| `/health` | GET | 健康检查 |

单文本 NER 调用（不传 `ner` 或传 `false` 时保持完全兼容的纯规则模式）：

```json
POST /api/v1/desensitize/text
{"text":"张三住在北京市海淀区，手机号13812345678","ner":true}
```

批量接口在 `options` 中传入 `"ner": true`。规则优先执行，NER 仅处理规则未替换的文本。

图片脱敏调用：

```json
POST /api/v1/desensitize/image
{
  "image_base64": "<base64 或 data:image/...;base64,...>",
  "mime_type": "image/jpeg",
  "ner": false,
  "return_coordinates": true,
  "max_side": 1600
}
```

返回 `image_base64` 为已打码图片；`replaced` 为命中统计；`coordinates` 为可选遮挡坐标。

## 降级策略

调用云模型时建议默认阻断并告警；只有经明确风险评估的本地或可信处理链路，才可使用原始文本降级。

```python
try:
    resp = requests.post(f"{desensitize_url}/api/v1/desensitize/text", json={"text": text})
    text = resp.json()["text"]
except Exception:
    logger.warning("desensitize service unavailable, using raw text")
```

## 局限性

规则与可选本地 NER 能覆盖常见 PII 和密钥泄露场景，但仍存在以下局限：

- 无法识别中文数字变体（如"一三八一二三四五六七八"）
- 图片脱敏依赖 OCR 识别质量，低清晰度、强倾斜或复杂背景图片可能漏检
- NER 当前仅处理人名和地址，且受文本上下文和模型置信度影响
