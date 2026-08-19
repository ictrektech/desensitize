export default function IntegrationPage() {
  return (
    <div>
      <div className="card">
        <div className="card-title">服务信息</div>
        <table>
          <tbody>
            <tr><th>服务 ID</th><td>com.ictrek.desensitize</td></tr>
            <tr><th>VOS 网关前缀</th><td>/api/com.ictrek.desensitize</td></tr>
            <tr><th>后端网络别名</th><td>desensitize-backend:5000</td></tr>
            <tr><th>容器端口</th><td>5000</td></tr>
          </tbody>
        </table>
      </div>

      <div className="card">
        <div className="card-title">其他应用接入方式</div>

        <div className="integration-section">
          <h3>方式 1: VOS 网络直连（推荐）</h3>
          <p>调用方必须也加入外部 <code>vos_default</code> 网络；使用固定 alias，不要依赖容器 IP：</p>
          <div className="code-block">{`BASE_URL=http://desensitize-backend:5000
POST $BASE_URL/api/v1/desensitize/text`}</div>
        </div>

        <div className="integration-section">
          <h3>方式 2: Traefik 网关</h3>
          <p>适用于已由 VOS 注入网关环境变量的应用。网关会移除应用前缀，再转发到后端：</p>
          <div className="code-block">{`BASE_URL=http://\${VOS_HOST_GW_IP}:\${VOS_API_GW_PORT_INTERNAL}/api/com.ictrek.desensitize
POST $BASE_URL/api/v1/desensitize/text`}</div>
        </div>

      </div>

      <div className="card">
        <div className="card-title">模型依赖</div>
        <p>NER 与图片 OCR 模型都不随脱敏镜像发布。启动后后端会通过 VOS alias <code>model-hub-backend:5005</code> 查询并自动请求 Model Hub 下载 ModelScope 模型；安装参数中的 Model Hub 共享目录默认是 <code>/data/vos_workspace/model_hub</code>，后端会将该总目录只读挂载为 <code>/modelhub</code>。</p>
        <div className="code-block">{`容器内模型路径：
/modelhub/export/ms/huluxiaohuowa/bert4ner-base-chinese-onnx/current
/modelhub/export/ms/huluxiaohuowa/rapidocr-ppocrv4-onnx/current

模型下载中：
- 文本纯规则 API 完全可用；
- ner=true 请求会返回 503：“模型下载中，请稍后”；
- 图片接口会返回 503：“图片 OCR 模型下载中，请稍后”。`}</div>
      </div>

      <div className="card">
        <div className="card-title">API 接口</div>

        <div className="integration-section">
          <h3>POST /api/v1/desensitize/text — 单文本脱敏</h3>
          <p>将所选方式的 <code>BASE_URL</code> 与此相对路径拼接。适用于任意单文本调用。</p>
          <div className="code-block">{`POST /api/v1/desensitize/text
Content-Type: application/json

{
  "text": "我的手机号是13812345678",
  "level": "standard",
  "ner": true
}

# Response
{
  "text": "我的手机号是[PHONE_NUMBER]",
  "replaced": [
    {"rule": "手机号 (中国)", "placeholder": "[PHONE_NUMBER]", "occurrences": 1}
  ],
  "latency_ms": 1.8
}`}</div>
          <p><code>ner</code> 默认为 <code>false</code>，保持历史纯规则行为；设为 <code>true</code> 后，在规则脱敏之后额外识别人名和地址。</p>
        </div>

        <div className="integration-section">
          <h3>POST /api/v1/desensitize — 批量消息脱敏</h3>
          <p>适用于调用方自己维护的多轮消息，支持跳过特定角色。</p>
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
    "preserve_length": false,
    "ner": true
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
          <h3>POST /api/v1/desensitize/image — 图片脱敏</h3>
          <p>图片接口不改变文本接口。该接口只接收 JSON base64 图片，不接收 multipart/form-data 文件上传；误用文件表单会返回 415。后端会先 OCR，再重建连续文本并执行多空间规则匹配：原文本、去空白紧凑文本、以及带校验门控的混淆归一化文本，避免手机号、身份证号、密钥被 OCR 拆成多个文本框或把 0/1 等字符识别成 O/l 后漏检；同时会识别身份证、发票、物流面单等图片中的字段标签，并遮挡同一行或右侧相邻的字段值。</p>
          <div className="code-block">{`POST /api/v1/desensitize/image
Content-Type: application/json

{
  "image_base64": "<base64 或 data:image/...;base64,...>",
  "mime_type": "image/jpeg",
  "level": "standard",
  "ner": false,
  "adaptive": true,
  "reversible": false,
  "ledger_key": "<可选：64 位 hex 密钥，仅 reversible=true 时需要>",
  "return_coordinates": true,
  "max_side": 1600
}

# Response
{
  "image_base64": "<masked-image-base64>",
  "mime_type": "image/jpeg",
  "replaced": [
    {"rule": "手机号 (中国)", "placeholder": "[PHONE_NUMBER]", "occurrences": 1}
  ],
  "metadata": {"ocr_engine": "rapidocr", "ocr_blocks": 12, "normalized_matching": true},
  "latency_ms": 320.5,
  "coordinates": [
    {"box": {"x1": 10, "y1": 20, "x2": 180, "y2": 48}, "quad": [[10,20],[180,20],[180,48],[10,48]]}
  ]
}`}</div>
          <p><code>adaptive=true</code> 会按 OCR 关键词识别身份证、发票、物流面单、配置截图等场景，并选择对应规则与兜底策略；信号不足时回退到全量规则。<code>reversible=true</code> 会返回加密 <code>ledger</code>，用于审计场景下还原被遮挡区域。tc192/L4T 等弱性能环境建议保持默认：<code>max_side=1600</code>、OCR 并发 <code>1</code>。需要人名/地址语义遮挡时再传 <code>ner=true</code>。</p>
        </div>

        <div className="integration-section">
          <h3>POST /api/v1/desensitize/image/restore — 可逆图片还原</h3>
          <p>仅当图片脱敏请求设置 <code>reversible=true</code> 且保存了响应中的 <code>ledger</code> 时可用。服务不会保存 ledger 或密钥，调用方必须自行保存并保护密钥。</p>
          <div className="code-block">{`POST /api/v1/desensitize/image/restore
Content-Type: application/json

{
  "image_base64": "<已脱敏图片 base64>",
  "ledger": "<脱敏响应返回的 ledger 对象>",
  "ledger_key": "<64 位 hex 密钥>",
  "mime_type": "image/png"
}

# Response
{
  "image_base64": "<restored-image-base64>",
  "mime_type": "image/png",
  "report": [{"index": 0, "restored": true}],
  "restored_count": 1
}`}</div>
          <p>还原接口默认输出 <code>image/png</code>，避免 JPEG 重新压缩破坏贴回像素。单个区域解密失败只记录在 <code>report</code> 中，不中断其余区域还原。</p>
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
  "pattern": "(?<![A-Za-z0-9])(wwapi_[A-Za-z0-9]{20,})(?![A-Za-z0-9])",
  "placeholder": "[WECOM_TOKEN]",
  "priority": 8,
  "enabled": true,
  "category": "api_key"
}`}</div>
        </div>

        <div className="integration-section">
          <h3>POST /api/v1/rules/test — 测试正则</h3>
          <div className="code-block">{`curl -X POST -G "$BASE_URL/api/v1/rules/test" \\
  --data-urlencode 'pattern=(?<!\\d)(1[3-9]\\d{9})(?!\\d)' \\
  --data-urlencode 'text=我的手机号是13812345678' \\
  --data-urlencode 'placeholder=[PHONE]'

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
        <div className="card-title">接入方实现要求</div>
        <div className="integration-section">
          <p>WeKnora、agent-room 等应用目前需要自行接入；仅设置环境变量或 config.yaml 不会自动启用脱敏。</p>
          <div className="code-block">{`const response = await fetch(
  \`\${baseUrl}/api/v1/desensitize/text\`,
  {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text: outboundText }),
  },
);
if (!response.ok) throw new Error('desensitize request failed');
const { text: sanitizedText } = await response.json();
// Only send sanitizedText to the cloud model.`}</div>
        </div>
      </div>

      <div className="card">
        <div className="card-title">接入校验</div>
        <div className="integration-section">
          <p>接入完成后，先调用规则列表和健康检查，再用包含手机号、身份证、密钥的测试文本确认命中数。</p>
          <div className="code-block">{`GET  $BASE_URL/health
GET  $BASE_URL/api/v1/rules?enabled_only=true
POST $BASE_URL/api/v1/desensitize/text

预期：内置规则数为 13；测试文本中的手机号、身份证、sk-live 密钥均被替换。`}</div>
        </div>
      </div>

      <div className="card">
        <div className="card-title">降级策略</div>
        <p style={{ fontSize: '13px' }}>调用云模型时建议默认阻断并告警；只有经明确风险评估的本地或可信处理链路，才可使用原始文本降级。</p>
        <div className="code-block">{`try {
  const resp = await fetch(desensitizeUrl, ...);
  // 使用脱敏后的文本
} catch (e) {
  // 默认阻断云端调用，避免敏感原文外发
  logger.error('desensitize service unavailable; cloud request blocked', e);
  throw new Error('desensitize service unavailable');
}`}</div>
      </div>
    </div>
  )
}
