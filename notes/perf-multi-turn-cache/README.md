# 多轮对话压测：KV 缓存命中率指标说明

> 本文整理 evalscope **性能压测（`evalscope perf`）多轮模式**下的 KV 缓存命中率指标：它是什么、怎么算、怎么展示、怎么判断数据是真实还是估算的。
> 注意：缓存命中率仅属于**性能压测模块**，模型能力评测（accuracy eval）侧没有此指标。

相关文档：[docs/zh/user_guides/stress_test/multi_turn.md](../../docs/zh/user_guides/stress_test/multi_turn.md)

---

## 1. 缓存命中率是什么

多轮对话每一轮都要把**完整历史**重新发给服务端，越聊越长。聪明的服务端会把算过的前缀结果存起来（KV cache / prefix caching），下次直接复用、只算新增部分。

**缓存命中率 = 这次请求中被服务端复用、无需重算的 token 比例。**

- 高 → 服务端高效，多轮又快又省
- 低 → 服务端在重复劳动，慢

启用方式：

```bash
evalscope perf --model 你的模型 --url 服务地址 --multi-turn ...
```

---

## 2. 怎么计算（不是只看最后一轮）

**核心：按 token 总量加权，不是按轮平均，也不是只取最后一轮。**

```
缓存命中率 = （所有轮被复用的 token 加总）÷（所有轮发出去的 token 加总）
```

代码：[trace_metrics.py:102-107](../../evalscope/perf/utils/trace_metrics.py#L102)

### 示例（一条对话 3 轮）

| 轮次 | 发出 token | 被复用 | 单轮命中率 |
|---|---|---|---|
| 第1轮 | 100 | 0（无历史） | 0% |
| 第2轮 | 250 | 150 | 60% |
| 第3轮 | 500 | 380 | 76% |

- ❌ 按轮平均（项目**不这么算**）：`(0+60+76)/3 = 45.3%`
- ✅ token 加总（项目实际）：`(0+150+380) / (100+250+500) = 530/850 = 62.4%`

后面的轮 token 多、更重要，加总能让“大轮”自然占更大权重。

### 第 1 轮也计入分母

第 1 轮命中率必然 0%（无历史可复用），但仍计入分母（[multi_turn.py:177-189](../../evalscope/perf/core/strategies/multi_turn.py#L177)）。
代表整场对话的真实平均水平；对话越长，第 1 轮的拖累越小，命中率自然越高。

---

## 3. 三个层面的指标

| 指标 | 含义 | 聚合方式 | 代码 |
|---|---|---|---|
| `Cache Hit (%)`（Per-Request 表） | 全局总账 | 所有对话所有轮 token 全加起来相除 | [benchmark_util.py:292-298](../../evalscope/perf/utils/benchmark_util.py#L292) |
| `Cache Hit Rate (%)`（Per-Trace 表） | 每条对话算一个，看分布 | 每对话 token 加总得一值，再取 mean/p50/p90/p99/max | [trace_metrics.py:102](../../evalscope/perf/utils/trace_metrics.py#L102) |
| `Eligible Cache Hit Rate (%)`（Per-Trace 表） | 更公平的版本 | 分母只算“理论上本该被缓存的 prefix”，剔除第 1 轮与当前轮新增内容 | [trace_metrics.py:110](../../evalscope/perf/utils/trace_metrics.py#L110) |

`Eligible` 的判别价值：
- 普通命中率和 Eligible 都低 → 服务端**根本没开**缓存
- Eligible 高、普通命中率低 → 缓存**开了，只是被新内容稀释**（正常）

### 💡 技术层面的真实区别与大白话解释

#### ① 单次请求缓存命中率 (Cache Hit %) —— “实际省了多少钱”
* **定义**： 每次 API 请求中，实际命中缓存的 Token 数 占 总输入 Token 数 的物理比例。
* **计算公式**： `实际命中缓存的 Token / (系统提示词 + 历史多轮对话 + 本轮最新提问)`
* **为什么很难达到 100%？** 
  因为大模型在进行多轮对话时，你最新发送的那一句话（比如刚刚敲下的几百字提问）是全新产生的，在服务端的缓存数据库里绝对不可能存在。这部分“新输入”是硬性无法命中的。即使历史全部完美缓存，分母里包含的新提问依然会把整体命中率稀释（例如稀释到 79.0%）。

#### ② 理论可缓存命中率 (Eligible Cache Hit Rate %) —— “系统缓存做得有多好”
* **定义**： 在排除掉那些“天生就绝对无法被缓存”的 Token 之后，剩余**“有资格、符合缓存规则”**的 Token 的实际命中比例。
* **哪些 Token “没有资格”（Not Eligible）被缓存？**
  * **本轮最新的用户输入**：全新内容，不可能提前在缓存中存在。
  * **不满对齐块的零头**：很多云厂商的 Prompt Cache 是按块（例如每 1024 个 Token 为一个 Block）缓存的。如果历史对话有 5200 个 Token，前 5120（1024×5）个是有资格缓存的，最后多出来的 80 个 Token 无法对齐，属于“不合格”部分。
  * **冷启动/第一轮对话**：完全没有历史上下文时，整个 Prompt 都不具备可缓存性。
* **计算公式**： `实际命中缓存的 Token / 理论上所有符合缓存条件的 Token`
* **为什么能高达 93.0%？** 
  这说明排除掉最新提问和无法对齐的零头后，模型/服务端对你前面聊过的历史记忆（System Prompt、前几轮的历史对话上下文等）保存和复用得极其完美，几乎全都秒识别（命中率 93.0%），没有发生因为缓存过期被踢出（Evicted）或者匹配失败的情况。

---

---

## 4. 数据来源：真实 vs 估算

选择逻辑在 [multi_turn.py:182-189](../../evalscope/perf/core/strategies/multi_turn.py#L182)：

```python
if real_cached_tokens is not None:
    cached_tokens = real_cached_tokens            # ① 真实：服务端给的
elif prev_prompt_tokens > 0:
    cached_tokens = prev_prompt + prev_completion # ② 估算：理论上限
```

- `real_cached_tokens` **只在服务端响应带 `usage.prompt_tokens_details.cached_tokens` 时**才被赋值
  （[default_api.py:145-150](../../evalscope/perf/plugin/api/default_api.py#L145)、[openai_responses_api.py:186-191](../../evalscope/perf/plugin/api/openai_responses_api.py#L186)）。
- 优先用真实值；服务端没回传时退化为客户端估算（上一轮 prompt + completion，即完整历史 = 理论上限）。

> ⚠️ 当前代码**不会**在输出里打一行“本次用的是真实还是估算”，也**不会**把 `cached_tokens` 存进结果 SQLite（[db_util.py](../../evalscope/perf/utils/db_util.py) 无该字段）。所以需用下面方法自行确认。

---

## 5. 怎么确认用的是真实值（两种方法）

### 方法 A（最准）：直接看服务端 usage 字段

单发一次请求，看响应里有没有 `prompt_tokens_details.cached_tokens`：

```bash
curl $URL/v1/chat/completions -H "Authorization: Bearer $KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"你的模型","messages":[{"role":"user","content":"hi"}]}' \
  | python -m json.tool
```

- 有 `"prompt_tokens_details": {"cached_tokens": N}` → 压测走**真实**路径 ✅
- 没有该字段 → 只能**估算** ⚠️

> vLLM / SGLang / DashScope / OpenAI 官方接口通常带；很多自建或老版本 OpenAI-compatible 服务不带。

### 方法 B（看结果即可判断）：盯 `Eligible Cache Hit Rate (%)`

关键巧合——两处定义完全相同：
- 估算时：`cached_tokens = prev_prompt + prev_completion`（[multi_turn.py:185](../../evalscope/perf/core/strategies/multi_turn.py#L185)）
- eligible 定义：`eligible = prev_prompt + prev_completion`（[trace_metrics.py:145](../../evalscope/perf/utils/trace_metrics.py#L145)）

因此**走估算路径时，`Eligible Cache Hit Rate` 必然精确等于 100.00**。

| 看到的 Eligible Cache Hit Rate | 结论 |
|---|---|
| 精确 **100.00** | 几乎肯定是**客户端估算**（服务端没回传 cached_tokens） |
| 87%、93% 等非整数 | **服务端真实值**（真实命中很难刚好顶满理论上限） |

---

## 6. 结果怎么展示与落盘

跑完后 [db_util.py:240 `summary_result`](../../evalscope/perf/utils/db_util.py#L240) 同时：终端打印 + 写文件。

### 终端表格

- Per-Request Metrics：`Cache Hit (%)`
- Per-Trace summary：`Cache Hit Rate (%)`、`Eligible Cache Hit Rate (%)`
- Workload throughput：`Cached Prompt tok/s`、`New Prompt tok/s`

### 落盘文件（结果目录）

- `trace_summary.json` ← Per-Trace 两个缓存命中率
- `workload_throughput.json`、`workload_timeline.json` ← 吞吐拆分
- `benchmark_summary.json`、`benchmark_percentile.json`、`benchmark_args.json`
- SQLite `.db`（注意：不含逐请求的 `cached_tokens`）

---

## 7. 一句话总结

- 测多轮缓存命中率 → `evalscope perf --multi-turn`，最好开 `--stream`。
- 命中率按 **token 总量加总**算，含第 1 轮（0%），非按轮平均、非只取末轮。
- 想要**真实**数据 → 服务端须回传 `usage.prompt_tokens_details.cached_tokens`（vLLM/SGLang 支持）。
- 快速判真伪 → 看 `Eligible Cache Hit Rate` 是否死磕在 **100.00**（是则为估算）。

---

## 8. 跨云/跨模型对比实验（方案 B：一次 run 内自动注入 session-id）

> 场景：对比 **阿里百炼** 与 **腾讯云** 的 DeepSeek 系列（v4-pro / v4-flash / v3.2），OpenAI 兼容接口，全部开推理（`reasoning_effort`），用 `swe_smith` 测多轮缓存命中率。不需要并发（`--parallel 1`）。

### 8.1 概念对齐：一条对话 = 一个 Session

- 多轮压测里，**一条对话**内部上下文不停累积（turn1 → turn1+turn2 → …），这就是「一个 session 不停加上下文」。
- 但一次压测要跑 `--number N` 条**互相独立**的对话 = N 个独立 session，每条从空上下文开始、各自累积，模拟「N 个用户各聊各的」。
- `--number 10` × 4 个模型 = **40 个 Session**；每个 Session 内 4~12 轮 = 4~12 个 HTTP 请求。

### 8.2 腾讯云的两个缓存字段（语义）

| 字段 | 传递方式 | 作用 | 赋值原则 |
|---|---|---|---|
| `X-Session-ID` | HTTP **Header** | 把同一会话的连续请求路由到**同一推理实例**，提高该实例 KV Cache 局部命中 | 一条对话一个值，对话内共享 |
| `prompt_cache_key` | **Body** 字段 | 告诉缓存系统哪些请求前缀相同、可复用 KV Cache | **整条对话唯一 ID（conversation_id）**，非 session_id |

两个字段都要求「**对话内所有轮相同，跨对话不同**」。阿里百炼**无**此类字段（隐式自动缓存），对比的是「各自最优缓存配置」。

### 8.3 为什么选方案 B（vs 方案 A）

- evalscope 的 `--headers` / `--extra-args` 是**全局静态**的：一次 run 内所有对话只能共用同一个值。
- **方案 A**（不改代码）：拆成 N 个 run，每条对话单独 `--number 1 --dataset-offset i`，外层循环换 session-id。可用但繁琐。
- **方案 B**（改代码）：一次 run 跑全部 N 条，代码按每条对话的 `trace_id` **自动注入**唯一 session-id / prompt_cache_key。一条命令搞定，且 **Per-Request 表直接给 token 级全局命中率**（所有对话共享一个累加器）。

### 8.4 代码改动（已实施，开关默认关闭 → 对现有功能零影响）

> 已落地到当前分支。做成 **opt-in 开关** `--multi-turn-session-cache`：不加这个 flag 时，请求体/请求头与改动前**逐字相同**，所有现有用法不受影响；只有显式开启才注入会话标识。

**改动 1 — [http_client.py](../../evalscope/perf/core/http_client.py#L68) 让 `post` 支持按请求覆盖 header（向后兼容，默认 `None` = 原行为）：**

```python
async def post(self, body, extra_headers: Optional[dict] = None) -> BenchmarkData:
    headers = self.headers if not extra_headers else {**self.headers, **extra_headers}
    try:
        output = await self.api_plugin.process_request(self.client, self.url, headers, body)
        return output
    except asyncio.TimeoutError as e:
        ...
```

**改动 2 — [arguments.py](../../evalscope/perf/arguments.py) 新增开关字段 + CLI flag：**

```python
# Arguments dataclass 字段
multi_turn_session_cache: bool = False
# CLI
parser.add_argument('--multi-turn-session-cache', action='store_true',
                    default=False, dest='multi_turn_session_cache', help=...)
```

**改动 3 — [multi_turn.py](../../evalscope/perf/core/strategies/multi_turn.py#L145) worker 发请求前按开关注入会话标识：**

```python
# 模块顶部常量
_SESSION_CACHE_BODY_FIELD = 'prompt_cache_key'
_SESSION_CACHE_HEADER = 'X-Session-ID'

# worker 内，build_request + max_tokens 之后、post 之前：
extra_headers: Optional[Dict[str, str]] = None
if self.args.multi_turn_session_cache:                  # 默认 False → 不进这个分支
    session_key = f'{self.args.model}-{trace_id}'       # 带模型名 → 同 endpoint 多模型不撞号
    request[_SESSION_CACHE_BODY_FIELD] = session_key    # body 字段（缓存复用标识）
    extra_headers = {_SESSION_CACHE_HEADER: session_key}  # HTTP header（路由标识）
benchmark_data = await self.client.post(request, extra_headers=extra_headers)
```

- `trace_id` 是 worker 已有的每对话唯一编号（`bench-0`、`bench-1`…，见 [multi_turn.py:80](../../evalscope/perf/core/strategies/multi_turn.py#L80)）。
- 加 `self.args.model` 前缀：腾讯云 3 个模型同 endpoint，避免 `bench-0` 撞号导致缓存串扰。
- 对**不支持**这两个字段的服务（阿里百炼）**无害**——未知 body 字段 / header 会被忽略；但仍建议只在腾讯云那几条命令加 `--multi-turn-session-cache`，阿里那条可加可不加。

### 8.5 第 0 步：生成统一数据集（一次，所有模型共用）

```powershell
python scripts/perf/build_swe_smith_dataset.py `
  --model-path Qwen/Qwen2.5-7B-Instruct `
  --first-turn-length 8192 `
  --subsequent-turn-length 1024 `
  --min-turns 4 --max-turns 12 `
  --number 10 `
  --output-path outputs/agentic_dataset.json `
  --seed 42
```

> PowerShell 反引号续行时行末不能再接 `#` 注释（反引号必须是行末最后一个字符），所以注释单独列在下表。

**逐行注释：**

| 参数 | 取值 | 含义 |
|---|---|---|
| `--model-path` | `Qwen/Qwen2.5-7B-Instruct` | 仅用作 **tokenizer**，给文本算 token 数好按长度截断；**不发起任何推理**，不影响公平性 |
| `--first-turn-length` | `8192` | 第 1 轮 prompt 的目标 token 长度（首轮最长，奠定后续可复用的前缀） |
| `--subsequent-turn-length` | `1024` | 之后**每轮新增**的目标 token 长度（在已有上下文上再叠 ~1024） |
| `--min-turns` `--max-turns` | `4` / `12` | 每条对话的轮数在 **[4,12] 均匀随机**抽取；原始轨迹 user 消息不够这个轮数的会被丢弃。注：预筛门槛按 `max_turns` 算（`8192+1024×11≈19.5k token`，~58k 字符），比 4-8 略高，候选不足时调小 `--subsequent-turn-length` |
| `--number` | `10` | 生成 **10 条**独立对话（= 压测时的 10 个 Session；够稳又省时，见 8.6 末说明） |
| `--output-path` | `outputs/agentic_dataset.json` | 落盘的统一数据集；4 个模型全部加载这一份 |
| `--seed` | `42` | 随机种子，固定「轮数抽样 + 轨迹选取」→ **每次生成逐字一致、可复现** |

- 单条对话总长 ≈ `first_turn_length + subsequent_turn_length × (轮数-1)`，即本配置约 `8192 + 1024×(4~12 −1)` ≈ 11k~19k token。
- 所有云/模型加载**同一份 JSON** → 收到逐字相同的输入，这是公平对比的地基。
- 候选轨迹不足（被丢弃太多导致凑不满 10 条）时，调小 `--first-turn-length` / `--max-turns` 再生成。

#### 8.5.1 生成「最大池子」（为复测用 offset 错开残留缓存）

若要**反复测同一 (模型, 厂商)** 取平均，需要一个比 `--number` 大的池子，靠 `--dataset-offset` 每次取不相交子集。池子上限 = 预筛后通过的候选轨迹数。两步拿到最大池子：

```powershell
# 第 1 步：探测候选上限（把 number 设超大，脚本预筛后打印候选数并 sys.exit 退出）
python scripts/perf/build_swe_smith_dataset.py `
  --model-path Qwen/Qwen2.5-7B-Instruct `
  --first-turn-length 8192 --subsequent-turn-length 1024 `
  --min-turns 4 --max-turns 12 `
  --number 100000 `
  --output-path outputs/agentic_dataset.json --seed 42
#  读输出： Pre-filter: <N> candidates ...  → 记下 N

# 第 2 步：用 N 生成最大池子（构建期个别轨迹轮数不足只 warning，照样保存已建成的 P 条）
python scripts/perf/build_swe_smith_dataset.py `
  --model-path Qwen/Qwen2.5-7B-Instruct `
  --first-turn-length 8192 --subsequent-turn-length 1024 `
  --min-turns 4 --max-turns 12 `
  --number <填上一步的 N> `
  --output-path outputs/agentic_dataset.json --seed 42
#  读输出： Built <P> conversations ...  → P = 最大池子（JSON metadata.num_conversations 亦记录）
```

- 想要**更大**的池子：调小 `--subsequent-turn-length`（如 512），预筛字符门槛随之降低 → 候选变多（代价：每轮增量变小）。
- **offset 怎么用**：池子 P、每次 `--number 10` → 复测时 `--dataset-offset 0 / 10 / 20 / …`，各取不相交的 10 条，最多 `floor(P/10)` 次互不蹭缓存的复测（offset 是整体轮转，只要 `offset+10 ≤ P` 就与 offset=0 那批不重叠）。

### 8.6 运行脚本（方案 B：每个模型一条命令）

```powershell
$tencentUrl = "https://tokenhub.tencentmaas.com/v1/chat/completions"   # 腾讯 TencentMaaS token hub；以你的控制台为准
$bailianUrl = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"

$common = @(
  "--api","openai",
  "--dataset","swe_smith","--dataset-path","outputs/agentic_dataset.json",
  "--multi-turn","--parallel","1","--number","10",
  "--max-tokens","16384","--seed","42","--temperature","0","--top-p","1.0","--stream",
  "--extra-args",'{"reasoning_effort":"low"}',   # reasoning_effort 非原生字段，走 extra-args 注入请求体；非推理模型删掉这行
  "--read-timeout","300",          # 读超时 300s：reasoning=high 单轮常需数十秒~分钟，60s 会误杀
  "--no-timestamp","--no-test-connection"
)

# 腾讯云三个：加 --multi-turn-session-cache，session-id / prompt_cache_key 由代码按对话自动注入
# --name / --outputs-dir 都带「厂商-模型」：同一款模型在不同厂商跑时输出与结果名各自唯一，绝不撞车
evalscope perf --model deepseek-v4-pro   --url $tencentUrl --api-key $env:TENCENT_API_KEY  @common --multi-turn-session-cache --name tencent-v4pro   --outputs-dir outputs/tencent-v4pro
evalscope perf --model deepseek-v4-flash --url $tencentUrl --api-key $env:TENCENT_API_KEY  @common --multi-turn-session-cache --name tencent-v4flash --outputs-dir outputs/tencent-v4flash
evalscope perf --model deepseek-v3.2     --url $tencentUrl --api-key $env:TENCENT_API_KEY  @common --multi-turn-session-cache --name tencent-v32    --outputs-dir outputs/tencent-v32
# 阿里百炼一个：无此类字段，不加 flag（加了也无害，未知字段被忽略）
evalscope perf --model deepseek-v3.2     --url $bailianUrl --api-key $env:DASHSCOPE_API_KEY @common --name bailian-v32    --outputs-dir outputs/bailian-v32
```

**参数三层分类：**

| 层级 | 参数 |
|---|---|
| 全程固定（保证一致） | `--dataset-path`、`--seed 42`、`--parallel 1`、`--number 10`、`--max-tokens`、`--temperature 0`、`--top-p 1.0`、`reasoning_effort low`、`--multi-turn` |
| 随被测对象变 | `--model`、`--url`、`--api-key`、`--name`（带厂商-模型）、`--outputs-dir`（带厂商-模型） |
| 开关触发（代码注入） | `--multi-turn-session-cache` → 自动注入 `X-Session-ID` / `prompt_cache_key` = `{model}-{trace_id}` |

> 不同 endpoint 缓存各自独立，**不要给不同模型换 offset**，用相同数据才最公平。只有重复测**同一模型**取平均时，第二轮才整体换一批 offset 避免自我蹭缓存。

#### 8.6.1 推荐用法：一次只比「一个模型」跨厂商

上面是一口气四个模型。实际更常用的是**一次只对比同一个模型在不同厂商的表现**（`deepseek-v3.2` 两家都有）：

```powershell
# $common / $tencentUrl / $bailianUrl 同上
# 同一个模型，两个厂商各跑一次（两个 endpoint 缓存物理隔离，互不污染）
# --name / --outputs-dir 都带厂商后缀：同模型跨厂商也不会撞目录、不会触发「db 已存在」退出
evalscope perf --model deepseek-v3.2 --url $tencentUrl --api-key $env:TENCENT_API_KEY  @common --multi-turn-session-cache --name v32-tencent --outputs-dir outputs/v32-tencent
evalscope perf --model deepseek-v3.2 --url $bailianUrl --api-key $env:DASHSCOPE_API_KEY @common --name v32-bailian --outputs-dir outputs/v32-bailian
```

- 换别的模型对比时，只改 `--model` + 对应的 `--url/--api-key/--outputs-dir`，其它一律不动。
- 腾讯那条带 `--multi-turn-session-cache`，百炼那条不带（无此字段）。

#### 8.6.2 第二次跑要不要改？（铁律：数据集 JSON 永不重生成）

**同一份输入才公平 —— 生成一次，所有模型/厂商/复测都用这份 `agentic_dataset.json`。** 是否改运行命令分三种情况：

| 第二次跑的是… | 数据集 | 运行命令 | 为什么 |
|---|---|---|---|
| **另一个厂商**（同次对比的第二条命令） | 不变 | 只改 `--url/--api-key/--outputs-dir` | 两个 endpoint 缓存**物理隔离**，互不污染 |
| **另一个模型**（下一轮对比） | 不变 | 只改 `--model` + `--url/--api-key/--outputs-dir` | 不同模型 → 注入的 `prompt_cache_key` 前缀不同（`{model}-bench-0`），不撞 |
| **同模型+同厂商再测一遍**（取平均/复测） | 不变 | ⚠️ **有坑，见下** | 上次的服务端 KV 缓存可能还在，会让本次「第 1 轮」也命中 → 命中率虚高 |

**只有「同模型同厂商复测」要特殊处理。** 因为注入的 `prompt_cache_key = {model}-bench-i` 跨 run **固定**，第二次会精准命中第一次的残留缓存，turn-1 本该冷启动却热了。两个解法：

1. **简单**：两次之间**隔开**，等服务端缓存 TTL 过期（通常几分钟~1 小时）再复测。
2. **彻底**：按 [8.5.1](#851-生成最大池子为复测用-offset-错开残留缓存) 生成大池子（P 条），每次只跑 `--number 10`，复测时加 `--dataset-offset 0 / 10 / 20 …` 取**不相交**的 10 条。
   ⚠️ **池子=跑的条数时 offset 无效**（同样 N 条只是换顺序，服务端缓存里全有）——必须 `池子 > --number` 才有用。

#### 8.6.3 用原生 CLI 跑（一次一个模型）

直接跑原生 `evalscope perf --multi-turn` 命令（`--url` / `--api-key` 显式传入）：

```bash
evalscope perf \
  --url https://tokenhub.tencentmaas.com/v1/chat/completions \
  --api-key '<YOUR_API_KEY>' \
  --model deepseek-v3.2 \
  --dataset swe_smith \
  --dataset-path outputs/agentic_dataset.json \
  --dataset-offset 0 \
  --multi-turn \
  --parallel 5 --number 10 \
  --max-tokens 16384 --seed 42 --temperature 1.0 --top-p 0.95 \
  --stream \
  --extra-args '{"reasoning_effort":"low"}' \
  --read-timeout 300 --no-test-connection \
  --name swe_deepseek-v3.2_tencent_offset-0_cache-off
```

- 换厂商/模型：改 `--url` / `--api-key` / `--model` / `--name`（`--name` 带 `<model>_<vendor>`）；
- 腾讯云需要显式 Session 路由 → 加 `--multi-turn-session-cache`；阿里百炼（隐式缓存）不加；
- 复测同一(模型,厂商) → 换 `--dataset-path outputs/agentic_pool.json` + `--dataset-offset 10/20/…`；
- 批量/多模型编排 + 出对比报告 → 用 `.trae/skills/evalscope-eval-compare` skill。

### 8.7 读取结果（两种命中率口径都能拿）

一次 run = 全部 10 条对话，终端直接打印：

- **Per-Request 表 `Cache Hit (%)`** = **token 级全局命中率**（总 cached ÷ 总 prompt，所有对话共享累加器）
- **Per-Trace 表 `Cache Hit Rate (%)` / `Eligible Cache Hit Rate (%)`** = 对话等权平均 + 分布

落盘文件在 `outputs/<时间戳>/swe_<model_id>_offset-<N>_cache-<tag>/parallel_5_number_10/`：
- `trace_summary.json` → 对话级命中率
- `workload_timeline.json` → 末点 `cum_cached_prompt` / `cum_new_prompt` = **原始 token 累计总数**（token 级命中率 = `cum_cached_prompt / (cum_cached_prompt + cum_new_prompt)`）

**跨 4 模型对比脚本**（目录已改为 `outputs/<ts>/swe_<model_id>_...`，下面示例按 `outputs` 递归，仅供参考）：

```powershell
Get-ChildItem outputs -Directory | ForEach-Object {
    $model = $_.Name
    # 对话级：平均每条对话的 Cache Hit Rate
    $traceRates = Get-ChildItem $_.FullName -Recurse -Filter trace_summary.json | ForEach-Object {
        $j = Get-Content $_.FullName -Raw | ConvertFrom-Json
        ($j.rows | Where-Object { $_.metric -eq "Cache Hit Rate (%)" }).mean
    }
    # token 级：聚合 workload_timeline 末点
    $cached = 0.0; $new = 0.0
    Get-ChildItem $_.FullName -Recurse -Filter workload_timeline.json | ForEach-Object {
        $last = (Get-Content $_.FullName -Raw | ConvertFrom-Json).points[-1]
        $cached += [double]$last.cum_cached_prompt; $new += [double]$last.cum_new_prompt
    }
    $tokenRate = if (($cached + $new) -gt 0) { $cached / ($cached + $new) * 100 } else { 0 }
    $traceAvg  = if ($traceRates) { ($traceRates | Measure-Object -Average).Average } else { 0 }
    "{0,-20} 对话级={1,6:N2}%  token级={2,6:N2}%" -f $model, $traceAvg, $tokenRate
}
```

### 8.8 务必确认的坑

1. **推理字段（已确认）**：本对比统一用 `--extra-args '{"reasoning_effort":"low"}'` 开启推理——腾讯云与阿里百炼的 DeepSeek 兼容接口都认这个字段，四家口径一致。（仅在换其他厂商/模型时才需重新确认字段名。）
2. **腾讯云 URL** 以控制台为准（示例是 LKEAP 接口）。
3. **temperature=0**：DeepSeek-R1 类推理模型常不支持，报错就删掉这两行（默认本就是 0）。
4. **真实 vs 估算**：看 `Eligible Cache Hit Rate` 是否死磕 100.00（是=客户端估算，服务端没回传 `cached_tokens`）。四家口径一致仍可比。
5. **必须用 `--api openai`**：`--api dashscope` 是白名单式参数组装，会丢掉 `extra_args` 与注入字段。（官方文档里连 DashScope 的 trie 示例也用 `--api openai` + compatible-mode URL，印证此选择。）
6. **别用 `ignore_eos`**：官方多数示例带 `--extra-args '{"ignore_eos": true}'` 来锁定输出长度——但那只对 **vLLM/SGLang 本地引擎**有效，腾讯云/阿里百炼**不支持**。本方案改用 `reasoning_effort` + `--max-tokens`，输出长度不锁定，但对 swe_smith 缓存命中率影响可忽略（前缀由大首轮决定）。
7. **Chat 模板开销 ~2~3pp**（官方文档）：每轮 role/special token 会让 `Cache Hit Rate` 比裸 completions 低约 2~3 个百分点。**四家口径一致**，不影响横向对比，只是别拿这个绝对值跟"理论 100%"较真。

### 8.9 与官方文档对照核查（[stress_test/multi_turn](https://evalscope.readthedocs.io/zh-cn/latest/user_guides/stress_test/multi_turn.html)）

| 我的方案 | 官方文档 | 结论 |
|---|---|---|
| 预生成 JSON + `--dataset swe_smith --dataset-path` | 官方列为**推荐**模式（prebuilt JSON）；live 模式才要 `--tokenizer-path` | ✅ 一致；我的运行命令/脚本**不带** `--tokenizer-path`（预生成模式不需要） |
| build 用 `--first-turn-length 8192 --subsequent-turn-length 1024` | 官方 build 示例同款 `8192 / 1024`（轮数 3-8、number 128） | ✅ 同源，仅轮数/条数按需调成 4-12 / 10 |
| `--multi-turn` 下 `--number`=对话数、`--parallel`=并发对话数 | 官方明确同义 | ✅ 一致 |
| 运行**不传** `--max-turns`（让 JSON 内置轮数生效） | 官方 prebuilt 示例同样不传 | ✅ 一致（运行期传 `--max-turns` 会**截断**对话） |
| `--dataset-offset` 取不相交子集做复测 | 官方：offset 用于 **sharded testing**（跳过前 N 条） | ✅ 一致；预生成 JSON 内部是**整体轮转**，`offset+number ≤ 池子`时即不重叠 |
| `--api openai` 接 DashScope/腾讯 compatible-mode | 官方 DashScope 示例正是 `--api openai` + compatible URL | ✅ 一致 |
| `Cache Hit (%)`（Per-Request）= token 级全局；`Cache Hit Rate / Eligible`（Per-Trace）= 对话级 | 官方指标定义逐字吻合（含"turn1 计入分母""Eligible 排除首轮+新内容"） | ✅ 一致 |
| `--multi-turn-session-cache` 注入 `X-Session-ID` / `prompt_cache_key` | 官方**无**任何 session-id / 缓存键功能 | ✅ 这是我们新增的能力，不与现有功能重复（故做成默认关闭的开关） |
| Python：`run_perf_benchmark(Arguments(...))` | 官方文档**只给 CLI**，无 Python 示例 | ⚠️ 我的 Python 脚本是**对照源码验证**过的（`main.py` 接受 `Arguments`/`dict`/`Namespace`），非文档原文 |
| `reasoning_effort:"low"` 开思考、不用 `ignore_eos` | 官方示例普遍用 `ignore_eos`（vLLM 专用） | ⚠️ 有意偏离：云端不支持 `ignore_eos`，见 8.8#6 |

**结论：** 方案与官方文档在数据集、参数语义、指标定义、API 选择上完全一致；两处有意偏离（不用 `ignore_eos`、用 Python API）均已验证可行；session 注入是文档未覆盖的新增能力。
