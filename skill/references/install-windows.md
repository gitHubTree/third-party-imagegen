# Windows 安装与更新

仅在安装、更新或迁移本技能时读取。不要输出 `config.toml`、`auth.json` 或密钥。

## 准备 Python 3.11+

在 PowerShell 中运行 `python --version`，确认版本不低于 3.11。

- 如果运行后打开了 Microsoft Store 或没有任何输出，说明 `python` 是 `WindowsApps` 下的应用商店占位程序，不是真正的 Python。
- 这时从 python.org 安装，或运行 `winget install Python.Python.3.13`。然后在“设置 → 应用 → 高级应用设置 → 应用执行别名”中关闭 `python.exe` 和 `python3.exe`。
- 可用 `(Get-Command python).Source` 查看实际调用的是哪个程序。

## 安装或更新

在仓库根目录运行：

```powershell
python install.py
```

Codex 配置目录不是默认的 `%USERPROFILE%\.codex` 时，先设置 `$env:CODEX_HOME`，或传 `--codex-home <目录>`。可选参数见 [docs/install.md](../../docs/install.md)。

## WSL

在 WSL 中运行 Codex 时，按 Linux 文档在 WSL 内安装。CC-Switch 运行在 Windows 主机上时，需要启用 WSL 镜像网络，WSL 内的 `127.0.0.1` 才能访问到它。

Codex 沙箱的联网和写入限制见 [docs/install.md](../../docs/install.md)。
