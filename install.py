#!/usr/bin/env python3
"""Install or update the third-party-imagegen skill into the current Codex home. Safe to run repeatedly."""
import argparse
from datetime import datetime
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys

NAME = 'third-party-imagegen'
LEGACY = 'cpa-imagegen'
MIN_PYTHON = (3, 11)
SOURCE = Path(__file__).resolve().parent / 'skill'
KEEP = {'.venv'}  # Never replaced by an update; the model memory lives outside the skill directory.
IGNORE = shutil.ignore_patterns('.venv', '__pycache__', '*.pyc', '.DS_Store')


def fail(message):
    print('安装失败：' + message, file=sys.stderr)
    sys.exit(1)


def remove(path):
    """Delete a file or tree; Windows refuses to delete read-only files, so clear the flag and retry."""
    def retry(func, target, _):
        os.chmod(target, stat.S_IWRITE)
        func(target)
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path, **({'onexc': retry} if sys.version_info >= (3, 12) else {'onerror': retry}))
    else:
        try:
            path.unlink()
        except PermissionError:
            os.chmod(path, stat.S_IWRITE)
            path.unlink()


def version_of(skill_dir):
    try:
        text = (skill_dir / 'scripts' / 'imagegen.py').read_text(encoding='utf-8')
    except OSError:
        return None
    match = re.search(r"^__version__ = '([^']+)'", text, re.M)
    return match.group(1) if match else '1.0（无版本号）'


def venv_python(skill_dir):
    return skill_dir / '.venv' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')


def venv_ok(python):
    try:
        result = subprocess.run([str(python), '-c', 'import sys; print(sys.version_info >= (3, 11))'],
                                capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.stdout.strip() == 'True'


def ensure_venv(skill_dir):
    """The skill only needs the standard library, so the venv is created without pip and works offline."""
    import venv
    python = venv_python(skill_dir)
    if venv_ok(python):
        return python, False
    shutil.rmtree(skill_dir / '.venv', ignore_errors=True)
    venv.EnvBuilder(with_pip=False, clear=True).create(skill_dir / '.venv')
    if not venv_ok(python):
        fail(f'虚拟环境创建后无法运行：{python}')
    return python, True


def has_pillow(python):
    return subprocess.run([str(python), '-c', 'import PIL'], capture_output=True).returncode == 0


def install_pillow(python, skill_dir):
    """Optional: only output format conversion needs Pillow, so failure is reported but not fatal."""
    if subprocess.run([str(python), '-m', 'pip', '--version'], capture_output=True).returncode != 0:
        if subprocess.run([str(python), '-m', 'ensurepip', '--upgrade'], capture_output=True).returncode != 0:
            return '当前 Python 缺少 ensurepip（Debian/Ubuntu 需安装 python3-venv），未安装 Pillow'
    result = subprocess.run([str(python), '-m', 'pip', 'install', '--disable-pip-version-check',
                             '-r', str(skill_dir / 'requirements.txt')])
    return None if result.returncode == 0 else 'pip 安装 Pillow 失败（检查网络或镜像源），未安装 Pillow'


def main():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding='utf-8', errors='replace')
        except (AttributeError, ValueError, OSError):
            pass
    if sys.version_info < MIN_PYTHON:
        fail(f'需要 Python 3.11 或更高版本，当前为 {sys.version.split()[0]}（{sys.executable}）。'
             'macOS 自带 Python 通常为 3.9，请安装新版后用其运行本脚本。')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--codex-home', type=Path, help='默认取环境变量 CODEX_HOME，否则为 ~/.codex')
    parser.add_argument('--with-pillow', action='store_true', help='安装可选的 Pillow，用于按 --out 扩展名转换格式')
    parser.add_argument('--remove-legacy', action='store_true', help=f'把旧技能 {LEGACY} 移到备份目录')
    parser.add_argument('--discover', action='store_true', help='安装后联网探测并保存图片模型（不生成图片）')
    args = parser.parse_args()

    home = (args.codex_home or Path(os.environ.get('CODEX_HOME') or '~/.codex')).expanduser().resolve()
    if not (home / 'config.toml').is_file():
        fail(f'{home} 下没有 config.toml；确认 CODEX_HOME 指向当前 Codex 配置目录，或用 --codex-home 指定。')
    if not (SOURCE / 'SKILL.md').is_file():
        fail(f'找不到技能源码 {SOURCE}；请在仓库根目录运行本脚本。')
    target = home / 'skills' / NAME
    stamp = datetime.now().strftime('%Y%m%d-%H%M%S')
    backups = home / f'{NAME}-backups' / stamp
    suffix = 1
    while backups.exists():  # Two runs within one second must not share a backup.
        backups = backups.with_name(f'{stamp}-{suffix}')
        suffix += 1

    old = version_of(target) if target.exists() else None
    if target.exists():
        shutil.copytree(target, backups / NAME, ignore=IGNORE)
        for entry in target.iterdir():
            if entry.name not in KEEP:
                remove(entry)
    shutil.copytree(SOURCE, target, ignore=IGNORE, dirs_exist_ok=True)
    python, created = ensure_venv(target)

    notes = []
    legacy = home / 'skills' / LEGACY
    if legacy.exists():
        if args.remove_legacy:
            backups.mkdir(parents=True, exist_ok=True)
            shutil.move(str(legacy), str(backups / LEGACY))
            notes.append(f'旧技能 {LEGACY} 已移到 {backups / LEGACY}')
        else:
            notes.append(f'发现旧技能 {legacy}，两个图片技能会同时触发；确认后加 --remove-legacy 重新运行')
    if args.with_pillow and not has_pillow(python):
        problem = install_pillow(python, target)
        if problem:
            notes.append(problem + '；不影响生成，只是不能转换输出格式')

    print(f'已安装 {NAME} {version_of(target)}' + (f'（原版本 {old}）' if old else '') + f'：{target}')
    print(f'运行解释器：{python}' + ('（新建）' if created else '（沿用）'))
    if old:
        print(f'更新前备份：{backups / NAME}')
    print('Pillow：' + ('已安装' if has_pillow(python) else '未安装（可选，加 --with-pillow 安装）'))
    for note in notes:
        print('注意：' + note)

    env = {**os.environ, 'CODEX_HOME': str(home)}
    script = str(target / 'scripts' / 'imagegen.py')
    commands = [['--check']] + ([['discover']] if args.discover else [])
    for command in commands:
        print(f'\n$ imagegen.py {" ".join(command)}', flush=True)
        if subprocess.run([str(python), script, *command], env=env).returncode != 0:
            fail(f'imagegen.py {" ".join(command)} 未通过，见上方提示。')
    print('\n完成。请重启或刷新 Codex 使技能说明生效。')


if __name__ == '__main__':
    main()
