# 定时智能体提示词（longalpaca 商业 API 基准测试）

把下面这段**一次性**发给你的本地定时调度智能体（hermes）。它会自己创建每天三次的定时任务，每个任务到点自动跑压测并整理归档——你只需发这一次。

配套：执行脚本 [scripts/perf/run_longalpaca_bench.py](../../scripts/perf/run_longalpaca_bench.py)、策略文档 [benchmark_strategy.md](benchmark_strategy.md)。

---

## 搭建提示词（一次性，发给 hermes）

```text
你是本地定时调度智能体。请在仓库 d:\MyCodes\Trae\evalscope 下，为 longalpaca 商业 API 性能压测建立每天三次的定时自动任务：每个任务到点自动执行压测并整理成归档报告。环境是 Windows + PowerShell。

【一、创建三个每日定时任务】
用你自己的定时机制创建下面 3 个「每天重复触发」的任务。三个任务做的事完全一样（见「二」），唯一区别是 offset：

  | 任务名                  | 触发时间    | offset |
  |-------------------------|------------|git--------|
  | longalpaca-bench-2100   | 每天 21:00 | 500    |
  | longalpaca-bench-0400   | 每天 04:00 | 1000   |
  | longalpaca-bench-1500   | 每天 15:00 | 1500   |

三档 offset 取互不重叠的数据，避免三次之间蹭到彼此残留的服务端缓存（每轮消耗 262 条，间隔 500 > 262，区间不重叠）。

【二、每个任务到点要执行的完整流程】
profile 固定 deepseek-v4-flash-bailian（要换模型/厂商就改这个值；profile 已在脚本 PROFILES 里登记）。

1) 执行压测——切到仓库根目录，运行下面命令，<offset> 用该任务对应的值：
       python scripts/perf/run_longalpaca_bench.py deepseek-v4-flash-bailian <offset>
   说明：脚本已把所有保证公平的参数（数据集/梯队/截断/流式/预热）固化好，API Key 从环境变量 DASHSCOPE_API_KEY 读，不要把明文 key 写进命令。

2) 定位输出——本次结果落在：
       results/longalpaca/<最新时间戳目录>/longalpaca_deepseek-v4-flash-bailian/
   目录内含 perf_report.html（HTML 报告）、benchmark.log（日志）、parallel_{1,8,16}_*/benchmark_data.db（各并发档明细）；命令执行完终端也会打印一张汇总表。取按修改时间最新的那个时间戳目录。

3) 整理归档——按 parallel=1 / 8 / 16 三档分别提取核心指标：
       TTFT(首字延迟，取 P50/P99)、TPOT(单 token 耗时，取 P50/P99)、RPS、TPS，
       辅以 Prompt/Completion Tokens 均值（确认数据稳定、max-tokens 512 生效）、成功/失败请求数。
   不要直接对比总 Latency（受输出长短影响不公平），以 TTFT/TPOT 为准。
   把结果写成一个 Markdown 文件，存到：
       notes/perf-commercial-apis/runs/<YYYYMMDD>_<HHMM>_deepseek-v4-flash-bailian.md
   内含：运行时间、模型、厂商、源结果目录路径、perf_report.html 路径、上面三档指标对比表。
   并在该次任务的执行回执里把这张表贴出来，附一两句点评（有无大量失败、TTFT/TPOT 是否异常偏高）。

4) 异常处理——命令报错或大量请求失败（鉴权失败/超时/限流 429 等）时，不要伪造数据，原样保留关键报错日志和失败统计，并说明可能原因。

【三、建完回执】
三个任务创建完成后，把任务清单（名称 + 触发时间 + offset）回给我确认，并说明如何查看 / 取消这些任务。
```

---

## 前置条件（必须先满足，否则定时任务会失败）

- **API Key 必须是持久环境变量**：我已确认 `DASHSCOPE_API_KEY`（及腾讯 profile 需要的 `TENCENT_API_KEY`）当前在用户级 / 机器级**都没设**。定时任务到点跑时取不到 key 会直接退出。请先设成持久变量：
  ```powershell
  setx DASHSCOPE_API_KEY "你的百炼key"
  # 用腾讯 profile 时再加： setx TENCENT_API_KEY "你的腾讯key"
  ```
  `setx` 写入后**需重开终端 / 让 hermes 任务环境重新加载**才生效。确保 hermes 创建的任务运行账号能读到这些变量。
- **python 指向仓库 venv**：本仓库用的是 `.venv`，解释器在 `d:\MyCodes\Trae\evalscope\.venv\Scripts\python.exe`。若 hermes 任务环境里 `python` 不是它，请在命令里换成这个绝对路径，或先激活 venv。

## 使用说明

- **profile（模型 × 厂商）**：默认 `deepseek-v4-flash-bailian`。换组合时把提示词「二」里的 profile 和归档文件名一起改。profile 需先在 [run_longalpaca_bench.py](../../scripts/perf/run_longalpaca_bench.py) 的 `PROFILES` 里登记（已内置 bailian / tencent × deepseek-v4-flash / v3.2 四个）。
- **为什么 profile 要带厂商名**：同一款模型常在多家厂商都有。输出路径是 `results/longalpaca/<时间戳>/longalpaca_<profile>/`，profile 带厂商（`...-bailian` / `...-tencent`）才能保证**同一模型不同厂商并发跑也不撞目录**（否则 evalscope 发现 `benchmark_data.db` 已存在会直接退出）。
- **每个时段用不同 offset**：21 点档=500、凌晨 4 点档=1000、15 点档=1500。三档取互不重叠的数据，确保即使前一档的服务端缓存还没过期，下一档也打的是全新语料。同档每天用同一 offset，相隔约 24 小时缓存已过期，方便做「同一时段的日间趋势对比」。
- **想手动跑某一档**：直接 `python scripts/perf/run_longalpaca_bench.py deepseek-v4-flash-bailian 500`，只是少了 hermes 那步自动归档与点评。
