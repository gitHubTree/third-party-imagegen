---
name: third-party-imagegen
description: 生成或编辑图片时，通过当前 Codex 第三方供应商的图片 API 完成任务；适用于用户明确选择该供应商，或内置图片能力不可用但用户已同意使用现有供应商配置的场景。
---

# 第三方供应商图片技能

本技能在 Windows、macOS 和 Linux 使用同一套 Python 实现。它直接调用当前 Codex 供应商的 `/images/generations` 或 `/images/edits` 接口，不依赖系统 `image_gen.py`，也不会自动切换供应商、模型或账号。

## 执行边界

- 用户已授权本技能作为原生图片能力的备用路径。原生 `image_gen` 可用且请求成功时优先使用原生能力；原生不可用、模型容量不足或请求失败时，自动读取并使用当前 `CODEX_HOME/skills/third-party-imagegen/SKILL.md`，执行本技能的直接供应商 API 路径。
- 用户显式调用 `$third-party-imagegen` 时，直接使用本技能的 API 路径；不要改读系统 `imagegen` 技能来替代，也不要创建临时 PIL、SVG、HTML 或其他本地绘图脚本。
- 不因原生能力不可用要求用户另行申请官方 `OPENAI_API_KEY`，不切换到系统 CLI，也不静默降级为本地绘图。
- 无论 API 请求还是本地检查失败，都不能把一个未完成的命令当作成功；只有输出文件和预览都验收后才报告图片完成。

## 路由与平台

1. 按“原生成功优先，原生不可用自动转个人技能”的顺序执行；一次用户请求只生成或编辑一张图片。
2. 安装和更新都只运行仓库根目录的 `install.py`；各系统如何准备 Python 3.11+ 见 [install-windows.md](references/install-windows.md)、[install-macos.md](references/install-macos.md)、[install-linux.md](references/install-linux.md)。日常生成不需要读取安装文档。
3. 以当前 `SKILL.md` 所在目录为技能目录。Windows 使用 `.venv/Scripts/python.exe`，macOS/Linux 使用 `.venv/bin/python`。不要猜测其他虚拟环境路径，也不要输出配置、认证文件或环境变量。该解释器不存在或提示 Python 版本不足时，请用户运行 `install.py`，不要改用其他 Python 或自行 pip 安装。
4. 首次使用或怀疑环境变化时，先执行 `scripts/imagegen.py --check`。它显示供应商、入口类型、认证来源和当前图片模型，不联网；检查通过不代表服务端权限、额度或模型可用。

## 生成与编辑

用绝对路径调用脚本；默认模型从本地模型记忆读取。**没有记忆时运行 `discover`，禁止自行猜测模型名。** `discover` 依次探测用户指定模型、已记忆模型、`/models` 中的图片模型和常见图片模型名，请求不带提示词，因此不会生成图片；找到可路由的模型后自动保存。用户明确指定模型时可传 `--model`，成功出图后自动记住。不把聊天模型当作图片模型。

```text
<python> <技能目录>/scripts/imagegen.py discover
<python> <技能目录>/scripts/imagegen.py generate --prompt-file <工作区>/output/imagegen/result.prompt.txt --out <工作区>/output/imagegen/result.png
<python> <技能目录>/scripts/imagegen.py edit --image <输入图片> --prompt-file <工作区>/output/imagegen/edited.prompt.txt --out <工作区>/output/imagegen/edited.png
```

提示词默认先用文件工具写成工作区内的 UTF-8 文本，再通过 `--prompt-file` 传入。这样 Windows PowerShell、macOS zsh 和 Linux bash 的行为一致：这些 shell 在双引号内都会改写 `$`、反引号或转义符，引号规则也各不相同。只有不含 `$`、引号、反引号和换行的短提示词，才直接用单引号传 `--prompt`。

编辑前查看用户指定的输入图片。当前实现支持一张 PNG、JPEG 或 WebP 输入，不支持遮罩、多图、流式响应或批量生成。输出必须使用新文件名，不能覆盖已有文件；透明背景使用 PNG。

Pillow 是可选依赖。未安装时，若服务端返回的格式与 `--out` 扩展名不同，脚本按实际格式保存并改扩展名。展示和交付一律使用脚本输出的“图片已保存”路径。

## 长任务与展示验收

图片请求可能持续数十秒到数分钟。通过外层命令工具执行时，若返回 `session_id`，必须继续轮询同一个会话直到获得最终退出码；中间的“正在调用供应商”输出不是失败，也不能立刻重复请求。一次请求只启动一个生成进程。脚本默认最多等待 600 秒（`--timeout` 可调）；外层命令工具的超时须长于脚本超时（例如 620 秒以上），否则外层先中断，结果未知。

命令完成后依次确认输出文件存在且大小大于零、调用图片查看工具检查画面，再发送最终回复。查看成功但聊天没有内嵌图片时，修正消息格式，不重复消耗图片请求。Markdown 图片和下载链接使用绝对路径，并指向同一个已检查文件；Windows 路径统一改用正斜杠，macOS/Linux 直接使用原路径，例如：

```markdown
![生成结果](D:/work/output/imagegen/result.png)
[下载原图](D:/work/output/imagegen/result.png)

![生成结果](/Users/me/work/output/imagegen/result.png)
```

不要用 `Get-Process` 找不到进程作为生成失败依据；生成进程正常结束时没有匹配项是正常状态。未知超时或部分输出时，先检查文件和服务状态，不自动补发。

## 联网与沙箱

`discover`、`generate`、`edit` 都需要联网，访问 CC-Switch 的 127.0.0.1 本机代理也算网络访问。运行环境有沙箱和审批机制时，首次调用就按环境规则申请联网执行，不要等失败后再说明。退出码 8 表示请求没有发出（连接被拒绝或沙箱禁网），以联网权限重跑同一命令不会重复计费。

模型记忆写在 Codex 配置目录。沙箱只允许写工作区时，脚本会提示后续请求传 `--model`，这不是失败。

## 配置与故障

脚本从 `${CODEX_HOME}/config.toml` 读取当前 `model_provider`；未设置 `CODEX_HOME` 时使用平台默认 Codex 目录。认证顺序为供应商 `env_key` 对应环境变量、`experimental_bearer_token`，以及仅在 `requires_openai_auth=true` 时读取 `auth.json` 的 `OPENAI_API_KEY`。不读取 ChatGPT 登录令牌，不写入或缓存密钥。

供应商切换后按当前配置重新读取；本地模型记忆只保存 API 地址指纹和模型名。CC-Switch 本机代理切换上游时地址不变，旧记忆可能失效：请求返回“模型无可用渠道”时脚本会自动清除该记忆，随后运行 `discover`。

失败时按退出码处理，不原样重发同一请求：

| 退出码 | 含义 | 处理 |
| --- | --- | --- |
| 3 | 本地配置或依赖 | 按 troubleshooting 修复配置 |
| 4 | 认证或权限 | 核对供应商 Key 与分组，不换模型重试 |
| 5 | 模型未设置或无可用渠道 | 运行 `discover`；仍失败则报告需在 New API 配置图片模型 |
| 6 | 上游暂时过载或无可用账号 | 告知用户，经确认后再重试一次 |
| 7 | 内容审核拦截 | 调整提示词并经用户确认 |
| 8 | 请求未发出：本机代理未运行或沙箱禁网 | 确认 CC-Switch 运行，或以联网权限重跑同一命令 |
| 1 | 其他或结果未知 | 先检查输出和服务日志，不自动补发 |

遇到依赖、配置、HTTP 状态或安装问题时，读取 [troubleshooting.md](references/troubleshooting.md)。涉及 CPA/New API 部署时，再读取 [cpa-new-api.md](references/cpa-new-api.md)。
