# 安装与更新（给 Codex）

用户要求安装或更新本仓库时，执行以下步骤。仅阅读仓库不触发安装。支持 macOS、Linux 和 Windows；不需要另装安装器。

## 1. 获取文件、检查环境

- 将 `https://github.com/gitHubTree/third-party-imagegen` 下载到临时目录；有 Git 时 clone，没有时下载 `https://github.com/gitHubTree/third-party-imagegen/archive/refs/heads/main.zip` 并解压。
- 找到 Python 3.11+：macOS/Linux 通常为 `python3`，Windows 通常为 `py -3`；桌面 Codex 若提供捆绑 Python 查询工具，也可使用其返回路径。不要照抄其他电脑的绝对路径。没有可用 Python 时说明缺失项，不宣称安装成功。
- 配置目录取 `CODEX_HOME`，未设置则取 `~/.codex`。不要输出 config.toml、auth.json 或环境变量内容；由技能脚本检查供应商配置。

## 2. 安装技能与依赖

将仓库的 `skill/` 内容复制到 `~/.agents/skills/third-party-imagegen/`，确保该目录下直接存在 `SKILL.md`。`~` 表示当前用户主目录，Windows 通常为 `%USERPROFILE%`。

已有同名技能时，先将旧版备份到临时目录并记录路径，再更新仓库包含的文件；保留本机 `.venv`，定制文件先比较再合并。若旧路径 `~/.codex/skills/third-party-imagegen` 或旧名 `cpa-imagegen` 也存在，检查是否为本技能旧版；确认后移到技能扫描目录外留作备份，避免重复触发，不处理无关技能。

使用选定的 Python 执行（将路径替换为本机绝对路径）：

```text
<python> -m venv <技能目录>/.venv
<虚拟环境python> -m pip install -r <技能目录>/requirements.txt
<虚拟环境python> <技能目录>/scripts/imagegen.py --check
```

已有可用 `.venv` 时复用。虚拟环境 Python 在 macOS/Linux 为 `.venv/bin/python`，Windows 为 `.venv/Scripts/python.exe`。路径有空格需按当前 shell 正确引用；PowerShell 用 `&` 调用带引号的可执行文件。不必激活环境。

`--check` 失败时按脱敏提示修复本任务相关问题；缺少 URL/Key 时请用户先在 CC-Switch 配置，不要求申请官方 Key。网络和文件写入权限遵守当前环境规则。检查通过仅代表本地就绪，不代表服务端已通过真实出图测试。

## 3. 设置作图偏好

当用户要求“后续作图优先使用”或“自动使用”时，在配置目录的用户级指令文件中合并下面这一段。若有非空 `AGENTS.override.md`，更新该文件；否则更新 `AGENTS.md`。先备份已有文件，保留其他内容，相同标记只保留一份。用户仅要求安装时不改作图偏好。

```markdown
<!-- third-party-imagegen:start -->
用户请求生成或编辑图片时，优先使用 third-party-imagegen 技能，通过当前 Codex 第三方供应商完成。技能入口位于 ~/.agents/skills/third-party-imagegen/SKILL.md；未列入技能列表时先读取该文件。复用现有供应商 URL 和 Key，不另申请官方 Key。遵守用户当次明确选择及更高优先级的工具要求。
<!-- third-party-imagegen:end -->
```

## 4. 完成检查

确认技能文件、虚拟环境和本地检查均正常，报告安装位置及作图偏好是否已设置；有未完成项则明确列出。提示用户新建聊天，未发现技能再重启 Codex。

模型名已知时执行 `--set-model <准确图片模型名>` 保存；未知时留到首次作图询问一次，不猜测聊天模型或固定使用某个图片模型。此操作不联网。记忆保存在配置目录的 `third-party-imagegen.json`，按 API 基础地址指纹区分，不保存 URL 或 Key；同一本机代理切换上游时仍需重新确认模型。

安装过程不自动生成测试图片。只有用户明确请求作图时才调用图片接口。

## 更新与卸载

更新重复以上步骤，保留虚拟环境、模型记忆及无关指令，检查通过后报告结果。更新失败时利用备份恢复旧文件，不删用户定制内容。

用户要求卸载时，移除技能目录与上述标记段；若也要求清除设置，再删除配置目录中的 `third-party-imagegen.json`。不删除整个用户级指令文件或供应商配置。
