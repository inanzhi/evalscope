# LLM (大语言模型) 极简均衡测试集抽取方案 (EvalScope 原生后端)

## 1. 需求背景与核心探讨

在对比不同供应商的 API 或不同大模型的效果时，全量运行大型测试集（如 CMMLU 的 11528 题）会耗费大量的 API 调用成本和测试时间。为了快速、高性价比地摸底模型差异，我们需要一套科学的"微缩版"测试方案。

### 💡 这两个数据集用来对比模型效果，合理吗？

**结论：非常合理，且极具性价比。这是一组"一文一理、一广一深"的黄金组合。**

1. **CMMLU (侧重中文语境与知识广度)**：涵盖 67 个中国本土学科（从初中数理化到中国历史、法律、甚至方言）。它能非常敏锐地测出模型是否针对**中文知识域**做过充分的预训练和对齐，能一眼看穿"套壳外企模型"和"本土优秀模型"的差异。
2. **HumanEvalPlus (侧重硬核逻辑与编程深度)**：在原版 HumanEval 的基础上增加了数万条严苛测试用例。代码能力是大模型"逻辑推理能力"的最高体现。即使某些模型在文科上能侃侃而谈，在 HumanEvalPlus 的沙盒里跑一下测试用例，其实际的逻辑漏洞就会原形毕露。

**优势**：只用极少的题量，就能同时锚定模型的"中文知识储备"和"数理逻辑上限"，是评估 API 供应商底层模型能力的利器。

---

## 2. 抽样方案：用 `--limit` 按学科分层截断

EvalScope 原生（native）后端内置了 `cmmlu` 和 `humaneval_plus`，并支持扁平 API 参数（`--model/--api-url/--api-key/--datasets`），是这套方案的推荐路径，无需任何手动截断脚本。

### 2.1 CMMLU：`--limit` 是「按学科」生效的，等价于分层截断

CMMLU 在 EvalScope 内部按 67 个学科（subject）拆成 67 个 subset，`--limit` 在 [`DatasetDict.from_dataset`](../../evalscope/api/dataset/dataset.py#L340) 里是**对每个 subset 单独**做 `samples[:limit]`。来源见 [cmmlu_adapter.py](../../evalscope/benchmarks/cmmlu/cmmlu_adapter.py#L120)（`subset_list` = 67 学科）与 [default_data_adapter.py:212-221](../../evalscope/api/benchmark/adapters/default_data_adapter.py#L212)。

因此：

```
--datasets cmmlu --limit 50   →   每个学科取 50 题 × 67 学科 = 3350 题
```

这正是"分层均衡截断"想要的效果，且：

- **零文件操作**：不碰任何 `.csv`，不需要备份/还原，不存在"反复跑越缩越小"的风险。
- **可复现**：固定 `--seed`（默认 42），同一数据集版本下每次抽到的题完全一致。
- **学科权重完美保留**：67 个学科各 50 题，分布天然均衡。

### 2.2 HumanEvalPlus：保持全量 164 题

- 原生数据集代号是 **`humaneval_plus`**（不是 `humaneval`；后者是原版 164 题，没有 Plus 的增强用例，见 [humanevalplus_adapter.py:50](../../evalscope/benchmarks/humanevalplus/humanevalplus_adapter.py#L50)）。
- 164 题本身极少、生成文本短、API 成本极低，主要消耗在本地/沙盒跑测试用例。强行压缩会让算法题型（动态规划、字符串、图论）覆盖度断层，**建议不加 `--limit`，跑全量 164**。
- ⚠️ **代码执行安全**：`humaneval_plus` 默认会在**本地环境**执行模型生成的代码。强烈建议开启 Docker 沙盒：加 `--sandbox '{"enabled": true, "engine": "docker"}'`（适配器自带 `python3.11-numpy` 镜像，默认超时 300s）。参考[沙盒文档](https://evalscope.readthedocs.io/zh-cn/latest/user_guides/sandbox.html)。

---

## 3. 评测执行命令

CMMLU 与 HumanEvalPlus 的 `--limit` 需求不同（前者每科 50、后者全量），所以分成两条命令最干净。

### 3.1 终端命令

```bash
# CMMLU 微缩版：每科 50 题，自动 3350 题，可复现，无需任何抽样脚本
evalscope eval \
  --model 你的模型名称或供应商模型 \
  --api-url $API_URL \
  --api-key $API_KEY \
  --datasets cmmlu \
  --limit 50 \
  --eval-batch-size 16 \             # 16 并发；不加默认单并发(1)，3350 题会很慢
  --generation-config timeout=60 \   # 单次请求超时 60s（重试默认 5 次、间隔 10s）
  --ignore-errors                    # 重试耗尽仍失败就跳过该样本，不中断整场

# HumanEvalPlus 全量 164 题（推荐开 Docker 沙盒执行生成代码）
evalscope eval \
  --model 你的模型名称或供应商模型 \
  --api-url $API_URL \
  --api-key $API_KEY \
  --datasets humaneval_plus \
  --sandbox '{"enabled": true, "engine": "docker"}' \
  --eval-batch-size 8 \              # 沙盒会并行起多个 docker，核少就调小
  --generation-config timeout=60 \
  --ignore-errors
```

- 提供 `--api-url` 后，EvalScope 会自动把 `eval-type` 设为 `openai_api`（见 [config.py:349-351](../../evalscope/config.py#L349)），因此走的是 OpenAI 兼容接口压测，无需额外指定后端。
- 想先小样跑通链路，可临时把 CMMLU 的 `--limit 50` 改成 `--limit 2`。
- 超时与重试在 `--generation-config` 里（见 [3.3 超时与错误处理](#33-超时与错误处理)）。

### 3.2 并发设置（默认是单并发，务必手动开）

native 后端的并发开关是 **`--eval-batch-size`**，它直接决定并发请求数（源码里被当成线程池 `max_workers`，见 [evaluator.py:310](../../evalscope/evaluator/evaluator.py#L310)）。**默认值是 1**（[config.py:150](../../evalscope/config.py#L150)），不手动加这 3350 题会一条一条串行打，非常慢。

| 写法 | 设置并发 |
|---|---|
| CLI | `--eval-batch-size 16` |
| Python | `TaskConfig(..., eval_batch_size=16)` |

**⚠️ 注意事项：**
1. **商业 API 有并发/QPS 上限**：百炼、腾讯云等对低档账号通常限并发，开太高会大面积 `429 Too Many Requests`。建议从 **8~16** 起步，报 429 就往下调。
2. **不影响分数，只影响速度**：accuracy 评测里并发只是加速，正确率不变（与 perf 压测追求"公平单并发"是两码事）。
3. **HumanEvalPlus + 沙盒**：并发会同时拉起多个 docker 执行生成代码，本地核少时 `--eval-batch-size` 别开太大（示例给了 8）。

### 3.3 超时与错误处理

超时和重试都在 **`--generation-config`** 里（[generate_config.py:30-37](../../evalscope/api/model/generate_config.py#L30)），出错处理用 **`--ignore-errors`**：

| 项 | 字段 | 默认 | 本方案取值 |
|---|---|---|---|
| 单次请求超时（秒） | `timeout` | `None`（用 SDK 默认） | **60** |
| 失败重试次数（仅 OpenAI 兼容） | `retries` | **5** | 默认 |
| 重试间隔（秒） | `retry_interval` | **10** | 默认 |
| 重试耗尽后是否跳过该样本 | `--ignore-errors` | 关（抛错中断） | **开** |

- 重试逻辑：任何异常都会触发重试，到 `retries` 次仍失败才抛出（[function_utils.py:71-82](../../evalscope/utils/function_utils.py#L71)）；超时本身也会被重试。
- 写法：CLI `--generation-config timeout=60` + `--ignore-errors`；Python `TaskConfig(generation_config={'timeout': 60}, ignore_errors=True)`。
- 要调重试：`--generation-config timeout=60,retries=3,retry_interval=5`。

### 3.4 Python 代码调用方式（批量对比多供应商）

见 [run_eval.py](./run_eval.py)；用 `TaskConfig` 的扁平字段（`model/api_url/api_key/datasets/limit`）即可，并发靠 `eval_batch_size`（默认 1），超时/跳过靠 `generation_config` + `ignore_errors`。

```python
from evalscope import run_task, TaskConfig

def eval_vendor(name, api_url, api_key):
    gen_cfg = {'timeout': 60}  # retries/retry_interval 默认 5 次 / 10s
    # CMMLU：每科 50 题，16 并发
    run_task(TaskConfig(
        model=name, api_url=api_url, api_key=api_key,
        datasets=['cmmlu'], limit=50,
        eval_batch_size=16,
        generation_config=gen_cfg, ignore_errors=True,
    ))
    # HumanEvalPlus：全量，开沙盒，8 并发
    run_task(TaskConfig(
        model=name, api_url=api_url, api_key=api_key,
        datasets=['humaneval_plus'],
        sandbox={'enabled': True, 'engine': 'docker'},
        eval_batch_size=8,
        generation_config=gen_cfg, ignore_errors=True,
    ))

eval_vendor('vendor-a-model', 'https://api.vendor-a.com/v1', 'KEY_A')
eval_vendor('vendor-b-model', 'https://api.vendor-b.com/v1', 'KEY_B')
```

通过这种方式，你可以用最低的成本，快速且高精度地描绘出不同供应商大模型的"能力雷达图"。
