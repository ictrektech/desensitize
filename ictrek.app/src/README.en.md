# Desensitize Service User Guide

Desensitize Service provides regex-based sensitive information detection and desensitization HTTP API. Other VOS apps like WeKnora and agent-room can use it to sanitize data before sending to cloud models.

> ⚠️ **Prerequisite: Model Hub**
>
> NER (semantic desensitization) and image OCR require Model Hub. Make sure Model Hub is installed and running before installing this app.
>
> The NER model `huluxiaohuowa/bert4ner-base-chinese-onnx` and OCR model `huluxiaohuowa/rapidocr-ppocrv4-onnx` are not bundled with this app. The service can automatically trigger Model Hub downloads, and the Web "Models" page can manually download, check versions, and update them. During download, regex-only APIs remain available; `ner=true` requests and image requests return retry messages.

## Installation Profiles

| Profile | Target |
| --- | --- |
| `amd` | AMD64 hosts |
| `arm` | ARM64 hosts |

## Access

Navigate via VOS sidebar: **Desensitize -> Desensitize Management**

Iframe URL: `/app/com.ictrek.desensitize/`

## Network Access

| Target | URL |
| --- | --- |
| App in the same VOS instance | `http://desensitize-backend:5000` (the caller must join external `vos_default`) |
| Internal VOS gateway | `http://${VOS_HOST_GW_IP}:${VOS_API_GW_PORT_INTERNAL}/api/com.ictrek.desensitize` |

Both values are API base URLs. Append `/api/v1/desensitize/text` for single-text
desensitization. Traefik removes `/api/com.ictrek.desensitize` before forwarding.

## Rule Management

Built-in rules cover common sensitive data such as phone numbers, ID cards,
email addresses, bank cards, API keys, bearer tokens, credentials, IP addresses,
sensitive URL parameters, taxpayer IDs, invoice numbers, order numbers, and
tracking numbers. Built-in rules cannot be edited or deleted, but each rule can
be enabled or disabled individually. Custom rules can be created, edited,
deleted, enabled, and disabled. Rule enabled states are persisted and remain the
same after restart or the next login.

## Model Dependencies through Model Hub

NER and image OCR weights are not embedded in this image. On startup the service
checks Model Hub through the VOS alias `model-hub-backend:5005` and requests the
ModelScope models `huluxiaohuowa/bert4ner-base-chinese-onnx` and
`huluxiaohuowa/rapidocr-ppocrv4-onnx` when they are absent. Set
`MODEL_HUB_SHARED_MODELS_PATH` at installation time (default:
`/data/vos_workspace/model_hub`); the whole root is mounted read-only at
`/modelhub`, and this service loads:

- `/modelhub/export/ms/huluxiaohuowa/bert4ner-base-chinese-onnx/current`
- `/modelhub/export/ms/huluxiaohuowa/rapidocr-ppocrv4-onnx/current`

This is non-blocking: regex-only requests remain unchanged while a download is
in progress, NER requests return 503 with a retry message, and image requests
return 503 until the OCR model is ready. Add `"ner": true` to a text request, or
to batch `options`, to additionally redact person and location entities.

`DESENSITIZE_NER_MAX_CONCURRENCY` is exposed at installation time and defaults to
4. Requests beyond that limit wait up to `DESENSITIZE_NER_QUEUE_TIMEOUT_SECONDS`
(default 30 seconds) before receiving a busy response.

The Web "Models" page shows separate NER and OCR cards with Model Hub status,
download progress, current version, access path, and download/check/update
buttons.

The top-right About button shows the current VOS app version, install profile,
frontend/backend images, NER state, and active ONNX Runtime provider.

## Image Desensitization

Image desensitization is an additional API and does not change the existing text
APIs. The service loads RapidOCR ONNX files from Model Hub, reconstructs
line/document text from OCR blocks, then applies regex matching on both the
rebuilt text and a compact whitespace-free view. This avoids common misses when
OCR splits one phone number, ID number, or API key into multiple boxes. Set
`"ner": true` to also use the text NER model for person and address masking.

```json
POST /api/v1/desensitize/image
{
  "image_base64": "<base64 or data:image/...;base64,...>",
  "mime_type": "image/jpeg",
  "ner": false,
  "return_coordinates": true,
  "max_side": 1600
}
```

The response `image_base64` is the masked image. `replaced` contains match
statistics. `coordinates` is returned only when `return_coordinates` is true.
When RapidOCR misses a long visible text row, the service applies a conservative
full-row fallback mask to prevent long API keys or tokens from being returned
unchanged. For Chinese ID cards, invoices, and logistics labels, the image
pipeline also detects nearby values for field labels such as ID number, phone,
address, email, taxpayer ID, invoice number, order number, and tracking number,
so fragmented or partially missed OCR digits can still be masked.

OCR is conservative by default for weaker devices:

| Config | Default | Description |
| --- | --- | --- |
| `DESENSITIZE_IMAGE_OCR_ENABLED` | `true` | Enables the image OCR API |
| `DESENSITIZE_IMAGE_OCR_MAX_CONCURRENCY` | `1` | Number of simultaneous OCR jobs |
| `DESENSITIZE_IMAGE_OCR_QUEUE_TIMEOUT_SECONDS` | `20` | Queue wait timeout when OCR is busy |

## API Endpoints

| Endpoint | Method | Description |
| --- | --- | --- |
| `/api/v1/rules` | GET | List all rules |
| `/api/v1/rules` | POST | Create custom rule |
| `/api/v1/rules/{id}` | PUT | Update a rule; built-in rules only allow enable/disable, custom rules allow full updates |
| `/api/v1/rules/{id}` | DELETE | Delete custom rule |
| `/api/v1/rules/test` | POST | Test regex pattern |
| `/api/v1/desensitize` | POST | Batch desensitize messages |
| `/api/v1/desensitize/text` | POST | Desensitize single text |
| `/api/v1/desensitize/image` | POST | OCR-based image desensitization |
| `/health` | GET | Health check |
