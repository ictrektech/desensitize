# Desensitize API reference

## Addresses, identity and navigation

In the VOS app choose **Integration → Complete API field reference**. The interactive explorer at `/api/com.ictrek.desensitize/docs` and machine-readable `/api/com.ictrek.desensitize/openapi.json` expose all 21 operations and their request/response fields. The relative OpenAPI URL works through the VOS proxy. Direct Docker address: `http://desensitize-backend:5000`; append each operation path below. No separate public host port is promised: use the installed VOS gateway and its actual access policy.

Native redaction and rule management currently have no per-user authentication in this backend; rules are shared globally. Keep direct access on the trusted VOS network. A V-Scheduler model API Key is not an authentication mechanism for these native administrative routes. Scheduler binding is restricted to the verified Scheduler application identity, with tokens provisioned automatically; users should not construct that binding manually. The canonical Scheduler address is `v-scheduler`; the binding snapshot currently validates the compatibility address `http://v-router:8080/scheduler/api/v1` exactly.

## Workflows and limitations

For text: call `/api/v1/desensitize/text` with JSON `{"text":"phone 13812345678","ner":false}`. Batch messages use `/api/v1/desensitize` with `messages` and `options`; assistant messages are skipped by default. `rules` omitted or empty means the default enabled set, not zero rules. Fetch `/api/v1/rules` to obtain actual rule IDs before selecting them. Built-in rules allow only `enabled` changes; other edits/deletion return 403. Custom-rule create returns 201, update 200 and delete 204 with no body. Regex test uses URL **query parameters**, not JSON: `POST /api/v1/rules/test?pattern=%5B0-9%5D%2B&text=abc123` returns matched spans and `result`.

`level` is currently reserved in text and image operations; changing it does not select stricter rules. The accepted `audit` batch flag does not enable persistent audit logs. Select rules/enabled state explicitly. `metadata.rule_count` is the number of replacement summary entries, not the number of enabled rules.

NER and OCR weights are not shipped in the image. Inspect `/api/v1/models/managed`, request `/managed/{key}/download` with `key=ner|ocr`, then poll managed state and the original Scheduler weight task. A successful download submission is not readiness. Runtime readiness also does not replace Scheduler binding and resource approval. Pure regex does not require model weights; `ner=true` fails with 503 when unavailable, without silently reverting to regex-only.

Image redaction accepts **application/json**, with base64 image bytes (not a multipart upload). Wrong content type returns 415; malformed images or ledger keys return 400; unavailable OCR/NER or admission failures return 503. `max_side` defaults to 1600 (256–4096); OCR resizing coordinates are mapped back to the output image. `coordinates` and `ledger` are optional/null unless requested. Reversible redaction requires a 64-hex-character AES-256 key via `ledger_key` or the administrator's `DESENSITIZE_LEDGER_KEY`; store the key privately, separately from the masked image and ledger. Restore requires that same key and ledger. Inspect **every** `report[].restored`: individual decrypt/tamper failures can appear in a successful HTTP response, and `restored_count` can be partial. Redaction is heuristic: review output before sharing sensitive material.

## Errors and retry

Errors use HTTP status plus `detail` (message or validation-error array), with possible non-JSON gateway errors. 404 means missing rule/model key; 409 is a conflicting or busy internal binding; 422 covers invalid schema/regex/binding; 503 can mean unavailable weights, binding, admission or dependency. Read the cause and restore the dependency before retry. Download/update and global-rule mutations are not idempotent by an arbitrary request key: check current state after a timeout before resubmitting. No job queue or cancel endpoint is advertised for synchronous redaction.


## Operations and responses

### GET /api/v1/scheduler/binding

Identity: public operation / boundary described above

See the field contracts and the integration workflow for this native application operation.

Response 200 — Native application JSON response.

`application/json`

`object`

| Field | Type | Requirement | Description |
| --- | --- | --- | --- |
| `protocol_version` | integer | Required |  · const=1 |
| `configured` | boolean | Required |  |
| `binding_revision` | integer | Optional |  |
| `approved_model_count` | integer | Optional |  |

Response default — Check HTTP status and Content-Type. FastAPI detail is a string or validation error list; unexpected gateway/server errors can be plain text.

`application/json`

`object`

| Field | Type | Requirement | Description |
| --- | --- | --- | --- |
| `detail` | JSON | Required | Message or validation details. |

`text/plain`

`string`

### POST /api/v1/scheduler/binding

Identity: SchedulerApplication

Internal automatic provisioning. Requires verified application identity, matching runtime settings, approved executors and a monotonic binding revision. Active work or conflicting revision returns 409; invalid binding returns 422. Do not edit this snapshot manually.

Request body: application/json

`object`

| Field | Type | Requirement | Description |
| --- | --- | --- | --- |
| `protocol_version` | integer | Required |  · const=1 |
| `binding_revision` | integer | Required |  · minimum=1 |
| `app_id` | string | Required |  · const="com.ictrek.desensitize" |
| `url` | string | Required |  · const="http://v-router:8080/scheduler/api/v1" |
| `upstream_url` | string | Required |  · const="http://desensitize-backend:5000/v1" |
| `token` | string | Required |  · minLength=32 · maxLength=4096 |
| `executor_token` | string | Required |  · minLength=32 · maxLength=4096 |
| `models` | object | Required |  |
| `gateway_executors` | object | Optional |  |
| `execution_settings` | object | Required |  |
| `execution_settings.ner_provider_requested` | string | Required |  |
| `execution_settings.ocr_provider_requested` | string | Required |  |
| `execution_settings.onnx_available_providers` | array<string> | Required |  |
| `execution_settings.onnxruntime_version` | string  /  null | Required |  |
| `execution_settings.rapidocr_version` | string  /  null | Required |  |
| `execution_settings.logical_cpu_count` | integer  /  null | Required |  |
| `execution_settings.ner_intra_op_threads` | integer | Required |  |
| `execution_settings.ner_inter_op_threads` | integer | Required |  |
| `execution_settings.ocr_thread_policy` | string | Required |  |
| `execution_settings.ocr_intra_op_threads` | integer | Required |  |
| `execution_settings.ocr_inter_op_threads` | integer | Required |  |
| `execution_settings.opencv_threads` | integer | Required |  |
| `execution_settings.math_thread_environment` | object | Required |  |
| `execution_settings.max_concurrent_inference` | integer | Required |  |
| `execution_settings.ner_max_tokens` | integer | Required |  |
| `model_limits` | object | Required | Provisioned per-model limits from the controller; not a caller-chosen budget. |

Response 200 — Native application JSON response.

`application/json`

`object`

| Field | Type | Requirement | Description |
| --- | --- | --- | --- |
| `configured` | boolean | Required |  |
| `binding_revision` | integer | Required |  |

Response default — Check HTTP status and Content-Type. FastAPI detail is a string or validation error list; unexpected gateway/server errors can be plain text.

`application/json`

`object`

| Field | Type | Requirement | Description |
| --- | --- | --- | --- |
| `detail` | JSON | Required | Message or validation details. |

`text/plain`

`string`

### GET /api/v1/rules

Identity: public operation / boundary described above

See the field contracts and the integration workflow for this native application operation.

- `query: enabled_only` · boolean · Optional · 

Response 200 — Successful Response

`application/json`

`array<RuleOut>`

Response 422 — Validation Error

`application/json`

`HTTPValidationError`

Response default — Check HTTP status and Content-Type. FastAPI detail is a string or validation error list; unexpected gateway/server errors can be plain text.

`application/json`

`object`

| Field | Type | Requirement | Description |
| --- | --- | --- | --- |
| `detail` | JSON | Required | Message or validation details. |

`text/plain`

`string`

### POST /api/v1/rules

Identity: public operation / boundary described above

See the field contracts and the integration workflow for this native application operation.

Request body: application/json

`RuleCreate`

Response 201 — Successful Response

`application/json`

`RuleOut`

Response 422 — Validation Error

`application/json`

`HTTPValidationError`

Response default — Check HTTP status and Content-Type. FastAPI detail is a string or validation error list; unexpected gateway/server errors can be plain text.

`application/json`

`object`

| Field | Type | Requirement | Description |
| --- | --- | --- | --- |
| `detail` | JSON | Required | Message or validation details. |

`text/plain`

`string`

### GET /api/v1/rules/builtin

Identity: public operation / boundary described above

See the field contracts and the integration workflow for this native application operation.

Response 200 — Successful Response

`application/json`

`array<RuleOut>`

Response default — Check HTTP status and Content-Type. FastAPI detail is a string or validation error list; unexpected gateway/server errors can be plain text.

`application/json`

`object`

| Field | Type | Requirement | Description |
| --- | --- | --- | --- |
| `detail` | JSON | Required | Message or validation details. |

`text/plain`

`string`

### GET /api/v1/rules/custom

Identity: public operation / boundary described above

See the field contracts and the integration workflow for this native application operation.

Response 200 — Successful Response

`application/json`

`array<RuleOut>`

Response default — Check HTTP status and Content-Type. FastAPI detail is a string or validation error list; unexpected gateway/server errors can be plain text.

`application/json`

`object`

| Field | Type | Requirement | Description |
| --- | --- | --- | --- |
| `detail` | JSON | Required | Message or validation details. |

`text/plain`

`string`

### GET /api/v1/rules/{rule_id}

Identity: public operation / boundary described above

See the field contracts and the integration workflow for this native application operation.

- `path: rule_id` · string · Required · 

Response 200 — Successful Response

`application/json`

`RuleOut`

Response 422 — Validation Error

`application/json`

`HTTPValidationError`

Response default — Check HTTP status and Content-Type. FastAPI detail is a string or validation error list; unexpected gateway/server errors can be plain text.

`application/json`

`object`

| Field | Type | Requirement | Description |
| --- | --- | --- | --- |
| `detail` | JSON | Required | Message or validation details. |

`text/plain`

`string`

### PUT /api/v1/rules/{rule_id}

Identity: public operation / boundary described above

See the field contracts and the integration workflow for this native application operation.

- `path: rule_id` · string · Required · 

Request body: application/json

`RuleUpdate`

Response 200 — Successful Response

`application/json`

`RuleOut`

Response 422 — Validation Error

`application/json`

`HTTPValidationError`

Response default — Check HTTP status and Content-Type. FastAPI detail is a string or validation error list; unexpected gateway/server errors can be plain text.

`application/json`

`object`

| Field | Type | Requirement | Description |
| --- | --- | --- | --- |
| `detail` | JSON | Required | Message or validation details. |

`text/plain`

`string`

### DELETE /api/v1/rules/{rule_id}

Identity: public operation / boundary described above

See the field contracts and the integration workflow for this native application operation.

- `path: rule_id` · string · Required · 

Response 204 — Successful Response

Response 422 — Validation Error

`application/json`

`HTTPValidationError`

Response default — Check HTTP status and Content-Type. FastAPI detail is a string or validation error list; unexpected gateway/server errors can be plain text.

`application/json`

`object`

| Field | Type | Requirement | Description |
| --- | --- | --- | --- |
| `detail` | JSON | Required | Message or validation details. |

`text/plain`

`string`

### POST /api/v1/rules/test

Identity: public operation / boundary described above

Query parameters, not a JSON body. Invalid regular expressions return 422.

- `query: pattern` · string · Required · 

- `query: text` · string · Required · 

- `query: placeholder` · string · Optional · 

Response 200 — Native application JSON response.

`application/json`

`object`

| Field | Type | Requirement | Description |
| --- | --- | --- | --- |
| `matched` | boolean | Required |  |
| `matches` | array<object> | Required |  |
| `result` | string | Required |  |
| `match_count` | integer | Required |  |

Response 422 — Validation Error

`application/json`

`HTTPValidationError`

Response default — Check HTTP status and Content-Type. FastAPI detail is a string or validation error list; unexpected gateway/server errors can be plain text.

`application/json`

`object`

| Field | Type | Requirement | Description |
| --- | --- | --- | --- |
| `detail` | JSON | Required | Message or validation details. |

`text/plain`

`string`

### POST /api/v1/desensitize

Identity: public operation / boundary described above

See the field contracts and the integration workflow for this native application operation.

Request body: application/json

`DesensitizeRequest`

Response 200 — Successful Response

`application/json`

`DesensitizeResponse`

Response 422 — Validation Error

`application/json`

`HTTPValidationError`

Response default — Check HTTP status and Content-Type. FastAPI detail is a string or validation error list; unexpected gateway/server errors can be plain text.

`application/json`

`object`

| Field | Type | Requirement | Description |
| --- | --- | --- | --- |
| `detail` | JSON | Required | Message or validation details. |

`text/plain`

`string`

### POST /api/v1/desensitize/text

Identity: public operation / boundary described above

See the field contracts and the integration workflow for this native application operation.

Request body: application/json

`DesensitizeTextRequest`

Response 200 — Successful Response

`application/json`

`DesensitizeTextResponse`

Response 422 — Validation Error

`application/json`

`HTTPValidationError`

Response default — Check HTTP status and Content-Type. FastAPI detail is a string or validation error list; unexpected gateway/server errors can be plain text.

`application/json`

`object`

| Field | Type | Requirement | Description |
| --- | --- | --- | --- |
| `detail` | JSON | Required | Message or validation details. |

`text/plain`

`string`

### POST /api/v1/desensitize/image

Identity: public operation / boundary described above

See the field contracts and the integration workflow for this native application operation.

Request body: application/json

`ImageDesensitizeRequest`

Response 200 — Successful Response

`application/json`

`ImageDesensitizeResponse`

Response 422 — Validation Error

`application/json`

`HTTPValidationError`

Response default — Check HTTP status and Content-Type. FastAPI detail is a string or validation error list; unexpected gateway/server errors can be plain text.

`application/json`

`object`

| Field | Type | Requirement | Description |
| --- | --- | --- | --- |
| `detail` | JSON | Required | Message or validation details. |

`text/plain`

`string`

### POST /api/v1/desensitize/image/restore

Identity: public operation / boundary described above

See the field contracts and the integration workflow for this native application operation.

Request body: application/json

`ImageRestoreRequest`

Response 200 — Successful Response

`application/json`

`ImageRestoreResponse`

Response 422 — Validation Error

`application/json`

`HTTPValidationError`

Response default — Check HTTP status and Content-Type. FastAPI detail is a string or validation error list; unexpected gateway/server errors can be plain text.

`application/json`

`object`

| Field | Type | Requirement | Description |
| --- | --- | --- | --- |
| `detail` | JSON | Required | Message or validation details. |

`text/plain`

`string`

### GET /api/v1/models/managed

Identity: public operation / boundary described above

See the field contracts and the integration workflow for this native application operation.

Response 200 — Native application JSON response.

`application/json`

`array<ManagedModel>`

Response default — Check HTTP status and Content-Type. FastAPI detail is a string or validation error list; unexpected gateway/server errors can be plain text.

`application/json`

`object`

| Field | Type | Requirement | Description |
| --- | --- | --- | --- |
| `detail` | JSON | Required | Message or validation details. |

`text/plain`

`string`

### POST /api/v1/models/managed/{key}/download

Identity: public operation / boundary described above

See the field contracts and the integration workflow for this native application operation.

- `path: key` · string · Required · 

Response 200 — Native application JSON response.

`application/json`

`object`

| Field | Type | Requirement | Description |
| --- | --- | --- | --- |
| `model` | ManagedModel | Required |  |
| `result` | JSON | Required | Unmodified result of V-Scheduler weight pull/check-update/update. A duplicate download may return a message instead of a new task. |

Response 422 — Validation Error

`application/json`

`HTTPValidationError`

Response default — Check HTTP status and Content-Type. FastAPI detail is a string or validation error list; unexpected gateway/server errors can be plain text.

`application/json`

`object`

| Field | Type | Requirement | Description |
| --- | --- | --- | --- |
| `detail` | JSON | Required | Message or validation details. |

`text/plain`

`string`

### POST /api/v1/models/managed/{key}/check-update

Identity: public operation / boundary described above

See the field contracts and the integration workflow for this native application operation.

- `path: key` · string · Required · 

Response 200 — Native application JSON response.

`application/json`

`object`

| Field | Type | Requirement | Description |
| --- | --- | --- | --- |
| `model` | ManagedModel | Required |  |
| `result` | JSON | Required | Unmodified result of V-Scheduler weight pull/check-update/update. A duplicate download may return a message instead of a new task. |

Response 422 — Validation Error

`application/json`

`HTTPValidationError`

Response default — Check HTTP status and Content-Type. FastAPI detail is a string or validation error list; unexpected gateway/server errors can be plain text.

`application/json`

`object`

| Field | Type | Requirement | Description |
| --- | --- | --- | --- |
| `detail` | JSON | Required | Message or validation details. |

`text/plain`

`string`

### POST /api/v1/models/managed/{key}/update

Identity: public operation / boundary described above

See the field contracts and the integration workflow for this native application operation.

- `path: key` · string · Required · 

Response 200 — Native application JSON response.

`application/json`

`object`

| Field | Type | Requirement | Description |
| --- | --- | --- | --- |
| `model` | ManagedModel | Required |  |
| `result` | JSON | Required | Unmodified result of V-Scheduler weight pull/check-update/update. A duplicate download may return a message instead of a new task. |

Response 422 — Validation Error

`application/json`

`HTTPValidationError`

Response default — Check HTTP status and Content-Type. FastAPI detail is a string or validation error list; unexpected gateway/server errors can be plain text.

`application/json`

`object`

| Field | Type | Requirement | Description |
| --- | --- | --- | --- |
| `detail` | JSON | Required | Message or validation details. |

`text/plain`

`string`

### GET /health

Identity: public operation / boundary described above

See the field contracts and the integration workflow for this native application operation.

Response 200 — Native application JSON response.

`application/json`

`object`

| Field | Type | Requirement | Description |
| --- | --- | --- | --- |
| `status` | string | Required |  |
| `service` | string | Required |  |

Response default — Check HTTP status and Content-Type. FastAPI detail is a string or validation error list; unexpected gateway/server errors can be plain text.

`application/json`

`object`

| Field | Type | Requirement | Description |
| --- | --- | --- | --- |
| `detail` | JSON | Required | Message or validation details. |

`text/plain`

`string`

### GET /api/v1/discovery

Identity: public operation / boundary described above

See the field contracts and the integration workflow for this native application operation.

Response 200 — Native application JSON response.

`application/json`

`object`

| Field | Type | Requirement | Description |
| --- | --- | --- | --- |
| `service_id` | string | Required |  |
| `scheduler` | object | Required |  |
| `scheduler.protocol_version` | integer | Required |  |
| `scheduler.app_id` | string | Required |  |
| `scheduler.binding_endpoint` | string | Required |  |
| `scheduler.lifecycle_protocol_version` | integer | Required |  |
| `scheduler.executor_base_url` | string | Required |  |
| `scheduler.upstream_url` | string | Required |  |
| `scheduler.provider` | string | Required |  |
| `scheduler.ocr_provider` | string | Required |  |
| `scheduler.num_threads` | integer | Required |  |
| `scheduler.max_concurrent_inference` | integer | Required |  |
| `scheduler.max_tokens` | integer | Required |  |
| `scheduler.sync_models` | array<object> | Required |  |
| `scheduler.execution_settings` | object | Required |  |
| `scheduler.execution_settings.ner_provider_requested` | string | Required |  |
| `scheduler.execution_settings.ocr_provider_requested` | string | Required |  |
| `scheduler.execution_settings.onnx_available_providers` | array<string> | Required |  |
| `scheduler.execution_settings.onnxruntime_version` | string  /  null | Required |  |
| `scheduler.execution_settings.rapidocr_version` | string  /  null | Required |  |
| `scheduler.execution_settings.logical_cpu_count` | integer  /  null | Required |  |
| `scheduler.execution_settings.ner_intra_op_threads` | integer | Required |  |
| `scheduler.execution_settings.ner_inter_op_threads` | integer | Required |  |
| `scheduler.execution_settings.ocr_thread_policy` | string | Required |  |
| `scheduler.execution_settings.ocr_intra_op_threads` | integer | Required |  |
| `scheduler.execution_settings.ocr_inter_op_threads` | integer | Required |  |
| `scheduler.execution_settings.opencv_threads` | integer | Required |  |
| `scheduler.execution_settings.math_thread_environment` | object | Required |  |
| `scheduler.execution_settings.max_concurrent_inference` | integer | Required |  |
| `scheduler.execution_settings.ner_max_tokens` | integer | Required |  |
| `scheduler.binding` | object | Required |  |
| `scheduler.binding.protocol_version` | integer | Required |  · const=1 |
| `scheduler.binding.configured` | boolean | Required |  |
| `scheduler.binding.binding_revision` | integer | Optional |  |
| `scheduler.binding.approved_model_count` | integer | Optional |  |

Response default — Check HTTP status and Content-Type. FastAPI detail is a string or validation error list; unexpected gateway/server errors can be plain text.

`application/json`

`object`

| Field | Type | Requirement | Description |
| --- | --- | --- | --- |
| `detail` | JSON | Required | Message or validation details. |

`text/plain`

`string`

### GET /api/v1/system/about

Identity: public operation / boundary described above

See the field contracts and the integration workflow for this native application operation.

Response 200 — Native application JSON response.

`application/json`

`object`

| Field | Type | Requirement | Description |
| --- | --- | --- | --- |
| `service_id` | string | Required |  |
| `service` | string | Required |  |
| `app_version` | string | Required |  |
| `profile` | string | Required |  |
| `backend_image` | string | Required |  |
| `frontend_image` | string | Required |  |
| `ner` | object | Required |  |
| `ner.enabled` | boolean | Required |  |
| `ner.state` | string | Required |  |
| `ner.model_id` | string | Required |  |
| `ner.model_dir` | string | Required |  |
| `ner.max_concurrency` | integer | Required |  |
| `ner.queue_timeout_seconds` | number | Required |  |
| `ner.error` | string  /  null | Required |  |
| `ner.requested_provider` | string | Optional |  |
| `ner.active_provider` | string  /  null | Optional |  |
| `ner.provider` | string | Optional |  |
| `ner.active_providers` | array<string> | Optional |  |
| `ner.ready` | boolean | Optional |  |
| `image_ocr` | object | Required |  |
| `image_ocr.enabled` | boolean | Required |  |
| `image_ocr.state` | string | Required |  |
| `image_ocr.model_id` | string | Required |  |
| `image_ocr.model_dir` | string | Required |  |
| `image_ocr.max_concurrency` | integer | Required |  |
| `image_ocr.queue_timeout_seconds` | number | Required |  |
| `image_ocr.error` | string  /  null | Required |  |
| `image_ocr.requested_provider` | string | Optional |  |
| `image_ocr.active_provider` | string  /  null | Optional |  |
| `image_ocr.provider` | string | Optional |  |
| `image_ocr.active_providers` | array<string> | Optional |  |
| `image_ocr.ready` | boolean | Optional |  |

Response default — Check HTTP status and Content-Type. FastAPI detail is a string or validation error list; unexpected gateway/server errors can be plain text.

`application/json`

`object`

| Field | Type | Requirement | Description |
| --- | --- | --- | --- |
| `detail` | JSON | Required | Message or validation details. |

`text/plain`

`string`

## Shared data types

Field names retain their API spelling. Interpret extension metadata according to its owning service.

### DesensitizeOptions

| Field | Type | Requirement | Description |
| --- | --- | --- | --- |
| `level` | string | Optional | Compatibility field, currently reserved; does not select a different rule set. Select rule IDs and enabled rules instead. · default="standard" |
| `rules` | array<string>  /  null | Optional |  |
| `preserve_length` | boolean | Optional |  · default=false |
| `skip_roles` | array<string> | Optional |  |
| `audit` | boolean | Optional | Reserved compatibility flag; does not enable persistent audit logging. · default=false |
| `ner` | boolean | Optional |  · default=false |

### DesensitizeRequest

| Field | Type | Requirement | Description |
| --- | --- | --- | --- |
| `messages` | array<Message> | Required |  |
| `options` | DesensitizeOptions | Optional |  |

### DesensitizeResponse

| Field | Type | Requirement | Description |
| --- | --- | --- | --- |
| `messages` | array<Message> | Required |  |
| `replaced` | array<ReplacedItem> | Required |  |
| `metadata` | object | Required |  |
| `metadata.latency_ms` | number | Required |  |
| `metadata.engine` | string | Required |  |
| `metadata.rule_count` | integer | Required |  |

### DesensitizeTextRequest

| Field | Type | Requirement | Description |
| --- | --- | --- | --- |
| `text` | string | Required |  |
| `level` | string | Optional | Compatibility field, currently reserved; does not select a different rule set. Select rule IDs and enabled rules instead. · default="standard" |
| `rules` | array<string>  /  null | Optional |  |
| `ner` | boolean | Optional |  · default=false |

### DesensitizeTextResponse

| Field | Type | Requirement | Description |
| --- | --- | --- | --- |
| `text` | string | Required |  |
| `replaced` | array<ReplacedItem> | Required |  |
| `latency_ms` | number | Required |  |

### HTTPValidationError

| Field | Type | Requirement | Description |
| --- | --- | --- | --- |
| `detail` | array<ValidationError> | Optional |  |

### ImageDesensitizeRequest

| Field | Type | Requirement | Description |
| --- | --- | --- | --- |
| `image_base64` | string | Required |  |
| `mime_type` | string | Optional |  · default="image/jpeg" |
| `level` | string | Optional | Compatibility field, currently reserved; does not select a different rule set. Select rule IDs and enabled rules instead. · default="standard" |
| `rules` | array<string>  /  null | Optional |  |
| `ner` | boolean | Optional |  · default=false |
| `adaptive` | boolean | Optional |  · default=false |
| `reversible` | boolean | Optional |  · default=false |
| `ledger_key` | string  /  null | Optional |  |
| `return_coordinates` | boolean | Optional |  · default=false |
| `max_side` | integer | Optional |  · default=1600 · minimum=256.0 · maximum=4096.0 |

### ImageDesensitizeResponse

| Field | Type | Requirement | Description |
| --- | --- | --- | --- |
| `image_base64` | string | Required |  |
| `mime_type` | string | Required |  |
| `replaced` | array<ReplacedItem> | Required |  |
| `metadata` | object | Required |  |
| `metadata.ocr_engine` | string | Required |  |
| `metadata.ocr_blocks` | integer | Required |  |
| `metadata.rebuilt_text_length` | integer | Required |  |
| `metadata.normalized_matching` | boolean | Required |  |
| `metadata.matched_via` | object | Required |  |
| `metadata.suppressed_by_space` | object | Required |  |
| `metadata.validator_rejected` | integer | Required |  |
| `metadata.gate_failure_policy` | string | Required |  |
| `metadata.adaptive` | boolean | Required |  |
| `metadata.scene` | object  /  null | Required |  |
| `metadata.field_fallback_regions` | integer | Required |  |
| `metadata.fallback_masked_lines` | integer | Required |  |
| `metadata.secondary_ocr` | object | Required |  |
| `metadata.secondary_ocr.enabled` | boolean | Required |  |
| `metadata.secondary_ocr.regions` | integer | Required |  |
| `metadata.secondary_ocr.blocks` | integer | Required |  |
| `metadata.secondary_ocr.reasons` | object | Required |  |
| `metadata.resized` | boolean | Required |  |
| `metadata.scale` | number | Required |  |
| `metadata.ocr` | object | Required |  |
| `metadata.ocr.enabled` | boolean | Required |  |
| `metadata.ocr.state` | string | Required |  |
| `metadata.ocr.model_id` | string | Required |  |
| `metadata.ocr.model_dir` | string | Required |  |
| `metadata.ocr.max_concurrency` | integer | Required |  |
| `metadata.ocr.queue_timeout_seconds` | number | Required |  |
| `metadata.ocr.error` | string  /  null | Required |  |
| `metadata.ocr.requested_provider` | string | Optional |  |
| `metadata.ocr.active_provider` | string  /  null | Optional |  |
| `metadata.ocr.provider` | string | Optional |  |
| `metadata.ocr.active_providers` | array<string> | Optional |  |
| `metadata.ocr.ready` | boolean | Optional |  |
| `latency_ms` | number | Required |  |
| `coordinates` | array<object>  /  null | Optional |  |
| `ledger` | ImageLedger  /  null | Optional |  |

### ImageRestoreRequest

| Field | Type | Requirement | Description |
| --- | --- | --- | --- |
| `image_base64` | string | Required |  |
| `ledger` | ImageLedger | Required |  |
| `ledger_key` | string  /  null | Optional |  |
| `mime_type` | string | Optional |  · default="image/png" |

### ImageRestoreResponse

| Field | Type | Requirement | Description |
| --- | --- | --- | --- |
| `image_base64` | string | Required |  |
| `mime_type` | string | Required |  |
| `report` | array<object> | Required |  |
| `restored_count` | integer | Required |  |

### Message

| Field | Type | Requirement | Description |
| --- | --- | --- | --- |
| `role` | string | Optional |  · default="user" |
| `content` | string | Optional |  · default="" |

### ReplacedItem

| Field | Type | Requirement | Description |
| --- | --- | --- | --- |
| `rule` | string | Required |  |
| `placeholder` | string | Required |  |
| `occurrences` | integer | Required |  |

### RuleCreate

| Field | Type | Requirement | Description |
| --- | --- | --- | --- |
| `name` | string | Required |  · minLength=1 · maxLength=100 |
| `description` | string | Optional |  · default="" · maxLength=500 |
| `pattern` | string | Required |  · minLength=1 |
| `placeholder` | string | Required |  · minLength=1 |
| `priority` | integer | Optional |  · default=0 · minimum=0.0 · maximum=100.0 |
| `enabled` | boolean | Optional |  · default=true |
| `category` | string | Optional |  · default="custom" |

### RuleOut

| Field | Type | Requirement | Description |
| --- | --- | --- | --- |
| `id` | string | Required |  |
| `name` | string | Required |  |
| `description` | string | Required |  |
| `pattern` | string | Required |  |
| `placeholder` | string | Required |  |
| `priority` | integer | Optional |  · default=0 |
| `enabled` | boolean | Optional |  · default=true |
| `builtin` | boolean | Optional |  · default=false |
| `category` | string | Optional |  · default="custom" |

### RuleUpdate

| Field | Type | Requirement | Description |
| --- | --- | --- | --- |
| `name` | string  /  null | Optional |  |
| `description` | string  /  null | Optional |  |
| `pattern` | string  /  null | Optional |  |
| `placeholder` | string  /  null | Optional |  |
| `priority` | integer  /  null | Optional |  |
| `enabled` | boolean  /  null | Optional |  |
| `category` | string  /  null | Optional |  |

### ValidationError

| Field | Type | Requirement | Description |
| --- | --- | --- | --- |
| `loc` | array<string  /  integer> | Required |  |
| `msg` | string | Required |  |
| `type` | string | Required |  |
| `input` | JSON | Optional |  |
| `ctx` | object | Optional |  |

### ModelRuntime

| Field | Type | Requirement | Description |
| --- | --- | --- | --- |
| `enabled` | boolean | Required |  |
| `state` | string | Required |  |
| `model_id` | string | Required |  |
| `model_dir` | string | Required |  |
| `max_concurrency` | integer | Required |  |
| `queue_timeout_seconds` | number | Required |  |
| `error` | string  /  null | Required |  |
| `requested_provider` | string | Optional |  |
| `active_provider` | string  /  null | Optional |  |
| `provider` | string | Optional |  |
| `active_providers` | array<string> | Optional |  |
| `ready` | boolean | Optional |  |

### ManagedModel

| Field | Type | Requirement | Description |
| --- | --- | --- | --- |
| `key` | string | Required |  |
| `name` | string | Required |  |
| `description` | string | Required |  |
| `model_id` | string | Required |  |
| `source` | string | Required |  |
| `pull_name` | string | Required |  |
| `model_dir` | string | Required |  |
| `status` | string | Required |  |
| `ready` | boolean | Required |  |
| `runtime` | ModelRuntime | Required |  |
| `model` | object  /  null | Required |  |
| `task` | object  /  null | Required |  |

### SchedulerBinding

| Field | Type | Requirement | Description |
| --- | --- | --- | --- |
| `protocol_version` | integer | Required |  · const=1 |
| `configured` | boolean | Required |  |
| `binding_revision` | integer | Optional |  |
| `approved_model_count` | integer | Optional |  |

### ExecutionSettings

| Field | Type | Requirement | Description |
| --- | --- | --- | --- |
| `ner_provider_requested` | string | Required |  |
| `ocr_provider_requested` | string | Required |  |
| `onnx_available_providers` | array<string> | Required |  |
| `onnxruntime_version` | string  /  null | Required |  |
| `rapidocr_version` | string  /  null | Required |  |
| `logical_cpu_count` | integer  /  null | Required |  |
| `ner_intra_op_threads` | integer | Required |  |
| `ner_inter_op_threads` | integer | Required |  |
| `ocr_thread_policy` | string | Required |  |
| `ocr_intra_op_threads` | integer | Required |  |
| `ocr_inter_op_threads` | integer | Required |  |
| `opencv_threads` | integer | Required |  |
| `math_thread_environment` | object | Required |  |
| `max_concurrent_inference` | integer | Required |  |
| `ner_max_tokens` | integer | Required |  |

### PixelBox

| Field | Type | Requirement | Description |
| --- | --- | --- | --- |
| `x1` | number | Required |  |
| `y1` | number | Required |  |
| `x2` | number | Required |  |
| `y2` | number | Required |  |

### ImageLedger

| Field | Type | Requirement | Description |
| --- | --- | --- | --- |
| `version` | integer | Required |  · const=1 |
| `alg` | string | Required |  · const="AES-256-GCM" |
| `region_count` | integer | Required |  |
| `regions` | array<object> | Required |  |
