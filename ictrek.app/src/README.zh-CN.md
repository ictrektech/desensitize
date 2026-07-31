# 数据脱敏服务 用户使用说明

数据脱敏服务（Desensitize Service）提供基于正则规则的敏感信息识别与脱敏 HTTP API，供 WeKnora、agent-room 等应用在调用云模型前统一脱敏，防止个人隐私和密钥泄露到云端。

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
| `DESENSITIZE_HOST_PORT` | `35010` | 脱敏服务后端 API 映射到宿主机的调试端口 |
| `DESENSITIZE_DATA_PATH` | `/data/vos_workspace/desensitize` | 持久化数据目录（存储自定义规则） |
| `MODEL_HUB_SHARED_MODELS_PATH` | `/data/vos_workspace/model_hub` | Model Hub 共享模型根目录；后端会将总目录只读挂载为 `/modelhub` |
| `DESENSITIZE_NER_ENABLED` | `true` | 是否允许请求通过 `ner=true` 启用语义脱敏 |

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

### NER 模型（Model Hub 依赖）

NER 权重不包含在本应用镜像中。先在 Model Hub 安装 ModelScope 模型
`huluxiaohuowa/bert4ner-base-chinese-onnx`；本服务从只读挂载的
`/modelhub/export/ms/huluxiaohuowa/bert4ner-base-chinese-onnx/current` 加载它。
未安装该模型时，原有正则 API 不受影响；只有请求传入 `ner=true` 才会返回 503 并提示安装模型。

### 接入指南

"接入指南"页面提供了其他应用接入的完整示例代码和配置说明。

## VOS 网络内连接方式

| 目标 | 地址 |
| --- | --- |
| 同一 VOS 实例的应用 | `http://desensitize-backend:5000`（调用方必须加入外部 `vos_default` 网络） |
| VOS 内部网关 | `http://${VOS_HOST_GW_IP}:${VOS_API_GW_PORT_INTERNAL}/api/com.ictrek.desensitize` |
| 宿主机调试端口 | `http://<vos-host>:35010`（仅限受控外部访问） |

三种地址都是 API 基地址；请求单文本脱敏时追加
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
| `/health` | GET | 健康检查 |

单文本 NER 调用（不传 `ner` 或传 `false` 时保持完全兼容的纯规则模式）：

```json
POST /api/v1/desensitize/text
{"text":"张三住在北京市海淀区，手机号13812345678","ner":true}
```

批量接口在 `options` 中传入 `"ner": true`。规则优先执行，NER 仅处理规则未替换的文本。

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
- 无法处理图片/截图中的敏感信息
- NER 当前仅处理人名和地址，且受文本上下文和模型置信度影响
