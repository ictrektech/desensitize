import unittest
from unittest.mock import Mock, patch
from fastapi import HTTPException
from app.services import scheduler as client
from app.services.scheduling_options import queue_wait_seconds

class NativeQueueTests(unittest.TestCase):
    def test_wait_bounds(self):
        self.assertEqual(queue_wait_seconds({}),30)
        self.assertEqual(queue_wait_seconds({'x-vscheduler-queue-wait-seconds':'0'}),0)
        for value in ['-1','1.5','301','true','']:
            with self.assertRaises(HTTPException):
                queue_wait_seconds({'x-vscheduler-queue-wait-seconds':value})

    def test_admission_wait_preserves_request_priority_and_operator_scope(self):
        config={'url':client.URL,'token':'a'*64}
        headers={'x-vscheduler-queue-wait-seconds':'5','authorization':'Bearer test-admin'}
        body={'executor_id':'approved','model_id':'shared-model','upstream_url':'http://fixture/v1','execution_token':'x'*64,'scheduling':{'priority':'high','force_admission':True}}
        response=Mock(status_code=200)
        response.json.return_value={'code':'OK','data':{'permit_id':'permit'}}
        context=client.headers_context.set(headers)
        with patch.object(client.httpx,'request',return_value=response) as call:
            result=client.controller(config,'POST','/permits',body,'request-id')
        client.headers_context.reset(context)
        self.assertEqual(result['permit_id'],'permit')
        self.assertTrue(call.call_args.args[1].endswith('/permits/wait'))
        kwargs=call.call_args.kwargs
        self.assertEqual(kwargs['timeout'],13)
        self.assertEqual(kwargs['json'],{'request':body,'wait_seconds':5})
        self.assertEqual(kwargs['headers']['X-VScheduler-Admin-Authorization'],'Bearer test-admin')
        self.assertNotIn('authorization',kwargs['json'])

    def test_rejected_admission_never_unloads_another_request(self):
        config={'models':{'model':'approved'},'model_limits':{'model':{}}}
        unload=Mock()
        with patch.object(client,'required',return_value=True), patch.object(client,'read_config',return_value=config), patch.object(client,'controller',side_effect=HTTPException(429,'busy')):
            with self.assertRaises(HTTPException):
                with client.compute('model',unload):
                    self.fail('rejected work must never execute')
        unload.assert_not_called()
