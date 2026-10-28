# Windows 安装与更新

仅在安装、更新或迁移本技能时读取。本机路径必须根据当前环境解析；不要照抄其他电脑的盘符，也不要输出 `config.toml`、`auth.json` 或密钥。

## 安装

在 PowerShell 中：

```powershell
$ErrorActionPreference = 'Stop'
$codexHome = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $HOME '.codex' }
$skillDir = Join-Path $codexHome 'skills\third-party-imagegen'
$python = (Get-Command python -ErrorAction Stop).Source

if (!(Test-Path (Join-Path $codexHome 'config.toml'))) { throw '请先确认 CODEX_HOME 是当前 Codex 配置目录。' }
if (Test-Path $skillDir) { throw '技能已存在；更新前先备份并比较定制文件。' }

New-Item -ItemType Directory -Force -Path (Split-Path $skillDir) | Out-Null
Copy-Item -Recurse -LiteralPath '<仓库>\skill' -Destination $skillDir
& $python -m venv (Join-Path $skillDir '.venv')
$runner = Join-Path $skillDir '.venv\Scripts\python.exe'
& $runner -m pip install -r (Join-Path $skillDir 'requirements.txt')
$env:CODEX_HOME = $codexHome
& $runner (Join-Path $skillDir 'scripts\imagegen.py') --check
```

`<仓库>` 替换为当前源码目录；如果使用发布包，复制包内 `skill` 目录的内容，使 `SKILL.md` 直接位于技能目录。安装位置应为 `$codexHome\skills\third-party-imagegen\SKILL.md`。

## 更新和卸载

从旧版迁移时，先把 `$codexHome\skills\cpa-imagegen` 完整备份到技能扫描目录外并移除，避免两个图片技能同时触发。更新前备份整个技能目录，并保留 `$codexHome\third-party-imagegen.json`。比较定制文件后再替换技能源码；不要覆盖供应商配置或图片文件。卸载只移除 `skills\third-party-imagegen`，除非用户明确要求清除模型记忆，否则保留配置目录中的模型记忆。

安装完成后重启或刷新 Codex 技能发现。显式调用 `$third-party-imagegen` 验证路由；自然语言自动选择属于单独的路由验证，不要用安装检查代替。

