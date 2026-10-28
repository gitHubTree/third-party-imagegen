# Linux 安装与更新

Linux 与 macOS 使用相同的 Python 入口；仅在安装、更新或迁移本技能时读取。先确认当前 Codex 配置目录；默认使用 `~/.codex`。

```bash
set -eu
codex_home="${CODEX_HOME:-$HOME/.codex}"
skill_dir="$codex_home/skills/third-party-imagegen"
python_bin="$(command -v python3)"

test -f "$codex_home/config.toml" || { echo '请先确认 CODEX_HOME 是当前 Codex 配置目录。' >&2; exit 1; }
test ! -e "$skill_dir" || { echo '技能已存在；更新前先备份并比较定制文件。' >&2; exit 1; }

mkdir -p "$(dirname "$skill_dir")"
cp -R '<仓库>/skill' "$skill_dir"
"$python_bin" -m venv "$skill_dir/.venv"
runner="$skill_dir/.venv/bin/python"
"$runner" -m pip install -r "$skill_dir/requirements.txt"
CODEX_HOME="$codex_home" "$runner" "$skill_dir/scripts/imagegen.py" --check
```

从旧版迁移时，先把 `$codex_home/skills/cpa-imagegen` 完整备份到技能扫描目录外并移除，避免两个图片技能同时触发。更新前备份技能目录并保留 `$codex_home/third-party-imagegen.json`。卸载只移除 `skills/third-party-imagegen`，除非用户明确要求清除模型记忆。完成后重启或刷新 Codex 技能发现，显式调用 `$third-party-imagegen` 验证路由。

