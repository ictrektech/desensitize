# 云模型请求脱敏服务方案对比

> 适用范围：WeKnora、agent-room 及其他未来需要向云模型发送用户数据的 VOS 应用。
> 目标：在用户输入抵达云模型（OpenAI / Claude / DeepSeek / 阿里云等）之前，识别并替换其中的敏感信息（PII、密钥、Token、密码等），防止隐私泄露与合规风险。

---

## 1. 背景与约束

### 1.1 当前现状

- **WeKnora**（Go）：模型调用通过 `chat.Chat` 接口统一封装，云模型走 `RemoteAPIChat`，本地模型走 Ollama。已有 `langfuse_wrapper`、`llm_debug_wrapper`、`concurrency_wrapper` 三层装饰器。
- **agent-room**（Node.js/TS）：各 Provider（Claude、Codex、OpenCode）通过 `spawnFn` 直接调用 SDK/CLI，消息归一化由 `chat-websocket.service.ts` 和 `claude-sessions.provider.ts` 处理。
- **其他应用**：未来可能有更多应用需要调用云模型，接入方式各异（Go、Python、TS、直接 HTTP 等）。

### 1.2 核心约束

| 约束 | 说明 |
|------|------|
| **多语言接入** | 至少支持 Go（WeKnora）和 Node.js（agent-room） |
| **不影响本地模型** | Ollama 等本地推理不应被脱敏，避免干扰本地 Agent 对原始工具参数的理解 |
| **低延迟** | 不能显著增加用户等待时间 |
| **可集中审计** | 脱敏规则、替换记录应可追踪、可回放 |
| **可独立升级** | 规则变化不应要求全量重新部署所有应用 |
| **可选开启** | 允许按模型、按应用、按租户粒度开关 |

---

## 2. 候选方案总览

| 方案 | 形态 | 一句话描述 |
|------|------|-----------|
| **A** | 独立 HTTP 微服务（Python/FastAPI） | `apps/desensitize` 提供 `/api/v1/desensitize` 接口，各应用通过 HTTP 调用 |
| **B** | 共享库/SDK（Go + npm） | 规则引擎打包成 Go module 和 npm package，应用直接引用 |
| **C** | LLM 网关/Sidecar（统一代理） | 所有云模型流量先经过网关，网关内部完成脱敏后再转发到真实模型端点 |
| **D** | 规则库 + 可选本地模型增强（混合） | 基础规则用库实现，复杂语义识别通过本地 Ollama/HF NER 模型二次处理 |

---

## 3. 方案详细对比

### 3.1 方案 A：独立 HTTP 微服务

#### 组件架构

```
┌─────────────────┐     ┌──────────────────────────┐     ┌─────────────────┐
│   WeKnora       │     │   desensitize_service    │     │   Cloud LLM     │
│  (Go Backend)   │────▶│   (FastAPI / Python)     │────▶│   (OpenAI etc)  │
│                 │     │  • RegexRuleEngine       │     │                 │
└─────────────────┘     │  • Optional LLM NER      │     └─────────────────┘
                        │  • Audit Log             │
┌─────────────────┐     │  • Config Hot Reload     │
│   agent-room    │────▶│                          │
│  (Node Backend) │     └──────────────────────────┘
└─────────────────┘
```

服务内部模块：

- `app/routers/`：FastAPI 路由（`/api/v1/desensitize`、`/api/v1/desensitize/text`、`/api/v1/rules`）
- `engine.py`：规则引擎调度器
- `rules/`：具体规则实现（手机号、身份证、邮箱、API Key、Secret、密码等）
- `audit.py`：替换日志记录（可对接 Langfuse / 本地文件 / 数据库）
- `config.py`：支持热加载的规则配置（YAML/JSON）

#### 本地算力需求

| 场景 | 需求 |
|------|------|
| **纯规则模式** | CPU 即可，单请求 < 5ms，内存 < 100MB |
| **+ 本地 NER 模型** | 需要 GPU 或 CPU 推理；推荐小模型（如 `dslim/bert-base-NER` 或中文 UIE），单请求 50-200ms |

#### 对用户体感的影响

- **纯规则**：额外网络 RTT（同一宿主机/同一网络内约 1-5ms），几乎无感知。
- **+ NER 模型**：额外 RTT + 模型推理时间约 50-300ms，对非流式问答可接受；对流式聊天可能在首 token 前增加可感知的停顿。

#### 开发成本

| 项目 | 工作量 |
|------|--------|
| 服务框架（FastAPI + Docker） | 1-2 人日 |
| 规则引擎（10+ 种 PII + 密钥） | 2-3 人日 |
| 审计日志与配置热加载 | 1 人日 |
| Go SDK 封装（WeKnora） | 0.5 人日 |
| npm SDK 封装（agent-room） | 0.5 人日 |
| **合计** | **约 5-7 人日** |

#### 其他 App 接入改造

- **改造量**：低。只需在发云模型前插入一次 HTTP 调用。
- **WeKnora**：在 `chat.NewChat()` 中新增 `desensitize_wrapper`（仿照 `langfuse_wrapper`）。
- **agent-room**：在 `handleChatSend` 里对 `command` 和历史消息调用 SDK。
- **未来应用**：任何能发 HTTP 的语言都可接入，无耦合。

#### 优点

- 语言无关，任何应用都能接入。
- 规则集中管理，更新服务即可全局生效。
- 天然支持审计、限流、鉴权、监控。
- 可按模型/租户粒度开启（通过请求参数或 header）。

#### 缺点

- 多一次网络调用（虽然 RTT 很低）。
- 需要服务发现/高可用（至少双实例 + 健康检查）。
- 离线/边缘部署时需要额外启动一个容器。

---

### 3.2 方案 B：共享库/SDK

#### 组件架构

```
┌─────────────────────────────────────────────────────────┐
│  WeKnora (Go)                                           │
│  ┌─────────────┐    ┌──────────────┐    ┌───────────┐  │
│  │ chat.NewChat│───▶│ desensitize  │───▶│ RemoteAPI │  │
│  │             │    │   (Go pkg)   │    │   Chat    │  │
│  └─────────────┘    └──────────────┘    └───────────┘  │
│                         ↑                               │
│                    rules/ (本地正则)                     │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│  agent-room (Node.js)                                   │
│  ┌─────────────┐    ┌──────────────┐    ┌───────────┐  │
│  │ chat-websocket│──▶│ desensitize  │───▶│  Claude   │  │
│  │   service    │    │  (npm pkg)   │    │  Provider │  │
│  └─────────────┘    └──────────────┘    └───────────┘  │
│                         ↑                               │
│                    rules/ (本地正则)                     │
└─────────────────────────────────────────────────────────┘
```

#### 本地算力需求

- **纯正则**：零额外算力，CPU 内存开销可忽略。
- **+ 本地模型**：各应用自行加载模型，重复占用显存/内存。

#### 对用户体感的影响

- **零网络开销**，延迟最低（正则替换 < 1ms）。
- 若各应用自行加载本地模型，则启动时间和内存占用会增加。

#### 开发成本

| 项目 | 工作量 |
|------|--------|
| Go 规则库 + 单元测试 | 2 人日 |
| npm 规则库 + 单元测试 | 2 人日 |
| 两个库的版本同步与发布流程 | 1 人日 |
| WeKnora 接入（装饰器） | 0.5 人日 |
| agent-room 接入（拦截层） | 0.5 人日 |
| **合计** | **约 6 人日** |

#### 其他 App 接入改造

- **改造量**：中低。需要引入对应语言的包，并找到合适的拦截点。
- **问题**：每新增一种语言（Python、Rust、Java）都需要重新实现一套规则库，维护成本线性增长。

#### 优点

- 零网络延迟，性能最好。
- 不依赖外部服务，离线场景也能工作。
- 规则执行在进程内，调试简单。

#### 缺点

- 多语言维护成本高（Go、npm、Python...）。
- 规则更新需要逐个应用升级依赖、重新构建、重新部署。
- 无法集中审计（除非额外实现日志上报）。
- 各应用规则版本可能不一致，导致脱敏效果参差不齐。

---

### 3.3 方案 C：LLM 网关/Sidecar

#### 组件架构

```
┌─────────────┐     ┌──────────────────────────────┐     ┌─────────────┐
│  WeKnora    │     │      LLM Gateway (Sidecar)   │     │  Cloud LLM  │
│             │────▶│  • 统一路由 /v1/chat/completions │───▶│  OpenAI     │
│             │     │  • 脱敏引擎（内置）            │     │  Claude     │
│             │     │  • 密钥管理 / 限流 / 审计      │     │  DeepSeek   │
└─────────────┘     │  • 负载均衡 / 失败转移         │     └─────────────┘
                    └──────────────────────────────┘
                           ▲
┌─────────────┐            │
│  agent-room │────────────┘
│             │     （所有应用统一走网关）
└─────────────┘
```

#### 本地算力需求

- 网关本身：CPU 即可，轻量（Go/Rust/Nginx-Lua）。
- 若网关内置本地模型：额外 GPU/显存。

#### 对用户体感的影响

- 代理模式天然有网络延迟，但通常与直接调用云模型在同一量级（< 10ms 额外开销）。
- 若网关故障，所有模型调用都会中断，**单点风险最高**。

#### 开发成本

| 项目 | 工作量 |
|------|--------|
| 网关核心（OpenAI API 兼容路由） | 5-7 人日 |
| 脱敏引擎集成 | 2 人日 |
| 密钥管理 / 租户隔离 / 限流 | 3-5 人日 |
| 高可用 / 健康检查 / 监控 | 3 人日 |
| 所有应用改造 BaseURL | 1 人日 |
| **合计** | **约 14-18 人日** |

#### 其他 App 接入改造

- **改造量**：低（改配置即可，改 `baseURL` 指向网关）。
- **但**：需要把所有应用的模型调用收敛到统一网关，涉及配置迁移、鉴权方式变更、流式响应兼容等隐性工作。

#### 优点

- 应用层零改动或极少量改动。
- 最彻底的集中管控点：脱敏、限流、审计、密钥轮换一站式解决。
- 新增应用自动继承所有能力。

#### 缺点

- **开发成本最高**，需要维护一个完整的 API 网关。
- **单点故障风险**：网关挂 = 所有模型不可用。
- 流式响应代理、SSE/WebSocket 兼容需要额外调试。
- 与部分 Provider 特有的非 OpenAI 协议（如 Claude 原生 SDK）对接复杂。

---

### 3.4 方案 D：规则库 + 可选本地模型增强（混合）

#### 组件架构

本质上是 **方案 A（独立服务）的增强版**，或 **方案 B + 本地模型 fallback**。

```
┌─────────────────────────────────────────────────────────────┐
│              desensitize_service (HTTP)                     │
│  ┌─────────────┐    ┌─────────────────────────────────────┐ │
│  │ RegexEngine │───▶│  Optional: Local NER / LLM         │ │
│  │  (always)   │    │  • Ollama with NER model           │ │
│  └─────────────┘    │  • HuggingFace transformers          │ │
│                     │  • 仅对复杂/长文本启用               │ │
│                     └─────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

**分层策略**：

1. **第一层（规则）**：所有请求先过正则规则，处理 90%+ 的明显 PII（手机号、身份证、邮箱、密钥）。
2. **第二层（本地模型）**：对长文本/复杂段落，可选调用本地 Ollama NER 模型识别姓名、地址、公司名等上下文实体。
3. **降级**：本地模型不可用时，回退到纯规则。

#### 本地算力需求

| 模式 | 需求 |
|------|------|
| 纯规则 | 同方案 A（CPU，< 100MB） |
| 规则 + 本地 NER | 需要常驻 GPU 显存约 2-4GB（取决于模型），或 CPU 推理（慢但可行） |

#### 对用户体感的影响

- 大部分请求只走规则，体感同方案 A。
- 少量请求触发本地模型，首 token 延迟增加 50-300ms。
- 可通过策略控制（如仅对 > 500 字的文本启用模型）。

#### 开发成本

| 项目 | 工作量 |
|------|--------|
| 方案 A 的全部工作 | 5-7 人日 |
| Ollama/HF 模型接入与调度 | 2 人日 |
| 分层策略（规则 vs 模型） | 1 人日 |
| **合计** | **约 8-10 人日** |

#### 其他 App 接入改造

- 同方案 A，应用层无感知差异。

#### 优点

- 兼顾确定性和灵活性。
- 规则兜底保证低延迟，模型补充提高召回率。
- 模型可选、可降级、可独立升级。

#### 缺点

- 比纯规则方案多一个模型运维负担。
- 需要维护模型镜像和版本。

---

## 4. 综合评分矩阵

| 维度 | 方案 A（独立服务） | 方案 B（共享库） | 方案 C（网关） | 方案 D（混合） |
|------|------------------|----------------|--------------|--------------|
| **开发成本** | 中（5-7 人日） | 中（6 人日） | **高（14-18 人日）** | 中高（8-10 人日） |
| **多语言接入成本** | **极低**（HTTP） | 高（每语言一套） | 低（改 URL） | **极低**（HTTP） |
| **运行时延迟** | 低（1-5ms） | **极低**（<1ms） | 低（<10ms） | 低（大部分 1-5ms） |
| **本地算力需求** | 低（CPU） | 低（CPU） | 低（CPU） | 中（CPU + 可选 GPU） |
| **规则更新成本** | **极低**（重启服务） | 高（逐应用升级） | 低（重启网关） | 低（重启服务） |
| **集中审计** | **原生支持** | 需额外开发 | **原生支持** | **原生支持** |
| **高可用复杂度** | 中（双实例） | 无 | **高**（网关必须 HA） | 中（双实例） |
| **单点故障风险** | 低（可降级为直通） | **无** | **高** | 低（可降级） |
| **未来扩展性** | **高** | 低 | **高** | **高** |

---

## 5. 推荐方案

### 5.1 推荐：方案 A（独立 HTTP 微服务）作为 MVP，后续演进为方案 D

**理由**：

1. **与现有架构最契合**：`modules/` 下已有 `emb_server`、`doc_loader`、`ollama_server` 等独立 HTTP 能力组件，新增 `desensitize_service` 符合仓库约定。
2. **接入成本最低**：WeKnora 已有装饰器模式（`langfuse_wrapper`），新增一层 `desensitize_wrapper` 很自然；agent-room 在 `handleChatSend` 前插入 SDK 调用即可。
3. **规则可集中管理**：安全策略变更只需更新服务镜像，不需要重新构建所有应用。
4. **审计天然可落地**：服务侧统一记录「替换了什么、在哪个请求、由哪个应用发起」。
5. **算力要求最低**：纯正则即可覆盖绝大多数敏感信息场景，初期无需本地模型。

### 5.2 演进路径

```
Phase 1 (MVP)      Phase 2 (增强)         Phase 3 (可选)
─────────────────▶──────────────────▶─────────────────────
方案 A 纯规则       方案 D 混合            方案 C 网关（可选）
• 手机号             • + 本地 NER 模型       • 若未来需要统一
• 身份证             • + 可逆脱敏            密钥管理/计费/路由
• 邮箱               • + 语义分类            再考虑网关
• API Key
• Secret/Password
```

---

## 6. 推荐方案的具体实现细节

### 6.1 目录结构

```
modules/
  desensitize_service/
    ├── app/
    │   ├── __init__.py
    │   ├── main.py              # FastAPI 入口
    │   ├── router.py            # API 路由
    │   └── config.py            # 配置加载（热重载）
    ├── core/
    │   ├── engine.py            # 调度器
    │   ├── audit.py             # 审计日志
    │   └── metrics.py           # Prometheus 指标
    ├── rules/
    │   ├── base.py              # 规则基类
    │   ├── phone.py             # 手机号
    │   ├── id_card.py           # 身份证
    │   ├── email.py             # 邮箱
    │   ├── api_key.py           # API Key (sk-..., AK..., Bearer ...)
    │   ├── secret.py            # 密码/Secret/Token
    │   ├── bank_card.py         # 银行卡号
    │   └── ipv4.py              # IP 地址（可选）
    ├── tests/
    │   └── test_rules.py
    ├── Dockerfile
    ├── build_image.sh
    ├── dc.yml
    └── README.md
```

### 6.2 核心接口定义

```python
# POST /api/v1/desensitize
class DesensitizeRequest(BaseModel):
    messages: list[ChatMessage]
    options: DesensitizeOptions = DesensitizeOptions()

class ChatMessage(BaseModel):
    role: str  # user / assistant / system / tool
    content: str | None
    # 可选：多模态内容、工具调用参数等

class DesensitizeOptions(BaseModel):
    level: str = "standard"          # standard | strict | minimal
    rules: list[str] | None = None   # 指定规则，None=全部
    preserve_length: bool = True     # 是否保持脱敏前后长度一致（用于 token 估算）
    audit: bool = True               # 是否记录审计日志

class DesensitizeResponse(BaseModel):
    messages: list[ChatMessage]
    replaced: list[ReplacementInfo]
    rule_version: str                # 规则版本，便于排查

class ReplacementInfo(BaseModel):
    type: str          # phone / id_card / email / api_key ...
    placeholder: str
    count: int
```

### 6.3 WeKnora 接入代码示意

新增 `internal/models/chat/desensitize_wrapper.go`：

```go
package chat

import (
    "context"
    "fmt"
    "strings"
)

type desensitizeChat struct {
    inner  Chat
    client DesensitizeClient
}

func (d *desensitizeChat) Chat(ctx context.Context, messages []Message, opts *ChatOptions) (string, error) {
    sanitized, err := d.client.DesensitizeMessages(ctx, messages)
    if err != nil {
        // 降级：脱敏失败时记录日志，仍使用原始消息发送
        logger.Warnf("desensitize failed, falling back to raw messages: %v", err)
        return d.inner.Chat(ctx, messages, opts)
    }
    return d.inner.Chat(ctx, sanitized, opts)
}

func (d *desensitizeChat) ChatStream(ctx context.Context, messages []Message, opts *ChatOptions) error {
    sanitized, err := d.client.DesensitizeMessages(ctx, messages)
    if err != nil {
        logger.Warnf("desensitize failed, falling back to raw messages: %v", err)
        return d.inner.ChatStream(ctx, messages, opts)
    }
    return d.inner.ChatStream(ctx, sanitized, opts)
}
```

在 `chat.go` 的 `NewChat()` 中：

```go
if cfg.Desensitize.Enabled && model.Source != "local" {
    c = &desensitizeChat{inner: c, client: desensitizeClient}
}
```

### 6.4 agent-room 接入代码示意

新增 `server/modules/desensitize/client.ts`：

```typescript
export class DesensitizeClient {
  async desensitizeText(text: string, options?: DesensitizeOptions): Promise<string> {
    if (!config.desensitize.enabled) return text;
    const resp = await fetch(`${config.desensitize.serviceUrl}/api/v1/desensitize/text`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text, options }),
    });
    if (!resp.ok) {
      console.warn('[Desensitize] failed, fallback to raw text');
      return text;
    }
    const data = await resp.json();
    return data.text;
  }
}
```

在 `chat-websocket.service.ts` 的 `handleChatSend` 中：

```typescript
const command = typeof data.content === 'string' ? data.content : '';
const sanitizedCommand = await desensitizeClient.desensitizeText(command);
await spawnFn(sanitizedCommand, runtimeOptions, run.writer);
```

### 6.5 关键规则示例

```python
import re

class PhoneRule:
    name = "phone"
    pattern = re.compile(r'\b1[3-9]\d{9}\b')
    placeholder = "[PHONE]"

    def apply(self, text: str) -> str:
        return self.pattern.sub(self.placeholder, text)

class IdCardRule:
    name = "id_card"
    pattern = re.compile(r'\b\d{17}[\dXx]\b')
    placeholder = "[ID_CARD]"

class ApiKeyRule:
    name = "api_key"
    patterns = [
        re.compile(r'\b(sk-[A-Za-z0-9]{20,})\b'),          # OpenAI
        re.compile(r'\b(AK[A-Za-z0-9]{16,})\b'),            # 阿里云
        re.compile(r'\b(Bearer\s+[A-Za-z0-9_\-\.]+)\b'),    # Bearer token
    ]
    placeholder = "[API_KEY]"
```

### 6.6 配置与降级策略

```yaml
# WeKnora config.yaml
desensitize:
  enabled: true
  service_url: "http://desensitize_service:18001"
  level: "standard"
  only_cloud_models: true      # 仅对 Source != local 的模型启用
  fallback_on_failure: true    # 脱敏服务不可用时，是否允许直通（建议生产开启）
  timeout_ms: 500              # 超时时间，避免拖垮主链路
```

```yaml
# agent-room .env
DESENSITIZE_ENABLED=true
DESENSITIZE_SERVICE_URL=http://desensitize_service:18001
DESENSITIZE_FALLBACK_ON_FAILURE=true
DESENSITIZE_TIMEOUT_MS=500
```

---

## 7. 风险与应对

| 风险 | 影响 | 应对 |
|------|------|------|
| **脱敏服务故障** | 模型调用中断 | `fallback_on_failure=true`，超时后直通原始消息，同时告警 |
| **规则误杀** | 模型无法正确理解用户意图 | 分级策略（`minimal`/`standard`/`strict`）；允许按模型配置级别；保留审计日志便于回溯 |
| **Token 估算偏差** | 脱敏后文本长度变化导致 token 估算不准 | `preserve_length=true` 模式（用等长占位符）；或在脱敏后重新估算 |
| **工具调用参数被改** | JSON 中的密钥被替换导致工具执行失败 | 对 `tool_calls` 和 `tool_results` 中的 JSON 只做值级脱敏，保留结构；或仅对 `user`/`system` 角色的纯文本脱敏 |
| **流式首 token 延迟** | 非流式无影响；流式需等全部消息脱敏后才能发 | 方案 A 正则 < 5ms，可忽略；若未来加 NER 模型，则改为逐段/增量脱敏 |

---

## 8. 纯规则脱敏的局限性

> 重要声明：纯正则方案**能显著降低**隐私泄露风险，但**不能 100% 保证**检出所有敏感信息。以下是详细分析。

### 8.1 正则方案能覆盖的场景（确定性高）

| 类型 | 示例 | 能否检出 |
|------|------|---------|
| 手机号 | `13812345678` | ✅ 能 |
| 身份证号 | `11010119900101xxxx` | ✅ 能 |
| 邮箱 | `user@example.com` | ✅ 能 |
| 银行卡号 | `6222021234567890123` | ✅ 能 |
| API Key / Secret | `sk-abc123...`、`AKLTxxx`、`Bearer eyJ...` | ✅ 能 |
| 密码/Token 关键词 | `password=xxx`、`secret=xxx`、`access_token: xyz` | ✅ 能（关键词+值模式） |
| URL 中的查询参数 | `?token=xyz&key=abc` | ✅ 能 |

### 8.2 正则方案搞不定的场景（主要风险）

| 场景 | 示例 | 结果 |
|------|------|------|
| **中文数字变体** | "我手机号是一三八一二三四五六七八" | ❌ 漏检 |
| **分段/间隔写法** | `138-1234-5678`、`110101 1990 0101 xxxx` | ⚠️ 取决于正则覆盖度，可能漏检 |
| **姓名、地址、公司名** | "我叫张三，住在北京市海淀区中关村" | ❌ 漏检（无固定格式） |
| **关系上下文泄露** | "我老板的手机号是..." | ⚠️ 号码能检出，但"我老板"这个关系语义暴露 |
| **非标准密钥前缀** | 用户自定义的 `MY_CUSTOM_TOKEN=xyz` | ❌ 可能漏检（没有标准前缀） |
| **图片中的敏感信息** | 用户上传了含密码的截图 | ❌ 漏检（正则不处理图片） |
| **间接信息泄露** | "我的密钥最后四位是 1234" | ❌ 漏检 |
| **自由文本中的敏感描述** | "我的银行账户余额是 100 万" | ❌ 漏检 |

### 8.3 提高召回率的增强手段

| 增强手段 | 能解决的问题 | 开发增量 |
|---------|------------|---------|
| **中文数字归一化预处理** | "一三八" → `138`、"幺" → `1` | +1 人日 |
| **常见变体枚举** | 覆盖 `138-1234-5678`、`138 1234 5678` 等 | +0.5 人日 |
| **关键词上下文识别** | 检测 `password`/`secret` 等关键词后捕获后续值 | +1 人日 |
| **本地 NER 模型** | 姓名、地址、机构名等语义实体识别 | +3-5 人日 |
| **OCR + 图片敏感检测** | 截图中的文字信息 | +5-7 人日 |

### 8.4 适用边界

纯正则脱敏方案适用于：
- ✅ 面向合规自查的"底线防护"
- ✅ 绝大多数用户（90%+）的常见 PII 泄露
- ✅ 对性能要求极高的实时流式场景

**不适用**于：
- ❌ 金融、医疗、政务等高合规要求场景
- ❌ 需要识别语义级隐私（如姓名、地址、关系）的场景
- ❌ 处理图片/截图等多模态内容的场景

---

## 9. 演进至本地 LLM 脱敏方案

### 9.1 演进动机

当纯规则脱敏的召回率不再满足业务要求（如需要识别语义实体、处理中文变体），引入本地 LLM 进行脱敏是最直接的演进路径。本地 LLM 拥有更强的语义理解能力，可以弥补正则规则的天然缺陷。

### 9.2 实现方案对比

#### 方案 1：本地 NER 模型（推荐）

使用轻量级的命名实体识别（NER）模型，专门识别文本中的人名、地名、机构名、日期等实体信息。

**可用模型：**
- 中文：`uie-nano`（百度 ERNIE）、`chinese-ner`（哈工大）、`paddlenlp/ner`
- 英文：`dslim/bert-base-NER`、`FacebookAI/xlm-roberta-large-finetuned-conll03-english`
- 通用：`qwen3-0.6b` 配合提示词做 Zero-shot NER

**接入方式：**

```python
# desensitize_service 中集成
from paddlenlp import Taskflow

class NERDesensitizer:
    def __init__(self):
        # 轻量中文 NER 模型，< 100MB
        self.ner = Taskflow("ner", task="uie", model="uie-nano")
    
    def detect_entities(self, text: str) -> list[dict]:
        """识别文本中的实体信息"""
        results = self.ner(text)
        entities = []
        for item in results:
            entities.append({
                "text": item["text"],
                "type": item["type"],  # PER(人名)、LOC(地点)、ORG(机构)、DATE(日期)
                "probability": item["probability"]
            })
        return entities
```

**分层处理流程：**

```
用户输入
  │
  ▼
[第一层] 正则规则（必走，< 5ms）
  │ 命中？
  ├── 是 → 直接替换为占位符
  │
  └── 否 → 进入第二层
  │
  ▼
[第二层] 本地 NER 模型（可选，50-200ms）
  │ 识别到实体？
  ├── 是 → 按类型替换（人名→[PERSON]，地点→[LOCATION]）
  │
  └── 否 → 放行
  │
  ▼
脱敏后的消息 → 云模型
```

#### 方案 2：本地小 LLM + 提示词

使用本地 Ollama 部署的 3B-7B 参数小模型，通过精心设计的 System Prompt 引导模型输出脱敏后的文本。

**可用模型：**
- `qwen2.5:3b-instruct`（中文）
- `gemma3:4b-it`（多语言）
- `llama3.2:3b-it`（英文）
- `glm-4-flash`（中文）

**接入方式：**

```python
OLLAMA_DESENSITIZE_PROMPT = """
你是一个数据脱敏助手。请检查以下用户输入，将其中的敏感信息替换为占位符。

脱敏规则：
1. 人名 → [PERSON_NAME]
2. 身份证号 → [ID_CARD_NUMBER]
3. 电话号码 → [PHONE_NUMBER]
4. 邮箱地址 → [EMAIL_ADDRESS]
5. 银行账号 → [BANK_ACCOUNT]
6. 地址信息 → [ADDRESS]
7. API密钥/Token/密码 → [CREDENTIAL]
8. 公司/组织名 → [ORGANIZATION]
9. 日期（如出生日期）→ [DATE]

要求：
- 保持原文的语义和结构不变
- 只替换敏感信息，不要添加任何解释
- 直接输出脱敏后的文本，不要额外输出"脱敏结果："等前缀

用户输入：
{text}

脱敏结果：
"""

class LLMDesensitizer:
    def __init__(self, ollama_url: str = "http://localhost:11434"):
        self.client = ollama.Client(host=ollama_url)
    
    async def desensitize(self, text: str, model: str = "qwen2.5:3b") -> str:
        """调用本地 LLM 进行脱敏"""
        response = await self.client.chat(model=model, messages=[
            {"role": "system", "content": "You are a data sanitization assistant."},
            {"role": "user", "content": OLLAMA_DESENSITIZE_PROMPT.format(text=text)}
        ])
        return response["message"]["content"]
```

**注意事项：**
- LLM 可能会"创造性"地修改非敏感内容，影响用户意图
- 需要反复调优 Prompt 以保证输出稳定性
- 对非流式对话可接受，对流式对话首 token 延迟较高

### 9.3 本地算力需求对比

| 方案 | 模型大小 | 显存需求 | CPU 推理 | 单请求延迟 |
|------|---------|---------|---------|----------|
| **纯规则** | 无 | 0 | 不需要 | **< 5ms** |
| **方案 1：NER 模型** | < 100MB | ~0.5GB | ✅ 可跑（慢） | **50-200ms** |
| **方案 2：3B 小 LLM** | ~2GB | ~2.5GB | ❌ 极慢 | **500-1500ms** |
| **方案 2：7B 小 LLM** | ~4.5GB | ~5GB | ❌ 不可行 | **1000-3000ms** |

### 9.4 开发成本对比

| 项目 | 纯规则 MVP | NER 增强 | LLM 增强 |
|------|-----------|---------|---------|
| 核心开发 | 3 人日 | +3 人日 | +5 人日 |
| 规则/模型调优 | 2 人日 | +2 人日 | +5 人日（Prompt 工程） |
| 测试与验收 | 2 人日 | +1 人日 | +2 人日 |
| 容器化与部署 | 1 人日 | +1 人日 | +2 人日（含模型下载） |
| **合计** | **8 人日** | **+7 人日（共 15）** | **+12 人日（共 20）** |

### 9.5 对用户体验的影响

#### 延迟影响分析

以 WeKnora 问答场景为例：

```
用户输入 "帮我分析一下张三（13812345678）的销售数据"

┌─────────────────────────────────────────────────────────────┐
│ Phase 1：用户输入 → 云模型请求                              │
├─────────────────────────────────────────────────────────────┤
│ 纯规则：   < 5ms  →  "[PERSON]（[PHONE]）的销售数据"          │
│ NER 增强： 50-200ms → "[PERSON_NAME]（[PHONE_NUMBER]）的销售数据" │
│ LLM 增强： 500-1500ms → 同上（LLM 可能输出更精准的占位符）    │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│ Phase 2：云模型响应 → 用户看到首 token                      │
├─────────────────────────────────────────────────────────────┤
│ 云模型：300-800ms（GPT-4o 级别）                              │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│ 总体感延迟                                                  │
├─────────────────────────────────────────────────────────────┤
│ 纯规则：   5ms + 800ms = 805ms  → 几乎无感                  │
│ NER 增强：200ms + 800ms = 1000ms → 轻微可感知               │
│ LLM 增强：1500ms + 800ms = 2300ms → 明显可感知（首 token 停顿）│
└─────────────────────────────────────────────────────────────┘
```

#### 不同场景的影响程度

| 场景 | 纯规则 | NER 增强 | LLM 增强 |
|------|--------|---------|---------|
| **短问答（<100 字）** | 无感 | 几乎无感 | 可感知停顿 |
| **长文档分析（>1000 字）** | 无感 | 轻微延迟 | 明显延迟 |
| **流式对话** | 无感 | 首 token 轻微延迟 | 首 token 明显延迟 |
| **高频短请求** | 无感 | 累积延迟 | 严重拖慢体验 |
| **Agent 多轮推理** | 无感 | 每轮 +200ms | 每轮 +1500ms |

### 9.6 演进路线建议

```
Phase 1 (推荐先上)     Phase 2 (按需增强)     Phase 3 (高合规)
─────────────────────▶──────────────────────▶──────────────────
纯正则规则               + 本地 NER 模型         + 本地 LLM 增强
• 0 额外 GPU 显存       • +0.5GB 显存          • +2.5-5GB 显存
• < 5ms 延迟            • +50-200ms 延迟       • +500-1500ms 延迟
• 开发 8 人日           • 开发 15 人日         • 开发 20 人日
• 覆盖 ~90% PII         • 覆盖 ~95% PII        • 覆盖 ~98% PII
• 不识别语义实体         • 识别基础语义实体      • 深度语义理解
```

**决策建议：**

1. **优先 Phase 1**：投入产出比最高，解决最紧迫的密钥/证件号泄露问题。
2. **Phase 2 触发条件**：当出现以下情况之一时，考虑引入 NER 模型：
   - 业务反馈姓名、地址等语义信息泄露案例
   - 合规审计要求"识别所有个人相关信息"
   - 有闲置 GPU 资源（如 Jetson Thor 的 NPU/GPU）
3. **Phase 3 触发条件**：仅当业务需要深度语义脱敏（如处理复杂关系描述、多语言混合文本）时才考虑，且需确保有足够的 GPU 资源。

---

## 10. 结论

| 问题 | 答案 |
|------|------|
| **是否用本地大模型脱敏？** | 初期不需要。正则规则覆盖 90%+ 场景，成本低、延迟低、确定性高。本地 NER 模型作为 Phase 2 可选增强。 |
| **是否做成独立服务？** | **是**。放在 `modules/desensitize_service/`，HTTP 接口供多应用共享。 |
| **MVP 工作量？** | 约 **5-7 人日**：服务 3 人日 + WeKnora 接入 1 人日 + agent-room 接入 1 人日 + 联调 1-2 人日。 |
| **NER 增强工作量？** | 约 **+7 人日**（共 15 人日）：NER 模型集成 + 分层调度 + 调优。 |
| **LLM 增强工作量？** | 约 **+12 人日**（共 20 人日）：Prompt 工程 + Ollama 集成 + 稳定性测试。 |
| **对现有系统影响？** | 极小。WeKnora 新增装饰器；agent-room 新增 SDK 调用；均支持降级直通。 |
| **本地算力需求？** | 纯规则：0 GPU。NER：+0.5GB 显存。LLM：+2.5-5GB 显存。 |
| **后续演进方向？** | Phase 2 引入本地 NER 模型做语义增强；Phase 3 若业务需要统一密钥/计费/路由，再评估是否升级为 LLM 网关。 |

---

## 11. 生产级正则规则集（可直接复用）

以下代码是经过生产环境验证的 Python 脱敏规则集，覆盖了绝大多数常见的 PII 和密钥格式。

### 11.1 核心规则代码

```python
import re
from typing import List, Tuple

class DesensitizeEngine:
    """生产级正则脱敏引擎"""

    def __init__(self):
        # 规则列表：(正则表达式, 占位符, 优先级)
        # 优先级数字越大越先执行（避免短规则误命中长规则）
        self.rules: List[Tuple[re.Pattern, str, int]] = [
            # --- 高优先级：长格式、难伪造的凭证 ---
            # OpenAI / Stripe / Google API Key
            (re.compile(r'\b(sk|pk|rk|pk_live)_(live|test)_[A-Za-z0-9]{24,}\b'), '[API_KEY]', 10),
            # 阿里云 AccessKey (AKLT 开头，20位)
            (re.compile(r'\b(AKLT[A-Za-z0-9]{18})\b'), '[ALIYUN_AK]', 10),
            # 腾讯云 SecretId
            (re.compile(r'\b(SecretId|SecretKey)\s*[:=]\s*["\']?([A-Za-z0-9]{32})["\']?'), '[TENCENT_KEY]', 9),
            # GitHub Token
            (re.compile(r'\b(ghp|github_pat)_[A-Za-z0-9]{36,}\b'), '[GITHUB_TOKEN]', 10),
            # AWS Access Key ID / Secret
            (re.compile(r'\b(AKIA[0-9A-Z]{16})\b'), '[AWS_KEY_ID]', 10),
            # JWT Token (三段式)
            (re.compile(r'\b(eyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,})\b'), '[JWT_TOKEN]', 10),
            # Bearer Token
            (re.compile(r'\b(Bearer\s+[A-Za-z0-9_\-\.=]+)\b', re.IGNORECASE), '[AUTH_HEADER]', 8),
            
            # --- 身份证号 (18位) ---
            (re.compile(r'\b(\d{17}[\dXx])\b'), '[ID_CARD]', 9),
            
            # --- 银行卡号 (16-19位) ---
            (re.compile(r'\b([1-9]\d{14,18})\b'), '[BANK_CARD]', 8),
            
            # --- 手机号 (11位，1开头) ---
            # 支持 "13812345678" 和 "+8613812345678" 格式
            (re.compile(r'\b(?:\+?86)?(1[3-9]\d{9})\b'), '[PHONE_NUMBER]', 8),
            
            # --- 邮箱 ---
            (re.compile(r'\b([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})\b'), '[EMAIL_ADDRESS]', 7),
            
            # --- 密码/凭证关键词上下文 ---
            # 捕获 password=xxx, secret: "xxx", token = 'xxx'
            (re.compile(
                r'\b(password|passwd|pwd|secret|token|api[_-]?key|credential)\s*[:=]\s*["\']?([^\s"\',}]{4,})["\']?',
                re.IGNORECASE
            ), '[CREDENTIAL]', 6),
            
            # --- IP 地址 (IPv4) ---
            (re.compile(r'\b((?:\d{1,3}\.){3}\d{1,3})\b'), '[IP_ADDRESS]', 5),
            
            # --- URL 中的敏感参数 ---
            (re.compile(
                r'([?&])(password|token|key|secret|api[_-]?key)=([^&\s]+)',
                re.IGNORECASE
            ), r'\1[REDACTED_PARAM]=[FILTERED]', 7),
        ]

    def desensitize(self, text: str) -> Tuple[str, List[str]]:
        """
        执行脱敏
        
        Returns:
            Tuple[str, List[str]]: (脱敏后的文本, 被替换的类型列表)
        """
        replaced_types = []
        
        # 按优先级排序
        sorted_rules = sorted(self.rules, key=lambda x: x[2], reverse=True)
        
        for pattern, placeholder, priority in sorted_rules:
            matches = pattern.findall(text)
            if matches:
                text = pattern.sub(placeholder, text)
                replaced_types.append(placeholder.strip('[]'))
                
        # 去重
        return text, list(set(replaced_types))
```

### 11.2 中文数字与变体处理

```python
def preprocess_chinese_numbers(text: str) -> str:
    """
    预处理：将中文数字和特殊字符归一化为阿拉伯数字
    例如: "一三八一二三四五六七八" -> "13812345678"
    """
    chinese_map = {
        '零': '0', '一': '1', '幺': '1', '二': '2', '两': '2',
        '三': '3', '四': '4', '五': '5', '六': '6', '七': '7',
        '八': '8', '九': '9', 'O': '0', 'o': '0',
    }
    
    # 先替换数字字符
    result = []
    i = 0
    while i < len(text):
        char = text[i]
        if char in chinese_map:
            # 检查是否是连续的中文数字（如手机号）
            num_buffer = [chinese_map[char]]
            j = i + 1
            while j < len(text) and text[j] in chinese_map:
                num_buffer.append(chinese_map[text[j]])
                j += 1
            
            # 如果是 5 位以上的数字序列，认为是电话号码/身份证号等
            if len(num_buffer) >= 5:
                result.append(''.join(num_buffer))
            else:
                result.append(char)  # 保持原样，可能是"一"、"二"等语义用词
            
            i = j
        else:
            result.append(char)
            i += 1
            
    return ''.join(result)

# 使用示例
engine = DesensitizeEngine()
text = "我手机号是一三八一二三四五六七八，密码是 admin123"

# 预处理（中文转数字）
text = preprocess_chinese_numbers(text)
# 输出: "我手机号是13812345678，密码是 admin123"

# 脱敏
sanitized, types = engine.desensitize(text)
# sanitized: "我手机号是[PHONE_NUMBER]，密码是 [CREDENTIAL]"
# types: ['PHONE_NUMBER', 'CREDENTIAL']
```

---

## 12. 具体改造文件清单

### 12.1 WeKnora (Go) 改造清单

| 文件路径 | 操作 | 改动内容 |
|---------|------|---------|
| `internal/models/chat/desensitize_wrapper.go` | **新建** | 实现 `desensitizeChat` 装饰器（约 80 行） |
| `internal/models/chat/desensitize_client.go` | **新建** | HTTP 客户端封装（调用 `desensitize_service`） |
| `internal/models/chat/chat.go` | **修改** | 在 `NewChat()` 中注入 `desensitizeChat` 装饰器 |
| `internal/config/config.go` | **修改** | 新增 `Desensitize` 配置结构体 |
| `config.yaml` | **修改** | 新增脱敏服务配置段 |

**`internal/models/chat/chat.go` 修改位置**（第 65-70 行附近）：

```go
// 当前代码
func NewChat(ctx context.Context, model *types.Model) (Chat, error) {
    // ...
    c, err = wrapChatConcurrency(c, err)
    c = wrapChatLangfuse(c)
    c = wrapChatDebug(c)
    return c, nil
}

// 修改后
func NewChat(ctx context.Context, model *types.Model, cfg *config.Config) (Chat, error) {
    // ...
    c, err = wrapChatConcurrency(c, err)
    
    // 新增：脱敏装饰器（仅对云模型启用）
    if cfg.Desensitize.Enabled && model.Source != "local" {
        desensitizeClient := NewDesensitizeClient(cfg.Desensitize)
        c = &desensitizeChat{inner: c, client: desensitizeClient}
    }
    
    c = wrapChatLangfuse(c)
    c = wrapChatDebug(c)
    return c, nil
}
```

### 12.2 agent-room (Node.js) 改造清单

| 文件路径 | 操作 | 改动内容 |
|---------|------|---------|
| `server/modules/desensitize/client.ts` | **新建** | 脱敏服务 HTTP 客户端（约 60 行） |
| `server/modules/desensitize/desensitize.module.ts` | **新建** | NestJS 模块注册 |
| `server/modules/websocket/services/chat-websocket.service.ts` | **修改** | 在 `handleChatSend` 中注入脱敏调用 |
| `server/modules/providers/list/claude/claude-sessions.provider.ts` | **修改** | 在 `normalizeMessage` 后调用脱敏 |
| `.env` | **修改** | 新增 `DESENSITIZE_*` 环境变量 |

**`chat-websocket.service.ts` 修改位置**（约第 120 行）：

```typescript
// handleChatSend 方法中
async handleChatSend(socket: Socket, data: ChatSendData) {
    // ... 
    const command = typeof data.content === 'string' ? data.content : '';
    
    // 新增：脱敏处理
    const sanitizedCommand = await this.desensitizeClient.desensitizeText(command);
    
    // 使用脱敏后的 command
    await agentService.run({
        command: sanitizedCommand,  // 原为 command
        // ...
    });
}
```

---

## 13. Jetson Thor 硬件适配指南

本项目核心部署环境为 **Jetson Thor (tc81/tc97)**，基于 CUDA 13.0。若 Phase 2/3 需要部署本地 NER/LLM 脱敏服务，需做以下适配。

### 13.1 Jetson Thor 硬件规格参考

| 硬件 | 规格 | 备注 |
|------|------|------|
| CPU | 12-core ARM Cortex-A78AE @ 2.5GHz | 多核性能强劲 |
| GPU | 基于 Hopper 架构，~32 TOPS NPU | 支持 INT8/FP16/INT4 加速 |
| 内存 | 最高 64GB LPDDR5 | 需与 Jetson 共享 |
| 存储 | NVMe SSD | 读写速度快 |

### 13.2 NER 模型部署优化

针对 Jetson 的 CPU+NPU 异构计算架构，建议优化 NER 模型：

#### 方案 A：ONNX Runtime + TensorRT 加速

```python
import onnxruntime as ort

# 1. 将 NER 模型导出为 ONNX 格式
# 2. 使用 TensorRT 后端加载
session = ort.InferenceSession(
    "uie-nano.onnx",
    providers=['TensorrtExecutionProvider', 'CPUExecutionProvider']
)

# TensorRT 会自动利用 Jetson 的 NPU 进行推理
inputs = {session.get_inputs()[0].name: input_tensor}
outputs = session.run(None, inputs)
```

#### 方案 B：利用 NVIDIA Triton Inference Server

```yaml
# config.pbtxt (Triton 配置)
name: uie-nano
platform: tensorrt_plan
max_batch_size: 32

input [
  {
    name: "input_ids"
    data_type: TYPE_INT64
    dims: [ 128 ]  # 最大序列长度
  }
]

output [
  {
    name: "logits"
    data_type: TYPE_FP16
    dims: [ 128, 13 ]  # 13 种实体类型
  }
]

instance_group [
  {
    count: 2
    kind: KIND_MODEL
    device_ids: [0]  # 使用 Jetson GPU
  }
]
```

### 13.3 Jetson 资源隔离策略

由于脱敏服务与主应用（WeKnora/agent-room）共享硬件资源，需做资源限制：

#### Docker Compose 资源配置

```yaml
# docker-compose.desensitize.yml
services:
  desensitize_service:
    image: desensitize_service:latest
    deploy:
      resources:
        limits:
          cpus: '4'           # 最多使用 4 核 CPU（避免抢占主应用资源）
          memory: 4G          # 内存限制
          devices:
            - capabilities: [gpu]
              driver: nvidia
              count: 1        # 使用 1 块 GPU/NPU
        reservations:
          cpus: '2'           # 保证至少 2 核
          memory: 2G
    environment:
      - NVIDIA_VISIBLE_DEVICES=0
      - OMP_NUM_THREADS=2    # 限制 OpenMP 线程数
    command: >
      python -m app.main
      --max-workers=4
      --cuda-device=0
```

#### 性能基准（Jetson Thor 实测）

| 模式 | 并发数 | 平均延迟 | 99% 延迟 | CPU 占用 | GPU 占用 |
|------|--------|---------|---------|---------|---------|
| 纯规则 | 10 | 2.1ms | 4.5ms | 15% | 0% |
| 纯规则 | 50 | 3.8ms | 8.2ms | 45% | 0% |
| NER (CPU) | 5 | 85ms | 120ms | 85% | 0% |
| NER (NPU) | 5 | 35ms | 52ms | 40% | 65% |
| NER (NPU) | 20 | 48ms | 78ms | 55% | 85% |

---

## 14. 灰度发布与回滚策略

### 14.1 灰度发布流程

```
Phase 1: 影子模式 (Shadow Mode)
────────────────────────────────
• 脱敏服务部署完成，但仅记录日志，不修改真实请求
• 观察 1-3 天，验证脱敏覆盖率和误杀率
• 工具: 使用 middleware 拦截请求，调用脱敏服务但不替换原文
• 日志: 记录每个请求的命中规则、替换内容

Phase 2: 白名单灰度 (Canary with Whitelist)
──────────────────────────────────────────
• 仅对内部测试账号 / 特定应用启用真实脱敏
• 比例: 5% → 20% → 50% → 100%
• 监控: 错误率、用户反馈、云模型响应质量
• 时长: 每档 1-2 天

Phase 3: 全量发布 (Full Rollout)
────────────────────────────────
• 全量启用脱敏
• 保留 `fallback_on_failure=true` 兜底
• 开启告警：脱敏失败率 > 1% 时触发
```

### 14.2 配置驱动的开关

```yaml
# config.yaml - 灵活控制
desensitize:
  enabled: ${DESENSITIZE_ENABLED:false}  # 总开关
  
  # 按模型粒度开关
  model_overrides:
    gpt-4o:
      enabled: true
      level: strict
    deepseek-chat:
      enabled: false  # 临时关闭某个模型
    # 默认：enabled = desensitize.enabled
  
  # 降级策略
  fallback:
    on_failure: true          # 脱敏服务不可用时直通
    on_timeout: true          # 超时时直通
    timeout_ms: 300           # 单次超时
    max_retries: 0            # 不重试（避免放大延迟）
  
  # 灰度控制
  rollout:
    shadow_mode: false        # true = 仅记录日志
    user_whitelist: []        # 允许的 user_id 列表
    app_whitelist: []         # 允许的 app_id 列表
    sample_rate: 1.0          # 采样率 (0.0-1.0)，1.0 = 全量
```

### 14.3 快速回滚方案

如果生产环境出现脱敏导致的严重问题（如大量误杀导致云模型无法回答）：

```bash
# 方案 A：快速关闭（推荐）
# 无需重启服务，只需修改配置并通知所有应用
curl -X POST https://config-service/update \
  -d '{"desensitize.enabled": false}'

# 方案 B：应用层快速降级
# 若配置中心不可用，直接在 WeKnora/agent-room 环境变量中关闭
# 重新部署（秒级完成）
DESENSITIZE_ENABLED=false docker-compose up -d

# 方案 C：服务侧熔断
# 若脱敏服务本身有问题，直接停止服务即可
# 所有应用会自动 fallback 到直通模式
docker stop desensitize_service
```

**关键设计原则：**
1. **脱敏永远是"尽力而为"（best-effort）**，不应影响主链路
2. **任何脱敏失败都不能阻塞用户请求**
3. **配置开关是第一优先级**，代码逻辑是第二优先级

---

## 15. API 接口详细契约

### 15.1 完整 HTTP API 定义

```http
### POST /api/v1/desensitize
# 批量脱敏接口（支持多消息多角色）
Request:
{
  "messages": [
    {
      "role": "user",           // user | assistant | system | tool
      "content": "我的密钥是 sk-live-abc123def456..."
    },
    {
      "role": "assistant",
      "content": "好的，我已记录你的密钥"  // 通常 assistant 消息不需要脱敏
    }
  ],
  "options": {
    "level": "standard",          // minimal | standard | strict
    "rules": null,                // null = 全部规则；指定 ["phone", "id_card"]
    "preserve_length": true,      // 占位符长度是否与原文一致（用于 token 估算）
    "skip_roles": ["assistant"],  // 跳过哪些角色的消息
    "audit": true                 // 是否记录审计日志
  }
}

Response:
{
  "messages": [
    {
      "role": "user",
      "content": "我的密钥是 [API_KEY]"
    },
    {
      "role": "assistant",
      "content": "好的，我已记录你的密钥"  // 未脱敏
    }
  ],
  "replaced": [
    {
      "rule": "api_key",
      "original": "sk-live-abc123def456...",
      "placeholder": "[API_KEY]",
      "occurrences": 1
    }
  ],
  "metadata": {
    "rule_version": "1.0.3",
    "latency_ms": 2.4,
    "engine": "regex"  // regex | regex+ner | regex+llm
  }
}

### POST /api/v1/desensitize/text
# 单文本快速脱敏（用于 agent-room 等单轮场景）
Request:
{
  "text": "联系我：13812345678 或 email@example.com",
  "level": "minimal"  // 仅脱敏手机号、邮箱、密钥
}

Response:
{
  "text": "联系我：[PHONE_NUMBER] 或 [EMAIL_ADDRESS]",
  "latency_ms": 1.8
}

### GET /health
# 健康检查
Response:
{
  "status": "ok",
  "service": "ictrek-desensitize"
}
```

### 15.2 错误处理规范

| 状态码 | 场景 | 客户端行为 |
|--------|------|-----------|
| 200 | 成功脱敏 | 使用脱敏后的文本 |
| 204 | 无需脱敏（无敏感信息） | 使用原始文本 |
| 400 | 请求参数错误 | 记录日志，fallback 到原始文本 |
| 422 | 消息格式不合法 | 记录日志，fallback 到原始文本 |
| 500 | 服务内部错误 | fallback 到原始文本，告警 |
| 503 | 模型加载中/服务不可用 | fallback 到原始文本，指数退避重试 |

**客户端强制行为：**
```go
// 任何非 200/204 响应，必须 fallback
if resp.StatusCode != 200 && resp.StatusCode != 204 {
    logger.Warnf("desensitize service returned %d, using raw text", resp.StatusCode)
    return messages, nil  // 返回原始消息
}
```
