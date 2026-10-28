import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]

def install(home, *flags):
    env = {k: v for k, v in os.environ.items() if k != 'CODEX_HOME'}
    result = subprocess.run([sys.executable, str(root / 'install.py'), '--codex-home', str(home), *flags],
                            capture_output=True, text=True, encoding='utf-8', env=env)
    return result.returncode, result.stdout + result.stderr

with tempfile.TemporaryDirectory() as td:
    home = Path(td)
    code, output = install(home)
    assert code == 1 and 'config.toml' in output, 'A directory without config.toml is not a Codex home'

    (home / 'config.toml').write_text('model_provider="custom"\n[model_providers.custom]\nbase_url="http://127.0.0.1:9/v1"\nexperimental_bearer_token="test-key"\n', encoding='utf-8')
    skill = home / 'skills' / 'third-party-imagegen'
    python = skill / '.venv' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')

    # Fresh install: files, offline venv and a passing check, without touching the network.
    code, output = install(home)
    assert code == 0, output
    assert (skill / 'SKILL.md').is_file() and (skill / 'scripts' / 'imagegen.py').is_file() and python.is_file(), output
    assert '本地检查通过' in output and 'test-key' not in output, output
    assert not (home / 'third-party-imagegen-backups').exists(), 'Nothing to back up on a fresh install'

    # Update: replaces code, backs up the old copy, keeps the venv and the model memory.
    (home / 'third-party-imagegen.json').write_text(json.dumps({'fingerprint': 'kept-model'}), encoding='utf-8')
    (skill / '.venv' / 'marker').write_text('kept', encoding='utf-8')
    (skill / 'SKILL.md').write_text('customized', encoding='utf-8')
    (skill / 'obsolete.txt').write_text('old', encoding='utf-8')
    os.chmod(skill / 'obsolete.txt', stat.S_IREAD)  # Windows cannot delete read-only files without help.
    os.chmod(skill / 'references' / 'troubleshooting.md', stat.S_IREAD)
    (home / 'skills' / 'cpa-imagegen').mkdir()
    code, output = install(home)
    assert code == 0 and '原版本' in output and '（沿用）' in output, output
    assert 'cpa-imagegen' in output and (home / 'skills' / 'cpa-imagegen').exists(), 'Legacy skill is only reported without --remove-legacy'
    assert (skill / 'SKILL.md').read_text(encoding='utf-8') != 'customized' and not (skill / 'obsolete.txt').exists()
    assert (skill / '.venv' / 'marker').is_file()
    assert json.loads((home / 'third-party-imagegen.json').read_text(encoding='utf-8')) == {'fingerprint': 'kept-model'}
    backup, = (home / 'third-party-imagegen-backups').iterdir()
    assert (backup / 'third-party-imagegen' / 'SKILL.md').read_text(encoding='utf-8') == 'customized'
    assert (backup / 'third-party-imagegen' / 'obsolete.txt').is_file() and not (backup / 'third-party-imagegen' / '.venv').exists()

    # A broken venv is rebuilt; the legacy skill moves into the backup on request.
    (skill / '.venv' / 'pyvenv.cfg').unlink()
    python.unlink()
    code, output = install(home, '--remove-legacy')
    assert code == 0 and '（新建）' in output and python.is_file(), output
    assert not (home / 'skills' / 'cpa-imagegen').exists()
    assert any((b / 'cpa-imagegen').is_dir() for b in (home / 'third-party-imagegen-backups').iterdir())
    code, output = install(home)
    code2, output2 = install(home)
    assert code == 0 and code2 == 0, output + output2
    assert len(list((home / 'third-party-imagegen-backups').iterdir())) == 4, 'Back-to-back runs need distinct backups'
print('PASS: install')
