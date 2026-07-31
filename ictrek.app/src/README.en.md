# Desensitize Service User Guide

Desensitize Service provides regex-based sensitive information detection and desensitization HTTP API. Other VOS apps like WeKnora and agent-room can use it to sanitize data before sending to cloud models.

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
| Host debug port | `http://<vos-host>:35010` (controlled external access only) |

Each value is an API base URL. Append `/api/v1/desensitize/text` for single-text
desensitization. Traefik removes `/api/com.ictrek.desensitize` before forwarding.

## Optional NER through Model Hub

NER weights are not embedded in this image. On startup the service checks Model
Hub through the VOS alias `model-hub-backend:5005` and requests the ModelScope
model `huluxiaohuowa/bert4ner-base-chinese-onnx` when it is absent. Set
`MODEL_HUB_SHARED_MODELS_PATH` at installation time (default:
`/data/vos_workspace/model_hub`); the whole root is mounted read-only at
`/modelhub`, and this service loads
`/modelhub/export/ms/huluxiaohuowa/bert4ner-base-chinese-onnx/current`.

This is non-blocking: regex-only requests remain unchanged while a download is
in progress, and NER requests return 503 with a retry message. Add `"ner": true` to a text request, or
to batch `options`, to additionally redact person and location entities. If the
Model Hub model is unavailable, only NER requests return 503.

## API Endpoints

| Endpoint | Method | Description |
| --- | --- | --- |
| `/api/v1/rules` | GET | List all rules |
| `/api/v1/rules` | POST | Create custom rule |
| `/api/v1/rules/{id}` | PUT | Update custom rule |
| `/api/v1/rules/{id}` | DELETE | Delete custom rule |
| `/api/v1/rules/test` | POST | Test regex pattern |
| `/api/v1/desensitize` | POST | Batch desensitize messages |
| `/api/v1/desensitize/text` | POST | Desensitize single text |
| `/health` | GET | Health check |
