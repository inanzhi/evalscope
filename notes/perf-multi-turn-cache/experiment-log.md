# 多轮缓存命中率对比 — 实验记录

> 配套方法见 [README.md](./README.md) 第 8 节。本文件只记录**实际跑出来的数据**。

---

## 第 0 步：统一数据集（已完成 ✅）

- **时间**：2026-06-01
- **命令**（README 8.5）：

```powershell
python scripts/perf/build_swe_smith_dataset.py `
  --model-path Qwen/Qwen2.5-7B-Instruct `
  --first-turn-length 8192 --subsequent-turn-length 1024 `
  --min-turns 4 --max-turns 12 `
  --number 10 `
  --output-path outputs/agentic_dataset.json --seed 42
```

- **产物**：`outputs/agentic_dataset.json`（538 KB）
- **构建日志**：`outputs/build_log.txt`

### 数据集统计

| 项 | 值 |
|---|---|
| 预筛候选 (Pre-filter candidates) | 12413（11687 太短被跳过，0 解析失败） |
| 实际构建对话数 | **10**（构建期 4 条因轮数不足被丢弃） |
| 每条对话轮数 | min=4, max=11, avg=7.4 |
| 各对话轮数明细 | `[8, 7, 5, 11, 5, 9, 11, 4, 5, 9]` |
| 第 1 轮 prompt tokens | min=8231, max=8281, avg=8248（贴合目标 8192） |
| 末轮 prompt tokens | min=11348, max=18630, avg=14898 |

> tokenizer=Qwen2.5-7B-Instruct（仅算 token，不推理）；seed=42 可复现。
>
> **池子说明**：预筛候选有 12413 条，但本次只 `--number 10`，池子=跑的条数 → **offset 无效**（README 8.6.2）。
> 横向对比统一用这份 `agentic_dataset.json`（offset=0）。复测取平均改用下方的大池子。

---

## 第 0 步附加：最大池子（已完成 ✅，供复测错开残留缓存）

- **时间**：2026-06-01
- **命令**（README 8.5.1 第 2 步，探测已知候选=12413）：

```powershell
python scripts/perf/build_swe_smith_dataset.py `
  --model-path Qwen/Qwen2.5-7B-Instruct `
  --first-turn-length 8192 --subsequent-turn-length 1024 `
  --min-turns 4 --max-turns 12 `
  --number 12413 `
  --output-path outputs/agentic_pool.json --seed 42
```

- **产物**：`outputs/agentic_pool.json`（**509 MB**），日志 `outputs/build_pool_log.txt`

| 项 | 值 |
|---|---|
| 请求条数 | 12413（=预筛候选数，取上限） |
| **实际池子大小 P** | **9549**（构建期 2864 条轮数不足被丢弃） |
| 可错开复测批数 | `floor(9549/10)` = **954** 批互不重叠的 10 条 |
| 轮数 | min=4, max=12, avg=7.3 |
| 首轮 prompt tokens | avg=8250 |
| 末轮 prompt tokens | avg=14765 |
| 与对比集对齐 | ✅ `pool[0:10]` 与 `agentic_dataset.json` 逐字一致（同 seed/参数）→ offset=0 取到同一批 |

> seed=42、参数与对比集完全相同，所以池子是对比集的**超集**，前 10 条即对比集那 10 条。

### 复测怎么用这个池子（同模型同厂商取平均）

1. 把运行脚本的 `dataset_path` 从 `agentic_dataset.json` 换成 **`agentic_pool.json`**（否则池子=number，offset 无效）。
2. 每次跑 `--number 10`，命令行第 2 个参数传 offset，取不相交的 10 条：

```powershell
python scripts/perf/run_perf_one.py v32-bailian       # offset=0  → 池子[0..9]
python scripts/perf/run_perf_one.py v32-bailian 10     # offset=10 → 池子[10..19]
python scripts/perf/run_perf_one.py v32-bailian 20     # offset=20 → 池子[20..29]
```

最多 954 批；只要 `offset+10 ≤ 9549` 就与前批零重叠 → 服务端前缀缓存里没有 → turn-1 真正冷启动。
⚠️ 复测各批结果默认都落在同一 `results/<profile>/`，记得给 outputs_dir 带上 offset 区分，否则后批覆盖前批。

---

## 第 1 步起：各模型压测结果（待填）

> 跑法：`python scripts/perf/run_perf_one.py <profile>`（见下方"运行脚本"）。
> 每跑完一个，把终端 Per-Request / Per-Trace 三个指标抄到下表。

### 横向对比总表

| Profile | 模型 | 厂商 | Cache Hit (%)<br>token级全局 | Cache Hit Rate (%)<br>对话级 mean | Eligible Cache Hit Rate (%) | 真实/估算<sup>※</sup> | 备注 |
|---|---|---|---|---|---|---|---|
| **v32-bailian** | **glm-5** | **阿里百炼** | **78.96** | **76.96**（p50 82.09, max 86.58） | **93.00**（p50 98.19, max 98.88） | **真实** ✅ | session-cache=off；offset 0；10 对话/74 请求 |
| v32-tencent | deepseek-v3.2 | 腾讯云 | _待填_ | _待填_ | _待填_ | _待填_ | session-cache=on |
| v4pro-tencent | deepseek-v4-pro | 腾讯云 | _待填_ | _待填_ | _待填_ | _待填_ | session-cache=on |
| v4flash-tencent | deepseek-v4-flash | 腾讯云 | _待填_ | _待填_ | _待填_ | _待填_ | session-cache=on |

<sup>※</sup> 判别法（README 5/8.8）：`Eligible Cache Hit Rate` **死磕 100.00** = 客户端估算（服务端没回传 `cached_tokens`）；非整数 = 服务端真实值。

> **glm-5 / 阿里百炼（2026-06-01，首条真实数据）**：Eligible=93.00（非 100）→ 服务端**回传了真实 `cached_tokens`**，走真实路径。
> 跑参：`run_perf_one.py v32-bailian`（用全局 Python，非 venv），offset 0，`agentic_dataset.json` 10 条对话 / 74 请求，全部成功。
> 其他实测：平均输入 12313 tok，平均输出 494 tok，Avg Turns/Req 4.61，TTFT 首轮 4388ms / 后续 3028ms，时长 929s。
> 结果目录：`results/v32-bailian/glm-5/parallel_1_number_10/`。

### token 级命中率（落盘交叉核对）

落盘后用 README 8.7 的 PowerShell 脚本批量算 `cum_cached_prompt / (cum_cached_prompt + cum_new_prompt)`，与终端 `Cache Hit (%)` 对齐。

---

## 运行脚本

优化版单模型脚本：[scripts/perf/run_perf_one.py](../../scripts/perf/run_perf_one.py)。

**每次重跑只改一处**：脚本顶部 `ACTIVE = '...'`，或用命令行覆盖：

```powershell
$env:TENCENT_API_KEY   = "<你的腾讯key>"
$env:DASHSCOPE_API_KEY = "<你的百炼key>"

python scripts/perf/run_perf_one.py v32-tencent      # 腾讯 deepseek-v3.2
python scripts/perf/run_perf_one.py v32-bailian      # 百炼 deepseek-v3.2
python scripts/perf/run_perf_one.py v4pro-tencent    # 腾讯 deepseek-v4-pro
python scripts/perf/run_perf_one.py v4flash-tencent  # 腾讯 deepseek-v4-flash
# 复测同一(模型,厂商)取不相交子集（需先扩池子）：第二个参数 = dataset_offset
python scripts/perf/run_perf_one.py v32-tencent 10
```

结果落盘在 `results/<profile>/`。
