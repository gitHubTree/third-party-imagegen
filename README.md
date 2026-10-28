# 第三方供应商图片技能

给通过 **CC-Switch 配置 Codex 第三方供应商**的用户使用：复用现有 URL 和 Key 生成、编辑图片，无需内置图片工具。

## 一句话安装

把下面这句话发给 Codex：

> 请读取 https://github.com/gitHubTree/third-party-imagegen ，按 docs/install.md 安装为当前用户全局可用，后续生成和编辑图片优先使用这个技能。

**给执行安装的 Codex：克隆仓库后在仓库根目录运行 `install.py`（Windows 用 `python`，macOS/Linux 用 Python 3.11+ 的 `python3`），按输出处理提示。细节见 [安装与更新步骤](docs/install.md)。**

也可以自己安装：

```text
git clone https://github.com/gitHubTree/third-party-imagegen.git
cd third-party-imagegen
python install.py            # macOS/Linux 用 python3（须 3.11+）
```

需要 Python 3.11+ 和已经配置好的 Codex 供应商；技能只用标准库，安装不需要 pip 联网。Pillow 可选（`--with-pillow`），只用于转换输出格式。供应商须支持图片 API；聊天能用不代表图片一定能用。

## 使用

安装后新建聊天，直接说：

> 生成一张橘猫坐在窗边看雨的水彩插画。

> 把这张图片的背景改成雪景，保留主体，另存并展示。

首次作图时技能会自动探测当前供应商可用的图片模型（探测不生成图片）并记在本地；切换上游后旧模型失效时会自动重新探测。URL 和 Key 自动读取当前 Codex 配置，不需要抄进技能。编辑时提供图片或本地路径，图片会发送给当前供应商。

技能安装在当前 Codex 用户的 `CODEX_HOME/skills/third-party-imagegen`，跨项目可用。原生图片能力成功时优先使用原生；原生不可用、容量不足或失败时自动切换到当前供应商 API，不要求额外官方 Key，也不会静默改用 PIL 等本地绘图。图片生成耗时较长时必须等待同一个命令会话结束，不能因中间输出重复发起请求。

## 更新与排错

更新：在仓库中 `git pull` 后重新运行 `install.py`。脚本会先备份旧版本，保留模型记忆和 `.venv`，可重复运行。也可以对 Codex 说：“请按这个仓库的安装文档更新第三方图片技能：https://github.com/gitHubTree/third-party-imagegen”。

- [安装与更新步骤](docs/install.md)
- [Windows 安装](skill/references/install-windows.md)
- [macOS 安装](skill/references/install-macos.md)
- [Linux 安装](skill/references/install-linux.md)
- [常见问题](skill/references/troubleshooting.md)
- [CPA / New API 管理员接入](skill/references/cpa-new-api.md)

本地检查不会生成图片或产生图片调用费用；实际作图按供应商计费。仓库不包含密钥、个人配置或虚拟环境。

## 自动测试（GitHub Actions）

[![test](https://github.com/gitHubTree/third-party-imagegen/actions/workflows/test.yml/badge.svg)](https://github.com/gitHubTree/third-party-imagegen/actions/workflows/test.yml)

GitHub Actions 是 GitHub 提供的自动运行服务。每次向仓库推送代码或提交 Pull Request，GitHub 都会在自己的服务器上临时开出全新的 Windows、macOS 和 Linux 环境，检查技能在各系统上能否正常安装和运行。上方徽章显示最近一次的结果，点击可查看每个环境的详细日志。

每次测试的内容：

| 环境 | Python | 说明 |
| --- | --- | --- |
| Windows、macOS、Ubuntu | 3.11 | 不装 Pillow，验证只用标准库也能工作 |
| Windows、macOS、Ubuntu | 3.13 | 安装 Pillow，验证输出格式转换 |
| Debian 系统自带 Python | 3.11 | 没有 ensurepip，验证常见服务器环境 |

每个环境都运行两项测试：

- `tests/test_imagegen.py`：配置读取、模型探测、错误分类、图片保存、网络失败提示等。供应商是模拟的，不发真实请求。
- `tests/test_install.py`：用 `install.py` 往临时目录实际安装，再执行更新、备份和虚拟环境重建，最后运行 `--check`。

测试不使用任何密钥或个人配置，不访问真实的供应商或 CC-Switch，不产生图片费用。公开仓库使用 GitHub Actions 免费。配置文件是 [.github/workflows/test.yml](.github/workflows/test.yml)；不需要时删除该文件，或在仓库 Settings → Actions 中停用。

在本机运行同样的测试：

```text
python tests/test_imagegen.py
python tests/test_install.py
```
