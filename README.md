# 第三方供应商图片技能

给通过 **CC-Switch 配置 Codex 第三方供应商**的用户使用：复用现有 URL 和 Key 生成、编辑图片，无需内置图片工具。

## 一句话安装

把下面这句话发给 Codex：

> 请读取 https://github.com/gitHubTree/third-party-imagegen ，按 docs/install.md 安装为当前用户全局可用，后续生成和编辑图片优先使用这个技能。

**给执行安装的 Codex：请先读取 [安装与更新步骤](docs/install.md)，然后完成安装和本地检查。**

需要 Python 3.11+、可联网安装依赖，以及已经配置好的 Codex 供应商。供应商须支持图片 API；聊天能用不代表图片一定能用。

## 使用

安装后新建聊天，直接说：

> 生成一张橘猫坐在窗边看雨的水彩插画。

> 把这张图片的背景改成雪景，保留主体，另存并展示。

首次作图时确认一次供应商支持的图片模型名，技能会记在本地。URL 和 Key 自动读取当前 Codex 配置，不需要抄进技能。编辑时提供图片或本地路径，图片会发送给当前供应商。

技能安装在用户目录，跨项目可用；作图偏好合并到用户级 Codex 指令中。自动选择仍受当前会话指令与工具限制影响。未发现技能时重启 Codex，也可明确说“使用 `$third-party-imagegen`”。

## 更新与排错

更新只需说：“请按这个仓库的安装文档更新第三方图片技能：https://github.com/gitHubTree/third-party-imagegen”。

- [安装与更新步骤](docs/install.md)
- [常见问题](skill/references/troubleshooting.md)
- [CPA / New API 管理员接入](skill/references/cpa-new-api.md)

本地检查不会生成图片或产生图片调用费用；实际作图按供应商计费。仓库不包含密钥、个人配置或虚拟环境。
