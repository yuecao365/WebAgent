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
  只调用它的公开函数（`admin.ensure_daemon` / `restart_daemon`，`helpers.cdp`、
  `click_at_xy`、`type_text`、`press_key`、`scroll`、`page_info`、`wait_for_load`、
  `wait_for_network_idle`），没有复制或修改它的任何模块。
- **Windows 验证结果**（Windows 11，Edge 157，无头模式）：daemon 通过 TCP 回环（127.0.0.1
  随机端口 + 端口文件里的 token）正常工作；导航、读取无障碍树
  （`Accessibility.getFullAXTree`）、坐标点击、事件缓冲都通过。
- **连接方式**：自己启动一个专用浏览器进程（`--remote-debugging-port` + 独立
  `--user-data-dir`），用 `BU_CDP_URL` 让 daemon 连接它；`BH_HOME` 指向项目自己的数据目录，
  daemon 的端口文件、日志都在里面。这样不碰用户日常浏览器的配置和登录状态，也不会触发
  Chrome 144+ 的“允许远程调试”弹窗。
- **浏览器**：本机没有安装 Chrome，只有 Edge（Chromium 内核，CDP 相同），先用 Edge；
  可用 `BROWSER_PATH` 换成 Chrome。
- **遥测**：所有运行都设置 `BH_TELEMETRY=0`（已确认 `telemetry.is_enabled()` 返回 False），
  同时设置 `BH_TAB_MARKER=0`，避免 daemon 往页面标题里加标记而影响观察。
- **值得注意的地方**：
  - daemon 的事件缓冲只有 500 条且读取即清空，一个 Magento 页面的网络事件就会溢出，
    不能用它来录制评测需要的网络记录（见“自己录制 HAR”）。
  - `helpers.cdp()` 默认 5 秒超时，读大页面的无障碍树时要传更长的超时（这里用 60 秒）。
  - `helpers` 在 import 时读取 `BU_NAME` 等环境变量，所以必须先设置环境变量再 import。
  - 非 `default` 名字的 daemon 会开后台标签页，这一点带来了下一条决策。
- **放弃**：连接用户正在使用的浏览器（会动到真实账号，违反 AGENTS.md）；Playwright（设计
  已选定 browser-harness + CDP）；复制 daemon 来加大事件缓冲（包装就够用，不需要改它）。

## 2026-11-16 前台标签页：daemon 名字用 default，并关闭后台节流

- **现象**：最初给 daemon 起了专用名字 `browser-agent`。结果后台列表页要 40 秒才渲染完，
  而且表格行在无障碍树里是空的（客户列表 72 行只有 178 行文本，表格宽高为 0）；daemon
  冷启动也要 17 秒。服务器本身每个请求不到 1 秒。
- **原因**：browser-harness 给非 `default` 名字的 daemon 单独开一个**后台**标签页
  （`Target.createTarget(background=True)`）。后台页面 `visibilityState` 是 hidden：Chrome
  把定时器限制为每秒一次（RequireJS 靠定时器串行加载几百个脚本），并且不对后来插入的内容
  做布局，这些节点在无障碍树里被标成 notRendered。
- **决定**：
  1. daemon 名字用 `default`，它会附着到浏览器自己的前台标签页；因为 `BH_HOME` 是项目专用
     目录，这个名字不会和用户机器上别的 browser-harness daemon 冲突。连接后再调用一次
     `Page.bringToFront`。
  2. 浏览器启动参数加 `--disable-background-timer-throttling`、
     `--disable-backgrounding-occluded-windows`、`--disable-renderer-backgrounding`。
  3. “页面稳定”的判断改为：load 事件 + 网络空闲 500 毫秒 + 元素数量连续两次不变，总超时
     30 秒。只等 load 事件时，1–2 秒就返回，拿到的是半成品页面。
- **结果**：会话启动 4.6 秒；仪表盘、客户列表、订单列表 2–3 秒稳定，商品编辑页约 5 秒；
  客户列表 1018 行文本，内容完整。
- **放弃**：给每个页面加站点专用的等待条件（例如等 Magento 的 loading mask 消失）——那是
  针对单个站点的知识，不该写进通用 harness。

## 2026-11-16 WebArena Verified：镜像、端口、reset 方式

- **决定**：只用 shopping-admin。镜像 `am1n3e/webarena-verified-shopping_admin:0.1.0`
  （Docker Hub，与当天的 `latest` 是同一个 digest `sha256:d0531dd27ed9…`），按 tag 固定，
  保证每次运行的站点数据一致。下载 1.25 GB，`docker images` 显示占用 4.49 GB（文档写的是
  解压后 2.9 GB，实际更大）。Docker Desktop + WSL2，数据盘已由用户移到
  `D:\Docker\DockerDesktopWSL`。
- **端口**：站点 7780、env-ctrl 7781，只发布在 127.0.0.1 上。
- **reset = 重建容器**：容器里的 env-ctrl 没有 reset 接口（`POST /reset` 返回 404，文档里有
  一处提到但代码没有实现，只有 `/status`、`/init`、`/start`、`/stop`、`/restart`）。官方的
  `SiteHandler.reset()` 就是“删除容器再启动并初始化”，这里做同样的事：`docker rm -f` →
  `docker run` → 等到 `/status` 健康并且带登录头请求 `/admin` 连续两次跳到仪表盘。实测一次
  78 秒，改动过的数据库值恢复为原值。
- **登录**：用镜像自带的请求头 `X-M2-Admin-Auto-Login: admin:admin1234`（基准公开的测试
  账号），通过 `Network.setExtraHTTPHeaders` 加到标签页的每个请求上，不走登录表单。
- **评测器**：直接在进程内调用 `webarena-verified==1.2.3` 的 `WebArenaVerified.evaluate_task`，
  成功与否完全由它判定。
- **放弃**：直接恢复数据库快照来加速 reset（要进容器操作 MySQL 和 Magento 缓存，偏离官方
  做法，结果可信度变差）；只在修改类任务后 reset（智能体在查询类任务里也可能误改数据）。
  runner 里保留了 `reset: "never"` 选项，仅用于调试。
- **代价**：60 个任务每轮 reset 合计约 78 分钟，这部分时间不计入任务耗时，单独记在
  `reset_seconds`。

## 2026-11-16 自己录制 HAR

- **决定**：`browser/network.py` 另开一条 CDP WebSocket 连接到同一个浏览器，监听所有页面的
  `Network.*` 事件，生成 HAR 文件交给官方评测器。静态资源（Image、Stylesheet、Font、
  Script、Media）不写入。
- **原因**：评测器对导航类和修改类任务要看网络记录（URL、方法、状态码、POST 数据、
  referer）。browser-harness 的事件缓冲太小（见上）。
- **细节**：真实请求头（cookie、`sec-fetch-*`）在 `requestWillBeSentExtraInfo` 里，和主事件
  的先后顺序不固定；重定向链共用一个 requestId。所以按“同一 requestId 内的第几个”来配对。
  评测器靠 `sec-fetch-*` 判断是否导航，缺了它会误判。
- **放弃**：响应体（shopping-admin 的评测规则不用 `response_content`，省掉大量数据）；
  Playwright 的 trace 格式。

## 2026-11-16 观察：完整的无障碍树文本，ref 用 backendNodeId

- **决定**：观察 = URL、标题、滚动位置 + 整页无障碍树，每个节点一行
  `[ref] role "name"`，加上 value 和少数状态（checked、expanded、disabled 等），缩进表示层级。
  本阶段不做任何裁剪和摘要。
- **ref 用 CDP 的 backendDOMNodeId**：节点存在期间不变，所以历史里旧观察的 ref 要么仍指向
  同一个元素，要么明确报错“不在当前页面”，不会悄悄指到别的元素上。
- **去掉的东西**（不丢内容）：被标为 ignored 的节点、没有名字的 generic/none/presentation
  包装节点（子节点上提一层）、InlineTextBox、和父节点名字完全相同的 StaticText。
- **安全上限**：单次观察超过 30 万字符时截断并写明省略了多少，避免超出模型上下文。
- **原因**：里程碑 1 要的是“朴素而完整”的基线，之后 E1 才能量出裁剪省了多少。无名包装节点
  如果留着，会把基线撑大、让 E1 的节省虚高，所以在基线里就去掉。
- **放弃**：每次观察重新编号的小整数 ref（省一点 token，但旧观察里的 ref 会指错元素）；
  只给可交互元素编号（有些可点击的东西只是带文字的 div）；链接的 href（token 太多，留给
  之后的裁剪组件决定）。
- **已知局限**：订单列表一页 200 行，一次观察约 12.8 万字符；iframe 里的内容读不到。

## 2026-11-16 工具集和 finish 的结构

- **决定**：本阶段的工具是 `click`、`type`、`goto`、`scroll`、`read_page`、`finish`，都用
  严格 schema（所有字段必填，`additionalProperties: false`），参数再用 pydantic 校验一遍。
  `run_skill`、`write_note` 等记忆和上下文组件做的时候再加。
- **每步只执行一个工具调用**：前一个动作会改变页面，后一个调用的 ref 可能已经失效。请求里
  关掉并行调用；模型仍然发多个时只执行第一个，其余返回“未执行”。
- **动作之后直接返回新页面**，`read_page` 只用于不操作而重读（例如等加载）。
- **下拉框**：`type` 作用在 `<select>` 上时按文字选择选项，点击 `<option>` 也直接选中。
  原生下拉列表画在页面之外，CDP 鼠标点不到，所以不单独加 select 工具。
- **`finish`**：字段和 WebArena Verified 的应答一致（task_type、status、retrieved_data、
  error_details）。`retrieved_data` 是“写成字符串的 JSON 数组”，因为严格 schema 描述不了
  “元素是任意键的对象”的数组；工具里解析并校验，格式不对就把错误退回给模型。
- **goto 只允许任务站点的源**；另外浏览器启动参数里用 `--host-resolver-rules` 让它只能解析
  localhost，从网络层面保证不会访问真实网站。
- **放弃**：非严格 schema；让 finish 接收自由文本答案再由程序猜结构。

## 2026-11-16 模型调用：两种 provider，价格和上限来自 .env

- **决定**：`harness/llm.py` 是唯一调用模型的地方。支持两种官方 SDK：`openai`（任何兼容
  Chat Completions 的服务，配 `LLM_BASE_URL`）和 `anthropic`。`LLM_PROVIDER` 不填时，模型名以
  `claude` 开头用 anthropic，否则用 openai。
- **价格由用户在 `.env` 里填**（`LLM_PRICE_INPUT_PER_MTOK`、`LLM_PRICE_OUTPUT_PER_MTOK`，
  可选缓存读、缓存写的价格），缺了就拒绝付费运行。**原因**：模型由用户选，内置价格表会过期，
  成本数字错了比没有更糟。
- **`BUDGET_USD` 是累计上限**：对 `results/spend.jsonl` 里记录的全部花费生效，跨运行累计。
  每次调用前按“估算的输入 token（字符数 ÷ 3，偏高）+ 最大输出 token”预留成本，加上已花的
  超过上限就不发请求，抛 `BudgetExceededError`，整个运行停止。所以实际会在上限之前停下。
- **记账**：每次成功调用往 `spend.jsonl` 追加一行（运行名、任务、模型、四类 token、美元、
  尝试次数、耗时）；`spend.md` 是按运行汇总的表，每次运行结束重写。
- **重试自己做**：两个 SDK 的自动重试都关掉（`max_retries=0`），在 `LLMClient` 里统一处理：
  限流、连接错误、超时、5xx 重试，指数退避加抖动，最多 4 次；其他错误不重试。这样两种
  provider 行为一致，重试次数进日志，也能离线测试。
- **Anthropic 的细节**：`tool_choice` 用 `auto` + `disable_parallel_tool_use`（新模型不接受
  强制工具调用）；不传 thinking 和采样参数；模型返回的 content 原样回传（保留 thinking 块）。
- **不启用拒答后的自动降级（server-side fallback）**：评测要量的是指定模型的成功率和成本，
  悄悄换成另一个模型会让数字失真。拒答记为 `model_refusal`，任务失败。
- **prompt caching 是开关**（`switches.prompt_caching`，默认关），缓存 token 的记账已经
  支持；提示词的缓存友好布局属于里程碑 2。
- **`LLM_OPENAI_MINIMAL=1`**：有些兼容服务不认 `strict`、`parallel_tool_calls`、
  `max_completion_tokens`，这个开关去掉它们。
- **放弃**：LiteLLM 之类的统一封装（AGENTS.md 要求不用框架，而且会遮住 token 细节）。

## 2026-11-16 循环：预算、卡住检测、失败恢复

- **预算**：每个任务有步数、token、时间、美元四个上限（默认 30 步、100 万 token、900 秒、
  2 美元，可在配置里改）。任何一个用完，就再给模型**一次**只带 `finish` 工具的调用，让它
  交出当前答案（强制结束）。所以任务预算是“软”的，最多超出一次调用；硬上限是
  `BUDGET_USD`。模型在强制结束时仍不调用 finish，就记为没有答案，评测时按
  `UNKNOWN_ERROR` 提交。
- **卡住检测**：同一个调用（工具名 + 参数）连续 3 次，或页面指纹连续 4 步没变，就在工具
  结果里追加一段“换策略”的提示。提示给过 2 次后再卡住，强制结束，原因记为 `stuck`。
- **失败恢复**：工具调用失败时把错误原文返回给模型让它重试；连续失败 3 次，回到最近一个
  操作成功的页面（URL），并把这一点告诉模型。
- **结束原因**：finished、budget_steps、budget_tokens、budget_time、budget_usd、stuck、
  spend_cap、model_error、model_refusal，写进每个任务的记录。
- **留给后续组件的接口**：`AgentLoop(view_messages=...)` 决定模型看到的历史（压缩、工作
  笔记用），`ToolExecutor(render_observation=...)` 决定观察的文本（裁剪、diff 用）。默认都是
  原样输出，没有做任何里程碑 2 的功能。

## 2026-11-16 事件日志和结果目录

- **决定**：每个任务一个只追加的 `events.jsonl`（task_start、model_call、tool_call、
  tool_result、nudge、stuck、recovery、budget、task_end），已存在的文件拒绝覆盖。
  `replay()` 从事件重建步骤序列、动作列表、token 和成本合计。
- **目录**：`results/<日期>_<名字>/`，里面是 `config.json`、`records.jsonl`、
  `summary.json`、`summary.md`；同名目录已存在时加 `_2`、`_3`，不覆盖。事件日志、HAR、
  应答和评测结果在 `traces/<任务号>/` 下，这个目录不进 git（单个任务可达几 MB，HAR 里还有
  会话 cookie）。
- **超过 5 个任务的运行要加 `--confirm-paid`**：对应 AGENTS.md “超过冒烟测试规模要先得到
  用户同意”，在创建任何目录、花任何钱之前就拒绝。

## 2026-11-16 任务子集：15 个模板 × 4 个任务

- **决定**：`configs/subset.json` 由 `build_subset()` 按固定规则生成，`scripts/build_subset.py`
  可以随时重建，测试会检查文件和规则是否一致。规则：
  1. 只要单站点 shopping-admin 任务，且期望状态是 SUCCESS（共 176 个）。同一模板里“期望
     失败”的任务考的是另一种能力，去掉后模板内的任务流程一致，适合“学一个、测其余”。
  2. 去掉评测器无法判为通过的模板（目前只有 253，见下）。
  3. 模板至少有 4 个这样的任务，且任务类型单一。
  4. 按类型配额选模板：查询 7、修改 6、导航 2，接近数据集里 47% / 43% / 10% 的比例。同一
     类型内用固定种子（0，每个类型各用一个随机数发生器）随机排序后依次选取；措辞和已选模板
     相似度超过 0.8 的跳过（例如“3 星以下的评论”和“4 星以上的评论”只留一个）。
  5. 每个模板取任务号最小的 4 个，第一个标 `learn`，其余标 `test`。
- **结果**：15 个模板、60 个任务（15 learn + 45 test）。
- **去掉模板 253（“Go to the list of orders that are {{status}}”，任务 676–680）**：它们是
  导航类任务，期望的网络事件却是订单表格取数据的 XHR（`mui/index/render` 带
  `filters[status]=...`）。评测器 1.2.3 对导航类任务只取网络记录里**最后一次页面导航**来
  比较，XHR 不算页面导航，所以即使操作完全正确也是 0 分。验证方法：拿真实录制的 HAR，手工
  追加一条参数完全符合期望的 XHR，评测结果仍是失败（“Checked 1 event(s) but none
  matched”）。仓库最新代码和 PyPI 1.2.3 的这段逻辑相同。留着它们只会白花钱、拉低所有实验
  组的成功率。规则写在 `scorable()` 里：导航类任务的期望 URL 是 `/mui/index/render` 就算
  不可评分。其他模板没有逐个验证评测器能否通过，跑基线时如果某个模板全部失败需要再查。
- **原因**：15 × 4 比 20 × 3 每个模板多一个测试任务，E2 里“学过的模板”上的信号更稳；随机
  选模板避免人为挑容易的；规则写成代码，可复现。
- **放弃**：手工挑选模板；用官方的 hard 子集（它按难度选，模板内任务数不均匀）；每个模板
  取 5 个（总数会到 75）。
- **冒烟测试用的 5 个任务**：344、208（查询）、704（导航）、470、496（修改），都是各自模板
  的 learn 任务，三种类型都覆盖。

## 2026-11-16 先测量：每次调用的 token 拆分和提示词分区

- **决定**：`harness/llm.py` 每次调用都记录输入 token 的三种（未缓存、缓存读、缓存写）和
  输出 token（已有），并新增**提示词分区**的估算：system、tools、task、history、
  observation、notes、status。写入 `spend.jsonl` 和事件日志的 `model_call`；每个任务的记录
  和运行汇总里有合计、缓存命中率（缓存读 ÷ 全部输入 token）和各分区每任务平均 token。
- **怎么分区**：消息由带分区标签的片段（`Part`）组成。最后一条消息的片段按自己的标签算
  （它是每步都变的“尾部”）；更早的消息里，任务算 task，其余都算 history——不管它当初是不是
  观察。
- **怎么估算**：API 只给出提示词 token 总数，所以按各分区字符数占比去分摊实测总数。合计
  等于实测值，分区之间的比例是近似的（假设每个分区“每 token 的字符数”差不多）。
- **放弃**：给每个分区单独调用 tokenizer（各家模型的 tokenizer 不同，离线也拿不到，为了
  一个诊断数字不值得）。
