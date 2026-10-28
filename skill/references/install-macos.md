# macOS 安装与更新

仅在安装、更新或迁移本技能时读取。不要输出 `config.toml`、`auth.json` 或密钥。

## 准备 Python 3.11+

macOS 自带的 `/usr/bin/python3` 通常是 3.9，不能使用。用 Homebrew 安装新版：

```bash
brew install python@3.13
python3.13 --version
```

## 安装或更新

在仓库根目录运行：

```bash
python3.13 install.py
```

Codex 配置目录不是默认的 `~/.codex` 时，先设置 `CODEX_HOME`，或传 `--codex-home <目录>`。可选参数见 [docs/install.md](../../docs/install.md)。
