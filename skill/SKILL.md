---
name: third-party-imagegen
description: 生成或编辑图片时，通过当前 Codex 第三方供应商的图片 API 完成任务；适用于 CC-Switch 用户指定或已设为作图偏好的场景，也适用于内置图片能力不可用时。
---

# 第三方供应商图片技能

复用当前 Codex 供应商的 URL 和 Key，独立调用图片 API，无需系统 imagegen 脚本。服务须支持 `/images/generations` 或 `/images/edits`。

## 执行流程

1. 用户明确调用本技能或已将其设为作图偏好时，优先使用第三方 API。遵守用户当次选择及更高优先级的工具约束，不能用本技能覆盖它们。
2. 定位本技能目录及虚拟环境：macOS/Linux 使用 `.venv/bin/python`，Windows 使用 `.venv/Scripts/python.exe`。先执行 `scripts/imagegen.py --check`，不打印配置、Key 或环境变量。
3. `--check` 会报告当前入口是否已有图片模型记忆。有记忆则直接复用；没有时使用用户指定或当前部署已确认支持的模型，执行 `scripts/imagegen.py --set-model <模型名>` 保存。未知时询问一次，不把聊天模型当作图片模型，不默认所有服务支持 `gpt-image-2`。`--model` 只覆盖本次请求。
4. 用绝对路径调用脚本，一次生成或编辑一张图片。按需传 `--size`、`--quality`、`--background`；不确定兼容性时省略可选参数。

```text
<python> <技能目录>/scripts/imagegen.py generate --prompt "完整图片描述" --out <工作区>/output/imagegen/result.png
<python> <技能目录>/scripts/imagegen.py edit --image <输入图片> --prompt "修改要求及保留内容" --out <工作区>/output/imagegen/edited.png
```

编辑前查看用户指定的输入图片；编辑会上传该图片给当前供应商。当前实现支持一张 PNG/JPEG/WebP 输入，不支持遮罩、多图、流式响应或批量生成。输出使用新文件名；透明背景建议保存为 PNG。

5. 成功后检查输出文件、预览并在回复中展示图片，说明使用了第三方供应商。检查通过或 HTTP 200 都不能代替输出和预览验证。

## 配置与边界

- 模型记忆位于 Codex 配置目录的 `third-party-imagegen.json`，按 API 地址指纹区分，不保存 URL 或 Key。供应商入口变化后需重新设置模型；同一本机代理切换上游时无法据地址识别，需核对模型是否仍可用。更新技能时保留此文件。

- 读取 `${CODEX_HOME}/config.toml`，未设置时使用 `~/.codex/config.toml`。按 `model_provider` 选择供应商；支持配置文件中的默认 `profile` 对供应商选择的覆盖。无法读取启动时的 `--profile`、`-c` 或其他进程内覆盖；如会话使用了这些覆盖，先核对配置，不能声称脚本一定与会话一致。
- 认证顺序：供应商声明的 `env_key` 环境变量 → `experimental_bearer_token` → 仅在 `requires_openai_auth=true` 时读取 `auth.json` 的 `OPENAI_API_KEY`。不读取 ChatGPT 登录令牌或 CC-Switch 数据库。
- 在 `base_url` 后追加 `/images/generations` 或 `/images/edits`，不自动添加 `/v1`。保留当前代理入口和系统代理环境，不切换供应商或绕过代理。
- 不写入或输出凭据，不修改 Codex 配置。不会因环境变量里没有 `OPENAI_API_KEY` 就要求另申请官方 Key。
- 不自动重试、切换模型或覆盖文件。超时或结果未知时先核对输出及服务状态；用户明确要求重试后再调用。网络权限按运行环境规则处理。

故障时读取 [故障排查](references/troubleshooting.md)；涉及 CPA/New API 渠道时读取 [管理员接入说明](references/cpa-new-api.md)。本地检查不验证服务端能力，安装本身不需要付费出图。
