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
- ⚠️ **代码执行安全**：`humaneval_plus` 默认会在**本地环境**执行模型生成的代码。强烈建议开启 Docker 沙盒：加 `--sandbox '{"enabled": true, "engine": "docker"}'`（适配器自带 `python3.11-numpy` 镜像）。参考[沙盒文档](https://evalscope.readthedocs.io/zh-cn/latest/user_guides/sandbox.html)。
- ⚠️ **沙盒执行超时（防"最后一题卡死"）**：每条样本的代码执行超时由 `review_timeout` 控制，`humaneval_plus` **默认 300s**（[humanevalplus_adapter.py:61](../../evalscope/benchmarks/humanevalplus/humanevalplus_adapter.py#L61)）。这是**沙盒侧硬超时**（实际 `review_timeout+10` 秒强制中断、该题判错但不卡整场，[sandbox_mixin.py:148](../../evalscope/api/mixin/sandbox_mixin.py#L148)），与 API 的 `timeout` **是两套、互不影响**。模型若吐死循环代码，不调小会让最后一题卡到 ~5 分钟。用 `--dataset-args '{"humaneval_plus": {"review_timeout": 60}}'` 调小即可——HumanEval 题计算量小、正确解通常 <10s，60s 不会误杀慢解。

---

## 3. 评测执行命令

CMMLU 与 HumanEvalPlus 的 `--limit` 需求不同（前者每科 50、后者全量），所以分成两条命令最干净。

### 3.1 终端命令

```bash
# CMMLU 微缩版：每科 50 题，自动 3350 题，可复现，无需任何抽样脚本
evalscope eval \
  --model 你的模型名称或供应商模型 \
  --model-id deepseek-v3.2_bailian \  # 报告里的可读标识；同名模型打不同厂商时务必带上厂商名以便区分（见 3.6）
  --api-url $API_URL \
  --api-key $API_KEY \
  --datasets cmmlu \
  --limit 50 \
  --eval-batch-size 16 \             # 16 并发；不加默认单并发(1)，3350 题会很慢
  --generation-config temperature=0,top_p=1.0,timeout=60,retries=3,retry_interval=5 \   # 模型参数走这里；必带 temperature（见 3.4 的坑）。推理模型再追加 reasoning_effort=high
  --model-args max_retries=0 \       # 关掉 OpenAI SDK 内层重试，避免"最后一题卡死"（见 3.3 的嵌套重试坑）
  --ignore-errors                    # 重试耗尽仍失败就跳过该样本，不中断整场

# HumanEvalPlus 全量 164 题（推荐开 Docker 沙盒执行生成代码）
evalscope eval \
  --model 你的模型名称或供应商模型 \
  --model-id deepseek-v3.2_bailian \  # 同上，多厂商对比时带厂商名
  --api-url $API_URL \
  --api-key $API_KEY \
  --datasets humaneval_plus \
  --sandbox '{"enabled": true, "engine": "docker"}' \
  --dataset-args '{"humaneval_plus": {"review_timeout": 60}}' \   # 沙盒执行代码超时(秒)，默认300；防死循环代码卡死最后一题
  --eval-batch-size 4 \              # 沙盒会并行起多个 docker，核少就调小
  --generation-config temperature=0,top_p=1.0,timeout=60,retries=3,retry_interval=5 \   # 推理模型再追加 reasoning_effort=high
  --model-args max_retries=0 \       # 同上，关掉 SDK 内层重试
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
| 失败重试次数（仅 OpenAI 兼容） | `retries` | **5** | **3** |
| 重试间隔（秒） | `retry_interval` | **10** | **5** |
| OpenAI SDK 内层重试 | `--model-args max_retries=` | **2** | **0**（关掉，见下方坑） |
| 重试耗尽后是否跳过该样本 | `--ignore-errors` | 关（抛错中断） | **开** |

- 重试逻辑：任何异常都会触发重试，到 `retries` 次仍失败才抛出（[function_utils.py:71-82](../../evalscope/utils/function_utils.py#L71)）；超时本身也会被重试。
- 写法：CLI `--generation-config timeout=60,retries=3,retry_interval=5 --model-args max_retries=0` + `--ignore-errors`；Python `TaskConfig(generation_config={'timeout': 60, 'retries': 3, 'retry_interval': 5}, model_args={'max_retries': 0}, ignore_errors=True)`。

> **⚠️ 嵌套重试坑：不关 SDK 内层重试 → "最后一题卡死十几分钟"**
>
> evalscope 的 `retries` 是**外层**重试（[openai_compatible.py:147](../../evalscope/models/openai_compatible.py#L147) 的 `retry_call`）。但底层 OpenAI SDK 客户端**自己还带一层** `max_retries`（默认 **2**），会对 `超时/429/5xx` 再重试，且 evalscope **没主动关它**（[openai_compatible.py:62](../../evalscope/models/openai_compatible.py#L62) 的 `OpenAI(**model_args)`）。两层相乘：
>
> ```
> 最坏耗时 ≈ retries × (1 + max_retries) × timeout + 外层间隔
>          = 5 × 3 × 60s + ... ≈ 15 分钟
> ```
>
> **现象**：并发池（[evaluator.py:306](../../evalscope/evaluator/evaluator.py#L306) 的 `eval_batch_size` 线程池）跑到只剩最后 1 题时，没有别的请求掩盖它，进度条死停在 `N-1/N`，看起来就是"最后一题卡死"。阿里云（DashScope）**限并发时把尾部请求挂队列**（而非秒回 429），最后一题最易反复 60s 超时、触发整条阶梯。
>
> **修法**：`--model-args max_retries=0`（CLI，经 `ast.literal_eval` 解析成 int）或 `TaskConfig(model_args={'max_retries': 0})`（Python）。`model_args` 会原样透传给 `OpenAI(**model_args)`，关掉内层重试后只剩外层 `retries`，最坏降到 `3 × 60s ≈ 3 分钟`。
>
> **如何确认是这个坑**：看日志是否反复出现 `Attempt x / 5 failed: ... Retrying`（[function_utils.py:79](../../evalscope/utils/function_utils.py#L79)），且相邻两条间隔约 180s（= 3×60s 内层重试），即坐实。
>
> **注意**：以上是 **API 侧**超时。`humaneval_plus` 段若卡在评分阶段，是 **Docker 沙盒执行生成代码**卡住（死循环代码），那是另一套——由 `review_timeout`（默认 300s）控制，用 `--dataset-args '{"humaneval_plus": {"review_timeout": 60}}'` 调小，详见 [2.2 节](#22-humanevalplus保持全量-164-题)。

### 3.4 模型生成参数

模型参数**没有独立 flag，全塞进 `--generation-config`**。两种格式二选一（值含列表/字典如 `stop_seqs`、`extra_body` 时**必须**用 JSON，否则逗号会被切错）。

**全参数示例（逗号式，标量参数全列出，按需删减）：**
```bash
--generation-config "temperature=0,top_p=0.8,top_k=20,max_tokens=2048,seed=42,n=1,presence_penalty=0,frequency_penalty=0,repetition_penalty=1.0,reasoning_effort=high,logprobs=False,stream=False,timeout=60,retries=5,retry_interval=10"
```

**含列表/字典时用 JSON：**
```bash
--generation-config '{"temperature":0,"top_p":0.8,"max_tokens":2048,"seed":42,"reasoning_effort":"high","stop_seqs":["\n\n"],"extra_body":{"enable_thinking":false}}'
```

| 类别 | 参数键 |
|---|---|
| 采样 | `temperature`、`top_p`、`top_k`、`seed`、`n`、`max_tokens`、`stop_seqs` |
| 惩罚 | `presence_penalty`、`frequency_penalty`、`repetition_penalty` |
| 思考模型 | `reasoning_effort`(low/medium/high)、`reasoning_tokens` |
| 流式/超时/重试 | `stream`、`timeout`、`retries`(默认5)、`retry_interval`(默认10) |
| 概率/私有 | `logprobs`、`top_logprobs`、`extra_body`、`extra_headers` |

> **不传 `--generation-config` 时的内部默认（API 评测，[config.py:387-397](../../evalscope/config.py#L387)）**：只注入 `DEFAULT_TEXT_GEN_SERVICE_CONFIG` = **`{'temperature': 0.0}`**——即**仅发 temperature=0.0**，`top_p` / `top_k` / `max_tokens` / `seed` / `reasoning_effort` 全是 `None` → **不发送**，由模型/服务端自有默认决定；`retries=5` / `retry_interval=10` / `timeout=None` 为 `GenerateConfig` 字段默认。（本地权重评测 `checkpoint` 默认不同：`max_tokens=2048, top_k=50, top_p=1.0, temperature=1.0`，本文打商业 API 用不到。）

**⚠️ 两个坑**：
1. **必带 `temperature`**：默认只有 `temperature=0.0`，但「**一传 `--generation-config` 就整体替换、不合并**」（[config.py:374](../../evalscope/config.py#L374)），漏写会让它变 `None`（走模型默认、破坏复现）。
2. **按需删减、别全抄**：`top_p`/`top_k` 在 `temperature=0` 时基本无意义；`reasoning_effort` 只对思考模型有效，非思考模型传了可能报错；`logprobs=True`、`n>1` 会改变输出结构。accuracy 评测最小集通常只需 `temperature=0,max_tokens=...,seed=...,timeout=...`。

### 3.5 Python 代码调用方式（批量对比多供应商）

见 [run_eval.py](./run_eval.py)；用 `TaskConfig` 的扁平字段（`model/api_url/api_key/datasets/limit`）即可，并发靠 `eval_batch_size`（默认 1），超时/跳过靠 `generation_config` + `ignore_errors`。

```python
from evalscope import run_task, TaskConfig

def eval_vendor(model, api_url, api_key, vendor):
    # model=请求体里真实的模型名（发给 API）；vendor=厂商，仅用于拼报告标识 model_id，不进请求体
    model_id = f'{model}_{vendor}'   # 报告里的可读标识；同名模型打不同厂商靠这个区分
    # 生成参数（键名见 generate_config.py）；retries/retry_interval 收紧为 3 次 / 5s
    gen_cfg = {
        'temperature': 0,      # 采样温度；0=贪心（可复现）
        'top_p': 1.0,          # 核采样；temperature=0 时为空操作，留作可调旋钮
        # 'reasoning_effort': 'high',  # 思考档位 low/medium/high；仅推理模型可开
        'timeout': 60,
        'retries': 3, 'retry_interval': 5,
    }
    client_args = {'max_retries': 0}   # ⚠️ 关掉 OpenAI SDK 内层重试，避免"最后一题卡死"（见 3.3）
    # CMMLU：每科 50 题，16 并发
    run_task(TaskConfig(
        model=model, model_id=model_id,
        api_url=api_url, api_key=api_key,
        datasets=['cmmlu'], limit=50,
        eval_batch_size=16,
        generation_config=gen_cfg, model_args=client_args, ignore_errors=True,
    ))
    # HumanEvalPlus：全量，开沙盒，8 并发
    run_task(TaskConfig(
        model=model, model_id=model_id,
        api_url=api_url, api_key=api_key,
        datasets=['humaneval_plus'],
        sandbox={'enabled': True, 'engine': 'docker'},
        dataset_args={'humaneval_plus': {'review_timeout': 60}},  # 沙盒执行超时(秒)，默认300，防死循环卡死
        eval_batch_size=2,
        generation_config=gen_cfg, model_args=client_args, ignore_errors=True,
    ))

# 同一款 deepseek-v3.2 分别打两家：model 一致（请求体不变），靠 vendor 区分报告
eval_vendor('deepseek-v3.2', 'https://api.vendor-a.com/v1', 'KEY_A', vendor='bailian')
eval_vendor('deepseek-v3.2', 'https://api.vendor-b.com/v1', 'KEY_B', vendor='tencent')
```

### 3.6 多厂商对比：用 `--model-id` 给报告打厂商标识

| 维度 | 字段 | 说明 |
|---|---|---|
| 请求体里的 model 名 | `--model` / `model` | 真正发给 API 的模型名，**不能塞厂商后缀**（否则服务端不认） |
| 报告/汇总里的模型标识 | `--model-id` / `model_id` | 仅用于报告展示；不传时自动从 model 名推导（[config.py:360-369](../../evalscope/config.py#L360)） |

- **为什么要显式传**：同一款模型打不同厂商（如 `deepseek-v3.2` 同时测百炼/腾讯云）时，`model_id` 会自动重名，报告里两家分不清。手动设成 `deepseek-v3.2_bailian` / `deepseek-v3.2_tencent` 即可区分。
- **和 perf 的 `--name` 不是一回事**：perf 压测的 `--name` 是结果库 db 名 + 输出子目录名，**同秒并发会撞库**才必须带厂商；而 `evalscope eval` 的输出路径是 `<work_dir>/<时间戳>/...`（默认带时间戳，[config.py:167](../../evalscope/config.py#L167)），不会撞车，`model_id` 纯粹是为了**报告可读 / 多厂商可区分**，机制不同别混。

通过这种方式，你可以用最低的成本，快速且高精度地描绘出不同供应商大模型的"能力雷达图"。
