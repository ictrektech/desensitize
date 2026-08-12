# 图片脱敏压测报告（tc192 / VOS）

测试时间：2026-08-12  
测试位置：tc192，VOS `vos_default` Docker 网络内  
测试接口：`POST /api/v1/desensitize/image`

## 环境

| 项目 | 值 |
| --- | --- |
| VOS App 版本 | `0.0.34` |
| Profile | `l4t` |
| 前端镜像 | `swr.cn-southwest-2.myhuaweicloud.com/ictrek/desensitize-frontend:arm_20260812` |
| 后端镜像 | `swr.cn-southwest-2.myhuaweicloud.com/ictrek/desensitize-backend:l4t_20260812` |
| OCR 模型 | `huluxiaohuowa/rapidocr-ppocrv4-onnx` |
| OCR 状态 | `ready / enabled / cuda` |
| OCR 并发配置 | `2`，排队超时 `20s` |
| NER 状态 | `ready / CUDAExecutionProvider` |
| 规则数 | 启用规则 `16` 条 |

## 方法

- 在 tc192 上生成 3 张合成 JPEG 测试图：普通卡片、密集票据、拍照风格表单。
- 在 `vos_default` 网络内直接请求 `desensitize-backend:5000`，避免经过外部网关。
- 请求参数使用规则脱敏，未启用 NER：
  - `level=standard`
  - `ner=false`
  - `return_coordinates=true`
  - `max_side=1600`
- 每张图片先预热 1 次，再分别按 1、2、4、8 并发压测。
- 额外在 8 并发短压测期间从宿主机采集 `tegrastats`。

## 结果

| 并发 | 请求数 | 成功 | 吞吐 RPS | 平均耗时 ms | P50 ms | P95 ms | Max ms | API 平均 ms | 平均命中 | 平均 OCR 块 |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 6 | 6 | 1.074 | 929.35 | 804.55 | 1473.20 | 1473.20 | 919.02 | 3.67 | 4.67 |
| 2 | 12 | 12 | 1.401 | 1404.18 | 1376.52 | 1851.35 | 1851.35 | 1388.47 | 3.67 | 4.67 |
| 4 | 24 | 24 | 1.411 | 2707.00 | 2809.03 | 3738.46 | 3773.33 | 2684.73 | 3.67 | 4.67 |
| 8 | 48 | 48 | 1.328 | 5711.69 | 6017.80 | 7519.93 | 7800.17 | 5692.18 | 3.67 | 4.67 |

8 并发短压测复测：

| 并发 | 请求数 | 成功 | 吞吐 RPS | 平均耗时 ms | P50 ms | Max ms | API 平均 ms | 平均命中 | 平均 OCR 块 |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 8 | 24 | 24 | 1.492 | 4624.56 | 5160.78 | 5856.48 | 4605.65 | 3.33 | 4.67 |

## GPU / CPU 观察

8 并发短压测期间，`tegrastats` 显示 CPU 多核长期接近满载，`GR3D_FREQ` 始终为 `0%`。这说明当前 tc192 L4T 图片脱敏链路虽然服务状态显示 OCR provider 为 `cuda`，但压测期间没有观测到 Jetson GPU 图形/ CUDA 负载，实际瓶颈表现为 CPU/OCR 处理与队列等待。

代表性采样：

```text
CPU [94%@1984,90%@1984,95%@1984,90%@1984,99%@1984,96%@1984,96%@1984,94%@1984] GR3D_FREQ 0%
CPU [95%@1984,93%@1984,97%@1984,97%@1984,100%@1984,96%@1984,96%@1984,90%@1984] GR3D_FREQ 0%
CPU [94%@1984,93%@1984,92%@1984,93%@1984,97%@1984,91%@1984,94%@1984,98%@1984] GR3D_FREQ 0%
```

完整采样见 `tegrastats_during_8w.txt`。

## 结论

1. 功能正确性：所有压测请求均成功，3 类图片都能命中并生成脱敏结果图。
2. 性能瓶颈：tc192 上 2 并发后吞吐基本不再提升，稳定上限约 `1.3 ~ 1.5 RPS`。
3. 排队表现：并发从 2 提升到 4/8 后，吞吐没有明显提升，但延迟显著升高，符合 OCR 并发上限为 2 时的排队特征。
4. GPU 观察：当前压测没有看到 `GR3D_FREQ` 上升，后续如果希望图片 OCR 真正吃到 GPU，需要单独核查 RapidOCR / ONNXRuntime 在 L4T 镜像内的 provider 绑定和算子落点。
5. 建议：tc192 这类弱性能 L4T 设备上，图片同步接口建议默认保持 OCR 并发 `2`；如果要支持批量图片脱敏，建议增加异步任务/进度查询，避免前端长时间等待同步请求。

## 产物

- `image_benchmark.json`：完整压测结果。
- `image_benchmark_8w_short.json`：8 并发短压测结果。
- `tegrastats_during_8w.txt`：8 并发期间宿主机采样。
- `plain_card.jpg` / `masked_plain_card.jpg`
- `dense_receipt.jpg` / `masked_dense_receipt.jpg`
- `photo_like_form.jpg` / `masked_photo_like_form.jpg`

