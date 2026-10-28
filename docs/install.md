# 安装与更新

本仓库发布一个跨平台技能 `third-party-imagegen`，Windows、macOS 和 Linux 共用源码和 API 实现，只按操作系统区分安装命令。

安装前确认当前 Codex 的实际配置目录：优先使用 `CODEX_HOME`，未设置时使用平台默认目录。不要因为安装技能而另设一个配置目录，也不要复制其他电脑的虚拟环境。

把仓库中的 `skill/` 内容安装到：

```text
<CODEX_HOME>/skills/third-party-imagegen/
```

安装后该目录下应直接存在 `SKILL.md`、`scripts/`、`references/` 和独立的 `.venv/`。按系统读取：

- Windows：[skill/references/install-windows.md](../skill/references/install-windows.md)
- macOS：[skill/references/install-macos.md](../skill/references/install-macos.md)
- Linux：[skill/references/install-linux.md](../skill/references/install-linux.md)

从旧版 `cpa-imagegen` 迁移时，先将 `<CODEX_HOME>/skills/cpa-imagegen` 完整备份到技能扫描目录外，再移除旧目录，避免两个图片技能同时触发。更新前比较定制文件后再替换。保留 `<CODEX_HOME>/third-party-imagegen.json` 中的模型记忆；不覆盖 Codex 配置、认证文件或已有图片。卸载只删除技能目录，清除模型记忆需要单独的明确要求。

安装检查使用技能虚拟环境执行 `scripts/imagegen.py --check`，不会发起图片请求。检查通过后刷新或重启 Codex，显式调用 `$third-party-imagegen` 验证技能发现，再在用户实际需要图片时验证真实接口。

安装完成后同步用户级 `AGENTS.md` 中的图片路由偏好：原生 `image_gen` 成功时优先原生；原生不可用、容量不足或失败时自动使用 `third-party-imagegen`。同步前备份原文件，只保留一份路由规则，不覆盖其他用户指令。
