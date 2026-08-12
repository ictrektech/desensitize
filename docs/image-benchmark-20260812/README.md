# 图片脱敏压测报告（tc192 / L4T / VOS）

测试日期：2026-08-12  
测试机器：tc192  
测试网络：VOS `vos_default` Docker 网络  
测试对象：`com.ictrek.desensitize` 图片 OCR 脱敏接口  
接口：`POST /api/v1/desensitize/image`

## 1. 测试结论

1. 功能正确性：图片接口在 1/2/4/8 并发下请求全部成功，合成样例中的手机号、身份证号、API Key、票据字段等均能产生遮挡结果。
2. 性能表现：tc192 上图片 OCR 同步接口吞吐上限约 `1.3 ~ 1.5 RPS`；2 并发后吞吐基本不再提升，4/8 并发主要增加排队延迟。
3. 原始压测 GPU 结论：已发布版本 `0.0.34` 的图片 OCR 显示配置为 `cuda`，但 `tegrastats` 中 `GR3D_FREQ` 始终为 `0%`，实际表现为 CPU 满载。
4. 根因：L4T 镜像内安装的是 JetPack/L4T 专用 ONNXRuntime GPU wheel，`onnxruntime.get_available_providers()` 包含 `CUDAExecutionProvider`；问题不在 wheel 缺失，而在 RapidOCR 初始化参数。代码传入了 `providers=[...]`，但 `rapidocr_onnxruntime` 实际识别的是 `det_use_cuda / rec_use_cuda / cls_use_cuda`，导致 det/cls/rec 三个 session 没有按预期启用 CUDA。
5. 修复验证：修复后在 tc192 已安装后端容器内用同一模型初始化 RapidOCR，det/cls/rec 三个 session 均为 `CUDAExecutionProvider`，并且图片推理期间 `GR3D_FREQ` 最高观测到 `99%`。

## 2. 被测环境

| 项目 | 值 |
| --- | --- |
| VOS App 版本 | `0.0.34` |
| Profile | `l4t` |
| 前端镜像 | `swr.cn-southwest-2.myhuaweicloud.com/ictrek/desensitize-frontend:arm_20260812` |
| 后端镜像 | `swr.cn-southwest-2.myhuaweicloud.com/ictrek/desensitize-backend:l4t_20260812` |
| 服务别名 | `desensitize-backend` |
| 服务端口 | `5000` |
| OCR 模型 | `huluxiaohuowa/rapidocr-ppocrv4-onnx` |
| OCR 模型目录 | `/modelhub/export/ms/huluxiaohuowa/rapidocr-ppocrv4-onnx/current` |
| OCR 发布配置 | `provider=cuda` |
| OCR 并发配置 | `2` |
| OCR 队列超时 | `20s` |
| NER 状态 | `ready / CUDAExecutionProvider` |
| 启用规则数 | `16` |

容器内 ONNXRuntime 检查：

```text
onnxruntime version: 1.23.0
available providers: ['TensorrtExecutionProvider', 'CUDAExecutionProvider', 'CPUExecutionProvider']
```

## 3. 测试样本

本轮使用 3 张在 tc192 压测脚本中生成的合成 JPEG。样本不是外部真实证件或真实隐私图片，避免引入真实个人信息。

| 样本 | 原图 | 脱敏结果 | 用途 |
| --- | --- | --- | --- |
| 普通卡片 | `plain_card.jpg` | `masked_plain_card.jpg` | 手机号、身份证号、API Key 混合文本 |
| 密集票据 | `dense_receipt.jpg` | `masked_dense_receipt.jpg` | 票据/订单/金额类密集文本 |
| 拍照风格表单 | `photo_like_form.jpg` | `masked_photo_like_form.jpg` | 模拟拍照倾斜、背景噪声和字段标签 |

## 4. 请求参数

压测请求直接在 `vos_default` 网络内访问后端 alias，避免外部网关影响结果。

```json
{
  "image_base64": "<base64 jpeg>",
  "mime_type": "image/jpeg",
  "level": "standard",
  "ner": false,
  "return_coordinates": true,
  "max_side": 1600
}
```

说明：

- 未启用 `ner`，本轮只测图片 OCR + 规则遮挡。
- 未传 `rules` 字段，使用服务端当前启用规则集合。
- `return_coordinates=true` 用于验证遮挡区域数量和坐标返回。
- 每个样本先预热 1 次，再进入并发压测。

## 5. 压测结果

| 并发 | 请求数 | 成功 | 错误数 | 吞吐 RPS | 平均耗时 ms | P50 ms | P95 ms | Max ms | API 平均 ms | 平均命中 | 平均 OCR 块 |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 6 | 6 | 0 | 1.074 | 929.35 | 804.55 | 1473.20 | 1473.20 | 919.02 | 3.67 | 4.67 |
| 2 | 12 | 12 | 0 | 1.401 | 1404.18 | 1376.52 | 1851.35 | 1851.35 | 1388.47 | 3.67 | 4.67 |
| 4 | 24 | 24 | 0 | 1.411 | 2707.00 | 2809.03 | 3738.46 | 3773.33 | 2684.73 | 3.67 | 4.67 |
| 8 | 48 | 48 | 0 | 1.328 | 5711.69 | 6017.80 | 7519.93 | 7800.17 | 5692.18 | 3.67 | 4.67 |

8 并发短压测复测：

| 并发 | 请求数 | 成功 | 错误数 | 吞吐 RPS | 平均耗时 ms | P50 ms | Max ms | API 平均 ms | 平均命中 | 平均 OCR 块 |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 8 | 24 | 24 | 0 | 1.492 | 4624.56 | 5160.78 | 5856.48 | 4605.65 | 3.33 | 4.67 |

## 6. 性能解读

### 6.1 吞吐

从 1 并发到 2 并发，吞吐从 `1.074 RPS` 提升到 `1.401 RPS`。继续提升到 4/8 并发后，吞吐没有继续增加，说明 tc192 上 OCR 已达到当前链路上限。

### 6.2 延迟

| 并发 | P50 变化 | 说明 |
| ---: | --- | --- |
| 1 | `804.55ms` | 单请求可用，但首轮/复杂图会接近 1.5s |
| 2 | `1376.52ms` | 接近 OCR 并发上限，仍可接受 |
| 4 | `2809.03ms` | 开始明显排队 |
| 8 | `6017.80ms` | 同步接口等待感明显，不适合作为默认交互并发 |

### 6.3 正确性

本轮所有请求均返回 200，且平均命中数稳定在 `3.33 ~ 3.67`。这说明 OCR block 重建 + 规则匹配链路在这 3 类样本上是稳定的。

## 7. GPU 诊断

### 7.1 已发布版本压测采样

原始 8 并发压测期间，宿主机 `tegrastats` 显示 CPU 多核接近满载，但 `GR3D_FREQ` 始终为 `0%`。

```text
CPU [94%@1984,90%@1984,95%@1984,90%@1984,99%@1984,96%@1984,96%@1984,94%@1984] GR3D_FREQ 0%
CPU [95%@1984,93%@1984,97%@1984,97%@1984,100%@1984,96%@1984,96%@1984,90%@1984] GR3D_FREQ 0%
CPU [94%@1984,93%@1984,92%@1984,93%@1984,97%@1984,91%@1984,94%@1984,98%@1984] GR3D_FREQ 0%
```

完整记录：`tegrastats_during_8w.txt`

### 7.2 ORT GPU wheel 检查

在 tc192 已安装后端容器内检查：

```text
onnxruntime version: 1.23.0
available providers: ['TensorrtExecutionProvider', 'CUDAExecutionProvider', 'CPUExecutionProvider']
```

这证明 l4t 镜像内不是 CPU-only ONNXRuntime。

### 7.3 RapidOCR 参数根因

`rapidocr_onnxruntime` 的 `RapidOCR(config_path=None, **kwargs)` 不通过 `providers` 参数设置 det/cls/rec session。它内部使用以下参数控制 CUDA：

```python
det_use_cuda=True
rec_use_cuda=True
cls_use_cuda=True
```

修复前代码传入的是：

```python
RapidOCR(
    providers=["CUDAExecutionProvider", "CPUExecutionProvider"],
    det_model_path=...,
    rec_model_path=...,
    cls_model_path=...,
)
```

这个参数没有真正落到 RapidOCR 的 det/cls/rec session，因此配置显示 `cuda`，实际推理仍可能走 CPU。

### 7.4 修复后 provider 验证

修复后在已安装后端容器内用同一模型初始化 RapidOCR：

```json
{
  "provider": "cuda",
  "active_providers": {
    "det": ["CUDAExecutionProvider", "CPUExecutionProvider"],
    "cls": ["CUDAExecutionProvider", "CPUExecutionProvider"],
    "rec": ["CUDAExecutionProvider", "CPUExecutionProvider"]
  },
  "state": "ready"
}
```

### 7.5 修复后 GPU 采样

使用修复源码在已安装后端容器内连续执行 12 次 OCR 推理，宿主机 `tegrastats` 观测到 GPU 负载：

```text
GR3D_FREQ 8%
GR3D_FREQ 12%
GR3D_FREQ 99%
GR3D_FREQ 60%
GR3D_FREQ 33%
GR3D_FREQ 66%
```

完整记录：`tegrastats_patched_cuda_probe.txt`

## 8. 修复范围

本次问题是通用 OCR wrapper 的初始化参数错误，不是单个 profile 的 Dockerfile 错误。因此影响范围为所有使用 `rapidocr_onnxruntime` 的 CUDA profile：

| Profile | 是否受影响 | 说明 |
| --- | --- | --- |
| `l4t` | 是 | 已在 tc192 复现并验证修复 |
| `arm-cuda` | 是 | 使用同一 OCR wrapper |
| `thor` | 是 | 使用同一 OCR wrapper |
| `amd-cuda` | 是 | 使用同一 OCR wrapper |
| CPU profiles | 不受 CUDA fallback 影响 | 仍使用同一 wrapper，但 provider 本来就是 CPU |

修复内容：

- CUDA OCR 初始化改为传入 `det_use_cuda=True / rec_use_cuda=True / cls_use_cuda=True`。
- CPU OCR 初始化显式传入 `det_use_cuda=False / rec_use_cuda=False / cls_use_cuda=False`。
- `/about` 和模型信息中新增 OCR `active_providers`，显示 det/cls/rec 三个 session 的真实 provider。
- 当配置要求 `provider=cuda` 但 det/cls/rec 没有全部使用 `CUDAExecutionProvider` 时，初始化直接失败并暴露错误，不再显示为 ready。

## 9. 建议

1. tc192 上即使修复 CUDA，图片 OCR 仍不适合高并发同步调用；默认 OCR 并发建议维持 `1~2`。
2. 如果需要批量图片脱敏，应提供异步任务接口和进度查询，不建议前端或调用方直接堆 8 个同步请求。
3. 后续构建所有 CUDA profile 后，都应在目标机器检查 `/about.image_ocr.active_providers`，不能只看 `provider=cuda`。
4. 压测报告应同时保存原图、脱敏图、JSON 结果和资源采样，避免只凭 UI 状态判断是否真的启用 GPU。

## 10. 产物清单

- `README.md`：本报告。
- `image_benchmark.json`：完整并发压测结果。
- `image_benchmark_8w_short.json`：8 并发短压测结果。
- `tegrastats_during_8w.txt`：已发布版本 8 并发资源采样。
- `tegrastats_patched_cuda_probe.txt`：修复源码 GPU 探针采样。
- `plain_card.jpg` / `masked_plain_card.jpg`
- `dense_receipt.jpg` / `masked_dense_receipt.jpg`
- `photo_like_form.jpg` / `masked_photo_like_form.jpg`

