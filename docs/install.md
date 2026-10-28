# 安装与更新

需要 Python 3.11+，以及已经配置好的 Codex 供应商（通常由 CC-Switch 写入 `config.toml`）。技能只用 Python 标准库，Pillow 是可选依赖。

安装和更新是同一条命令，在仓库根目录运行，可以重复执行：

```text
Windows:      python install.py
macOS/Linux:  python3 install.py
```

脚本会依次：

1. 检查 Python 版本；低于 3.11 时给出提示并退出。
2. 定位 Codex 配置目录：`--codex-home` 参数，其次是环境变量 `CODEX_HOME`，最后是 `~/.codex`。该目录下必须已有 `config.toml`。
3. 已安装时，先把旧技能备份到 `<CODEX_HOME>/third-party-imagegen-backups/<时间>/`，再替换为仓库中的 `skill/`。
4. 保留技能的 `.venv` 和模型记忆 `<CODEX_HOME>/third-party-imagegen.json`。
5. `.venv` 不存在或已损坏时，用当前 Python 重建。它不含 pip，创建时不需要联网。
6. 运行 `scripts/imagegen.py --check`。

可选参数：

| 参数 | 作用 |
| --- | --- |
| `--with-pillow` | 安装 Pillow，按 `--out` 扩展名转换输出格式；需要联网，失败不影响安装 |
| `--discover` | 安装后联网探测并保存图片模型；请求不带提示词，不会生成图片 |
| `--remove-legacy` | 把旧技能 `cpa-imagegen` 移入备份目录，避免两个图片技能同时触发 |
| `--codex-home <目录>` | 指定 Codex 配置目录 |

各系统如何准备 Python 3.11+：

- Windows：[skill/references/install-windows.md](../skill/references/install-windows.md)
- macOS：[skill/references/install-macos.md](../skill/references/install-macos.md)
- Linux：[skill/references/install-linux.md](../skill/references/install-linux.md)

## Codex 沙箱（各系统）

图片命令需要联网，访问本机 CC-Switch 代理也算联网；模型记忆写在 Codex 配置目录，不在工作区内。Codex 的沙箱在 Windows（`[windows] sandbox`）、macOS（Seatbelt）和 Linux 上实现不同，但 workspace-write 这类模式通常都禁止联网，并且只允许写工作区。技能对此的处理：

- 联网被拒时退出码为 8，表示请求未发出；按环境规则授予联网权限后重跑同一命令。
- 模型记忆写入失败不会让命令失败，脚本会提示后续请求传 `--model`。

## 安装后

安装后重启或刷新 Codex，显式调用 `$third-party-imagegen` 验证技能发现。安装和 `--check` 不发起图片请求。

卸载只删除 `<CODEX_HOME>/skills/third-party-imagegen`。模型记忆和备份目录需要用户明确要求才删除。

安装完成后同步用户级 `AGENTS.md` 中的图片路由偏好：原生 `image_gen` 成功时优先原生；原生不可用、容量不足或失败时自动使用 `third-party-imagegen`。同步前备份原文件，只保留一份路由规则，不覆盖其他用户指令。
