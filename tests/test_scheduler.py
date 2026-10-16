import tempfile
import unittest
import json
import os
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.services import scheduler


class AdmissionTests(unittest.TestCase):
    def config(self):
        return {'app_id': scheduler.APP_ID, 'url': scheduler.URL, 'upstream_url': scheduler.UPSTREAM, 'token': 'a' * 32, 'models': {'model': 'app.model'}, 'gateway_executors': {'model': 'gateway.model'}, 'model_limits': {'model': {'duration_seconds': 10}}}

    def controller(self, config, method, path, body=None, key=''):
        self.calls.append((method, path, body))
        if path == '/permits':
            return {'permit_id': 'permit'}
        if path.endswith('/verify'):
            return {'state': 'active', 'lease_seconds': 30}
        return {}

    def setUp(self):
        self.calls = []
        self.token = scheduler.headers_context.set({})
        self.patches = [patch.object(scheduler, 'required', return_value=True), patch.object(scheduler, 'read_config', side_effect=self.config), patch.object(scheduler, 'controller', side_effect=self.controller)]
        for item in self.patches:
            item.start()

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()
        scheduler.headers_context.reset(self.token)

    def test_direct_call_claims_then_unloads_before_release(self):
        unload = Mock(side_effect=lambda: self.calls.append(('unload', '', None)))
        with scheduler.compute('model', unload):
            self.assertEqual(self.calls[-1][1], '/permits/permit/verify')
            self.assertTrue(self.calls[-1][2]['claim'])
        self.assertEqual([row[1] for row in self.calls], ['/permits', '/permits/permit/verify', '', '/permits/permit/release'])
        self.assertTrue(self.calls[-1][2]['stopped'])
        self.assertEqual(scheduler.active, 0)

    def test_gateway_proof_reuses_one_reservation(self):
        scheduler.headers_context.set({'x-vscheduler-permit-id': 'inherited', 'x-vscheduler-executor-id': 'gateway.model', 'x-vscheduler-execution-token': 'b' * 32})
        with scheduler.compute('model', Mock()):
            pass
        self.assertEqual([row[1] for row in self.calls], ['/permits/inherited/verify'])

    def test_spoofed_gateway_proof_does_not_execute(self):
        scheduler.headers_context.set({'x-vscheduler-permit-id': 'forged'})
        with self.assertRaises(HTTPException):
            with scheduler.compute('model', Mock()):
                self.fail('unverified compute ran')
        self.assertEqual(self.calls, [])

    def test_unapproved_model_does_not_execute(self):
        with self.assertRaises(HTTPException):
            with scheduler.compute('unknown', Mock()):
                self.fail('unapproved compute ran')
        self.assertEqual(self.calls, [])

    def test_unknown_stop_never_releases_as_stopped(self):
        with self.assertRaises(RuntimeError):
            with scheduler.compute('model', Mock(side_effect=RuntimeError('unload failed'))):
                pass
        self.assertFalse(self.calls[-1][2]['stopped'])
        self.assertEqual(scheduler.active, 0)

    def test_direct_call_cannot_exceed_calibrated_input(self):
        with self.assertRaises(HTTPException):
            with scheduler.compute('model', Mock(), {'duration_seconds': 11}):
                self.fail('oversized compute ran')
        self.assertEqual(self.calls, [])
        self.assertEqual(scheduler.active, 0)


class BindingTests(unittest.TestCase):
    def test_binding_requires_scheduler_identity_and_preserves_revision(self):
        app = FastAPI()
        app.include_router(scheduler.router)
        config = {'protocol_version': 1, 'binding_revision': 2, 'app_id': scheduler.APP_ID, 'url': scheduler.URL, 'upstream_url': scheduler.UPSTREAM, 'token': 'a' * 32, 'executor_token': 'b' * 32, 'models': {'model': 'app.model'}}
        config['execution_settings'] = scheduler.execution_settings()
        config['model_limits'] = {'model': {'duration_seconds': 10}}
        client = AsyncMock()
        client.__aenter__.return_value = client
        executor = {'id': 'app.model', 'app_id': scheduler.APP_ID, 'contract_version': '1', 'task_type': 'model.infer', 'upstream_urls': [scheduler.UPSTREAM]}
        with tempfile.TemporaryDirectory() as directory, patch.object(scheduler, 'config_path', return_value=Path(directory) / 'binding.json'), patch.object(scheduler.httpx, 'AsyncClient', return_value=client), patch.object(scheduler, 'controller', return_value=[executor]), patch.dict(os.environ, {'VOS_USERINFO_URL': 'http://identity/userinfo'}):
            client.get.return_value = httpx.Response(200, json={'sub': 'ordinary-user', 'enable': 1}, request=httpx.Request('GET', 'http://identity/userinfo'))
            with TestClient(app) as api:
                self.assertEqual(api.post('/api/v1/scheduler/binding', json=config).status_code, 403)
                client.get.return_value = httpx.Response(200, json={'sub': 'com.ictrek.v-scheduler', 'enable': 1}, request=httpx.Request('GET', 'http://identity/userinfo'))
                response = api.post('/api/v1/scheduler/binding', json=config)
                self.assertEqual(response.status_code, 200, response.text)
                saved = scheduler.config_path()
                self.assertEqual(saved.stat().st_mode & 0o777, 0o600)
                self.assertEqual(json.loads(saved.read_text()), config)
                self.assertEqual(api.post('/api/v1/scheduler/binding', json=config).status_code, 200)
                self.assertNotIn(config['token'], api.get('/api/v1/scheduler/binding').text)
                self.assertEqual(api.post('/api/v1/scheduler/binding', json={**config, 'binding_revision': 1}).status_code, 409)


if __name__ == '__main__':
    unittest.main()
