# 决策记录

每条：日期、决定了什么、为什么、放弃了什么。

## 2026-11-16 用 pip 安装 uv，缓存和托管 Python 放 D 盘

- **决定**：本机没有 uv，用 `python -m pip install --user uv` 安装（得到 0.10.12），通过
  `python -m uv ...` 调用。每次运行前设置 `UV_CACHE_DIR=D:\uv-cache`、
  `UV_PYTHON_INSTALL_DIR=D:\uv-python`。项目固定 Python 3.12（`.python-version`，
  `requires-python = ">=3.12,<3.13"`），由 uv 下载，不使用系统的 3.13。
- **原因**：AGENTS.md 要求用 uv 管理 3.12，且 C 盘只剩约 14 GB，缓存必须放 D 盘。机器上没有
  winget，pip 是现成的最小改动安装方式。
- **放弃**：官方安装脚本（要执行远程脚本，没有必要）；把缓存路径写进 `pyproject.toml`
  （机器相关的路径不该进仓库，改为写在 README 和 setup 文档里）。
- **注意**：`.venv` 仍在项目目录（C 盘），约几百 MB；缓存跨盘所以 uv 用复制而不是硬链接。

## 2026-11-16 依赖 browser-harness 0.1.13，包装而不是复制

- **决定**：以 PyPI 包 `browser-harness==0.1.13`（MIT，上游提交 8ec26f6，2026-11-15）作为依赖，
  只调用它的公开函数（`admin.ensure_daemon` / `restart_daemon`，`helpers.cdp`、`goto_url`、
  `click_at_xy`、`type_text`、`press_key`、`scroll`、`page_info`、`wait_for_load` 等），
  没有复制或修改它的任何模块。
- **Windows 验证结果**（Windows 11，Edge 157，无头模式）：daemon 通过 TCP 回环（127.0.0.1
  随机端口 + 端口文件里的 token）正常工作；导航、读取无障碍树
  （`Accessibility.getFullAXTree`）、坐标点击、事件缓冲都通过。
- **连接方式**：自己启动一个专用浏览器进程（`--remote-debugging-port` + 独立
  `--user-data-dir`），用 `BU_CDP_URL` 让 daemon 连接它，`BU_NAME` 设为本项目专用名字。
  这样不碰用户日常浏览器的配置和登录状态，也不会触发 Chrome 144+ 的“允许远程调试”弹窗。
- **浏览器**：本机没有安装 Chrome，只有 Edge（Chromium 内核，CDP 相同），先用 Edge；
  可用 `BROWSER_PATH` 换成 Chrome。
- **遥测**：所有运行都设置 `BH_TELEMETRY=0`（已确认 `telemetry.is_enabled()` 返回 False），
  同时设置 `BH_TAB_MARKER=0`，避免 daemon 往页面标题里加标记而影响观察。
- **值得注意的地方**：
  - daemon 冷启动约 17 秒，所以一次评测只启动一次浏览器和 daemon，任务之间只清理状态。
  - daemon 的事件缓冲只有 500 条且读取即清空，一个 Magento 页面的网络事件就会溢出，
    不能用它来录制评测需要的网络记录（见下面 HAR 的决策）。
  - `helpers.cdp()` 默认 5 秒超时，读大页面的无障碍树时要传更长的超时。
  - `helpers` 在 import 时读取 `BU_NAME` 等环境变量，所以必须先设置环境变量再 import。
- **放弃**：连接用户正在使用的浏览器（会动到真实账号，违反 AGENTS.md）；Playwright（设计
  已选定 browser-harness + CDP）；复制 daemon 来加大事件缓冲（包装就够用，不需要改它）。
