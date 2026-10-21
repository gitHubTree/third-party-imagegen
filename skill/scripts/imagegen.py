#!/usr/bin/env python3
"""Generate/edit one image using the selected Codex provider. Python 3.11+."""
import argparse
import base64
import hashlib
import io
import json
import os
from pathlib import Path
import socket
import sys
import tomllib
import uuid
import urllib.error
import urllib.parse
import urllib.request


class ImageError(Exception):
    pass


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # Never forward provider credentials to a redirected endpoint.


def resolve(home, environ):
    try:
        config = tomllib.loads((home / 'config.toml').read_text(encoding='utf-8'))
        # Profiles can override provider selection; do not silently use the root provider.
        profile = config.get('profile')
        if profile:
            selected = config.get('profiles', {}).get(profile)
            if not isinstance(selected, dict):
                raise ImageError('默认 profile 不存在，请检查 Codex 配置。')
            config = {**config, **selected}
        provider = config.get('model_providers', {}).get(config.get('model_provider'))
        if not isinstance(provider, dict):
            raise ImageError('未找到当前自定义供应商，请先在 CC-Switch 中启用供应商。')
        base = provider.get('base_url', '')
        url = urllib.parse.urlsplit(base)
        if url.scheme not in ('http', 'https') or not url.hostname or url.username or url.password or url.query or url.fragment:
            raise ImageError('供应商 base_url 无效，应为兼容 API 基础地址。')
        key = environ.get(provider.get('env_key', ''), '') or provider.get('experimental_bearer_token', '')
        if not key and provider.get('requires_openai_auth') is True:
            auth = home / 'auth.json'
            if auth.is_file():
                key = json.loads(auth.read_text(encoding='utf-8')).get('OPENAI_API_KEY', '')
        if not isinstance(key, str) or not key.strip() or '\n' in key or '\r' in key:
            raise ImageError('当前供应商 Key 不可用；检查 env_key 或 auth.json 中的 OPENAI_API_KEY，不必另申请官方 Key。')
        return base.rstrip('/'), key.strip()
    except ImageError:
        raise
    except (OSError, ValueError, TypeError, AttributeError):
        raise ImageError('无法读取 Codex 配置；未输出配置或凭据。') from None


def saved_model(home, base, model=None):
    """Remember only a model per endpoint fingerprint; never persist URL or Key."""
    path = home / 'third-party-imagegen.json'
    fingerprint = hashlib.sha256(base.encode()).hexdigest()
    try:
        settings = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
        if not isinstance(settings, dict) or not all(isinstance(v, str) for v in settings.values()):
            raise ValueError()
        if model is None:
            return settings.get(fingerprint)
        model = model.strip()
        if not model:
            raise ImageError('图片模型名不能为空。')
        settings[fingerprint] = model
        home.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
        try:
            temporary.write_text(json.dumps(settings, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
            temporary.replace(path)
        finally:
            if temporary.exists():
                temporary.unlink()
        return model
    except (OSError, ValueError, TypeError):
        raise ImageError('无法读取或保存本地图片模型设置，请检查 third-party-imagegen.json。') from None


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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='只检查本地配置和依赖，不联网')
    parser.add_argument('command', nargs='?', choices=['generate', 'edit'])
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
        parser.error('请选择 --check、--set-model 或 generate/edit 中的一项')
    if args.command:
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
            raise ImageError('缺少 Pillow，请按安装文档在技能虚拟环境安装 requirements.txt。') from None
        home = Path(os.environ.get('CODEX_HOME') or '~/.codex').expanduser()
        base, key = resolve(home, os.environ)
        if args.set_model is not None:
            saved_model(home, base, args.set_model)
            print('已保存当前入口的图片模型；未联网，尚未验证模型可用性。')
            return 0
        if args.check:
            print('当前入口的图片模型：' + ('已设置' if saved_model(home, base) else '未设置，首次作图前需确认一次'))
            print('本地检查通过：配置、认证来源、Pillow 可用；未联网，未验证 Key 有效性、模型、权限或额度。')
            return 0
        args.model = args.model or saved_model(home, base)
        if not args.model:
            raise ImageError('尚未设置图片模型；先用 --set-model 保存供应商支持的模型，或本次传 --model。')
        if args.out.exists():
            raise ImageError('输出文件已存在，请使用新文件名。')
        data = request_image(base, key, args)
        save_image(data, args.out)
        print('图片已保存：' + str(args.out.resolve()))
        return 0
    except ImageError as exc:
        print(str(exc), file=sys.stderr)
    except urllib.error.HTTPError as exc:
        messages = {400: '参数或模型不兼容', 401: '认证失败', 403: '权限不足', 404: '接口或模型不存在', 429: '限流或额度不足', 503: '服务不可用；核对图片渠道、分组及端点'}
        print(f'HTTP {exc.code}：{messages.get(exc.code, "请求失败或发生重定向")}。未输出原始响应，不自动重试。', file=sys.stderr)
    except (TimeoutError, socket.timeout):
        print('等待超时，请求结果未知；先检查输出及服务日志，不自动补发。', file=sys.stderr)
    except urllib.error.URLError:
        print('网络连接失败或超时；核对网络权限、代理与服务状态，不自动补发。', file=sys.stderr)
    except Exception:
        print('执行失败；检查依赖、响应格式和本地文件。原始错误已隐藏，不自动补发请求。', file=sys.stderr)
    return 1


if __name__ == '__main__':
    sys.exit(main())
