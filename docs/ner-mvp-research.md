# Desensitize：NER 最小可行扩展调研与建议

> 调研日期：2026-07-30。目标是为当前规则脱敏服务增加**可选的语义识别路径**，而不是替换已有正则规则。模型已导出、发布为 ModelScope `huluxiaohuowa/bert4ner-base-chinese-onnx`，运行时由 Model Hub 管理并挂载。

## 结论

推荐实施一个**ONNX Runtime 驱动、请求显式开启的中文 PII NER 扩展**：

```text
输入
  ├─ 规则引擎（始终执行，识别结构化 PII / 密钥）
  └─ 可选 NER 引擎（仅 hybrid 模式，识别姓名与自然语言地点/地址）
          ↓
       合并不重叠区间，统一替换与命中记录
```

首个实施候选是
[`shibing624/bert4ner-base-chinese`](https://huggingface.co/shibing624/bert4ner-base-chinese)。它是 Apache-2.0 的约 0.1B 中文 BERT token-classification 模型，公开模型文件约 **407 MB**，标签只有 `PER`、`LOC`、`ORG`、`TIME`。这正好与当前规则分工：规则继续覆盖手机号、邮箱、身份证、银行卡、密钥等结构化敏感数据；NER 只补充**自然语言中的人名和地址/地点**。

该模型的官方项目说明它以人民日报中文数据训练，公布的 CNER、PEOPLE 与 MSRA-NER 评测为 94.98、95.25、94.65（不同测试集的 F1，不能直接等同于本服务的 PII 召回）。它是标准 `AutoModelForTokenClassification` 模型，没有自定义算子；可由 Optimum 导出 ONNX，并通过 ONNX Runtime 运行。首版仍应把它作为**额外召回层**：`ORG` 与 `TIME` 默认不掩码，避免把普通业务语义过度删除。

## 为什么是 ONNX CPU 路径

- 当前 VOS 已有 AMD64、ARM64/L4T 两种通用发布路径。ONNX Runtime 官方 Python 安装文档明确将 `onnxruntime` CPU 包列为 Arm CPU 的推荐选择，且发布表列出 Linux x64 与 ARM64 CPU 支持；因此同一份模型可以进入两个镜像，不需要首先拆出 CUDA / L4T / PyTorch 专用 profile。
- Hugging Face 的 Optimum 官方文档支持把 Transformers 模型导出为 ONNX，并以 `ORTModelForTokenClassification` / ONNX Runtime 管线加载；这意味着后续若替换或微调模型，不必改动 HTTP API 和服务调度层。
- MVP 不需要 GPU：先统一 CPU，才符合“多路服务、资源可控”的目标。是否为 AMD CUDA 或 L4T 加速，应以同一基准文本在 tc232/tc192 的实测数据决定，而不是预先让包和镜像矩阵膨胀。

## 候选比较

| 候选 | 能识别的相关类别 | 许可证/供应链 | 资源与部署 | 决定 |
| --- | --- | --- | --- | --- |
| `shibing624/bert4ner-base-chinese` | 人名、地点、组织、时间；首版只使用人名/地点 | Apache-2.0；模型卡与官方项目均给出标准 Transformers 用法 | 标准约 0.1B BERT；权重约 407 MB；一次性导出 ONNX 后 CPU 可跨 AMD64/ARM64 | **推荐 MVP** |
| `protectai/gyr66-bert-base-chinese-finetuned-ner-onnx` | 姓名、地址、手机号、邮箱、QQ、微信号；另有组织、公司等非默认掩码标签 | 模型卡标记 Apache-2.0；但它是对第三方 checkpoint 的转换，发布前必须完成上游模型与训练数据许可证复核 | 已有 ONNX；`model.onnx` 约 407 MB；CPU 可跨 AMD64/ARM64 | 后续候选，不作为首发 |
| `gyr66/bert-base-chinese-finetuned-ner` | 同上 | 模型卡未声明许可证；训练集为 `gyr66/privacy_detection` | PyTorch checkpoint，需自行导出或使用上行 ONNX 转换 | 不直接随产品发布 |
| `ckiplab/albert-tiny-chinese-ner` | 中文 NER，体积较小 | GPL-3.0 | 虽小，但许可证不适合作为本服务默认内嵌模型 | 排除 |
| [`openai/privacy-filter`](https://huggingface.co/openai/privacy-filter) | 8 类 PII（姓名、地址、邮箱、电话、账户、URL、日期、secret） | Apache-2.0 | 1.5B 总参数；模型卡称主要面向英语并提示非英语/非拉丁文本性能可能下降 | 不作为中文 MVP；可作为后续多语方案对照 |

## MVP 的功能边界

### 对外 API

不新增第二个服务，也不改变现有规则调用。扩展 `POST /api/v1/desensitize/text` 的请求选项即可：

```json
{
  "text": "张三住在北京市海淀区，邮箱是zhang@example.com",
  "ner": true
}
```

- `ner: false`（默认）：维持原有规则行为和延迟。
- `ner: true`：先规则、后 NER；NER 只补充规则没有覆盖的区间。
- 不提供 NER-only 模式。密钥、身份证、银行卡、IP、URL 参数等强结构化数据必须继续由规则覆盖，不能绕开。

NER 返回值仍应转换为既有命中记录结构。建议初始映射：

| NER 标签 | 占位符 |
| --- | --- |
| `PER` | `[PERSON_NAME]` |
| `LOC` | `[ADDRESS]` |

`ORG`、`TIME` 不应默认脱敏；它们是否属于敏感信息取决于产品政策，避免把普通业务文本过度删除。手机号、邮箱、身份证、银行卡、Token 等仍由现有规则输出既有占位符。

### 服务内部

1. 新建 `NerEngine`，仅负责分段、tokenize、ONNX 推理、BIO 合并和坐标映射。
2. `DesensitizeEngine` 保持规则为第一阶段；NER 只能处理规则未占用的字符区间。
3. 模型由 Model Hub 下载、校验和原子导出；服务启动后经 VOS alias `model-hub-backend:5005` 查询模型状态，不存在时调用 Model Hub 的 pull API。该后台流程不阻塞规则服务启动；NER 请求在下载期间返回“模型下载中，请稍后”。服务只读挂载整个 `${MODEL_HUB_SHARED_MODELS_PATH:-/data/vos_workspace/model_hub}` 到 `/modelhub`，读取 `/modelhub/export/ms/huluxiaohuowa/bert4ner-base-chinese-onnx/current`。镜像不包含权重，也禁止运行时联网下载。
4. 单请求按 tokenizer 的 512 token 上限切块，并保留重叠窗口；合并时以原始字符串字符坐标去重。
5. 模型加载失败时：`rules` 请求正常完成；`hybrid` 返回明确的 `ner_unavailable` 状态，**不得假装已做语义脱敏**。

## 实施顺序（仅 Desensitize）

1. **生成并固定推理资产**：用 Optimum 将 `shibing624/bert4ner-base-chinese` 导出为 ONNX，验证导出输出；固定模型、tokenizer、ONNX 的 revision/SHA256。导出应在受控构建环境完成，运行时不联网下载。
2. **实现可插拔 NER 引擎**：新增 `onnxruntime`、tokenizer、`NerEngine` 和 `mode=rules|hybrid`，默认仍为 `rules`；MVP 只处理 `PER`、`LOC`。
3. **建立小型黄金集**：至少覆盖中文姓名、地址、邮箱、手机号、QQ/微信号，以及“不应脱敏”的公司/产品名。每例断言输出和命中类别；这不是要求大量业务数据，而是防止规则/NER 合并回归。
4. **双端实测**：同一镜像分别在 tc232 AMD 与 tc192 L4T 上检查模型加载、输出一致性、内存峰值和 P50/P95；之后才决定是否保留 CPU-only 或增加加速 profile。
5. **再纳入发布流程**：按 VOS profile 构建运行时镜像；CPU 使用 `onnxruntime`，CUDA profile 使用匹配平台的 GPU ORT。模型始终由 Model Hub 单独管理。

## 明确不做的事

- 不用远程云端 NER：脱敏文本本身不能为了识别而再次外发。
- 不先引入 vLLM、Ollama 或大语言模型：这会创造新的多架构运行时与资源治理问题，且不适合首个确定性 PII 扩展。
- 不把 NER 的结果覆盖规则结果，也不允许 `ner` 单独模式绕过规则。
- 不因 NER 修改 VOS、其他应用或调用方；本计划仅扩展 `apps/desensitize`。

## 官方与模型来源

- [Shibing624 中文 BERT NER 模型卡](https://huggingface.co/shibing624/bert4ner-base-chinese)（Apache-2.0、`PER/LOC/ORG/TIME` 标签与标准 Transformers 调用）
- [Nerpy 官方项目](https://github.com/shibing624/nerpy)（Apache-2.0、训练数据、复现与模型用法）
- [ProtectAI ONNX 中文 PII NER 模型卡](https://huggingface.co/protectai/gyr66-bert-base-chinese-finetuned-ner-onnx)（后续候选；ONNX、Apache-2.0、上游来源）
- [上游中文隐私 NER 模型卡](https://huggingface.co/gyr66/bert-base-chinese-finetuned-ner)（训练数据与自述评估指标；许可证尚需复核）
- [Hugging Face Token Classification 官方指南](https://huggingface.co/docs/transformers/tasks/token_classification)（NER / token classification 的标准推理语义）
- [Hugging Face Optimum ONNX 导出指南](https://huggingface.co/docs/optimum/exporters/onnx/usage_guides/export_a_model)（导出、验证与 ONNX Runtime 加载）
- [Hugging Face Optimum ONNX Runtime 推理指南](https://huggingface.co/docs/optimum/onnxruntime/usage_guides/models)（`ORTModelForTokenClassification` 与管线加载）
- [ONNX Runtime Python 安装与平台支持](https://onnxruntime.ai/docs/get-started/with-python.html)（Linux x64/ARM64 CPU 与 GPU 包）
- [CKIP ALBERT Tiny 中文 NER 模型卡](https://huggingface.co/ckiplab/albert-tiny-chinese-ner)（GPL-3.0，排除依据）
- [OpenAI Privacy Filter 模型卡](https://huggingface.co/openai/privacy-filter)（Apache-2.0、1.5B、语言限制与 PII 类别，对照候选）
