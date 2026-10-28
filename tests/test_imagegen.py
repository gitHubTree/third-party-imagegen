import ast
import base64
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import ssl
import struct
import tempfile
from types import SimpleNamespace
from unittest.mock import patch
import urllib.error
import urllib.request
import zlib

root = Path(__file__).resolve().parents[1]
source = root / 'skill/scripts/imagegen.py'
spec = importlib.util.spec_from_file_location('imagegen', source)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

def make_png(width=8, height=8):
    """A valid RGB PNG without Pillow, so the suite also runs where Pillow is absent."""
    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data))
    raw = b''.join(b'\x00' + b'\xff\x00\x00' * width for _ in range(height))
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(raw)) + chunk(b'IEND', b''))
png = make_png()
pillow = m._pillow()

# Old interpreters must reach the friendly version message instead of a SyntaxError.
for path in (source, root / 'install.py'):
    ast.parse(path.read_text(encoding='utf-8'), feature_version=(3, 8))

class Response(io.BytesIO):
    pass

class Opener:
    def __init__(self, payloads):
        self.payloads = iter(payloads)
        self.requests = []
    def open(self, req, timeout):
        self.requests.append(req)
        return Response(next(self.payloads))

class Router:
    def __init__(self, handler):
        self.handler, self.requests = handler, []
    def open(self, req, timeout):
        self.requests.append(req)
        return Response(self.handler(req))

def http_error(code, body):
    return urllib.error.HTTPError('https://example.invalid', code, 'error', {}, io.BytesIO(json.dumps(body).encode()))

def no_channel(model):
    return http_error(503, {'error': {'message': f'No available channel for model {model} under group default, key sk-secret123', 'type': 'new_api_error', 'code': 'model_not_found'}})

def provider(working=(), status=None, failure=None):
    def handler(req):
        if failure:
            raise failure
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

with tempfile.TemporaryDirectory() as td:
    home = Path(td)
    endpoint = 'https://example.invalid/v1'

    def run(argv, opener=None):
        stdout, stderr = io.StringIO(), io.StringIO()
        offline = {'side_effect': AssertionError('must stay offline')}
        with patch.dict(os.environ, {'CODEX_HOME': str(home)}), patch('sys.argv', ['imagegen', *argv]), \
                patch.object(m.urllib.request, 'build_opener', **({'return_value': opener} if opener else offline)), \
                contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            return m.main(), stdout.getvalue(), stderr.getvalue()

    # Config and credential resolution.
    config = 'model_provider="custom"\n[model_providers.custom]\nbase_url="http://127.0.0.1:9999/v1"\nenv_key="TEST_IMAGE_KEY"\nrequires_openai_auth=true\n'
    (home/'config.toml').write_text('﻿' + config, encoding='utf-8')
    (home/'auth.json').write_text('﻿' + json.dumps({'OPENAI_API_KEY':'auth-key','tokens':{'access_token':'do-not-use'}}), encoding='utf-8')
    assert m.resolve(home, {'TEST_IMAGE_KEY':'env-key'}) == ('http://127.0.0.1:9999/v1','env-key')
    assert m.resolve(home, {})[1] == 'auth-key'
    (home/'config.toml').write_text(config.replace('requires_openai_auth=true', 'requires_openai_auth=false'))
    try: m.resolve(home, {})
    except m.ImageError: pass
    else: raise AssertionError('Must not reuse auth without provider opt-in')
    (home/'config.toml').write_text('profile="image"\n' + config + '\n[profiles.image]\nmodel_provider="second"\n[model_providers.second]\nbase_url="https://example.invalid/v1"\nexperimental_bearer_token="second-key"\n')
    assert m.resolve(home, {}) == (endpoint,'second-key')

    # Model memory.
    assert m.saved_model(home, endpoint) is None
    m.saved_model(home, endpoint, 'image-test')
    assert m.saved_model(home, endpoint) == 'image-test'
    assert m.saved_model(home, 'https://other.invalid/v1') is None
    saved = (home/'third-party-imagegen.json').read_text()
    assert 'https://' not in saved and 'second-key' not in saved
    m.saved_model(home, 'https://other.invalid/v1', 'other-image')
    assert m.saved_model(home, endpoint) == 'image-test'
    assert run(['--set-model','saved-by-cli'])[0] == 0
    assert m.saved_model(home, endpoint) == 'saved-by-cli'

    # Request payloads and credential isolation.
    args = SimpleNamespace(model='test-model', prompt='测试图片', size=None, quality=None, background=None,response_format=None,command='generate',timeout=10)
    op = Opener([json.dumps({'data':[{'b64_json':base64.b64encode(png).decode()}]}).encode()])
    with patch.object(m.urllib.request, 'build_opener', return_value=op):
        assert m.request_image(endpoint,'test-key',args) == png
    req = op.requests[0]
    assert req.full_url.endswith('/v1/images/generations')
    assert req.get_header('Authorization') == 'Bearer test-key'
    assert json.loads(req.data) == {'model':'test-model','prompt':'测试图片','n':1}
    op = Opener([json.dumps({'data':[{'b64_json':'data:image/png;base64,' + base64.encodebytes(png).decode()}]}).encode()])
    with patch.object(m.urllib.request, 'build_opener', return_value=op):
        assert m.request_image(endpoint,'test-key',args) == png, 'Data URI prefix and line breaks must be accepted'
    inp = home/'input.png'
    inp.write_bytes(png)
    args.command, args.image = 'edit', inp
    op = Opener([json.dumps({'data':[{'url':'https://images.invalid/output.png'}]}).encode(),png])
    with patch.object(m.urllib.request, 'build_opener', return_value=op) as build:
        assert m.request_image(endpoint,'test-key',args) == png
    assert op.requests[0].full_url.endswith('/v1/images/edits')
    assert b'name="image"' in op.requests[0].data and b'Content-Type: image/png' in op.requests[0].data and png in op.requests[0].data
    assert isinstance(op.requests[1],str), 'Download must not include Authorization'
    api_handlers, download_handlers = (call.args for call in build.call_args_list)
    assert any(isinstance(h, m.NoRedirect) for h in api_handlers), 'API calls must not follow redirects'
    assert not any(isinstance(h, m.NoRedirect) for h in download_handlers), 'Key-less downloads may follow redirects'
    webp = home/'input.webp'
    webp.write_bytes(b'RIFF\x00\x00\x00\x00WEBPVP8 ')
    assert b'Content-Type: image/webp' in m.multipart({'model': 'x'}, webp)[0]
    bad = home/'input.txt'
    bad.write_bytes(b'not an image')
    try: m.multipart({'model': 'x'}, bad)
    except m.ImageError: pass
    else: raise AssertionError('Invalid input image accepted')
    assert m.NoRedirect().redirect_request(None,None,302,'',{},'https://other.invalid') is None

    # Loopback endpoints bypass system proxies; remote ones keep them.
    with patch.object(m.urllib.request, 'build_opener') as build:
        m._opener('http://127.0.0.1:15721/v1')
        m._opener('https://example.invalid/v1')
    loopback, remote = (call.args for call in build.call_args_list)
    assert any(isinstance(h, urllib.request.ProxyHandler) and h.proxies == {} for h in loopback)
    assert not any(isinstance(h, urllib.request.ProxyHandler) for h in remote)

    # Saving: exact formats are written as-is; mismatches convert with Pillow or follow the actual format.
    out = home/'new/result.png'
    assert m.save_image(png,out) == (out, None) and out.read_bytes() == png
    try: m.save_image(png,out)
    except m.ImageError: pass
    else: raise AssertionError('Overwrite allowed')
    try: m.save_image(b'garbage', home/'garbage.png')
    except m.ImageError: pass
    else: raise AssertionError('Invalid image saved')
    with patch.object(m, '_pillow', return_value=None):
        path, note = m.save_image(png, home/'no-pillow.jpg')
    assert path == home/'no-pillow.png' and path.read_bytes() == png and 'Pillow' in note
    if pillow:
        path, note = m.save_image(png, home/'converted.jpg')
        assert path == home/'converted.jpg' and note is None and m.image_format(path.read_bytes()) == 'JPEG'

    # CLI generation with remembered model, offline check, overwrite guard.
    cli_out = home/'remembered.png'
    op = Opener([json.dumps({'data':[{'b64_json':base64.b64encode(png).decode()}]}).encode()])
    assert run(['generate','--prompt','p','--out',str(cli_out)], op)[0] == 0
    assert json.loads(op.requests[0].data)['model'] == 'saved-by-cli'
    assert cli_out.is_file()
    code, stdout, _ = run(['--check'])
    assert code == 0 and 'saved-by-cli（本地记忆）' in stdout and m.__version__ in stdout and 'Pillow' in stdout
    assert run(['generate','--model','m','--prompt','p','--out',str(out)])[0] == 1, 'Existing output must fail before request'

    # Prompt files bypass shell quoting differences between PowerShell, bash and zsh.
    prompt_file = home/'prompt.txt'
    shell_hostile = '价格 $100，带 "引号"、`反引号` 和\n第二行'
    prompt_file.write_text('﻿' + shell_hostile + '\n', encoding='utf-8')
    op = Opener([json.dumps({'data':[{'b64_json':base64.b64encode(png).decode()}]}).encode()])
    assert run(['generate','--prompt-file',str(prompt_file),'--out',str(home/'from-file.png')], op)[0] == 0
    assert json.loads(op.requests[0].data)['prompt'] == shell_hostile
    for argv in (['generate','--prompt','p','--prompt-file',str(prompt_file),'--out',str(home/'x.png')],
                 ['discover','--prompt-file',str(prompt_file)],
                 ['generate','--prompt-file',str(home/'missing.txt'),'--out',str(home/'x.png')]):
        try: run(argv)
        except SystemExit as exc: assert exc.code == 2, argv
        else: raise AssertionError(argv)
    with patch.object(m.sys, 'version_info', (3, 10, 0)):
        code, _, stderr = run(['--check'])
    assert code == m.EXIT_CONFIG and '3.11' in stderr

    # Error classification never echoes free text.
    moderation = http_error(400, {'error': {'code': 'moderation_blocked'}})
    assert m.classify_http_error(moderation) == ('moderation', ['moderation_blocked'])
    kind, ids = m.classify_http_error(no_channel('gpt-image-1'))
    assert kind == 'model' and ids == ['new_api_error', 'model_not_found'] and 'sk-secret123' not in str(ids)
    assert m.classify_http_error(http_error(503, {'error': {'message': 'auth_unavailable: no auth available (last upstream error: {"code":"server_is_overloaded"})'}}))[0] == 'transient'
    assert m.classify_http_error(http_error(400, {'error': {'message': 'prompt is required'}}))[0] == 'prompt'
    assert m.classify_http_error(http_error(401, {'error': {'message': 'Invalid token'}}))[0] == 'auth'
    assert m.classify_http_error(http_error(503, {}))[0] == 'server'
    assert m.classify_http_error(http_error(404, {}))[0] == 'route'

    # Discovery.
    op = provider(working=('gpt-image-2',))
    code, stdout, _ = run(['discover'], op)
    assert code == 0 and 'gpt-image-2' in stdout
    assert m.saved_model(home, endpoint) == 'gpt-image-2'
    probes = [json.loads(r.data) for r in op.requests if not r.full_url.endswith('/models')]
    assert [p['model'] for p in probes] == ['saved-by-cli', 'flux-image', 'gpt-image-2'], probes
    assert all('prompt' not in p for p in probes), 'Probes must never send a prompt'
    code, stdout, _ = run(['--check'])
    assert code == 0 and 'gpt-image-2（本地记忆）' in stdout and '远程服务' in stdout and 'second-key' not in stdout

    # Stale memory is dropped; a missing model points to discover.
    stale_out = home/'stale.png'
    code, _, stderr = run(['generate', '--prompt', 'p', '--out', str(stale_out)], provider())
    assert code == m.EXIT_MODEL and 'discover' in stderr and '已清除' in stderr and 'sk-secret123' not in stderr
    assert m.saved_model(home, endpoint) is None and not stale_out.exists()
    code, _, stderr = run(['generate', '--prompt', 'p', '--out', str(stale_out)])
    assert code == m.EXIT_MODEL and 'discover' in stderr, 'Missing model must point to discover'
    code, _, stderr = run(['discover'], provider())
    assert code == m.EXIT_MODEL and 'gpt-image-1：无可用渠道' in stderr and m.saved_model(home, endpoint) is None
    assert run(['discover'], provider(status=401))[0] == m.EXIT_AUTH

    # A read-only Codex home (sandbox) must not turn a found model into a failure.
    with patch.object(m, '_store', side_effect=PermissionError()):
        code, stdout, _ = run(['discover'], provider(working=('gpt-image-2',)))
    assert code == 0 and '--model gpt-image-2' in stdout and m.saved_model(home, endpoint) is None

    # Successful models are remembered; a damaged memory file is ignored and rewritten.
    (home/'third-party-imagegen.json').write_text('{broken', encoding='utf-8')
    assert m.saved_model(home, endpoint) is None
    code, stdout, _ = run(['generate', '--model', 'gpt-image-1', '--prompt', 'p', '--out', str(stale_out)], provider(working=('gpt-image-1',)))
    assert code == 0 and stale_out.is_file() and m.saved_model(home, endpoint) == 'gpt-image-1', 'Successful model must be remembered'

    # Transport failures: blocked or refused requests were never sent; timeouts are unknown.
    blocked = urllib.error.URLError(PermissionError(13, 'denied'))
    code, _, stderr = run(['discover'], provider(failure=blocked))
    assert code == m.EXIT_NETWORK and '沙箱' in stderr
    code, _, stderr = run(['discover'], provider(failure=urllib.error.URLError(ConnectionRefusedError())))
    assert code == m.EXIT_NETWORK and 'CC-Switch' in stderr
    certificate = urllib.error.URLError(ssl.SSLCertVerificationError(1, 'certificate verify failed'))
    code, _, stderr = run(['discover'], provider(failure=certificate))
    assert code == m.EXIT_NETWORK and 'Install Certificates' in stderr
    code, _, stderr = run(['generate', '--prompt', 'p', '--out', str(home/'timeout.png')], provider(failure=TimeoutError()))
    assert code == m.EXIT_FAILED and '结果未知' in stderr
    code, _, stderr = run(['generate', '--prompt', 'p', '--out', str(home/'odd.png')], provider(failure=RuntimeError('secret detail')))
    assert code == m.EXIT_FAILED and 'RuntimeError' in stderr and 'secret detail' not in stderr
print('PASS: imagegen (Pillow ' + ('present' if pillow else 'absent') + ')')
