import base64
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
from unittest.mock import patch
import urllib.error
from PIL import Image

source = Path(__file__).resolve().parents[1] / 'skill/scripts/imagegen.py'
spec = importlib.util.spec_from_file_location('imagegen', source)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
buf = io.BytesIO()
Image.new('RGB', (8, 8), 'red').save(buf, format='PNG')
png = buf.getvalue()

class Response(io.BytesIO):
    pass

class Opener:
    def __init__(self, payloads):
        self.payloads = iter(payloads)
        self.requests = []
    def open(self, req, timeout):
        self.requests.append(req)
        return Response(next(self.payloads))

with tempfile.TemporaryDirectory() as td:
    home = Path(td)
    config = 'model_provider="custom"\n[model_providers.custom]\nbase_url="http://127.0.0.1:9999/v1"\nenv_key="TEST_IMAGE_KEY"\nrequires_openai_auth=true\n'
    (home/'config.toml').write_text('\ufeff' + config, encoding='utf-8')
    (home/'auth.json').write_text('\ufeff' + json.dumps({'OPENAI_API_KEY':'auth-key','tokens':{'access_token':'do-not-use'}}), encoding='utf-8')
    assert m.resolve(home, {'TEST_IMAGE_KEY':'env-key'}) == ('http://127.0.0.1:9999/v1','env-key')
    assert m.resolve(home, {})[1] == 'auth-key'
    (home/'config.toml').write_text(config.replace('requires_openai_auth=true', 'requires_openai_auth=false'))
    try: m.resolve(home, {})
    except m.ImageError: pass
    else: raise AssertionError('Must not reuse auth without provider opt-in')
    (home/'config.toml').write_text('profile="image"\n' + config + '\n[profiles.image]\nmodel_provider="second"\n[model_providers.second]\nbase_url="https://example.invalid/v1"\nexperimental_bearer_token="second-key"\n')
    assert m.resolve(home, {}) == ('https://example.invalid/v1','second-key')
    assert m.saved_model(home, 'https://example.invalid/v1') is None
    m.saved_model(home, 'https://example.invalid/v1', 'image-test')
    assert m.saved_model(home, 'https://example.invalid/v1') == 'image-test'
    assert m.saved_model(home, 'https://other.invalid/v1') is None
    saved = (home/'third-party-imagegen.json').read_text()
    assert 'https://' not in saved and 'second-key' not in saved
    m.saved_model(home, 'https://other.invalid/v1', 'other-image')
    assert m.saved_model(home, 'https://example.invalid/v1') == 'image-test'
    with patch.dict(os.environ,{'CODEX_HOME':str(home)}), patch('sys.argv',['imagegen','--set-model','saved-by-cli']), patch.object(m.urllib.request,'build_opener',side_effect=AssertionError('set-model must be offline')):
        assert m.main() == 0
    assert m.saved_model(home, 'https://example.invalid/v1') == 'saved-by-cli'
    args = SimpleNamespace(model='test-model', prompt='测试图片', size=None, quality=None, background=None,response_format=None,command='generate',timeout=10)
    op = Opener([json.dumps({'data':[{'b64_json':base64.b64encode(png).decode()}]}).encode()])
    with patch.object(m.urllib.request, 'build_opener', return_value=op):
        assert m.request_image('https://example.invalid/v1','test-key',args) == png
    req = op.requests[0]
    assert req.full_url.endswith('/v1/images/generations')
    assert req.get_header('Authorization') == 'Bearer test-key'
    payload = json.loads(req.data)
    assert payload == {'model':'test-model','prompt':'测试图片','n':1}
    inp = home/'input.png'
    inp.write_bytes(png)
    args.command, args.image = 'edit', inp
    op = Opener([json.dumps({'data':[{'url':'https://images.invalid/output.png'}]}).encode(),png])
    with patch.object(m.urllib.request, 'build_opener', return_value=op):
        assert m.request_image('https://example.invalid/v1','test-key',args) == png
    assert op.requests[0].full_url.endswith('/v1/images/edits')
    assert b'name="image"' in op.requests[0].data and png in op.requests[0].data
    assert isinstance(op.requests[1],str), 'Download must not include Authorization'
    out = home/'new/result.png'
    m.save_image(png,out)
    with Image.open(out) as im: assert im.size == (8,8)
    try: m.save_image(png,out)
    except m.ImageError: pass
    else: raise AssertionError('Overwrite allowed')
    cli_out = home/'remembered.png'
    op = Opener([json.dumps({'data':[{'b64_json':base64.b64encode(png).decode()}]}).encode()])
    with patch.dict(os.environ,{'CODEX_HOME':str(home)}), patch('sys.argv',['imagegen','generate','--prompt','p','--out',str(cli_out)]), patch.object(m.urllib.request,'build_opener',return_value=op):
        assert m.main() == 0
    assert json.loads(op.requests[0].data)['model'] == 'saved-by-cli'
    assert cli_out.is_file()
    assert m.NoRedirect().redirect_request(None,None,302,'',{},'https://other.invalid') is None
    with patch.dict(os.environ,{'CODEX_HOME':str(home)}), patch('sys.argv',['imagegen','--check']), patch.object(m.urllib.request,'build_opener',side_effect=AssertionError('check must be offline')):
        assert m.main() == 0
    with patch.dict(os.environ,{'CODEX_HOME':str(home)}), patch('sys.argv',['imagegen','generate','--model','m','--prompt','p','--out',str(out)]), patch.object(m.urllib.request,'build_opener',side_effect=AssertionError('existing output must fail before request')):
        assert m.main() == 1
    moderation = urllib.error.HTTPError(
        'https://example.invalid/v1/images/generations', 400, 'bad request', {},
        io.BytesIO(json.dumps({'error': {'code': 'moderation_blocked'}}).encode()),
    )
    assert m.classify_http_error(moderation) == ('moderation', ['moderation_blocked'])

    def http_error(code, body):
        return urllib.error.HTTPError('https://example.invalid', code, 'error', {}, io.BytesIO(json.dumps(body).encode()))
    def no_channel(model):
        return http_error(503, {'error': {'message': f'No available channel for model {model} under group default, key sk-secret123', 'type': 'new_api_error', 'code': 'model_not_found'}})
    kind, ids = m.classify_http_error(no_channel('gpt-image-1'))
    assert kind == 'model' and ids == ['new_api_error', 'model_not_found'] and 'sk-secret123' not in str(ids)
    assert m.classify_http_error(http_error(503, {'error': {'message': 'auth_unavailable: no auth available (last upstream error: {"code":"server_is_overloaded"})'}}))[0] == 'transient'
    assert m.classify_http_error(http_error(400, {'error': {'message': 'prompt is required'}}))[0] == 'prompt'
    assert m.classify_http_error(http_error(401, {'error': {'message': 'Invalid token'}}))[0] == 'auth'
    assert m.classify_http_error(http_error(503, {}))[0] == 'server'
    assert m.classify_http_error(http_error(404, {}))[0] == 'route'

    class Router:
        def __init__(self, handler):
            self.handler, self.requests = handler, []
        def open(self, req, timeout):
            self.requests.append(req)
            return Response(self.handler(req))
    def provider(working=(), status=None):
        def handler(req):
            if req.full_url.endswith('/models'):
                return json.dumps({'data': [{'id': 'gpt-4o'}, {'id': 'flux-image'}]}).encode()
            payload = json.loads(req.data)
            if status:
                raise http_error(status, {'error': {'message': 'Invalid token'}})
            if payload['model'] not in working:
                raise no_channel(payload['model'])
            if 'prompt' not in payload:
                raise http_error(400, {'error': {'message': 'prompt is required'}})
            return json.dumps({'data': [{'b64_json': base64.b64encode(png).decode()}]}).encode()
        return Router(handler)
    def run(argv, opener):
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch.dict(os.environ, {'CODEX_HOME': str(home)}), patch('sys.argv', ['imagegen', *argv]),                 patch.object(m.urllib.request, 'build_opener', return_value=opener),                 contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            return m.main(), stdout.getvalue(), stderr.getvalue()
    endpoint = 'https://example.invalid/v1'

    op = provider(working=('gpt-image-2',))
    code, stdout, _ = run(['discover'], op)
    assert code == 0 and 'gpt-image-2' in stdout
    assert m.saved_model(home, endpoint) == 'gpt-image-2'
    probes = [json.loads(r.data) for r in op.requests if not r.full_url.endswith('/models')]
    assert [p['model'] for p in probes] == ['saved-by-cli', 'flux-image', 'gpt-image-2'], probes
    assert all('prompt' not in p for p in probes), 'Probes must never send a prompt'

    code, stdout, _ = run(['--check'], provider())
    assert code == 0 and 'gpt-image-2（本地记忆）' in stdout and '远程服务' in stdout and 'second-key' not in stdout

    stale_out = home/'stale.png'
    code, _, stderr = run(['generate', '--prompt', 'p', '--out', str(stale_out)], provider())
    assert code == m.EXIT_MODEL and 'discover' in stderr and '已清除' in stderr and 'sk-secret123' not in stderr
    assert m.saved_model(home, endpoint) is None and not stale_out.exists()

    code, _, stderr = run(['generate', '--prompt', 'p', '--out', str(stale_out)], provider())
    assert code == m.EXIT_MODEL and 'discover' in stderr, 'Missing model must point to discover'

    code, _, stderr = run(['discover'], provider())
    assert code == m.EXIT_MODEL and 'gpt-image-1：无可用渠道' in stderr and m.saved_model(home, endpoint) is None

    code, _, _ = run(['discover'], provider(status=401))
    assert code == m.EXIT_AUTH

    code, stdout, _ = run(['generate', '--model', 'gpt-image-1', '--prompt', 'p', '--out', str(stale_out)], provider(working=('gpt-image-1',)))
    assert code == 0 and stale_out.is_file() and m.saved_model(home, endpoint) == 'gpt-image-1', 'Successful model must be remembered'
print('PASS: config/auth priority, profile, model persistence, offline check, generation/edit payloads, credential isolation, image validation/save, overwrite prevention, redirect protection, error classification, model discovery, stale model invalidation')
