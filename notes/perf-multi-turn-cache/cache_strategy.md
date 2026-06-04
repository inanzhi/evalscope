# 多轮对话 KV 缓存命中率压测方案 (Multi-Turn Cache)

## 1. 测试背景与核心指标
本方案专门用于评估大模型服务端在**多轮连续对话**中，对历史上下文缓存（KV Cache / Prefix Cache）的复用能力。通过 `evalscope perf --multi-turn` 触发。

多轮评测绝不能看单轮的绝对 Latency，而必须看以下两个核心的命中率指标：

| 核心指标 | 计算逻辑 | 业务意义与价值 |
| --- | --- | --- |
| **Cache Hit (%)** <br>*(单次请求/全局总账)* | `实际命中 Token / (系统提示词 + 历史记录 + 本轮新提问)` | **实际省了多少钱/算力**。按 Token 总量加权，代表全场多轮压测下来，总共复用了多大比例的上下文。 |
| **Eligible Cache Hit Rate (%)** <br>*(理论可缓存命中率)* | `实际命中 Token / 理论上符合缓存条件的 Token` (剔除了第一轮冷启动和最新提问) | **系统缓存做得有多好**。排除不可避免的新增内容后，衡量厂商底层缓存系统的真实复用能力（无过期、无挤兑）。 |

> **💡 黄金判别法（辨别数据真伪）**：如果跑出来的 `Eligible Cache Hit Rate` 死磕在 **100.00%**，说明服务端没有返回真实缓存数据，这是客户端的**理论估算值**。如果跑到 93.00% 这种非整数，说明走的是真实回传数据（如阿里百炼 GLM-5）。

## 2. 核心压测策略与对齐机制

为了保证跨厂商（腾讯云 vs 阿里百炼）的绝对公平，必须引入以下三大策略：

### 2.1 数据集绝对统一（预生成 JSON）
抛弃在线实时生成，提前通过脚本跑出一份固定的多轮对话 JSON 文件（如 `agentic_dataset.json`）。所有待测云厂商都吃同一份数据，保证它们遇到的对话轮数、每轮历史长度**逐字相同**。

### 2.2 会话隔离与路由（Session 注入机制）
* **腾讯云**：依赖底层的路由标识才能复用缓存。需要在代码层面开启 `--multi-turn-session-cache`，自动为每个请求注入 `X-Session-ID` Header 和 `prompt_cache_key` Body。
* **阿里百炼**：无此字段（隐式缓存），不需要加该参数。

### 2.3 防复测污染（超大池子 + Offset）
如果对**同一个模型和厂商**重测取平均，第二次压测绝对不能用同一批数据，否则第一轮压测的缓存还残留在服务端，会导致第二次的“第一轮冷启动”出现虚高的命中率。
* **解法**：预先生成一个超大对话池（如 `agentic_pool.json` 包含近万条对话）。每次复测通过增加 `--dataset-offset 10` 来取**完全不相交**的子集。

## 3. 具体测试方案与流程

### Step 1: 预构建统一多轮数据集

这里使用的是基于 **`swe_smith` (Software Engineering Smith)** 衍生出的多轮数据格式。
> **📌 数据集科普：为什么要用 swe_smith？**
> `swe_smith` 是一个专门用于模拟“软件工程 Agent 开发（如 SWE-bench）”的对话轨迹数据集。
> 它的典型特征是：**首轮爆长，后续增量**。第一轮通常会抛出上万字的仓库代码上下文和 GitHub Issue 描述；之后的每一轮则是大模型执行一个 `bash` 命令、或者查看一小段日志、输出少量修改。
> 这种“长首轮、短尾巴”的纺锤形数据结构，是压测服务端 **Prefix Cache (长文本前缀缓存)** 和长下文复用能力的**最完美且最贴近真实的场景**。

> **⚙️ 上下文生成与截断规则：**
> 脚本是如何把原始的 `swe_smith` 数据拼装成特定 Token 长度的多轮对话的？
> 1. **剥离历史回复**：剔除数据集中原本存在的所有 Assistant（助手）回复，只保留 User（用户）发送的代码和命令。因为压测时系统只发 Prompt，回复由待测厂商的 API 实时生成。
> 2. **首轮聚合 (第一轮)**：从对话开头疯狂读取 User 消息拼在一起，直到总长度正好达到 `--first-turn-length`（比如 8192 Token）。这当做第一轮的提问一次性发给大模型。
> 3. **后续增量聚合 (第二轮及以后)**：接着往下读 User 消息，每攒够 `--subsequent-turn-length`（比如 1024 Token）的长度，就作为新的一轮发出去。
> 4. **丢弃短数据**：如果某条原始数据的文本不够长，凑不齐你要求的 `--min-turns`（最小轮数），脚本会直接把它抛弃，保证最终生出来的 10 条测试数据每一条都极其严谨、饱满。

**操作说明**：通过自带脚本，预构建 JSON 测试集。建议**一次把两份都生成好**——小集做横向对比、大池子做同模型复测：

```bash
# ① 小集（10 条）：跨厂商/模型横向对比用，所有人第一把都吃这 10 条
python scripts/perf/build_swe_smith_dataset.py \
  --model-path Qwen/Qwen2.5-7B-Instruct \
  --first-turn-length 8192 --subsequent-turn-length 1024 \
  --min-turns 4 --max-turns 12 --number 10 \
  --output-path outputs/agentic_dataset.json --seed 42

# ② 大池子（近万条）：复测同模型时按 offset 取不相交子集用。仅 --number 与 --output-path 不同，其余必须与小集一致
python scripts/perf/build_swe_smith_dataset.py \
  --model-path Qwen/Qwen2.5-7B-Instruct \
  --first-turn-length 8192 --subsequent-turn-length 1024 \
  --min-turns 4 --max-turns 12 --number 10000 \
  --output-path outputs/agentic_pool.json --seed 42
```
> 两份务必用**相同的轮长/轮数参数**生成，保证小集和大池子里的对话同构、可比（凑不齐长度的会被丢弃，所以实际条数会略少于 `--number`）。

### Step 2: 编写单例运行脚本 (`scripts/perf/run_perf_one.py`)
因为多轮测试参数多且复杂，推荐使用 Python 脚本固定公共参数，每次只改顶部几行：

```python
# ===== 每次只需改这里的变量 =====
model = 'deepseek-v3.2'
url = 'https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions'
multi_turn_session_cache = False  # 腾讯云设为 True，阿里百炼设为 False
dataset_offset = 0                # 同模型复测时，每次加 10

# ===== 全程固定参数（保证公平） =====
# api='openai', dataset='swe_smith', dataset_path='outputs/agentic_dataset.json'
# multi_turn=True, parallel=5（会话级并发，详见 Step 3.3）, number=10, max_tokens=16384
# 生成参数（可自行修改，键名见 evalscope/perf/arguments.py）：
#   temperature=0.0   # 采样温度；0=贪心（可复现）
#   top_p=1.0         # 核采样；temperature=0 时为空操作，留作可调旋钮
#   extra_args={'reasoning_effort': 'high'}  # 思考档位 low/medium/high；非原生字段，走 extra_args 注入请求体。非推理模型请删掉
```

> **不传时 perf 的内部默认（[arguments.py](../../evalscope/perf/arguments.py#L281)）**：硬默认 `temperature=0.0`、`max_tokens=2048`、`stream=True`、`total_timeout=6h`；`top_p` / `top_k` / `seed` / `reasoning_effort` 默认 `None` → **不发送**，由服务端自有默认决定。脚本里显式写 `max_tokens=16384`、`seed=42`、`extra_args=reasoning_effort` 就是为覆盖这些默认、锁死可复现。

### Step 3: 执行与指标验收
执行 `python scripts/perf/run_perf_one.py`，查看跑出的结果。

### Step 3.1: 小集 vs 大池子——什么时候用哪个、命令怎么写

`run_perf_one.py` 的**第二个参数 `offset` 会自动决定用哪份数据**，你不用手动改 `--dataset-path`：

| 用途 | offset | 自动选用的数据 | 落盘目录 |
| --- | --- | --- | --- |
| **横向对比**不同厂商/模型（第一把都用它，绝对公平） | `0`（默认，不传） | 小集 `outputs/agentic_dataset.json`（10 条） | `results/<profile>_cache-{on/off}` |
| **复测同一(模型,厂商)** 取平均（防残留缓存让命中率虚高） | `>0` | 大池子 `outputs/agentic_pool.json`（近万条） | `results/<profile>_offset-<N>_cache-{on/off}` |

> 目录尾巴的 `_cache-on` / `_cache-off` 记录的是本次 `session_cache`（Session 缓存路由注入）的**实际生效状态**，让同一模型「开缓存 / 关缓存」两种跑法各自落盘、互不覆盖。

**① 横向对比（小集）——不传 offset：**
```powershell
python scripts/perf/run_perf_one.py deepseek-v4-pro_tencent
```

**② 复测同模型（大池子）——传 offset > 0：**
每轮跑 `number=10` 条，从 offset 起取 10 条（`offset .. offset+9`）。复测时每次 **+10** 取完全不重叠的新一批：
```powershell
python scripts/perf/run_perf_one.py deepseek-v4-pro_tencent 10   # 第 10~19 条 → results/...-off10
python scripts/perf/run_perf_one.py deepseek-v4-pro_tencent 20   # 第 20~29 条 → results/...-off20
python scripts/perf/run_perf_one.py deepseek-v4-pro_tencent 30   # 第 30~39 条 → results/...-off30
```

- offset **必须 > 0** 才会切到大池子（`=0` 会退回小集）；取 **10 的倍数** 才能整批不重叠。
- 上限 `offset + 10 ≤ 池子条数`（当前 9549），即 offset 最大约 **9539**，够测几百轮互不蹭缓存。
- ⚠️ **铁律**：不同厂商/模型**横向对比时绝不要换 offset**，都用小集（offset=0）才最公平；只有**同一(模型,厂商)复测取平均**时才换 offset。

**③ 临时开关 session_cache（第 3 个参数）——同模型对比开 / 关缓存：**
`session_cache` 默认取 `VENDORS[厂商]` 里登记的值（腾讯云 `False`、阿里百炼 `True`）；想在不改代码的前提下临时翻转，传**第 3 个参数** `on`/`off`（`on/1/true/yes` 为开，其余为关）。生效状态会写进目录尾巴 `_cache-on` / `_cache-off`，两种跑法各自落盘：
```powershell
python scripts/perf/run_perf_one.py deepseek-v4-pro_tencent 0 on    # 强开  → results/deepseek-v4-pro_tencent_cache-on
python scripts/perf/run_perf_one.py deepseek-v4-pro_tencent 0 off   # 强关  → results/deepseek-v4-pro_tencent_cache-off
```
> 第 3 个参数省略时即用厂商登记的默认值；要传它就得把第 2 个 offset 参数也占上位（不复测就填 `0`）。

### Step 3.2: `number=10` 到底发了多少次请求？（别被"10"骗了）

`number=10` 数的是**会话(Session)条数**，不是请求数。一条会话是一整段多轮对话，里面有好几个 turn，**每个 turn 才是一次真正发给模型的请求**（带累积历史）。`multi_turn=True` 的语义就是模拟真人一轮一轮地发：

```
轮1: 用户问 A        → 发 1 次请求，模型答 A'
轮2: 用户接着问 B     → 发 1 次请求（带上 A、A'）
轮3: 用户接着问 C     → 发 1 次请求（带上 A A' B B'）
...                  历史一轮轮累积，prompt_tokens 越来越大（8200→9300→10300…）
```

而每条会话的 turn 数**长短不一**（数据集 `min_turns=4, max_turns=12`）。以大池子 `offset=10` 取的第 10~19 条为例，实测每条的 turn 数：

```
会话0:  6 turn  → 发  6 次请求
会话1: 10 turn  → 发 10 次请求
会话2:  8 turn  → 发  8 次请求
会话3: 11 turn  → 发 11 次请求
会话4: 11 turn  → 发 11 次请求
会话5: 10 turn  → 发 10 次请求
会话6:  5 turn  → 发  5 次请求
会话7:  9 turn  → 发  9 次请求
会话8:  5 turn  → 发  5 次请求
会话9:  4 turn  → 发  4 次请求
────────────────────────────
合计 = 6+10+8+11+11+10+5+9+5+4 = 79 次串行请求
```

所以"跑 10 条"≈ **跑 79 次请求**。在 JSON 里这体现为：每条会话是个**列表**，列表里有几个元素（每个元素 `{messages, prompt_tokens}`）就代表要发几次请求。叠加 `reasoning_effort='high'`（深度思考几十秒~分钟）、`max_tokens=16384`（长输出）、每轮上万 token 的长 prefill，慢是必然的。

### Step 3.3: 会话级并发（`parallel`）——想跑快点看这里

`parallel=N` 在多轮模式下并发的是**会话之间**，不是会话内部的 turn（[multi_turn.py](../../evalscope/perf/core/strategies/multi_turn.py)）：

- 框架起 **N 个 worker**，每个 worker 一次认领**一整条会话**，串行跑完它所有 turn，再认领下一条；
- **会话内的 turn 永远串行**，改不了也不该改——第 N 轮必须等第 N-1 轮的回复回来、append 进上下文后才能发（multi-turn 不支持 open-loop，本质如此）。

| 设置 | 效果 |
| --- | --- |
| `parallel=1` | 1 个 worker，79 次请求完全排队，最慢 |
| `parallel=5` | 5 条会话同时进行，整体快约 5 倍 |
| `parallel=10` | 10 条会话全开，最快 |

**关键：并发不污染缓存命中率。** 每条会话有自己独立的 `session_key = model-trace_id`，缓存命中是在**同一条会话内部**度量的（turn N 复用 turn N-1 的上下文），会话之间 key 不同、互不串味，所以 **Cache Hit / Eligible Cache Hit Rate 指标不受 `parallel` 影响**。

**那 `parallel` 锁死的是什么？** 是**延迟类指标的可比性**：并发上去后服务端同时扛 N 条会话，排队争抢会让单请求的 **TTFT / TPOT 变大**。所以：

- **只关心缓存命中率** → 放心调大 `parallel`，结果一样还快很多。
- **要测单点延迟并和其它厂商横向对比** → 必须**所有厂商用同一个 `parallel` 档**，否则延迟数不可比。

> 改 `parallel` 改的是 `run_perf_one.py` 里 `FIXED` 的那一行；正在运行的进程不受影响，需**重启命令**才生效。

---

## 4. 进阶答疑与避坑指南

### 4.1 避坑指南
1. **别用 `ignore_eos`**：多轮长文本下，云厂商普遍不支持强行忽略结束符，改用 `{"reasoning_effort":"high"}` 并配合足够大的 `--max-tokens`（如 16384）让其自然输出即可。
2. **`--api openai` 是铁律**：测试 DashScope 或腾讯云的兼容接口时，必须用 `--api openai` 才能保证自定义的 Extra Args 和注入字段不被丢弃。
3. **换厂商必须换输出目录**：保证 `results/` 目录下各模型各厂商的 JSON 不被覆盖。

### 4.2 数据集生成的随机性与对齐（控制变量的核心）
**问：每次测试的 `--min-turns 4 --max-turns 12` 包含随机性，对比不同模型时，实际执行的轮次能保证一致吗？**

**绝对能保证一致！这正是“预构建 JSON”这种隔离设计的精妙之处：**
1. **随机性被“冻结”在本地文件中**：`--min-turns` 等带随机性的参数仅仅出现在 `build_swe_smith_dataset.py` 这一准备阶段。程序抽样完成后，会把最终确定下来的 10 条多轮对话（包含确定的轮数、确定的文本内容）**全部固化并保存**到 `agentic_dataset.json` 这个实体文件里。
2. **压测工具只负责“无脑读取”**：后续真正执行压测时，无论是测百炼还是腾讯云，压测命令里都不包含轮次参数，而是统一读取 `--dataset-path outputs/agentic_dataset.json`。压测工具只会机械地把这个 JSON 文件里的 10 条对话原封不动地发出去。
3. **随机种子（双保险）**：由于带上了 `--seed 42`，即使用户不小心删了 JSON 重新跑构建命令，生成出来的每一条对话的轮数和文本也会和之前逐字不差。

这就完美保证了真正的压测阶段 100% 锁死了随机变量，所有测试基于完全相同的数据流。

### 4.3 压测场景的真实性剖析（拟真度与妥协）
**问：把 Assistant 回复删掉，强制按 Token 切分段落，这样真的接近真实使用场景吗？**

这取决于你定义的“真实业务”是什么。如果是指普通的“人类对话”，这种做法确实略微失真；但对于当下的**代码 Agent**与**长文本问答**业务来说，这是公认的最佳实践：

**✅ 极度拟真点 (高度吻合 Agent 场景)**：
* 真实工作流中（如 SWE-agent），往往是丢给大模型几万字的仓库代码（8192 Token 强前缀），然后每次执行终端命令，再把简短的终端日志喂给它（1024 Token 尾部增量）。这种“长不变、尾部小增量”的业务结构，正是评估厂商 **Prefix Cache（前缀缓存）能力** 最完美的场景。

**⚠️ 人为的妥协 (牺牲语义换取负载控制)**：
* **强行截断**：真实说话是按句子来的，但为了保证压测的控制变量绝对精准，脚本是在刚刚达到 1024 Token 的地方一刀切。这可能会把一句话截成两半。这虽然会破坏大模型的“推理准确度”，但在**性能测试（测延迟、测缓存命中率、测吞吐）**的语境下，底层 GPU 是完全不在乎句子通顺与否的，它只在乎 Token 的绝对数量。
* **单边发包**：剥离 Assistant 历史回复是为了防止模型过去生成的错误代码影响当前的表现。

**结论**：这个策略在“语义连贯性”上做了妥协，但在**“系统负载与下文递增规律”**上做到了极致的拟真。用它来测缓存和首字延迟，最能逼出底层算力的真实底子。
