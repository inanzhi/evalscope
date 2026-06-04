# 定时智能体提示词（longalpaca 商业 API 基准测试）

把下面这段**一次性**发给你的本地定时调度智能体（hermes）。它会自己创建每天三次的定时任务，每个任务到点自动跑压测并整理归档——你只需发这一次。

配套：执行脚本 [scripts/perf/run_longalpaca_bench.py](../../scripts/perf/run_longalpaca_bench.py)、策略文档 [benchmark_strategy.md](benchmark_strategy.md)。

---

## 搭建提示词（一次性，发给 hermes）

```text
你是本地定时调度智能体。请在仓库 d:\MyCodes\Trae\evalscope 下，为 longalpaca 商业 API 性能压测建立每天三次的定时自动任务：每个任务到点自动执行压测并整理成归档报告。环境是 Windows 11 + PowerShell 7。

【一、创建三个每日定时任务】
用你自己的定时机制创建下面 3 个「每天重复触发」的任务。三个任务做的事完全一样（见「二」），只是触发时间不同：

  | 任务名                  | 触发时间    |
  |-------------------------|------------|
  | longalpaca-bench-2100   | 每天 21:00 |
  | longalpaca-bench-0400   | 每天 04:00 |
  | longalpaca-bench-1500   | 每天 15:00 |

【二、每个任务到点要执行的完整流程】
本次要测的 profile 列表（要加/减模型就改这个列表），统一 offset=10：
       deepseek-v4-pro_aliyun
       deepseek-v4-pro_tencent
说明：profile 名固定写成 "<模型名>_<厂商名>"（厂商 = 最后一个下划线之后那段）。
   要加模型，只需：① 在脚本 scripts/perf/run_longalpaca_bench.py 的 PROFILES 列表里加一行同样格式的字符串；② 在上面这个列表里也加上。
   模型名/厂商/URL/Key 全部由 profile 名自动推导，命令和输出目录都按 profile 名自动生成，无需改其它任何地方。
   列表里每个 profile 都要跑、各自独立归档；它们 name 带 profile+offset，落到不同目录互不撞车，所以可以同时并发跑。

1) 执行压测——切到仓库根目录，对列表里的**每个** profile 起一条命令，可同时并发启动（PowerShell 后台作业示例）：
       Start-Job { python scripts/perf/run_longalpaca_bench.py deepseek-v4-pro_aliyun 10 }
       Start-Job { python scripts/perf/run_longalpaca_bench.py deepseek-v4-pro_tencent 10 }
       Get-Job | Wait-Job        # 等全部跑完
   也可顺序一条条跑（不在意耗时的话）。脚本已把所有保证公平的参数（数据集/梯队/截断/流式/预热/数据游标）固化好；URL 和 API Key 已写死在 scripts/perf/run_perf_one.py 的 VENDORS 里（本脚本直接复用），命令里不需要任何 key，也不依赖环境变量。

2) 定位输出——对每个 profile，本次结果落在：
       results/longalpaca/<最新时间戳目录>/longalpaca_<profile>_offset-10/
   （如 longalpaca_deepseek-v4-pro_aliyun_offset-10 / longalpaca_deepseek-v4-pro_tencent_offset-10）。
   目录内含 perf_report.html（HTML 报告）、benchmark.log（日志）、parallel_{1,8,16}_*/benchmark_data.db（各并发档明细）；命令执行完终端也会打印一张汇总表。各 profile 取按修改时间最新的那个时间戳目录。

3) 整理归档——对**每个** profile 分别按 parallel=1 / 8 / 16 三档提取核心指标：
       TTFT(首字延迟，取 P50/P99)、TPOT(单 token 耗时，取 P50/P99)、RPS、TPS，
       辅以 Prompt/Completion Tokens 均值、成功/失败请求数。
   注意：Completion Tokens 均值应在 ~500，借此确认 max-tokens 512 已生效、对比基础公平。
   不要直接对比总 Latency（受输出长短影响不公平），以 TTFT/TPOT 为准。
   每个 profile 各写一个 Markdown 文件，存到：
       notes/perf-commercial-apis/runs/<YYYYMMDD>_<HHMM>_<profile>.md
   内含：运行时间、模型、厂商、源结果目录路径、perf_report.html 路径、上面三档指标对比表。
   并在该次任务的执行回执里把各 profile 的表都贴出来，附一两句点评（有无大量失败、TTFT/TPOT 是否异常偏高）；多个 profile 建议再附一张同档横向对比表（同模型跨厂商谁更快）。

4) 异常处理——命令报错或大量请求失败（鉴权失败/超时/限流 429 等）时，不要伪造数据，原样保留关键报错日志和失败统计，并说明可能原因。脚本设了 read-timeout 300s 且 perf 不自动重试，单条超时即计为失败、属正常现象；但若失败数大面积偏高，需在点评里点出（多半是限流或服务端卡死）。**某个 profile 失败不影响其它**——分别记录，能跑出来的照常归档。

【三、建完回执】
三个任务创建完成后，把任务清单（名称 + 触发时间）回给我确认，并说明如何查看 / 取消这些任务。
```

---

## 前置条件（必须先满足，否则定时任务会失败）

- **API Key 已写死在脚本里，无需环境变量**：URL 和 API Key 集中维护在 [run_perf_one.py](../../scripts/perf/run_perf_one.py) 顶部的 `VENDORS` 字典里（填一次，`run_longalpaca_bench.py` 直接 `import` 复用），定时任务到点跑时不再依赖 `DASHSCOPE_API_KEY` / `TENCENT_API_KEY` 环境变量。换 key / 换 URL / 加厂商，只改 `VENDORS` 这一处。⚠️ 明文 key 在源码里，注意别把这两个脚本推到公开仓库。
- **python 指向仓库 venv**：本仓库用的是 `.venv`，解释器在 `d:\MyCodes\Trae\evalscope\.venv\Scripts\python.exe`。若 hermes 任务环境里 `python` 不是它，请在命令里换成这个绝对路径，或先激活 venv。

## 使用说明

- **profile（模型 × 厂商）**：默认测 `deepseek-v4-pro_aliyun` + `deepseek-v4-pro_tencent` 两个。profile 名固定格式 `<模型名>_<厂商名>`（厂商 = 最后一个下划线之后那段，须是 `VENDORS` 里登记过的厂商，目前 aliyun / tencent）。**加一个模型 = 两步**：① 往 [run_longalpaca_bench.py](../../scripts/perf/run_longalpaca_bench.py) 的 `PROFILES` 列表里加一行 `'<模型名>_<厂商名>'` 字符串；② 在提示词「二」开头的 profile 列表里也加上。模型名 / 厂商 / URL / Key 全部从 profile 名 + `VENDORS` 自动推导，命令、输出目录、归档文件名都按 `<profile>` 自动生成，无需另改任何地方。
- **为什么 profile 要带厂商名**：同一款模型常在多家厂商都有。输出路径是 `results/longalpaca/<时间戳>/longalpaca_<profile>_offset-<offset>/`，profile 带厂商（`..._aliyun` / `..._tencent`）才能保证**同一模型不同厂商并发跑也不撞目录**（否则 evalscope 发现 `benchmark_data.db` 已存在会直接退出）。
- **offset 写进目录名**：结果目录后缀 `_offset-<offset>`，所以同一 profile 用不同 offset 复测、或多档并发也各自独立不撞目录。命令第 2 个参数即 offset（如上例传 `10`）；不传则用脚本内置默认 500。
- **同时跑多个模型**：每个 profile 各起一条命令即可并发，互不干扰。例如同时打阿里云与腾讯云：
  ```powershell
  python scripts/perf/run_longalpaca_bench.py deepseek-v4-pro_aliyun 10
  python scripts/perf/run_longalpaca_bench.py deepseek-v4-pro_tencent 10
  ```
  两条 name 各带 profile+offset，落到不同目录，可在两个终端或后台同时启动。
- **想手动跑一次**：直接 `python scripts/perf/run_longalpaca_bench.py deepseek-v4-pro_aliyun 10`，只是少了 hermes 那步自动归档与点评。
- **测推理模型的深度思考**：在脚本 `FIXED` 里取消注释 `extra_args={'reasoning_effort': 'high'}`（`reasoning_effort` 不是 perf 原生 CLI 参数，只能经 `extra_args` 注入请求体）。⚠️ 仅推理模型可开，非推理模型加了会报错。
