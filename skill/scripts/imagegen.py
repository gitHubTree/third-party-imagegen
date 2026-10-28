#!/usr/bin/env python3
"""Generate/edit one image using the selected Codex provider. Python 3.11+."""
import argparse
import base64
import hashlib
import io
import ipaddress
import json
import os
from pathlib import Path
import re
import socket
import sys
import tomllib
import uuid
import urllib.error
import urllib.parse
import urllib.request

# Exit codes let the caller branch; only EXIT_TRANSIENT suggests a later retry may succeed.
EXIT_FAILED, EXIT_CONFIG, EXIT_AUTH, EXIT_MODEL, EXIT_TRANSIENT, EXIT_MODERATION = 1, 3, 4, 5, 6, 7
CANDIDATES = ('gpt-image-2', 'gpt-image-1.5', 'gpt-image-1', 'gpt-image-1-mini', 'dall-e-3')
PROBE_LIMIT = 10


class ImageError(Exception):
    def __init__(self, message, code=EXIT_FAILED):
        super().__init__(message)
        self.code = code


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # Never forward provider credentials to a redirected endpoint.


def _resolve(home, environ):
    """Return provider name, base URL, Key and a Key source label that never contains the Key."""
    try:
        config = tomllib.loads((home / 'config.toml').read_text(encoding='utf-8-sig'))
        # Profiles can override provider selection; do not silently use the root provider.
        profile = config.get('profile')
        if profile:
            selected = config.get('profiles', {}).get(profile)
            if not isinstance(selected, dict):
                raise ImageError('默认 profile 不存在，请检查 Codex 配置。', EXIT_CONFIG)
            config = {**config, **selected}
        name = config.get('model_provider')
        provider = config.get('model_providers', {}).get(name)
        if not isinstance(provider, dict):
            raise ImageError('未找到当前自定义供应商，请先在 CC-Switch 中启用供应商。', EXIT_CONFIG)
        base = provider.get('base_url', '')
        url = urllib.parse.urlsplit(base)
        if url.scheme not in ('http', 'https') or not url.hostname or url.username or url.password or url.query or url.fragment:
            raise ImageError('供应商 base_url 无效，应为兼容 API 基础地址。', EXIT_CONFIG)
        env_key = provider.get('env_key', '')
        key = environ.get(env_key, '') if env_key else ''
        source = '环境变量 ' + str(env_key)
        if not key:
            key, source = provider.get('experimental_bearer_token', ''), 'experimental_bearer_token'
        if not key and provider.get('requires_openai_auth') is True:
            auth = home / 'auth.json'
            if auth.is_file():
                key, source = json.loads(auth.read_text(encoding='utf-8-sig')).get('OPENAI_API_KEY', ''), 'auth.json'
        if not isinstance(key, str) or not key.strip() or '\n' in key or '\r' in key:
            raise ImageError('当前供应商 Key 不可用；检查 env_key 或 auth.json 中的 OPENAI_API_KEY，不必另申请官方 Key。', EXIT_CONFIG)
        return name, base.rstrip('/'), key.strip(), source
    except ImageError:
        raise
    except (OSError, ValueError, TypeError, AttributeError):
        raise ImageError('无法读取 Codex 配置；未输出配置或凭据。', EXIT_CONFIG) from None


def resolve(home, environ):
    _, base, key, _ = _resolve(home, environ)
    return base, key


def _is_loopback(host):
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return host == 'localhost'


def _settings(home):
    path = home / 'third-party-imagegen.json'
    settings = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
    if not isinstance(settings, dict) or not all(isinstance(v, str) for v in settings.values()):
        raise ValueError()
    return path, settings


def _store(home, path, settings):
    home.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        temporary.write_text(json.dumps(settings, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()


def saved_model(home, base, model=None):
    """Remember only a model per endpoint fingerprint; never persist URL or Key."""
    fingerprint = hashlib.sha256(base.encode()).hexdigest()
    try:
        path, settings = _settings(home)
        if model is None:
            return settings.get(fingerprint)
        model = model.strip()
        if not model:
            raise ImageError('图片模型名不能为空。')
        if settings.get(fingerprint) != model:
            settings[fingerprint] = model
            _store(home, path, settings)
        return model
    except (OSError, ValueError, TypeError):
        raise ImageError('无法读取或保存本地图片模型设置，请检查 third-party-imagegen.json。') from None


def forget_model(home, base):
    """Drop a stale model; a local proxy keeps one URL while its upstream changes."""
    fingerprint = hashlib.sha256(base.encode()).hexdigest()
    try:
        path, settings = _settings(home)
        if settings.pop(fingerprint, None) is not None:
            _store(home, path, settings)
        return True
    except (OSError, ValueError, TypeError):
        return False


def multipart(fields, image):
    from PIL import Image
    try:
        data = image.read_bytes()
        with Image.open(io.BytesIO(data)) as im:
            fmt = im.format
            im.verify()
        mime, suffix = {'PNG': ('image/png', 'png'), 'JPEG': ('image/jpeg', 'jpg'), 'WEBP': ('image/webp', 'webp')}[fmt]
    except (OSError, ValueError, KeyError):
        raise ImageError('输入图片须为有效的 PNG、JPEG 或 WebP。') from None
    boundary = 'imagegen-' + uuid.uuid4().hex
    chunks = []
    for name, value in fields.items():
        chunks.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode())
    chunks.append(f'--{boundary}\r\nContent-Disposition: form-data; name="image"; filename="input.{suffix}"\r\nContent-Type: {mime}\r\n\r\n'.encode() + data + b'\r\n')
    chunks.append(f'--{boundary}--\r\n'.encode())
    return b''.join(chunks), 'multipart/form-data; boundary=' + boundary


def request_image(base, key, args):
    fields = {'model': args.model, 'prompt': args.prompt, 'n': 1}
    for name in ('size', 'quality', 'background', 'response_format'):
        value = getattr(args, name)
        if value is not None:
            fields[name] = value
    if args.command == 'edit':
        body, content_type = multipart(fields, args.image)
        endpoint = '/images/edits'
    else:
        body, content_type = json.dumps(fields).encode(), 'application/json'
        endpoint = '/images/generations'
    req = urllib.request.Request(base + endpoint, data=body, headers={
        'Authorization': 'Bearer ' + key, 'Content-Type': content_type,
    })
    # urllib has no automatic retry; honors standard proxy environment variables.
    with urllib.request.build_opener(NoRedirect()).open(req, timeout=args.timeout) as response:
        payload = json.load(response)
    try:
        item = payload['data'][0]
        if item.get('b64_json'):
            return base64.b64decode(item['b64_json'], validate=True)
        url = urllib.parse.urlsplit(item['url'])
        if url.scheme not in ('https', 'http') or not url.hostname or url.username or url.password:
            raise ValueError()
        # A separate request downloads the result without the provider Key.
        with urllib.request.build_opener(NoRedirect()).open(item['url'], timeout=args.timeout) as response:
            return response.read()
    except (KeyError, IndexError, TypeError, ValueError):
        raise ImageError('响应没有有效的 data[0].b64_json 或图片 URL；不要自动重复生成。') from None


def save_image(data, output):
    from PIL import Image
    formats = {'.png': 'PNG', '.jpg': 'JPEG', '.jpeg': 'JPEG', '.webp': 'WEBP'}
    try:
        with Image.open(io.BytesIO(data)) as im:
            im.load()
            if formats[output.suffix.lower()] == 'JPEG':
                im = im.convert('RGB')
            buffer = io.BytesIO()
            im.save(buffer, format=formats[output.suffix.lower()])
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open('xb') as handle:
            handle.write(buffer.getvalue())
    except FileExistsError:
        raise ImageError('输出文件已存在，请使用新文件名。') from None
    except (OSError, ValueError):
        raise ImageError('图片响应无效或无法保存；先检查输出和服务端结果，不要自动重复生成。') from None


# Only short identifiers are echoed; free-text messages stay private and are matched locally.
_ERROR_ID = re.compile(r'\\?"(?:code|type)\\?"\s*:\s*\\?"([A-Za-z0-9_.:-]{1,40})\\?"')
_ERROR_PATTERNS = (
    ('moderation', ('moderation_blocked',)),
    ('model', ('no available channel', '无可用渠道', 'model_not_found', 'model not found', 'model_not_supported',
               'unsupported model', 'invalid model', 'does not exist')),
    ('auth', ('invalid token', 'invalid api key', 'invalid_api_key', 'incorrect api key', 'unauthorized')),
    ('transient', ('overloaded', 'auth_unavailable', 'no auth available', 'try again later',
                   'temporarily unavailable')),
)
_ERROR_HINTS = {
    'moderation': ('内容审核拦截；调整提示词后由用户决定是否重试', EXIT_MODERATION),
    'model': ('模型 {model} 没有可用渠道或不存在；不要重试同一模型，运行 discover 查找可用图片模型', EXIT_MODEL),
    'auth': ('认证失败或无权限；核对当前供应商 Key 及令牌分组', EXIT_AUTH),
    'transient': ('上游暂时过载或无可用账号；稍后可由用户确认后重试一次', EXIT_TRANSIENT),
    'quota': ('限流或额度不足；检查余额、额度与并发，不自动重试', EXIT_FAILED),
    'prompt': ('服务端要求提示词；检查 --prompt 内容', EXIT_FAILED),
    'route': ('接口不存在；核对 base_url 是否含 /v1 及图片路由', EXIT_CONFIG),
    'server': ('服务端错误，原因未识别；核对服务日志，不自动重试', EXIT_FAILED),
    'other': ('请求失败或发生重定向', EXIT_FAILED),
}


def classify_http_error(exc):
    """Return (kind, safe error identifiers) without exposing the raw provider payload."""
    try:
        body = exc.read(64 * 1024).decode('utf-8', errors='replace')
    except (OSError, AttributeError):
        body = ''
    text = body.lower()
    ids = list(dict.fromkeys(i for i in _ERROR_ID.findall(body) if not i.lower().startswith('sk-')))[:3]
    kind = next((kind for kind, needles in _ERROR_PATTERNS if any(n in text for n in needles)), None)
    if kind is None:
        if exc.code in (401, 403):
            kind = 'auth'
        elif exc.code == 429:
            kind = 'quota'
        elif exc.code in (400, 422) and 'prompt' in text:
            kind = 'prompt'
        elif exc.code == 404:
            kind = 'route'
        elif exc.code >= 500:
            kind = 'server'
        else:
            kind = 'other'
    return kind, ids


def http_failure(exc, model):
    kind, ids = classify_http_error(exc)
    hint, code = _ERROR_HINTS[kind]
    detail = f'（{", ".join(ids)}）' if ids else ''
    return kind, ImageError(f'HTTP {exc.code}：{hint.format(model=model)}{detail}。未输出原始响应。', code)


def list_image_models(base, key, timeout):
    """Image-like ids from /models; proxies such as CC-Switch may legitimately return none."""
    req = urllib.request.Request(base + '/models', headers={'Authorization': 'Bearer ' + key})
    try:
        with urllib.request.build_opener(NoRedirect()).open(req, timeout=timeout) as response:
            items = json.load(response).get('data', [])
        return [i['id'] for i in items if isinstance(i, dict) and isinstance(i.get('id'), str)
                and ('image' in i['id'].lower() or 'dall-e' in i['id'].lower())]
    except Exception:
        return []


def probe_model(base, key, model, timeout):
    """Ask for an image without a prompt: routing and validation errors arrive before any image is made."""
    req = urllib.request.Request(base + '/images/generations', data=json.dumps({'model': model}).encode(), headers={
        'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json',
    })
    try:
        with urllib.request.build_opener(NoRedirect()).open(req, timeout=timeout) as response:
            response.read()
        return 'ok'
    except urllib.error.HTTPError as exc:
        return classify_http_error(exc)[0]


def discover(home, base, key, args):
    labels = {'model': '无可用渠道', 'transient': '上游暂时不可用', 'quota': '限流或额度不足'}
    candidates = [m for m in (args.model, saved_model(home, base)) if m]
    candidates += list_image_models(base, key, min(args.timeout, 30)) + list(CANDIDATES)
    results = []
    for model in list(dict.fromkeys(candidates))[:PROBE_LIMIT]:
        kind = probe_model(base, key, model, min(args.timeout, 60))
        if kind in ('ok', 'prompt'):
            saved_model(home, base, model)
            print(f'已发现并保存当前入口的图片模型：{model}（探测未生成图片）。')
            return
        if kind in ('auth', 'route'):
            raise ImageError('探测已停止：' + _ERROR_HINTS[kind][0] + '。', _ERROR_HINTS[kind][1])
        results.append(f'{model}：{labels.get(kind, "未识别的响应")}')
    code = EXIT_TRANSIENT if any('暂时' in r for r in results) else EXIT_MODEL
    raise ImageError('未发现可用图片模型。' + '；'.join(results)
                     + '。请在 New API 为图片渠道添加模型并启用分组，或用 --model 指定候选后重新运行 discover。', code)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='只检查本地配置和依赖，不联网')
    parser.add_argument('command', nargs='?', choices=['generate', 'edit', 'discover'],
                        help='discover 联网探测并保存可用图片模型，不生成图片')
    parser.add_argument('--model', help='本次请求使用的图片模型；省略则读取本地记忆')
    parser.add_argument('--set-model', metavar='MODEL', help='保存当前入口的图片模型，不联网')
    parser.add_argument('--prompt')
    parser.add_argument('--image', type=Path)
    parser.add_argument('--out', type=Path)
    parser.add_argument('--size')
    parser.add_argument('--quality')
    parser.add_argument('--background', choices=['transparent', 'opaque', 'auto'])
    parser.add_argument('--response-format', choices=['b64_json', 'url'])
    parser.add_argument('--timeout', type=int, default=240)
    args = parser.parse_args()
    if args.timeout <= 0:
        parser.error('--timeout 必须大于零')
    if sum((args.check, args.set_model is not None, args.command is not None)) != 1:
        parser.error('请选择 --check、--set-model 或 generate/edit/discover 中的一项')
    if args.command == 'discover':
        if args.prompt or args.out or args.image:
            parser.error('discover 只接受 --model 和 --timeout')
    elif args.command:
        if not args.prompt or not args.out:
            parser.error('需要 --prompt 和 --out')
        if args.command == 'edit' and not args.image:
            parser.error('edit 需要 --image')
        if args.command == 'generate' and args.image:
            parser.error('--image 仅适用于 edit')
        if args.out.suffix.lower() not in ('.png', '.jpg', '.jpeg', '.webp'):
            parser.error('--out 扩展名须为 .png、.jpg 或 .webp')
    try:
        try:
            from PIL import Image
        except ImportError:
            raise ImageError('缺少 Pillow，请按安装文档在技能虚拟环境安装 requirements.txt。', EXIT_CONFIG) from None
        home = Path(os.environ.get('CODEX_HOME') or '~/.codex').expanduser()
        name, base, key, source = _resolve(home, os.environ)
        if args.set_model is not None:
            saved_model(home, base, args.set_model)
            print('已保存当前入口的图片模型；未联网，尚未验证模型可用性。')
            return 0
        remembered = saved_model(home, base)
        if args.check:
            url = urllib.parse.urlsplit(base)
            print(f'供应商：{name}（{"本机代理" if _is_loopback(url.hostname) else "远程服务"}，路径 {url.path or "/"}）')
            print(f'认证来源：{source}')
            print('图片模型：' + (f'{remembered}（本地记忆）' if remembered else '未设置，作图前运行 discover'))
            print('本地检查通过：配置、认证来源、Pillow 可用；未联网，未验证 Key、模型、权限或额度。需要验证时运行 discover（不生成图片）。')
            return 0
        if args.command == 'discover':
            discover(home, base, key, args)
            return 0
        args.model = args.model or remembered
        if not args.model:
            raise ImageError('尚未设置图片模型；先运行 discover 自动查找并保存，不要猜测模型名。', EXIT_MODEL)
        if args.out.exists():
            raise ImageError('输出文件已存在，请使用新文件名。')
        try:
            data = request_image(base, key, args)
        except urllib.error.HTTPError as exc:
            kind, error = http_failure(exc, args.model)
            if kind == 'model' and args.model == remembered and forget_model(home, base):
                error = ImageError(str(error) + '已清除该入口的旧模型记忆。', error.code)
            raise error from None
        save_image(data, args.out)
        print('图片已保存：' + str(args.out.resolve()))
        if args.model != remembered:
            saved_model(home, base, args.model)
            print(f'已记住当前入口的图片模型：{args.model}')
        return 0
    except ImageError as exc:
        print(str(exc), file=sys.stderr)
        return exc.code
    except urllib.error.HTTPError as exc:
        error = http_failure(exc, args.model)[1]
        print(str(error), file=sys.stderr)
        return error.code
    except (TimeoutError, socket.timeout):
        print('等待超时，请求结果未知；先检查输出及服务日志，不自动补发。', file=sys.stderr)
    except urllib.error.URLError as exc:
        if isinstance(exc.reason, socket.timeout):
            print('等待超时，请求结果未知；先检查输出及服务日志，不自动补发。', file=sys.stderr)
        else:
            print('网络连接失败或超时；核对网络权限、代理与服务状态，不自动补发。', file=sys.stderr)
    except Exception:
        print('执行失败；检查依赖、响应格式和本地文件。原始错误已隐藏，不自动补发请求。', file=sys.stderr)
    return EXIT_FAILED


if __name__ == '__main__':
    sys.exit(main())
