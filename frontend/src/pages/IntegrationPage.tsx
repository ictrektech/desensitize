export default function IntegrationPage() {
  return (
    <div>
      <div className="card">
        <div className="card-title">服务信息</div>
        <table>
          <tbody>
            <tr><th>服务 ID</th><td>com.ictrek.desensitize</td></tr>
            <tr><th>API 前缀</th><td>/api/com.ictrek.desensitize</td></tr>
            <tr><th>VOS 网络别名</th><td>desensitize-backend</td></tr>
            <tr><th>容器端口</th><td>5000</td></tr>
          </tbody>
        </table>
      </div>

      <div className="card">
        <div className="card-title">其他应用接入方式</div>

        <div className="integration-section">
          <h3>方式 1: VOS 网络直连（推荐）</h3>
          <p>安装在同一个 VOS 实例中的应用，通过 <code>vos_default</code> Docker 网络直接访问：</p>
          <div className="code-block">{`http://desensitize-backend:5000`}</div>
        </div>

        <div className="integration-section">
          <h3>方式 2: Traefik 网关</h3>
          <p>通过 VOS Traefik 网关访问：</p>
          <div className="code-block">{`http://<VOS_HOST_GW_IP>:<VOS_API_GW_PORT_INTERNAL>/api/com.ictrek.desensitize`}</div>
        </div>

        <div className="integration-section">
          <h3>方式 3: 宿主机端口</h3>
          <p>通过映射的宿主机端口访问（默认 35010）：</p>
          <div className="code-block">{`http://<vos-host>:35010`}</div>
        </div>
      </div>

      <div className="card">
        <div className="card-title">API 接口</div>

        <div className="integration-section">
          <h3>POST /api/v1/desensitize/text — 单文本脱敏</h3>
          <p>适用于 agent-room 等单轮场景</p>
          <div className="code-block">{`POST /api/v1/desensitize/text
Content-Type: application/json

{
  "text": "我的手机号是13812345678",
  "level": "standard"
}

# Response
{
  "text": "我的手机号是[PHONE_NUMBER]",
  "replaced": [
    {"rule": "手机号 (中国)", "placeholder": "[PHONE_NUMBER]", "occurrences": 1}
  ],
  "latency_ms": 1.8
}`}</div>
        </div>

        <div className="integration-section">
          <h3>POST /api/v1/desensitize — 批量消息脱敏</h3>
          <p>适用于 WeKnora 等多轮对话场景，支持跳过特定角色</p>
          <div className="code-block">{`POST /api/v1/desensitize
Content-Type: application/json

{
  "messages": [
    {"role": "user", "content": "我的密钥是 sk-live-abc123def456..."},
    {"role": "assistant", "content": "好的"}
  ],
  "options": {
    "level": "standard",
    "skip_roles": ["assistant"],
    "preserve_length": false
  }
}

# Response
{
  "messages": [
    {"role": "user", "content": "我的密钥是 [API_KEY]"},
    {"role": "assistant", "content": "好的"}
  ],
  "replaced": [
    {"rule": "OpenAI API Key", "placeholder": "[API_KEY]", "occurrences": 1}
  ],
  "metadata": {"latency_ms": 2.4, "engine": "regex", "rule_count": 1}
}`}</div>
        </div>

        <div className="integration-section">
          <h3>GET /api/v1/rules — 列出所有规则</h3>
          <div className="code-block">{`GET /api/v1/rules?enabled_only=true

# Response
[
  {"id": "phone_cn", "name": "手机号 (中国)", "pattern": "...", "placeholder": "[PHONE_NUMBER]", ...},
  {"id": "email", "name": "邮箱地址", "pattern": "...", "placeholder": "[EMAIL_ADDRESS]", ...}
]`}</div>
        </div>

        <div className="integration-section">
          <h3>POST /api/v1/rules — 创建自定义规则</h3>
          <div className="code-block">{`POST /api/v1/rules
Content-Type: application/json

{
  "name": "企业微信 Token",
  "description": "匹配企微 API Token",
  "pattern": "\\\\b(wwapi_[A-Za-z0-9]{20,})\\\\b",
  "placeholder": "[WECOM_TOKEN]",
  "priority": 8,
  "enabled": true,
  "category": "api_key"
}`}</div>
        </div>

        <div className="integration-section">
          <h3>POST /api/v1/rules/test — 测试正则</h3>
          <div className="code-block">{`GET /api/v1/rules/test?pattern=\\\\b1[3-9]\\\\d{9}\\\\b&text=13812345678&placeholder=[PHONE]

# Response
{
  "matched": true,
  "matches": [{"value": "13812345678", "start": 0, "end": 11}],
  "result": "[PHONE]",
  "match_count": 1
}`}</div>
        </div>
      </div>

      <div className="card">
        <div className="card-title">WeKnora 接入示例</div>
        <div className="integration-section">
          <p>在 WeKnora 的 config.yaml 中配置：</p>
          <div className="code-block">{`desensitize:
  enabled: true
  service_url: http://desensitize-backend:5000
  level: standard
  only_cloud_models: true`}</div>
          <p style={{ marginTop: '8px' }}>WeKnora 会在调用云模型前自动脱敏，本地模型（Ollama）不脱敏。</p>
        </div>
      </div>

      <div className="card">
        <div className="card-title">agent-room 接入示例</div>
        <div className="integration-section">
          <p>在 agent-room 的 .env 中配置：</p>
          <div className="code-block">{`DESENSITIZE_SERVICE_URL=http://desensitize-backend:5000
DESENSITIZE_ENABLED=true`}</div>
          <p style={{ marginTop: '8px' }}>在 handleChatSend 中调用：</p>
          <div className="code-block">{`const resp = await fetch(
  \`\${process.env.DESENSITIZE_SERVICE_URL}/api/v1/desensitize/text\`,
  {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text: command }),
  }
);
const { text: sanitizedCommand } = await resp.json();
await spawnFn(sanitizedCommand, runtimeOptions, run.writer);`}</div>
        </div>
      </div>

      <div className="card">
        <div className="card-title">降级策略</div>
        <p style={{ fontSize: '13px' }}>所有客户端应实现降级逻辑：当脱敏服务不可用时，直接使用原始文本，不阻塞用户请求。</p>
        <div className="code-block">{`try {
  const resp = await fetch(desensitizeUrl, ...);
  // 使用脱敏后的文本
} catch (e) {
  // 降级：使用原始文本
  logger.warn('desensitize service unavailable, using raw text');
}`}</div>
      </div>
    </div>
  )
}
