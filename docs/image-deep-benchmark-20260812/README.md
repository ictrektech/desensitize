# 数据脱敏服务图片 OCR 性能测试报告

测试日期：2026-08-12  
测试环境：192.168.1.192（Jetson Orin, ARM64）  
服务版本：desensitize-backend `0.0.35`（l4t profile）  
测试网络：VOS `vos_default` Docker 网络内直连 `desensitize-backend:5000`  
测试对象：图片 OCR 脱敏接口 `/api/v1/desensitize/image`  
对照接口：文本脱敏接口 `/api/v1/desensitize/text`

## 1. 测试环境

| 项目 | 规格 |
| --- | --- |
| 硬件平台 | NVIDIA Jetson Orin（ARM64） |
| CPU | 8 核 ARM Cortex-A78AE，最高 1984MHz |
| GPU | Orin nvgpu |
| 统一内存 | 15,656 MB（CPU + GPU 共享） |
| 操作系统 | Ubuntu ARM64 |
| 后端框架 | FastAPI（Python） |
| VOS App 版本 | `0.0.35` |
| 后端镜像 | `swr.cn-southwest-2.myhuaweicloud.com/ictrek/desensitize-backend:l4t_20260812` |
| 前端镜像 | `swr.cn-southwest-2.myhuaweicloud.com/ictrek/desensitize-frontend:arm_20260812` |
| NER 模型 | `huluxiaohuowa/bert4ner-base-chinese-onnx` |
| NER 模型路径 | `/modelhub/export/ms/huluxiaohuowa/bert4ner-base-chinese-onnx/current` |
| NER Provider | `CUDAExecutionProvider` |
| NER 最大并发 | 4 |
| OCR 模型 | `huluxiaohuowa/rapidocr-ppocrv4-onnx` |
| OCR 模型路径 | `/modelhub/export/ms/huluxiaohuowa/rapidocr-ppocrv4-onnx/current` |
| OCR det Provider | `CUDAExecutionProvider` |
| OCR cls Provider | `CUDAExecutionProvider` |
| OCR rec Provider | `CUDAExecutionProvider` |
| OCR 最大并发 | 4 |
| OCR 队列等待 | 20 秒 |
| 启用规则 | 16 条 |
| 测试客户端 | Python urllib，容器内通过 `vos_default` 网络访问服务 alias |

服务运行信息来自 `/api/v1/system/about`：

```json
{
  "app_version": "0.0.35",
  "profile": "l4t",
  "ner": {
    "state": "ready",
    "active_provider": "CUDAExecutionProvider",
    "max_concurrency": 4
  },
  "image_ocr": {
    "state": "ready",
    "provider": "cuda",
    "active_providers": {
      "det": ["CUDAExecutionProvider", "CPUExecutionProvider"],
      "cls": ["CUDAExecutionProvider", "CPUExecutionProvider"],
      "rec": ["CUDAExecutionProvider", "CPUExecutionProvider"]
    },
    "max_concurrency": 4
  }
}
```

## 2. 测试数据说明

本轮使用 6 张合成图片，覆盖证件、票据、物流、聊天、拍照表单、低对比度配置等常见图片脱敏场景。所有敏感值均为合成数据，不包含真实个人信息。

| 编号 | 文件 | 场景 | 尺寸 | 主要敏感信息 | 图像特点 |
| --- | --- | --- | --- | --- | --- |
| 01 | `01_id_card_like.jpg` | 身份信息采集表 | 1240×780 | 姓名、身份证号、手机号、邮箱、银行卡、地址 | 证件式排版，字段标签清晰 |
| 02 | `02_invoice_dense.jpg` | 发票/票据 | 1500×1060 | 发票号、税号、银行卡、订单号、API Key、手机号 | 密集表格文本 |
| 03 | `03_shipping_label_skew.jpg` | 物流面单 | 1180×900 | 收寄件人、手机号、地址、运单号、订单号、密码 | 轻微旋转，含条码 |
| 04 | `04_chat_screenshot.jpg` | 聊天截图 | 1080×1500 | 手机号、身份证号、API Key、GitHub Token、邮箱、地址 | 多气泡、多行文本 |
| 05 | `05_photo_form_noisy.jpg` | 拍照表单 | 1300×950 | 姓名、手机号、身份证号、银行卡、邮箱、IP、AWS Key | 倾斜、噪声、拍照背景 |
| 06 | `06_low_contrast_config.jpg` | 配置截图 | 1200×620 | API Key、URL token、手机号、邮箱、IP | 低对比度、轻微模糊 |

产物中保留每张原图、规则-only 脱敏图、规则+NER 脱敏图：

| 原图 | 规则-only 输出 | 规则+NER 输出 |
| --- | --- | --- |
| `01_id_card_like.jpg` | `masked_rules_01_id_card_like.jpg` | `masked_hybrid_01_id_card_like.jpg` |
| `02_invoice_dense.jpg` | `masked_rules_02_invoice_dense.jpg` | `masked_hybrid_02_invoice_dense.jpg` |
| `03_shipping_label_skew.jpg` | `masked_rules_03_shipping_label_skew.jpg` | `masked_hybrid_03_shipping_label_skew.jpg` |
| `04_chat_screenshot.jpg` | `masked_rules_04_chat_screenshot.jpg` | `masked_hybrid_04_chat_screenshot.jpg` |
| `05_photo_form_noisy.jpg` | `masked_rules_05_photo_form_noisy.jpg` | `masked_hybrid_05_photo_form_noisy.jpg` |
| `06_low_contrast_config.jpg` | `masked_rules_06_low_contrast_config.jpg` | `masked_hybrid_06_low_contrast_config.jpg` |

说明：05 的规则+NER 输出文件名为 `masked_hybrid_05_photo_form_noisy.jpg`，06 的规则+NER 输出文件名为 `masked_hybrid_06_low_contrast_config.jpg`。

## 3. 测试方法

### 3.1 图片接口请求

```http
POST /api/v1/desensitize/image
```

规则-only 模式：

```json
{
  "image_base64": "<jpeg base64>",
  "mime_type": "image/jpeg",
  "level": "standard",
  "ner": false,
  "return_coordinates": true,
  "max_side": 1800
}
```

规则+NER 模式：

```json
{
  "image_base64": "<jpeg base64>",
  "mime_type": "image/jpeg",
  "level": "standard",
  "ner": true,
  "return_coordinates": true,
  "max_side": 1800
}
```

### 3.2 文本接口基线

```http
POST /api/v1/desensitize/text
```

```json
{
  "text": "<synthetic text>",
  "level": "standard",
  "ner": true
}
```

### 3.3 测试项目

| 项目 | 方法 |
| --- | --- |
| 单请求延迟 | 选取低对比度配置图、物流面单、发票图 3 类样本；每个样本每种模式执行 30 次 |
| 图片吞吐 | 6 张图片混合请求，分别以 1/2/4/8 并发执行 |
| 文本 NER 基线 | 1/2/4/8/16 并发，对照文本接口延迟与吞吐 |
| 持续压力测试 | 4 线程混合图片请求，持续约 25 秒 |
| 资源采样 | 4 并发图片 OCR+规则+NER，使用 `tegrastats --interval 500` 采样 |

## 4. 单请求延迟（无并发，30 次采样）

### 4.1 图片 OCR + 规则（ner=false）

| 样本 | OCR 块 | 平均命中 | 平均遮挡区域 | 平均延迟 | P50 | P95 | P99 | 成功率 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 低对比度配置图 | 4 | 6 | 6 | 398.24ms | 393.06ms | 415.54ms | 552.19ms | 100% |
| 物流面单 | 14 | 6 | 9 | 740.17ms | 735.23ms | 805.99ms | 808.94ms | 100% |
| 发票/票据 | 12 | 13 | 17 | 757.71ms | 728.71ms | 901.09ms | 911.76ms | 100% |

### 4.2 图片 OCR + 规则 + NER（ner=true）

| 样本 | OCR 块 | 平均命中 | 平均遮挡区域 | 平均延迟 | P50 | P95 | P99 | 成功率 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 低对比度配置图 | 4 | 6 | 6 | 414.91ms | 414.94ms | 424.54ms | 427.37ms | 100% |
| 物流面单 | 14 | 13 | 16 | 747.96ms | 745.05ms | 771.75ms | 777.45ms | 100% |
| 发票/票据 | 12 | 17 | 21 | 750.06ms | 744.67ms | 804.21ms | 806.75ms | 100% |

### 4.3 关键发现

- 图片接口单请求延迟主要由 OCR 决定，低对比度小图约 400ms，物流/发票类复杂图约 740~760ms。
- NER 对低对比度配置图无新增命中，因为该图主要是结构化密钥、URL 参数、手机号、邮箱，规则已覆盖。
- NER 对物流面单和发票图有明显增益：物流面单平均命中从 6 增至 13，发票图从 13 增至 17。
- 单请求 30 次采样全部成功，无 4xx/5xx、无 OCR/NER 队列超时。

## 5. 吞吐性能（混合图片并发测试）

### 5.1 图片 OCR + 规则（ner=false）

6 张图片混合请求，每组 12 个请求。

| 并发数 | 请求数 | QPS | 平均延迟 | P50 | P90 | P95 | 最大延迟 | 成功率 | 平均命中 | 平均遮挡区域 |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 12 | 1.361 | 733.95ms | 726.10ms | 1011.07ms | 1014.76ms | 1014.76ms | 100% | 8.83 | 10.33 |
| 2 | 12 | 1.722 | 1115.64ms | 985.33ms | 1508.05ms | 1515.74ms | 1515.74ms | 100% | 8.83 | 10.33 |
| 4 | 12 | 1.596 | 2294.39ms | 2114.32ms | 3209.80ms | 3401.32ms | 3401.32ms | 100% | 8.83 | 10.33 |
| 8 | 12 | 2.026 | 3153.44ms | 2953.88ms | 4358.96ms | 4396.88ms | 4396.88ms | 100% | 8.83 | 10.33 |

### 5.2 图片 OCR + 规则 + NER（ner=true）

6 张图片混合请求，每组 12 个请求。

| 并发数 | 请求数 | QPS | 平均延迟 | P50 | P90 | P95 | 最大延迟 | 成功率 | 平均命中 | 平均遮挡区域 |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 12 | 1.324 | 754.70ms | 747.24ms | 1023.45ms | 1043.78ms | 1043.78ms | 100% | 13.83 | 15.33 |
| 2 | 12 | 1.788 | 1115.44ms | 998.93ms | 1562.26ms | 1614.63ms | 1614.63ms | 100% | 13.83 | 15.33 |
| 4 | 12 | 1.838 | 2029.07ms | 1978.95ms | 2890.24ms | 3053.67ms | 3053.67ms | 100% | 13.83 | 15.33 |
| 8 | 12 | 2.083 | 3072.09ms | 3147.17ms | 3744.89ms | 4170.24ms | 4170.24ms | 100% | 13.83 | 15.33 |

### 5.3 关键发现

- 2 并发开始吞吐进入 `1.7~1.8 QPS` 区间，4 并发规则+NER 达到 `1.838 QPS`。
- 8 并发 QPS 略有提高，但平均延迟超过 3 秒，P95 超过 4 秒，不适合作为默认同步交互并发。
- 规则+NER 相比规则-only 平均命中从 `8.83` 增至 `13.83`，平均遮挡区域从 `10.33` 增至 `15.33`。
- NER 增益主要体现在人名、地址、收寄件人、聊天参与者等语义实体；手机号、身份证、密钥、邮箱等结构化字段主要由规则覆盖。

## 6. 文本 NER+规则基线

本节用于对照图片 OCR 的成本。文本接口不经过 OCR，仅执行规则和 NER。

| 并发数 | 请求数 | QPS | 平均延迟 | P50 | P90 | P95 | 最大延迟 | 成功率 | 平均命中 |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 12 | 47.393 | 20.97ms | 19.82ms | 24.77ms | 29.88ms | 29.88ms | 100% | 4.50 |
| 2 | 24 | 63.759 | 31.16ms | 30.60ms | 33.17ms | 33.31ms | 33.80ms | 100% | 4.50 |
| 4 | 48 | 50.749 | 78.17ms | 79.84ms | 92.89ms | 93.06ms | 95.33ms | 100% | 4.50 |
| 8 | 64 | 48.802 | 157.54ms | 169.12ms | 191.09ms | 197.43ms | 201.52ms | 100% | 4.50 |
| 16 | 64 | 51.756 | 275.09ms | 330.89ms | 360.33ms | 364.15ms | 367.03ms | 100% | 4.50 |

关键发现：

- 文本 NER+规则吞吐约 `50 QPS`，图片 OCR+NER 吞吐约 `2 QPS`，两者不是同一量级。
- 文本接口 4 并发 P95 约 93ms；图片接口 4 并发 P95 约 3 秒。
- 图片接口的主要成本是 OCR 图像检测、方向分类、文本识别和坐标遮挡；NER 在本轮样本中不是主要瓶颈。

## 7. 压力测试（4 线程混合图片，约 25 秒）

### 7.1 吞吐汇总

| 模式 | 线程数 | 测试时长 | 总请求数 | 成功数 | QPS | 平均延迟 | P50 | P95 | P99 | 成功率 | 平均命中 | 平均遮挡区域 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 图片 OCR + 规则 | 4 | 26.72s | 56 | 56 | 2.096 | 1866.04ms | 1785.54ms | 3018.55ms | 3784.48ms | 100% | 8.89 | 10.45 |
| 图片 OCR + 规则 + NER | 4 | 26.52s | 59 | 59 | 2.224 | 1761.55ms | 1784.98ms | 2371.86ms | 3200.52ms | 100% | 13.97 | 15.49 |

### 7.2 硬件资源占用（tegrastats）

资源采样场景：4 并发图片 OCR + 规则 + NER，18 个请求。

| 指标 | 最小值 | 最大值 | 平均值 |
| --- | ---: | ---: | ---: |
| RAM 占用 | 13,661 MB | 13,876 MB | 13,733 MB（87.7%） |
| Swap 占用 | 2,676 MB | 2,676 MB | 2,676 MB |
| GPU 频率 | 0% | 99% | 62.75% |
| GPU 频率 P50 | - | - | 96.5% |

代表性采样：

```text
RAM 13719/15656MB SWAP 2676/7828MB GR3D_FREQ 99%
RAM 13683/15656MB SWAP 2676/7828MB GR3D_FREQ 99%
RAM 13705/15656MB SWAP 2676/7828MB GR3D_FREQ 77%
RAM 13706/15656MB SWAP 2676/7828MB GR3D_FREQ 99%
RAM 13701/15656MB SWAP 2676/7828MB GR3D_FREQ 94%
```

完整采样见 `tegrastats_hybrid_4w.txt`。

### 7.3 关键发现

- 4 线程持续压力测试下，图片 OCR+NER 维持约 `2.2 QPS`，全程 0 失败。
- GPU 频率多次达到 99%，OCR 推理阶段能够有效使用 Jetson GPU。
- RAM 占用较高，平均约 13.7GB，且已有约 2.7GB swap 使用；这是 192 上继续提高图片并发的主要风险。
- 规则+NER 模式没有比规则-only 明显更慢，说明该场景的主瓶颈仍是 OCR，而不是 NER。

## 8. 性能分析

### 8.1 图片 OCR 模式的性能天花板

- 单请求延迟：约 400ms 到 760ms，取决于图片尺寸、OCR 块数量、文本密度和图像质量。
- 持续吞吐：4 线程混合图片约 `2.1~2.2 QPS`。
- 并发上限：当前配置为 OCR 并发 4，8 并发请求会进入排队，吞吐略升但延迟明显变差。
- 主要瓶颈：OCR det/cls/rec 推理 + 图像后处理 + 遮挡绘制。

### 8.2 NER 对图片脱敏的影响

- NER 对结构化密钥类图片帮助有限；手机号、身份证、邮箱、API Key、URL token 等主要由规则覆盖。
- NER 对自然语言图片帮助明显；证件、物流、聊天截图、表单中的姓名和地址能增加遮挡区域。
- 在本轮 6 张图片中，规则+NER 平均命中 `13.83`，规则-only 平均命中 `8.83`，增益约 `56.6%`。

### 8.3 不同场景的推荐配置

| 场景 | 推荐模式 | 推荐并发 | 预期延迟 | 备注 |
| --- | --- | ---: | --- | --- |
| 单张配置截图/低对比度截图 | OCR + 规则 | 1~2 | 400~800ms | 结构化密钥规则已足够 |
| 证件/表单/物流面单 | OCR + 规则 + NER | 1~4 | 0.7~3s | NER 增加姓名、地址遮挡 |
| 批量图片脱敏 | OCR + 规则 + NER | 4 | 秒级 | 建议异步任务队列 |
| 实时聊天文本 | 文本规则+NER | 4 | <100ms | 不经过 OCR |
| 高并发文本网关 | 文本规则-only 或规则+NER | 4~8 | <200ms | 图片接口不适合共用文本接口并发预期 |

## 9. 与设计预期的对比

| 预期 | 实测 | 结论 |
| --- | --- | --- |
| 图片 OCR 能在 l4t 上运行 | 6 类复杂图片全部成功 | 满足 |
| OCR provider 使用 GPU | det/cls/rec 均为 `CUDAExecutionProvider`，GR3D 最高 99% | 满足 |
| 图片接口支持规则脱敏 | 结构化字段稳定命中，规则-only 平均 8.83 命中/请求 | 满足 |
| 图片接口支持 NER 增强 | 规则+NER 平均 13.83 命中/请求 | 满足 |
| 4 并发可用 | 4 并发 OCR+NER 成功率 100%，P95 约 3s | 满足，但延迟为秒级 |
| 高并发稳定性 | 25 秒 4 线程压力测试 0 失败 | 满足 |
| 资源可控 | GPU 可用，但 RAM 平均 13.7GB、swap 2.7GB | 可用但内存压力较高 |

## 10. 已知限制

1. 本轮图片样本为合成图片，不包含真实个人信息；真实拍照图片还需要补充人工标注集验证召回率。
2. OCR 质量受清晰度、倾斜、背景噪声、字体和压缩影响；低质量图片可能依赖兜底遮挡。
3. 物流单号、税号、信用代码等长字母数字串在缺少上下文时可能有类别泛化，需要后续用更多版式样本细化规则。
4. 192 的内存余量有限，图片 OCR+NER 已使用较高 RAM 和 swap，不建议继续提高默认图片并发。
5. 图片同步接口在 4 并发下 P95 约 3 秒，不适合作为高 QPS 网关接口；批量图片建议做异步任务。

## 11. 后续优化建议

| 优化项 | 预期收益 | 复杂度 |
| --- | --- | --- |
| 批量图片异步任务队列 | 避免前端同步等待，提升用户体验 | 中 |
| 图片尺寸自适应策略 | 降低大图 OCR 延迟和内存占用 | 低 |
| 真实版式标注集 | 量化召回率、误遮率和漏遮率 | 中 |
| 税号/订单号上下文约束 | 降低长字母数字串类别泛化 | 低 |
| OCR 结果缓存 | 重复图片或重复测试场景降耗 | 中 |
| OCR 模型 TensorRT/量化评估 | 降低延迟，提高 GPU 利用效率 | 中 |

## 12. 附录

### 12.1 测试产物

- `deep_benchmark.json`：完整接口返回、逐样本、并发矩阵。
- `pdf_style_extra.json`：单请求 30 次采样和 25 秒持续压测结果。
- `resource_probe_hybrid_4w.json`：4 并发 OCR+NER 资源探针请求统计。
- `tegrastats_hybrid_4w.txt`：4 并发 OCR+NER 宿主机资源采样。
- `01_id_card_like.jpg` / `masked_rules_01_id_card_like.jpg` / `masked_hybrid_01_id_card_like.jpg`
- `02_invoice_dense.jpg` / `masked_rules_02_invoice_dense.jpg` / `masked_hybrid_02_invoice_dense.jpg`
- `03_shipping_label_skew.jpg` / `masked_rules_03_shipping_label_skew.jpg` / `masked_hybrid_03_shipping_label_skew.jpg`
- `04_chat_screenshot.jpg` / `masked_rules_04_chat_screenshot.jpg` / `masked_hybrid_04_chat_screenshot.jpg`
- `05_photo_form_noisy.jpg` / `masked_rules_05_photo_form_noisy.jpg` / `masked_hybrid_05_photo_form_noisy.jpg`
- `06_low_contrast_config.jpg` / `masked_rules_06_low_contrast_config.jpg` / `masked_hybrid_06_low_contrast_config.jpg`

### 12.2 测试数据口径

- “平均延迟”使用客户端 wall time，包含 HTTP 请求、FastAPI 调度、OCR/NER/规则处理和响应序列化。
- “API 平均延迟”来自服务端响应中的 `latency_ms`。
- “命中”统计响应中的 `replaced` 条目数。
- “遮挡区域”统计响应中的 `coordinates` 数量。
- “OCR 块”统计响应 metadata 中的 `ocr_blocks`。
- “QPS”按测试脚本实测总请求数 / 实际持续时间计算。
