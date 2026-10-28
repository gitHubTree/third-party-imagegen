# Linux 安装与更新

仅在安装、更新或迁移本技能时读取。不要输出 `config.toml`、`auth.json` 或密钥。

## 准备 Python 3.11+

运行 `python3 --version` 确认版本。Ubuntu 22.04 和 Debian 11 自带的 Python 低于 3.11，需要另装：

```bash
sudo apt install python3.11        # Ubuntu 22.04 可能需要先添加 deadsnakes PPA
```

安装脚本创建的 `.venv` 不含 pip，因此不需要 `python3-venv` 软件包。只有使用 `--with-pillow` 时，才需要额外安装 `python3.11-venv`（Debian/Ubuntu）以提供 pip。

## 安装或更新

在仓库根目录运行：

```bash
python3.11 install.py
```

Codex 配置目录不是默认的 `~/.codex` 时，先设置 `CODEX_HOME`，或传 `--codex-home <目录>`。可选参数见 [docs/install.md](../../docs/install.md)。
