# 定时智能体提示词（longalpaca 商业 API 基准测试）

把下面这段**一次性**发给你的本地定时调度智能体（hermes）。它会自己创建每天三次的定时任务，每个任务到点自动跑压测并整理归档——你只需发这一次。

> ⚠️ **迁移说明**：本文档此前依赖的 [run_longalpaca_bench.py](../../scripts/perf/run_longalpaca_bench.py) 与 [run_perf_one.py](../../scripts/perf/run_perf_one.py) 已删除，现已统一改用原生 `evalscope perf` 命令（`--url` / `--api-key` 显式传入）；批量多模型评测 + 出对比报告可用 `.trae/skills/evalscope-eval-compare` skill。

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
本次要测的 (模型 × 厂商) 列表（要加/减模型就改这个列表），统一 --dataset-offset 10：
       deepseek-v4-pro_aliyun     # 模型名 deepseek-v4-pro，厂商 aliyun
       deepseek-v4-pro_tencent    # 模型名 deepseek-v4-pro，厂商 tencent
说明：每个条目要给出 模型名、厂商后缀、url、api_key 四要素，拼成一条原生 evalscope perf 命令。
   加模型 = 在下面「1) 执行压测」里加一条命令（或改用 .trae/skills/evalscope-eval-compare 的 YAML 加一条）。
   每条命令用 --name longalpaca_<model>_<vendor> 带厂商名，落到不同目录互不撞车，所以可以同时并发跑。

1) 执行压测——切到仓库根目录，对列表里的**每个** (模型,厂商) 起一条原生 evalscope perf 命令，可同时并发启动（PowerShell 后台作业示例）：
       Start-Job { evalscope perf --url <阿里云url> --api-key <key> --model deepseek-v4-pro --dataset longalpaca --dataset-offset 10 --max-tokens 512 --parallel 1 8 16 --number 20 80 160 --temperature 0 --top-p 1.0 --stream --warmup-num 2 --read-timeout 300 --name longalpaca_deepseek-v4-pro_aliyun }
       Start-Job { evalscope perf --url <腾讯云url> --api-key <key> --model deepseek-v4-pro --dataset longalpaca --dataset-offset 10 --max-tokens 512 --parallel 1 8 16 --number 20 80 160 --temperature 0 --top-p 1.0 --stream --warmup-num 2 --read-timeout 300 --name longalpaca_deepseek-v4-pro_tencent }
       Get-Job | Wait-Job        # 等全部跑完
   也可顺序一条条跑（不在意耗时的话）。命令已固化所有保证公平的参数（数据集/梯队/截断/流式/预热/数据游标）；url 和 api_key 直接显式传在命令里（或提前设成变量）。

2) 定位输出——对每个 (模型,厂商)，本次结果落在：
       outputs/<最新时间戳目录>/longalpaca_<model>_<vendor>/
   （如 longalpaca_deepseek-v4-pro_aliyun / longalpaca_deepseek-v4-pro_tencent）。
   目录内含 perf_report.html（HTML 报告）、benchmark.log（日志）、parallel_{1,8,16}_*/benchmark_data.db（各并发档明细）；命令执行完终端也会打印一张汇总表。各 (模型,厂商) 取按修改时间最新的那个时间戳目录。

3) 整理归档——对**每个** profile 分别按 parallel=1 / 8 / 16 三档提取核心指标：
       TTFT(首字延迟，取 P50/P99)、TPOT(单 token 耗时，取 P50/P99)、RPS、TPS，
       辅以 Prompt/Completion Tokens 均值、成功/失败请求数。
   注意：Completion Tokens 均值应在 ~500，借此确认 max-tokens 512 已生效、对比基础公平。
   不要直接对比总 Latency（受输出长短影响不公平），以 TTFT/TPOT 为准。
   每个 profile 各写一个 Markdown 文件，存到：
       notes/perf-commercial-apis/runs/<YYYYMMDD>_<HHMM>_<profile>.md
   内含：运行时间、模型、厂商、源结果目录路径、perf_report.html 路径、上面三档指标对比表。
   并在该次任务的执行回执里把各 profile 的表都贴出来，附一两句点评（有无大量失败、TTFT/TPOT 是否异常偏高）；多个 profile 建议再附一张同档横向对比表（同模型跨厂商谁更快）。

4) 异常处理——命令报错或大量请求失败（鉴权失败/超时/限流 429 等）时，不要伪造数据，原样保留关键报错日志和失败统计，并说明可能原因。命令设了 --read-timeout 300s 且 perf 不自动重试，单条超时即计为失败、属正常现象；但若失败数大面积偏高，需在点评里点出（多半是限流或服务端卡死）。**某个 (模型,厂商) 失败不影响其它**——分别记录，能跑出来的照常归档。

【三、建完回执】
三个任务创建完成后，把任务清单（名称 + 触发时间）回给我确认，并说明如何查看 / 取消这些任务。
```

---

## 前置条件（必须先满足，否则定时任务会失败）

- **API Key 通过命令显式传入**：`--url` / `--api-key` 直接写在压测命令里（或用 `.trae/skills/evalscope-eval-compare` 的 YAML 配置，key 只存在于本地 YAML）。⚠️ 明文 key 别推到公开仓库。
- **python 指向仓库 venv**：本仓库用的是 `.venv`，解释器在 `d:\MyCodes\Trae\evalscope\.venv\Scripts\python.exe`。若 hermes 任务环境里 `python` 不是它，请在命令里换成这个绝对路径，或先激活 venv。

## 使用说明

- **profile（模型 × 厂商）**：默认测 `deepseek-v4-pro_aliyun` + `deepseek-v4-pro_tencent` 两个。直接用原生 `evalscope perf` 命令，`--name longalpaca_<model>_<vendor>` 带上厂商名、`--url`/`--api-key` 显式传入；加模型就多写一条命令（或用 skill 的 YAML 加一条）。
- **为什么 profile 要带厂商名**：同一款模型常在多家厂商都有。输出路径是 `outputs/<时间戳>/longalpaca_<model>_<vendor>/`，`--name` 带厂商（`..._aliyun` / `..._tencent`）才能保证**同一模型不同厂商并发跑也不撞目录**（否则 evalscope 发现 `benchmark_data.db` 已存在会直接退出）。
- **offset 写进目录名**：`--dataset-offset` 决定游标，复测用不同 offset 取不相交子集；`--name` 里带上 offset 就能各自独立不撞目录。
- **同时跑多个模型**：每个 (模型,厂商) 各起一条原生命令即可并发，互不干扰。例如同时打阿里云与腾讯云：
  ```powershell
  evalscope perf --url <阿里云url> --api-key <key> --model deepseek-v4-pro --dataset longalpaca --dataset-offset 10 --max-tokens 512 --parallel 1 8 16 --number 20 80 160 --temperature 0 --top-p 1.0 --stream --warmup-num 2 --read-timeout 300 --name longalpaca_deepseek-v4-pro_aliyun
  evalscope perf --url <腾讯云url> --api-key <key> --model deepseek-v4-pro --dataset longalpaca --dataset-offset 10 --max-tokens 512 --parallel 1 8 16 --number 20 80 160 --temperature 0 --top-p 1.0 --stream --warmup-num 2 --read-timeout 300 --name longalpaca_deepseek-v4-pro_tencent
  ```
  两条 `--name` 各带厂商，落到不同目录，可在两个终端或后台同时启动。
- **想手动跑一次**：直接跑上面的原生 `evalscope perf` 命令即可，只是少了 hermes 那步自动归档与点评。
- **测推理模型的深度思考**：加 `--extra-args '{"reasoning_effort":"high"}'`（`reasoning_effort` 不是 perf 原生 CLI 参数，只能经 `--extra-args` 注入请求体）。⚠️ 仅推理模型可开，非推理模型加了会报错。
