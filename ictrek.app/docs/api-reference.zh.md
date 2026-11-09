# Desensitize API 详细参考

## 地址、身份与文档入口

应用内选择“接入指南 → 完整 API 字段参考”，可打开 `/api/com.ictrek.desensitize/docs` 交互文档和 `/api/com.ictrek.desensitize/openapi.json`，查看全部 21 个操作的请求/返回字段。OpenAPI 使用相对地址，兼容 VOS 代理。Docker 内直连 `http://desensitize-backend:5000`，后接下列接口路径。不承诺独立宿主机映射端口，外部访问使用实际安装的 VOS 网关及访问策略。

原生脱敏和规则管理后端当前没有按用户鉴权，规则为全局共享。直连地址只应放在可信 VOS 网络内；V-Scheduler 模型 API Key 不用于这些原生管理接口。调度绑定仅接受已核验的 V-Scheduler 应用身份，由系统自动下发，不应由用户手工编造。其他应用推荐使用正式地址 `v-scheduler`；本应用内部绑定快照目前严格校验兼容地址 `http://v-router:8080/scheduler/api/v1`。

## 调用流程与限制

纯文本调用 `POST /api/v1/desensitize/text`，JSON 示例：`{"text":"手机号13812345678","ner":false}`。批量消息使用 `/api/v1/desensitize` 的 `messages` 和 `options`，默认跳过 assistant 消息。`rules` 省略或为空数组时使用默认已启用规则，并不表示禁用全部规则。先通过 `/api/v1/rules` 获取真实规则 ID。内置规则只能修改 `enabled`，其他修改/删除返回 403；自定义规则创建返回 201，修改 200，删除 204 且无正文。正则测试使用 URL 查询参数而非 JSON：`POST /api/v1/rules/test?pattern=%5B0-9%5D%2B&text=abc123`，返回命中位置和替换后的 `result`。

文本和图片中的 `level` 当前均为保留字段，修改它不会切换更严格的规则；批量 `audit` 参数不会开启持久审计日志。应显式选择规则及其启用状态。`metadata.rule_count` 是替换汇总条目数，并非已启用规则总数。

NER/OCR 权重不随镜像发布。通过 `/api/v1/models/managed` 查询，对 `key=ner|ocr` 调用 `/managed/{key}/download` 后轮询状态及 Scheduler 原始权重任务。下载请求成功不表示就绪，运行时就绪也不代替调度绑定和资源许可。纯正则不需要模型权重；请求 `ner=true` 而 NER 不可用时返回 503，不会静默降级为纯正则。

图片仅接受 application/json，以 base64 传入图片，不支持 multipart。错误 Content-Type 返回 415；图片或账本密钥错误返回 400；OCR/NER、调度许可或依赖不可用返回 503。`max_side` 默认 1600，范围 256–4096；OCR 缩放坐标会映射回输出图片。未请求时 `coordinates`、`ledger` 可为空或 null。可逆脱敏需要 `ledger_key` 或管理员的 `DESENSITIZE_LEDGER_KEY` 提供 64 位十六进制 AES-256 密钥；密钥应与脱敏图片、账本分开保密保存。还原使用原密钥和账本，并逐项检查 `report[].restored`：即使 HTTP 成功也可能部分解密失败，`restored_count` 可能只是部分成功。脱敏使用启发式识别，分享敏感材料前仍应检查结果。

## 错误与重试

错误结合 HTTP 状态和 `detail` 判断，后者可能是字符串或校验错误数组，网关异常也可能不是 JSON。404 表示规则/模型 key 不存在；409 表示内部绑定冲突或忙碌；422 表示结构、正则或绑定不合法；503 可能来自权重、绑定、资源许可或依赖。恢复对应依赖后再重试。下载、更新及全局规则修改不因自带请求 ID 自动幂等；超时后先查询状态，再决定是否重发。同步脱敏不提供任务队列或取消接口。


## 完整接口与返回

### GET /api/v1/scheduler/binding

身份：公开接口 / 按文中调用边界

See the field contracts and the integration workflow for this native application operation.

响应 200 — Native application JSON response.

`application/json`

`object`

| 字段 | 类型 | 要求 | 说明 |
| --- | --- | --- | --- |
| `protocol_version` | integer | 必填 |  · const=1 |
| `configured` | boolean | 必填 |  |
| `binding_revision` | integer | 可选 |  |
| `approved_model_count` | integer | 可选 |  |

响应 default — Check HTTP status and Content-Type. FastAPI detail is a string or validation error list; unexpected gateway/server errors can be plain text.

`application/json`

`object`

| 字段 | 类型 | 要求 | 说明 |
| --- | --- | --- | --- |
| `detail` | JSON | 必填 | Message or validation details. |

`text/plain`

`string`

### POST /api/v1/scheduler/binding

身份：SchedulerApplication

Internal automatic provisioning. Requires verified application identity, matching runtime settings, approved executors and a monotonic binding revision. Active work or conflicting revision returns 409; invalid binding returns 422. Do not edit this snapshot manually.

请求体：application/json

`object`

| 字段 | 类型 | 要求 | 说明 |
| --- | --- | --- | --- |
| `protocol_version` | integer | 必填 |  · const=1 |
| `binding_revision` | integer | 必填 |  · minimum=1 |
| `app_id` | string | 必填 |  · const="com.ictrek.desensitize" |
| `url` | string | 必填 |  · const="http://v-router:8080/scheduler/api/v1" |
| `upstream_url` | string | 必填 |  · const="http://desensitize-backend:5000/v1" |
| `token` | string | 必填 |  · minLength=32 · maxLength=4096 |
| `executor_token` | string | 必填 |  · minLength=32 · maxLength=4096 |
| `models` | object | 必填 |  |
| `gateway_executors` | object | 可选 |  |
| `execution_settings` | object | 必填 |  |
| `execution_settings.ner_provider_requested` | string | 必填 |  |
| `execution_settings.ocr_provider_requested` | string | 必填 |  |
| `execution_settings.onnx_available_providers` | array<string> | 必填 |  |
| `execution_settings.onnxruntime_version` | string  /  null | 必填 |  |
| `execution_settings.rapidocr_version` | string  /  null | 必填 |  |
| `execution_settings.logical_cpu_count` | integer  /  null | 必填 |  |
| `execution_settings.ner_intra_op_threads` | integer | 必填 |  |
| `execution_settings.ner_inter_op_threads` | integer | 必填 |  |
| `execution_settings.ocr_thread_policy` | string | 必填 |  |
| `execution_settings.ocr_intra_op_threads` | integer | 必填 |  |
| `execution_settings.ocr_inter_op_threads` | integer | 必填 |  |
| `execution_settings.opencv_threads` | integer | 必填 |  |
| `execution_settings.math_thread_environment` | object | 必填 |  |
| `execution_settings.max_concurrent_inference` | integer | 必填 |  |
| `execution_settings.ner_max_tokens` | integer | 必填 |  |
| `model_limits` | object | 必填 | Provisioned per-model limits from the controller; not a caller-chosen budget. |

响应 200 — Native application JSON response.

`application/json`

`object`

| 字段 | 类型 | 要求 | 说明 |
| --- | --- | --- | --- |
| `configured` | boolean | 必填 |  |
| `binding_revision` | integer | 必填 |  |

响应 default — Check HTTP status and Content-Type. FastAPI detail is a string or validation error list; unexpected gateway/server errors can be plain text.

`application/json`

`object`

| 字段 | 类型 | 要求 | 说明 |
| --- | --- | --- | --- |
| `detail` | JSON | 必填 | Message or validation details. |

`text/plain`

`string`

### GET /api/v1/rules

身份：公开接口 / 按文中调用边界

See the field contracts and the integration workflow for this native application operation.

- `query: enabled_only` · boolean · 可选 · 

响应 200 — Successful Response

`application/json`

`array<RuleOut>`

响应 422 — Validation Error

`application/json`

`HTTPValidationError`

响应 default — Check HTTP status and Content-Type. FastAPI detail is a string or validation error list; unexpected gateway/server errors can be plain text.

`application/json`

`object`

| 字段 | 类型 | 要求 | 说明 |
| --- | --- | --- | --- |
| `detail` | JSON | 必填 | Message or validation details. |

`text/plain`

`string`

### POST /api/v1/rules

身份：公开接口 / 按文中调用边界

See the field contracts and the integration workflow for this native application operation.

请求体：application/json

`RuleCreate`

响应 201 — Successful Response

`application/json`

`RuleOut`

响应 422 — Validation Error

`application/json`

`HTTPValidationError`

响应 default — Check HTTP status and Content-Type. FastAPI detail is a string or validation error list; unexpected gateway/server errors can be plain text.

`application/json`

`object`

| 字段 | 类型 | 要求 | 说明 |
| --- | --- | --- | --- |
| `detail` | JSON | 必填 | Message or validation details. |

`text/plain`

`string`

### GET /api/v1/rules/builtin

身份：公开接口 / 按文中调用边界

See the field contracts and the integration workflow for this native application operation.

响应 200 — Successful Response

`application/json`

`array<RuleOut>`

响应 default — Check HTTP status and Content-Type. FastAPI detail is a string or validation error list; unexpected gateway/server errors can be plain text.

`application/json`

`object`

| 字段 | 类型 | 要求 | 说明 |
| --- | --- | --- | --- |
| `detail` | JSON | 必填 | Message or validation details. |

`text/plain`

`string`

### GET /api/v1/rules/custom

身份：公开接口 / 按文中调用边界

See the field contracts and the integration workflow for this native application operation.

响应 200 — Successful Response

`application/json`

`array<RuleOut>`

响应 default — Check HTTP status and Content-Type. FastAPI detail is a string or validation error list; unexpected gateway/server errors can be plain text.

`application/json`

`object`

| 字段 | 类型 | 要求 | 说明 |
| --- | --- | --- | --- |
| `detail` | JSON | 必填 | Message or validation details. |

`text/plain`

`string`

### GET /api/v1/rules/{rule_id}

身份：公开接口 / 按文中调用边界

See the field contracts and the integration workflow for this native application operation.

- `path: rule_id` · string · 必填 · 

响应 200 — Successful Response

`application/json`

`RuleOut`

响应 422 — Validation Error

`application/json`

`HTTPValidationError`

响应 default — Check HTTP status and Content-Type. FastAPI detail is a string or validation error list; unexpected gateway/server errors can be plain text.

`application/json`

`object`

| 字段 | 类型 | 要求 | 说明 |
| --- | --- | --- | --- |
| `detail` | JSON | 必填 | Message or validation details. |

`text/plain`

`string`

### PUT /api/v1/rules/{rule_id}

身份：公开接口 / 按文中调用边界

See the field contracts and the integration workflow for this native application operation.

- `path: rule_id` · string · 必填 · 

请求体：application/json

`RuleUpdate`

响应 200 — Successful Response

`application/json`

`RuleOut`

响应 422 — Validation Error

`application/json`

`HTTPValidationError`

响应 default — Check HTTP status and Content-Type. FastAPI detail is a string or validation error list; unexpected gateway/server errors can be plain text.

`application/json`

`object`

| 字段 | 类型 | 要求 | 说明 |
| --- | --- | --- | --- |
| `detail` | JSON | 必填 | Message or validation details. |

`text/plain`

`string`

### DELETE /api/v1/rules/{rule_id}

身份：公开接口 / 按文中调用边界

See the field contracts and the integration workflow for this native application operation.

- `path: rule_id` · string · 必填 · 

响应 204 — Successful Response

响应 422 — Validation Error

`application/json`

`HTTPValidationError`

响应 default — Check HTTP status and Content-Type. FastAPI detail is a string or validation error list; unexpected gateway/server errors can be plain text.

`application/json`

`object`

| 字段 | 类型 | 要求 | 说明 |
| --- | --- | --- | --- |
| `detail` | JSON | 必填 | Message or validation details. |

`text/plain`

`string`

### POST /api/v1/rules/test

身份：公开接口 / 按文中调用边界

Query parameters, not a JSON body. Invalid regular expressions return 422.

- `query: pattern` · string · 必填 · 

- `query: text` · string · 必填 · 

- `query: placeholder` · string · 可选 · 

响应 200 — Native application JSON response.

`application/json`

`object`

| 字段 | 类型 | 要求 | 说明 |
| --- | --- | --- | --- |
| `matched` | boolean | 必填 |  |
| `matches` | array<object> | 必填 |  |
| `result` | string | 必填 |  |
| `match_count` | integer | 必填 |  |

响应 422 — Validation Error

`application/json`

`HTTPValidationError`

响应 default — Check HTTP status and Content-Type. FastAPI detail is a string or validation error list; unexpected gateway/server errors can be plain text.

`application/json`

`object`

| 字段 | 类型 | 要求 | 说明 |
| --- | --- | --- | --- |
| `detail` | JSON | 必填 | Message or validation details. |

`text/plain`

`string`

### POST /api/v1/desensitize

身份：公开接口 / 按文中调用边界

See the field contracts and the integration workflow for this native application operation.

请求体：application/json

`DesensitizeRequest`

响应 200 — Successful Response

`application/json`

`DesensitizeResponse`

响应 422 — Validation Error

`application/json`

`HTTPValidationError`

响应 default — Check HTTP status and Content-Type. FastAPI detail is a string or validation error list; unexpected gateway/server errors can be plain text.

`application/json`

`object`

| 字段 | 类型 | 要求 | 说明 |
| --- | --- | --- | --- |
| `detail` | JSON | 必填 | Message or validation details. |

`text/plain`

`string`

### POST /api/v1/desensitize/text

身份：公开接口 / 按文中调用边界

See the field contracts and the integration workflow for this native application operation.

请求体：application/json

`DesensitizeTextRequest`

响应 200 — Successful Response

`application/json`

`DesensitizeTextResponse`

响应 422 — Validation Error

`application/json`

`HTTPValidationError`

响应 default — Check HTTP status and Content-Type. FastAPI detail is a string or validation error list; unexpected gateway/server errors can be plain text.

`application/json`

`object`

| 字段 | 类型 | 要求 | 说明 |
| --- | --- | --- | --- |
| `detail` | JSON | 必填 | Message or validation details. |

`text/plain`

`string`

### POST /api/v1/desensitize/image

身份：公开接口 / 按文中调用边界

See the field contracts and the integration workflow for this native application operation.

请求体：application/json

`ImageDesensitizeRequest`

响应 200 — Successful Response

`application/json`

`ImageDesensitizeResponse`

响应 422 — Validation Error

`application/json`

`HTTPValidationError`

响应 default — Check HTTP status and Content-Type. FastAPI detail is a string or validation error list; unexpected gateway/server errors can be plain text.

`application/json`

`object`

| 字段 | 类型 | 要求 | 说明 |
| --- | --- | --- | --- |
| `detail` | JSON | 必填 | Message or validation details. |

`text/plain`

`string`

### POST /api/v1/desensitize/image/restore

身份：公开接口 / 按文中调用边界

See the field contracts and the integration workflow for this native application operation.

请求体：application/json

`ImageRestoreRequest`

响应 200 — Successful Response

`application/json`

`ImageRestoreResponse`

响应 422 — Validation Error

`application/json`

`HTTPValidationError`

响应 default — Check HTTP status and Content-Type. FastAPI detail is a string or validation error list; unexpected gateway/server errors can be plain text.

`application/json`

`object`

| 字段 | 类型 | 要求 | 说明 |
| --- | --- | --- | --- |
| `detail` | JSON | 必填 | Message or validation details. |

`text/plain`

`string`

### GET /api/v1/models/managed

身份：公开接口 / 按文中调用边界

See the field contracts and the integration workflow for this native application operation.

响应 200 — Native application JSON response.

`application/json`

`array<ManagedModel>`

响应 default — Check HTTP status and Content-Type. FastAPI detail is a string or validation error list; unexpected gateway/server errors can be plain text.

`application/json`

`object`

| 字段 | 类型 | 要求 | 说明 |
| --- | --- | --- | --- |
| `detail` | JSON | 必填 | Message or validation details. |

`text/plain`

`string`

### POST /api/v1/models/managed/{key}/download

身份：公开接口 / 按文中调用边界

See the field contracts and the integration workflow for this native application operation.

- `path: key` · string · 必填 · 

响应 200 — Native application JSON response.

`application/json`

`object`

| 字段 | 类型 | 要求 | 说明 |
| --- | --- | --- | --- |
| `model` | ManagedModel | 必填 |  |
| `result` | JSON | 必填 | Unmodified result of V-Scheduler weight pull/check-update/update. A duplicate download may return a message instead of a new task. |

响应 422 — Validation Error

`application/json`

`HTTPValidationError`

响应 default — Check HTTP status and Content-Type. FastAPI detail is a string or validation error list; unexpected gateway/server errors can be plain text.

`application/json`

`object`

| 字段 | 类型 | 要求 | 说明 |
| --- | --- | --- | --- |
| `detail` | JSON | 必填 | Message or validation details. |

`text/plain`

`string`

### POST /api/v1/models/managed/{key}/check-update

身份：公开接口 / 按文中调用边界

See the field contracts and the integration workflow for this native application operation.

- `path: key` · string · 必填 · 

响应 200 — Native application JSON response.

`application/json`

`object`

| 字段 | 类型 | 要求 | 说明 |
| --- | --- | --- | --- |
| `model` | ManagedModel | 必填 |  |
| `result` | JSON | 必填 | Unmodified result of V-Scheduler weight pull/check-update/update. A duplicate download may return a message instead of a new task. |

响应 422 — Validation Error

`application/json`

`HTTPValidationError`

响应 default — Check HTTP status and Content-Type. FastAPI detail is a string or validation error list; unexpected gateway/server errors can be plain text.

`application/json`

`object`

| 字段 | 类型 | 要求 | 说明 |
| --- | --- | --- | --- |
| `detail` | JSON | 必填 | Message or validation details. |

`text/plain`

`string`

### POST /api/v1/models/managed/{key}/update

身份：公开接口 / 按文中调用边界

See the field contracts and the integration workflow for this native application operation.

- `path: key` · string · 必填 · 

响应 200 — Native application JSON response.

`application/json`

`object`

| 字段 | 类型 | 要求 | 说明 |
| --- | --- | --- | --- |
| `model` | ManagedModel | 必填 |  |
| `result` | JSON | 必填 | Unmodified result of V-Scheduler weight pull/check-update/update. A duplicate download may return a message instead of a new task. |

响应 422 — Validation Error

`application/json`

`HTTPValidationError`

响应 default — Check HTTP status and Content-Type. FastAPI detail is a string or validation error list; unexpected gateway/server errors can be plain text.

`application/json`

`object`

| 字段 | 类型 | 要求 | 说明 |
| --- | --- | --- | --- |
| `detail` | JSON | 必填 | Message or validation details. |

`text/plain`

`string`

### GET /health

身份：公开接口 / 按文中调用边界

See the field contracts and the integration workflow for this native application operation.

响应 200 — Native application JSON response.

`application/json`

`object`

| 字段 | 类型 | 要求 | 说明 |
| --- | --- | --- | --- |
| `status` | string | 必填 |  |
| `service` | string | 必填 |  |

响应 default — Check HTTP status and Content-Type. FastAPI detail is a string or validation error list; unexpected gateway/server errors can be plain text.

`application/json`

`object`

| 字段 | 类型 | 要求 | 说明 |
| --- | --- | --- | --- |
| `detail` | JSON | 必填 | Message or validation details. |

`text/plain`

`string`

### GET /api/v1/discovery

身份：公开接口 / 按文中调用边界

See the field contracts and the integration workflow for this native application operation.

响应 200 — Native application JSON response.

`application/json`

`object`

| 字段 | 类型 | 要求 | 说明 |
| --- | --- | --- | --- |
| `service_id` | string | 必填 |  |
| `scheduler` | object | 必填 |  |
| `scheduler.protocol_version` | integer | 必填 |  |
| `scheduler.app_id` | string | 必填 |  |
| `scheduler.binding_endpoint` | string | 必填 |  |
| `scheduler.lifecycle_protocol_version` | integer | 必填 |  |
| `scheduler.executor_base_url` | string | 必填 |  |
| `scheduler.upstream_url` | string | 必填 |  |
| `scheduler.provider` | string | 必填 |  |
| `scheduler.ocr_provider` | string | 必填 |  |
| `scheduler.num_threads` | integer | 必填 |  |
| `scheduler.max_concurrent_inference` | integer | 必填 |  |
| `scheduler.max_tokens` | integer | 必填 |  |
| `scheduler.sync_models` | array<object> | 必填 |  |
| `scheduler.execution_settings` | object | 必填 |  |
| `scheduler.execution_settings.ner_provider_requested` | string | 必填 |  |
| `scheduler.execution_settings.ocr_provider_requested` | string | 必填 |  |
| `scheduler.execution_settings.onnx_available_providers` | array<string> | 必填 |  |
| `scheduler.execution_settings.onnxruntime_version` | string  /  null | 必填 |  |
| `scheduler.execution_settings.rapidocr_version` | string  /  null | 必填 |  |
| `scheduler.execution_settings.logical_cpu_count` | integer  /  null | 必填 |  |
| `scheduler.execution_settings.ner_intra_op_threads` | integer | 必填 |  |
| `scheduler.execution_settings.ner_inter_op_threads` | integer | 必填 |  |
| `scheduler.execution_settings.ocr_thread_policy` | string | 必填 |  |
| `scheduler.execution_settings.ocr_intra_op_threads` | integer | 必填 |  |
| `scheduler.execution_settings.ocr_inter_op_threads` | integer | 必填 |  |
| `scheduler.execution_settings.opencv_threads` | integer | 必填 |  |
| `scheduler.execution_settings.math_thread_environment` | object | 必填 |  |
| `scheduler.execution_settings.max_concurrent_inference` | integer | 必填 |  |
| `scheduler.execution_settings.ner_max_tokens` | integer | 必填 |  |
| `scheduler.binding` | object | 必填 |  |
| `scheduler.binding.protocol_version` | integer | 必填 |  · const=1 |
| `scheduler.binding.configured` | boolean | 必填 |  |
| `scheduler.binding.binding_revision` | integer | 可选 |  |
| `scheduler.binding.approved_model_count` | integer | 可选 |  |

响应 default — Check HTTP status and Content-Type. FastAPI detail is a string or validation error list; unexpected gateway/server errors can be plain text.

`application/json`

`object`

| 字段 | 类型 | 要求 | 说明 |
| --- | --- | --- | --- |
| `detail` | JSON | 必填 | Message or validation details. |

`text/plain`

`string`

### GET /api/v1/system/about

身份：公开接口 / 按文中调用边界

See the field contracts and the integration workflow for this native application operation.

响应 200 — Native application JSON response.

`application/json`

`object`

| 字段 | 类型 | 要求 | 说明 |
| --- | --- | --- | --- |
| `service_id` | string | 必填 |  |
| `service` | string | 必填 |  |
| `app_version` | string | 必填 |  |
| `profile` | string | 必填 |  |
| `backend_image` | string | 必填 |  |
| `frontend_image` | string | 必填 |  |
| `ner` | object | 必填 |  |
| `ner.enabled` | boolean | 必填 |  |
| `ner.state` | string | 必填 |  |
| `ner.model_id` | string | 必填 |  |
| `ner.model_dir` | string | 必填 |  |
| `ner.max_concurrency` | integer | 必填 |  |
| `ner.queue_timeout_seconds` | number | 必填 |  |
| `ner.error` | string  /  null | 必填 |  |
| `ner.requested_provider` | string | 可选 |  |
| `ner.active_provider` | string  /  null | 可选 |  |
| `ner.provider` | string | 可选 |  |
| `ner.active_providers` | array<string> | 可选 |  |
| `ner.ready` | boolean | 可选 |  |
| `image_ocr` | object | 必填 |  |
| `image_ocr.enabled` | boolean | 必填 |  |
| `image_ocr.state` | string | 必填 |  |
| `image_ocr.model_id` | string | 必填 |  |
| `image_ocr.model_dir` | string | 必填 |  |
| `image_ocr.max_concurrency` | integer | 必填 |  |
| `image_ocr.queue_timeout_seconds` | number | 必填 |  |
| `image_ocr.error` | string  /  null | 必填 |  |
| `image_ocr.requested_provider` | string | 可选 |  |
| `image_ocr.active_provider` | string  /  null | 可选 |  |
| `image_ocr.provider` | string | 可选 |  |
| `image_ocr.active_providers` | array<string> | 可选 |  |
| `image_ocr.ready` | boolean | 可选 |  |

响应 default — Check HTTP status and Content-Type. FastAPI detail is a string or validation error list; unexpected gateway/server errors can be plain text.

`application/json`

`object`

| 字段 | 类型 | 要求 | 说明 |
| --- | --- | --- | --- |
| `detail` | JSON | 必填 | Message or validation details. |

`text/plain`

`string`

## 共享数据结构

字段保持 API 的原始拼写；JSON 任意扩展字段按其所属服务说明解释。

### DesensitizeOptions

| 字段 | 类型 | 要求 | 说明 |
| --- | --- | --- | --- |
| `level` | string | 可选 | Compatibility field, currently reserved; does not select a different rule set. Select rule IDs and enabled rules instead. · default="standard" |
| `rules` | array<string>  /  null | 可选 |  |
| `preserve_length` | boolean | 可选 |  · default=false |
| `skip_roles` | array<string> | 可选 |  |
| `audit` | boolean | 可选 | Reserved compatibility flag; does not enable persistent audit logging. · default=false |
| `ner` | boolean | 可选 |  · default=false |

### DesensitizeRequest

| 字段 | 类型 | 要求 | 说明 |
| --- | --- | --- | --- |
| `messages` | array<Message> | 必填 |  |
| `options` | DesensitizeOptions | 可选 |  |

### DesensitizeResponse

| 字段 | 类型 | 要求 | 说明 |
| --- | --- | --- | --- |
| `messages` | array<Message> | 必填 |  |
| `replaced` | array<ReplacedItem> | 必填 |  |
| `metadata` | object | 必填 |  |
| `metadata.latency_ms` | number | 必填 |  |
| `metadata.engine` | string | 必填 |  |
| `metadata.rule_count` | integer | 必填 |  |

### DesensitizeTextRequest

| 字段 | 类型 | 要求 | 说明 |
| --- | --- | --- | --- |
| `text` | string | 必填 |  |
| `level` | string | 可选 | Compatibility field, currently reserved; does not select a different rule set. Select rule IDs and enabled rules instead. · default="standard" |
| `rules` | array<string>  /  null | 可选 |  |
| `ner` | boolean | 可选 |  · default=false |

### DesensitizeTextResponse

| 字段 | 类型 | 要求 | 说明 |
| --- | --- | --- | --- |
| `text` | string | 必填 |  |
| `replaced` | array<ReplacedItem> | 必填 |  |
| `latency_ms` | number | 必填 |  |

### HTTPValidationError

| 字段 | 类型 | 要求 | 说明 |
| --- | --- | --- | --- |
| `detail` | array<ValidationError> | 可选 |  |

### ImageDesensitizeRequest

| 字段 | 类型 | 要求 | 说明 |
| --- | --- | --- | --- |
| `image_base64` | string | 必填 |  |
| `mime_type` | string | 可选 |  · default="image/jpeg" |
| `level` | string | 可选 | Compatibility field, currently reserved; does not select a different rule set. Select rule IDs and enabled rules instead. · default="standard" |
| `rules` | array<string>  /  null | 可选 |  |
| `ner` | boolean | 可选 |  · default=false |
| `adaptive` | boolean | 可选 |  · default=false |
| `reversible` | boolean | 可选 |  · default=false |
| `ledger_key` | string  /  null | 可选 |  |
| `return_coordinates` | boolean | 可选 |  · default=false |
| `max_side` | integer | 可选 |  · default=1600 · minimum=256.0 · maximum=4096.0 |

### ImageDesensitizeResponse

| 字段 | 类型 | 要求 | 说明 |
| --- | --- | --- | --- |
| `image_base64` | string | 必填 |  |
| `mime_type` | string | 必填 |  |
| `replaced` | array<ReplacedItem> | 必填 |  |
| `metadata` | object | 必填 |  |
| `metadata.ocr_engine` | string | 必填 |  |
| `metadata.ocr_blocks` | integer | 必填 |  |
| `metadata.rebuilt_text_length` | integer | 必填 |  |
| `metadata.normalized_matching` | boolean | 必填 |  |
| `metadata.matched_via` | object | 必填 |  |
| `metadata.suppressed_by_space` | object | 必填 |  |
| `metadata.validator_rejected` | integer | 必填 |  |
| `metadata.gate_failure_policy` | string | 必填 |  |
| `metadata.adaptive` | boolean | 必填 |  |
| `metadata.scene` | object  /  null | 必填 |  |
| `metadata.field_fallback_regions` | integer | 必填 |  |
| `metadata.fallback_masked_lines` | integer | 必填 |  |
| `metadata.secondary_ocr` | object | 必填 |  |
| `metadata.secondary_ocr.enabled` | boolean | 必填 |  |
| `metadata.secondary_ocr.regions` | integer | 必填 |  |
| `metadata.secondary_ocr.blocks` | integer | 必填 |  |
| `metadata.secondary_ocr.reasons` | object | 必填 |  |
| `metadata.resized` | boolean | 必填 |  |
| `metadata.scale` | number | 必填 |  |
| `metadata.ocr` | object | 必填 |  |
| `metadata.ocr.enabled` | boolean | 必填 |  |
| `metadata.ocr.state` | string | 必填 |  |
| `metadata.ocr.model_id` | string | 必填 |  |
| `metadata.ocr.model_dir` | string | 必填 |  |
| `metadata.ocr.max_concurrency` | integer | 必填 |  |
| `metadata.ocr.queue_timeout_seconds` | number | 必填 |  |
| `metadata.ocr.error` | string  /  null | 必填 |  |
| `metadata.ocr.requested_provider` | string | 可选 |  |
| `metadata.ocr.active_provider` | string  /  null | 可选 |  |
| `metadata.ocr.provider` | string | 可选 |  |
| `metadata.ocr.active_providers` | array<string> | 可选 |  |
| `metadata.ocr.ready` | boolean | 可选 |  |
| `latency_ms` | number | 必填 |  |
| `coordinates` | array<object>  /  null | 可选 |  |
| `ledger` | ImageLedger  /  null | 可选 |  |

### ImageRestoreRequest

| 字段 | 类型 | 要求 | 说明 |
| --- | --- | --- | --- |
| `image_base64` | string | 必填 |  |
| `ledger` | ImageLedger | 必填 |  |
| `ledger_key` | string  /  null | 可选 |  |
| `mime_type` | string | 可选 |  · default="image/png" |

### ImageRestoreResponse

| 字段 | 类型 | 要求 | 说明 |
| --- | --- | --- | --- |
| `image_base64` | string | 必填 |  |
| `mime_type` | string | 必填 |  |
| `report` | array<object> | 必填 |  |
| `restored_count` | integer | 必填 |  |

### Message

| 字段 | 类型 | 要求 | 说明 |
| --- | --- | --- | --- |
| `role` | string | 可选 |  · default="user" |
| `content` | string | 可选 |  · default="" |

### ReplacedItem

| 字段 | 类型 | 要求 | 说明 |
| --- | --- | --- | --- |
| `rule` | string | 必填 |  |
| `placeholder` | string | 必填 |  |
| `occurrences` | integer | 必填 |  |

### RuleCreate

| 字段 | 类型 | 要求 | 说明 |
| --- | --- | --- | --- |
| `name` | string | 必填 |  · minLength=1 · maxLength=100 |
| `description` | string | 可选 |  · default="" · maxLength=500 |
| `pattern` | string | 必填 |  · minLength=1 |
| `placeholder` | string | 必填 |  · minLength=1 |
| `priority` | integer | 可选 |  · default=0 · minimum=0.0 · maximum=100.0 |
| `enabled` | boolean | 可选 |  · default=true |
| `category` | string | 可选 |  · default="custom" |

### RuleOut

| 字段 | 类型 | 要求 | 说明 |
| --- | --- | --- | --- |
| `id` | string | 必填 |  |
| `name` | string | 必填 |  |
| `description` | string | 必填 |  |
| `pattern` | string | 必填 |  |
| `placeholder` | string | 必填 |  |
| `priority` | integer | 可选 |  · default=0 |
| `enabled` | boolean | 可选 |  · default=true |
| `builtin` | boolean | 可选 |  · default=false |
| `category` | string | 可选 |  · default="custom" |

### RuleUpdate

| 字段 | 类型 | 要求 | 说明 |
| --- | --- | --- | --- |
| `name` | string  /  null | 可选 |  |
| `description` | string  /  null | 可选 |  |
| `pattern` | string  /  null | 可选 |  |
| `placeholder` | string  /  null | 可选 |  |
| `priority` | integer  /  null | 可选 |  |
| `enabled` | boolean  /  null | 可选 |  |
| `category` | string  /  null | 可选 |  |

### ValidationError

| 字段 | 类型 | 要求 | 说明 |
| --- | --- | --- | --- |
| `loc` | array<string  /  integer> | 必填 |  |
| `msg` | string | 必填 |  |
| `type` | string | 必填 |  |
| `input` | JSON | 可选 |  |
| `ctx` | object | 可选 |  |

### ModelRuntime

| 字段 | 类型 | 要求 | 说明 |
| --- | --- | --- | --- |
| `enabled` | boolean | 必填 |  |
| `state` | string | 必填 |  |
| `model_id` | string | 必填 |  |
| `model_dir` | string | 必填 |  |
| `max_concurrency` | integer | 必填 |  |
| `queue_timeout_seconds` | number | 必填 |  |
| `error` | string  /  null | 必填 |  |
| `requested_provider` | string | 可选 |  |
| `active_provider` | string  /  null | 可选 |  |
| `provider` | string | 可选 |  |
| `active_providers` | array<string> | 可选 |  |
| `ready` | boolean | 可选 |  |

### ManagedModel

| 字段 | 类型 | 要求 | 说明 |
| --- | --- | --- | --- |
| `key` | string | 必填 |  |
| `name` | string | 必填 |  |
| `description` | string | 必填 |  |
| `model_id` | string | 必填 |  |
| `source` | string | 必填 |  |
| `pull_name` | string | 必填 |  |
| `model_dir` | string | 必填 |  |
| `status` | string | 必填 |  |
| `ready` | boolean | 必填 |  |
| `runtime` | ModelRuntime | 必填 |  |
| `model` | object  /  null | 必填 |  |
| `task` | object  /  null | 必填 |  |

### SchedulerBinding

| 字段 | 类型 | 要求 | 说明 |
| --- | --- | --- | --- |
| `protocol_version` | integer | 必填 |  · const=1 |
| `configured` | boolean | 必填 |  |
| `binding_revision` | integer | 可选 |  |
| `approved_model_count` | integer | 可选 |  |

### ExecutionSettings

| 字段 | 类型 | 要求 | 说明 |
| --- | --- | --- | --- |
| `ner_provider_requested` | string | 必填 |  |
| `ocr_provider_requested` | string | 必填 |  |
| `onnx_available_providers` | array<string> | 必填 |  |
| `onnxruntime_version` | string  /  null | 必填 |  |
| `rapidocr_version` | string  /  null | 必填 |  |
| `logical_cpu_count` | integer  /  null | 必填 |  |
| `ner_intra_op_threads` | integer | 必填 |  |
| `ner_inter_op_threads` | integer | 必填 |  |
| `ocr_thread_policy` | string | 必填 |  |
| `ocr_intra_op_threads` | integer | 必填 |  |
| `ocr_inter_op_threads` | integer | 必填 |  |
| `opencv_threads` | integer | 必填 |  |
| `math_thread_environment` | object | 必填 |  |
| `max_concurrent_inference` | integer | 必填 |  |
| `ner_max_tokens` | integer | 必填 |  |

### PixelBox

| 字段 | 类型 | 要求 | 说明 |
| --- | --- | --- | --- |
| `x1` | number | 必填 |  |
| `y1` | number | 必填 |  |
| `x2` | number | 必填 |  |
| `y2` | number | 必填 |  |

### ImageLedger

| 字段 | 类型 | 要求 | 说明 |
| --- | --- | --- | --- |
| `version` | integer | 必填 |  · const=1 |
| `alg` | string | 必填 |  · const="AES-256-GCM" |
| `region_count` | integer | 必填 |  |
| `regions` | array<object> | 必填 |  |
