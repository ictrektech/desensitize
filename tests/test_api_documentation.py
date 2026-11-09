import unittest
from fastapi.testclient import TestClient
from app.main import app

class ApiDocumentationTests(unittest.TestCase):
    def test_all_success_contracts_and_references(self):
        spec=app.openapi()
        operations=[o for m in spec["paths"].values() for o in m.values()]
        self.assertEqual(len(operations),21)
        for op in operations:
            for status,response in op["responses"].items():
                if status=="204": self.assertNotIn("content",response)
                elif str(status).startswith("2"): self.assertTrue(response["content"]["application/json"]["schema"])
        def check(value):
            if isinstance(value,dict):
                if "$ref" in value:
                    target=spec
                    for part in value["$ref"][2:].split("/"):target=target[part]
                for child in value.values():check(child)
            elif isinstance(value,list):
                for child in value:check(child)
        check(spec)
        op=spec["paths"]["/api/v1/rules/test"]["post"]
        self.assertNotIn("requestBody",op)
        self.assertEqual({p["name"] for p in op["parameters"]},{"pattern","text","placeholder"})
        self.assertEqual(spec["paths"]["/api/v1/scheduler/binding"]["post"]["security"],[{"SchedulerApplication":[]}])

    def test_proxy_reference_and_native_test_operation(self):
        client=TestClient(app,root_path="/api/com.ictrek.desensitize")
        page=client.get("/docs")
        self.assertEqual(page.status_code,200)
        self.assertIn("url: 'openapi.json'",page.text)
        good=client.post("/api/v1/rules/test",params={"pattern":"[0-9]+","text":"abc123"})
        self.assertEqual(good.json(),{"matched":True,"matches":[{"value":"123","start":3,"end":6}],"result":"abc[REDACTED]","match_count":1})
        self.assertEqual(client.post("/api/v1/rules/test",params={"pattern":"[","text":"x"}).status_code,422)
        self.assertEqual(client.post("/api/v1/desensitize/image",content=b"not-json",headers={"content-type":"application/octet-stream"}).status_code,415)
