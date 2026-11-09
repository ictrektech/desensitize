"""Documentation metadata; handlers and response filtering remain unchanged."""
from copy import deepcopy
from fastapi.openapi.utils import get_openapi
from fastapi.routing import APIRoute

S = {"type": "string"}
I = {"type": "integer"}
B = {"type": "boolean"}
N = {"type": "number"}
def obj(p, required=None):
    return {"type": "object", "properties": deepcopy(p), "required": list(p) if required is None else required, "additionalProperties": True}
def arr(s): return {"type": "array", "items": s}
def ref(s): return {"$ref": "#/components/schemas/" + s}
def nullable(s): return {"anyOf": [s, {"type": "null"}]}

def build_openapi(app):
    if app.openapi_schema: return app.openapi_schema
    spec = get_openapi(title=app.title, version=app.version, routes=app.routes, servers=[{"url": "."}])
    components = spec.setdefault("components", {}).setdefault("schemas", {})
    runtime = obj({"enabled": B, "state": S, "model_id": S, "model_dir": S, "max_concurrency": I, "queue_timeout_seconds": N, "error": nullable(S), "requested_provider": S, "active_provider": nullable(S), "provider": S, "active_providers": arr(S), "ready": B}, ["enabled", "state", "model_id", "model_dir", "max_concurrency", "queue_timeout_seconds", "error"])
    managed = obj({**{k:S for k in ("key", "name", "description", "model_id", "source", "pull_name", "model_dir", "status")}, "ready": B, "runtime": ref("ModelRuntime"), "model": nullable({"type":"object", "description":"Original V-Scheduler weight-management model record; see its OpenAPI."}), "task": nullable({"type":"object", "description":"Original V-Scheduler download task; poll its phase, not HTTP success alone."})})
    binding = obj({"protocol_version": {"type":"integer","const":1}, "configured": B, "binding_revision": I, "approved_model_count": I}, ["protocol_version", "configured"])
    execution = obj({"ner_provider_requested":S,"ocr_provider_requested":S,"onnx_available_providers":arr(S),"onnxruntime_version":nullable(S),"rapidocr_version":nullable(S),"logical_cpu_count":nullable(I),"ner_intra_op_threads":I,"ner_inter_op_threads":I,"ocr_thread_policy":S,"ocr_intra_op_threads":I,"ocr_inter_op_threads":I,"opencv_threads":I,"math_thread_environment":{"type":"object","additionalProperties":nullable(S)},"max_concurrent_inference":I,"ner_max_tokens":I})
    box = obj({k:N for k in ("x1","y1","x2","y2")})
    ledger = obj({"version":{"type":"integer","const":1},"alg":{"type":"string","const":"AES-256-GCM"},"region_count":I,"regions":arr(obj({"index":I,"box":ref("PixelBox"),"nonce":S,"ciphertext":S}))})
    components.update({"ModelRuntime":runtime,"ManagedModel":managed,"SchedulerBinding":binding,"ExecutionSettings":execution,"PixelBox":box,"ImageLedger":ledger})
    responses={
        "health_check":obj({"status":S,"service":S}),
        "system_about":obj({**{k:S for k in ("service_id","service","app_version","profile","backend_image","frontend_image")},"ner":runtime,"image_ocr":runtime}),
        "discovery":obj({"service_id":S,"scheduler":obj({"protocol_version":I,"app_id":S,"binding_endpoint":S,"lifecycle_protocol_version":I,"executor_base_url":S,"upstream_url":S,"provider":S,"ocr_provider":S,"num_threads":I,"max_concurrent_inference":I,"max_tokens":I,"sync_models":arr(obj({"id":S,"task_type":S})),"execution_settings":execution,"binding":binding})}),
        "binding_status":binding,"bind":obj({"configured":B,"binding_revision":I}),
        "list_managed_models":arr(ref("ManagedModel")),
        "test_pattern":obj({"matched":B,"matches":arr(obj({"value":S,"start":I,"end":I})),"result":S,"match_count":I}),
    }
    for name in ("download_managed_model","check_managed_model_update","update_managed_model"):
        responses[name]=obj({"model":ref("ManagedModel"),"result":{"description":"Unmodified result of V-Scheduler weight pull/check-update/update. A duplicate download may return a message instead of a new task."}})
    components["DesensitizeResponse"]["properties"]["metadata"] = obj({"latency_ms":N,"engine":S,"rule_count":I})
    components["ImageDesensitizeResponse"]["properties"]["coordinates"]=nullable(arr(obj({"box":box,"quad":arr(arr(N))})))
    components["ImageDesensitizeResponse"]["properties"]["ledger"]=nullable(ref("ImageLedger"))
    components["ImageRestoreRequest"]["properties"]["ledger"]=ref("ImageLedger")
    components["ImageRestoreResponse"]["properties"]["report"]=arr(obj({"index":I,"restored":B,"error":S},["index","restored"]))
    components["ImageDesensitizeResponse"]["properties"]["metadata"]=obj({"ocr_engine":S,"ocr_blocks":I,"rebuilt_text_length":I,"normalized_matching":B,"matched_via":{"type":"object","additionalProperties":I},"suppressed_by_space":{"type":"object","additionalProperties":I},"validator_rejected":I,"gate_failure_policy":S,"adaptive":B,"scene":nullable(obj({"type":S,"signal_counts":{"type":"object","additionalProperties":I},"policy":{"type":"object","description":"Scene-specific matching policy; does not change the API fields."}})),"field_fallback_regions":I,"fallback_masked_lines":I,"secondary_ocr":obj({"enabled":B,"regions":I,"blocks":I,"reasons":{"type":"object","additionalProperties":I}}),"resized":B,"scale":N,"ocr":runtime})
    for name in ("DesensitizeOptions","DesensitizeTextRequest","ImageDesensitizeRequest"):
        components[name]["properties"]["level"]["description"]="Compatibility field, currently reserved; does not select a different rule set. Select rule IDs and enabled rules instead."
    components["DesensitizeOptions"]["properties"]["audit"]["description"]="Reserved compatibility flag; does not enable persistent audit logging."
    from app.services.scheduler import URL, UPSTREAM, APP_ID, router as scheduler
    from app.routers import rules, desensitize, models
    spec["components"]["securitySchemes"]={"SchedulerApplication":{"type":"http","scheme":"bearer","description":"Verified V-Scheduler application identity; not an ordinary VOS user or model API Key."}}
    seen=set()
    for router in (scheduler,rules.router,desensitize.router,models.router,app):
        for route in router.routes:
            if not isinstance(route,APIRoute) or not route.include_in_schema: continue
            name=route.endpoint.__name__
            for method in route.methods:
                if (route.path,method) in seen: continue
                seen.add((route.path,method));op=spec["paths"][route.path][method.lower()];code=str(route.status_code or 200)
                if name in responses:op["responses"][code]={"description":"Native application JSON response.","content":{"application/json":{"schema":responses[name]}}}
                op["security"]=[{"SchedulerApplication":[]}] if name=="bind" else []
                op["responses"].setdefault("default",{"description":"Check HTTP status and Content-Type. FastAPI detail is a string or validation error list; unexpected gateway/server errors can be plain text.","content":{"application/json":{"schema":obj({"detail":{"description":"Message or validation details."}})},"text/plain":{"schema":S}}})
                op["summary"]=name.replace("_", " ").capitalize()
                op["description"]= {"test_pattern":"Query parameters, not a JSON body. Invalid regular expressions return 422.","bind":"Internal automatic provisioning. Requires verified application identity, matching runtime settings, approved executors and a monotonic binding revision. Active work or conflicting revision returns 409; invalid binding returns 422. Do not edit this snapshot manually."}.get(name, "See the field contracts and the integration workflow for this native application operation.")
                op["x-contract-source"]=route.endpoint.__module__+"."+name
                if name=="bind":
                    op["requestBody"]={"required":True,"content":{"application/json":{"schema":obj({"protocol_version":{"type":"integer","const":1},"binding_revision":{"type":"integer","minimum":1},"app_id":{"type":"string","const":APP_ID},"url":{"type":"string","const":URL},"upstream_url":{"type":"string","const":UPSTREAM},"token":{"type":"string","minLength":32,"maxLength":4096,"writeOnly":True},"executor_token":{"type":"string","minLength":32,"maxLength":4096,"writeOnly":True},"models":{"type":"object","additionalProperties":S,"minProperties":1,"maxProperties":512},"gateway_executors":{"type":"object","additionalProperties":S,"maxProperties":512},"execution_settings":execution,"model_limits":{"type":"object","description":"Provisioned per-model limits from the controller; not a caller-chosen budget."}},["protocol_version","binding_revision","app_id","url","upstream_url","token","executor_token","models","execution_settings","model_limits"])}}}
    spec["info"]["description"]="Stateless text/image redaction and shared rule management on the trusted VOS application network. Native routes do not implement per-user model API Key authorization. Heavy NER/OCR additionally require Scheduler approval. Binding is an internal application-identity operation."
    app.openapi_schema=spec
    return spec
