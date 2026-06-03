# VLM (多模态大模型) 极简均衡测试集抽取方案

## 0. 运行前必读

### 0.1 先核对数据集名
EvalScope 装的是定制版 `ms-vlmeval`，**版本可能比上游旧**，个别数据集名（如 `MMMU_Pro_10c`、`MME-RealWorld-Lite`）不一定在你装的版本里。运行前先确认一次：

```python
from evalscope.backend.vlm_eval_kit import VLMEvalKitBackendManager
print(VLMEvalKitBackendManager.list_supported_datasets())
```

把命令里的名字和这个列表对一下；缺失就 `pip install ms-vlmeval -U`，或换列表里的近义集。

### 0.2 VLMEvalKit 后端用 `eval_config` 配置
VLMEvalKit 后端通过 `eval_config` 嵌套配置驱动（见 [run.py:64-89](../../evalscope/run.py#L64)），统一用 `TaskConfig(eval_backend='VLMEvalKit', eval_config={...})` 或 `--eval-config 配置文件` 来跑（不是 native 那套扁平 `--datasets/--model/--api-url`）。下面第 2 节的 `run_vlm.py` 已封装好。

---

## 1. 需求背景与核心痛点
标准 VLM 测试集（如 `MMBench_DEV_EN_V11`、`MME-RealWorld-Lite`、`MMMU_Pro_10c`）题量大多 1000 - 2000 题。为压缩测试时间与 API 成本，我们希望每个测试集控制在 **500 题左右**。

**核心痛点**：专业测试集通常按"类别/主题"集中排序存放，VLMEvalKit 后端的 `limit` 是**全局前 N 条**，直接设 500 相当于只截"前 500 题"（可能某些类别一题没抽到），评估维度严重失衡。

**解决策略 (分层抽样)**：VLMEvalKit 后端的数据集以 `.tsv` 缓存在本地（默认 `~/LMUData/`，见 [vlmevalkit_backend.md](../../docs/zh/user_guides/backend/vlmevalkit_backend.md) 第 2 节）。我们用 Python 读 TSV，按**类别字段（能力类别 / 任务类型 / 场景 / 学科等，因集而异）**做**"等比例分层抽样"**，存回原文件名直接喂给框架。

### 为什么科学且 100% 可复现？
核心是 `df.groupby(分层列).apply(lambda x: x.sample(frac=比例, random_state=42))`：

1. **绝对可复现 (`random_state=42`)**：任何机器跑出来都是**完全相同的那 ~500 题**，满足"控制变量法"，确保对比不同 API 时考卷一致。
2. **能力分布镜像 (`groupby` + `frac`)**：先按类别"分班"，再按统一比例抽题，微缩集中各细分能力占比与原集**基本一致**。

> ⚠️ 不同数据集 TSV 的"分层列"叫法不一（`category` / `l2-category` / `sub_category` / `subject`…，VLM 多是能力类别/任务类型，并非学科）。下面脚本用 `pick_strata_column()` **自动探测**并打印，避免写死列名导致 `KeyError`。

---

## 2. 通用运行器（统一用 eval_config）

把下面存成 `run_vlm.py`。下载、抽样后正式跑，全走它。

```python
# run_vlm.py
import os
from evalscope import run_task, TaskConfig

# api_base 必须是「完整」的 /v1/chat/completions；例如百炼：
#   https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions
API_BASE = os.environ.get('API_URL', 'http://localhost:8000/v1/chat/completions')
API_KEY = os.environ.get('API_KEY', 'EMPTY')
MODEL_TYPE = '你的模型名'  # API 请求体里的 model 字段（如 qwen-vl-max）


def run_vlm(dataset: str, limit=None, video_llm: bool = False):
    run_task(TaskConfig(
        eval_backend='VLMEvalKit',
        work_dir='outputs',
        eval_config={
            'data': [dataset],
            'mode': 'all',          # 推理 + 评测
            'limit': limit,         # None=全量；下载链路时设 1
            'reuse': False,
            'nproc': 16,
            'ignore': True,         # 跳过失败样本, 不中断整场（默认开）
            'retry': 3,             # 单条失败重试次数
            'model': [{
                'type': MODEL_TYPE,
                'name': 'CustomAPIModel',   # 固定值，必须是 CustomAPIModel
                'api_base': API_BASE,
                'key': API_KEY,
                'temperature': 0.0,         # 采样温度；0=贪心（可复现）。官方文档支持的 model 配置键
                'top_p': 0.95,               # 核采样；非具名参数→进 BaseAPI.default_kwargs→原样透传成请求体顶层字段。temperature=0 时为空操作，留作可调旋钮
                # 'reasoning_effort': 'high',  # 思考档位；同 top_p 走 **kwargs 透传进请求体，能否生效取决于目标 API 是否认该字段（OpenAI 兼容推理端点通常认）
                'max_tokens': 1024,
                'img_size': -1,
                'video_llm': video_llm,     # 视频集且要传 video_url 时设 True
            }],
        },
    ))


if __name__ == '__main__':
    # 例：先下载（limit=1 快速触发），再跑全量/微缩版
    run_vlm('MMBench_DEV_EN_V11', limit=1)
```

> 也可用 CLI：把上面的 `eval_config` 写成 `vlm_config.yaml`（结构见 [vlmevalkit_backend.md](../../docs/zh/user_guides/backend/vlmevalkit_backend.md) 第 3 节），然后 `evalscope eval --eval-config vlm_config.yaml`。

> **这些键在源码里到底怎么处理的（已核实 VLMEvalKit `OpenAIWrapper`=`CustomAPIModel`，见其 `vlmeval/api/gpt.py` 与 `vlmeval/api/base.py`）：**
>
> 1. **具名构造参数 → 有 wrapper 默认值**：`temperature`、`max_tokens`、`img_size`、`timeout`、`key`、`api_base` 是 `OpenAIWrapper.__init__` 的显式形参，**不写就用 wrapper 默认** `temperature=0`、`max_tokens=2048`、`img_size=-1`、`timeout=300s`。（官方文档化的就 `temperature`/`max_tokens`/`img_size` 三个，见 [vlmevalkit_backend.md](../../docs/zh/user_guides/backend/vlmevalkit_backend.md)。）
> 2. **非具名键 → `**kwargs` 透传进请求体**：`top_p` / `reasoning_effort` 等不是构造形参，会落进 `__init__(**kwargs)` → `BaseAPI` 存 `self.default_kwargs = kwargs` → `generate()` 里 `kwargs = deepcopy(default_kwargs); kwargs.update(...)` → `generate_inner(**kwargs)` → `payload = dict(model=…, messages=…, temperature=…, max_tokens=…, **kwargs)` → **作为请求体顶层字段原样发给 OpenAI 兼容 API**。
> 3. **所以**：`top_p` 写了就发、不写则 body 里没有该字段（服务端用自己默认）；`reasoning_effort` 同样**会被透传进 body**，能否生效取决于目标 API 是否认这个字段（OpenAI 兼容的推理模型端点通常认）——不是"框架丢弃"或"wrapper 自有默认"。
>
> 选择题型保持 `temperature=0.0`（可复现）；思考型 VLM 按模型卡推荐值（常见 0.6）再调。

#### 并发设置：`nproc`（VLM 这边不是单并发）
VLMEvalKit 后端的并发开关是 `eval_config` 里的 **`nproc`**（并行调用 API 的数量，见 [vlmevalkit_backend.md](../../docs/zh/user_guides/backend/vlmevalkit_backend.md) 参数说明）。上面 `run_vlm.py` 已默认 `'nproc': 16`，即**默认就是 16 并发**，不像 native 后端默认单并发。想调整就改这个数：

```python
'nproc': 16,   # 调大=更快更省时；调小=更稳、更不容易触发限流
```

**⚠️ 注意事项：**
1. **商业 API 限并发**：开太高会大面积 `429 Too Many Requests`，从 **8~16** 起步，报错就调小。
2. **视频集更吃资源**：`Video-MME` 每条要下载+截帧解析整段视频，`nproc` 太大易打满带宽/磁盘，视频集建议比图片集设得更小（如 4~8）。
3. **只影响速度不影响分数**：并发只是加速，正确率不变。

#### 错误处理与超时
`run_vlm.py` 的 `eval_config` 已设：
- **`ignore: True`**：单条样本失败就跳过、不中断整场（对应 [backend_manager.py:131](../../evalscope/backend/vlm_eval_kit/backend_manager.py#L131) 的 `--ignore`）。
- **`retry: 3`**：单条失败重试 3 次（[backend_manager.py:138](../../evalscope/backend/vlm_eval_kit/backend_manager.py#L138)）。

> 超时其实**可控**：`OpenAIWrapper.__init__` 有具名参数 `timeout`（默认 **300s**），在 `model` 配置 dict 里加 `'timeout': 300` 即可透传覆盖（与 `temperature` 等同级）。本方案沿用默认 300s 未显式写，需要时自行加。

### 2.1 先下载全量数据集（生成本地 TSV）
抽样前要让框架先把原始 `.tsv` 下到 `~/LMUData/`。用 `limit=1` 快速触发即可（首次评测会自动下载）：

```python
from run_vlm import run_vlm
for ds in ['MMBench_DEV_EN_V11', 'MME-RealWorld-Lite', 'MMMU_Pro_10c']:
    run_vlm(ds, limit=1)
run_vlm('Video-MME', limit=1, video_llm=True)
```

---

## 3. 通用分层抽样工具

四个数据集共用下面的工具（自动探测分层列、自动备份、可复现）。存成 `sample_utils.py`。

```python
# sample_utils.py
import os
import shutil
import pandas as pd

# 候选分层列，按优先级排列；取「存在且取值多于 1 种」的第一个
_STRATA_CANDIDATES = ['category', 'l2-category', 'sub_category', 'subject', 'subfield', 'task_type', 'split', 'domain']


def pick_strata_column(df: pd.DataFrame) -> str:
    print(f'[columns] {list(df.columns)}')
    for col in _STRATA_CANDIDATES:
        if col in df.columns and df[col].nunique() > 1:
            print(f'[strata] 使用分层列: {col} ({df[col].nunique()} 类)')
            return col
    raise KeyError(f'未找到合适的分层列，请人工从 {list(df.columns)} 中指定')


def resample_tsv(name: str, target: int, seed: int = 42, strata_col: str | None = None):
    """对 ~/LMUData/{name}.tsv 做分层抽样，原地覆盖（首次自动备份为 {name}_FULL.tsv）。"""
    original = os.path.expanduser(f'~/LMUData/{name}.tsv')
    backup = os.path.expanduser(f'~/LMUData/{name}_FULL.tsv')
    if not os.path.exists(backup):
        shutil.copy(original, backup)  # 备份全量，避免反复抽样越缩越小

    df = pd.read_csv(backup, sep='\t')  # 始终从全量备份读
    col = strata_col or pick_strata_column(df)
    frac = min(1.0, target / len(df))
    sampled = (df.groupby(col, group_keys=False)
                 .apply(lambda x: x.sample(frac=frac, random_state=seed), include_groups=True)
                 .sort_index())
    sampled.to_csv(original, sep='\t', index=False)
    print(f'✅ {name}: {len(df)} → {len(sampled)} 题 (分层列={col})')
    return sampled
```

> `include_groups=True` 兼容 pandas≥2.2 的 `groupby.apply` 行为变更；老版本若报参数错误删掉它即可。

---

## 4. 各数据集 500 题抽样方案

> 流程统一：① `run_vlm(ds, limit=1)` 触发下载 → ② `resample_tsv(...)` 抽样 → ③ `run_vlm(ds)` 跑微缩版。

### 4.1 基础视力：MMBench_DEV_EN_V11 (~1164 → ~500)
```python
from sample_utils import resample_tsv
from run_vlm import run_vlm

resample_tsv('MMBench_DEV_EN_V11', target=500)  # 分层列通常是 category（能力类别），自动探测
run_vlm('MMBench_DEV_EN_V11')                    # 名字不变，底层跑 500 题
```

### 4.2 实景理解：MME-RealWorld-Lite (~2150 → ~500)
```python
from sample_utils import resample_tsv
from run_vlm import run_vlm

resample_tsv('MME-RealWorld-Lite', target=500)
run_vlm('MME-RealWorld-Lite')
```

### 4.3 极限推理：MMMU_Pro_10c (~1730 → ~500)
> MMMU_Pro 有多个版本：`MMMU_Pro_10c`（10 选项标准版，本文采用）、`MMMU_Pro_10c_COT`、`MMMU_Pro_V`（截图版）、`MMMU_Pro_V_COT`。
```python
from sample_utils import resample_tsv
from run_vlm import run_vlm

resample_tsv('MMMU_Pro_10c', target=500)
run_vlm('MMMU_Pro_10c')
```

### 4.4 视频理解：Video-MME (按视频抽样至 ~300 题)
**📖 原集规格**：900 个视频 × 3 题 = 2700 题；按时长分 Short(300, ~80s) / Medium(300, ~8.6min) / Long(300, ~41min)。

> ⚠️ **视频集必须按"视频"抽样，不能按"题"抽样**！否则每个视频只抽到一两道题，但模型下载+截帧解析整段视频的耗时一点没省，账单照样爆炸。
>
> 要点：
> - 数据集代号是 **`Video-MME`**（短/中/长不是单独的数据集名）。
> - 唯一视频标识列是 **`video`**；时长是 **`duration`** 列（取值 `short`/`medium`/`long`）。
> - 想只测短视频，按 `duration == 'short'` 过滤列即可。

```python
import os, shutil
import numpy as np
import pandas as pd
from run_vlm import run_vlm

name = 'Video-MME'
original = os.path.expanduser(f'~/LMUData/{name}.tsv')
backup = os.path.expanduser(f'~/LMUData/{name}_FULL.tsv')
if not os.path.exists(backup):
    shutil.copy(original, backup)

df = pd.read_csv(backup, sep='\t')
print(f'[columns] {list(df.columns)}')

# 可选：只保留短视频（节省时间）。不需要就注释掉这两行。
if 'duration' in df.columns:
    df = df[df['duration'] == 'short']

# 1. 按唯一视频标识列抽样（列名优先 video，其次 video_path）
vid_col = 'video' if 'video' in df.columns else 'video_path'
unique_videos = df[vid_col].unique()

# 2. 随机抽 100 个视频（每个 3 题 → 约 300 题）
np.random.seed(42)
pick = np.random.choice(unique_videos, size=min(100, len(unique_videos)), replace=False)

# 3. 把这些视频的所有题完整挑出
sampled = df[df[vid_col].isin(pick)].sort_index()
sampled.to_csv(original, sep='\t', index=False)
print(f'✅ Video-MME: 抽中 {len(pick)} 个视频 → {len(sampled)} 题 (标识列={vid_col})')

run_vlm('Video-MME', video_llm=True)  # 名字不变，底层跑抽好的子集
```

> 还原全量：把 `~/LMUData/{name}_FULL.tsv` 覆盖回 `~/LMUData/{name}.tsv` 即可。

---

## 5. 数据集速查表

| 能力 | 数据集代号 | 题型 | 原集题量 | 分层维度 | 抽样方式 |
|---|---|---|---|---|---|
| 基础视力 | `MMBench_DEV_EN_V11` | 单选（A–D，circular 循环评测）| ~1164 | 能力类别（`category`） | 分层抽 ~500 |
| 实景理解 | `MME-RealWorld-Lite` | 单选（**5 选项** A–E）| ~2150 | 场景 / 任务类型 | 分层抽 ~500 |
| 极限推理 | `MMMU_Pro_10c` | 单选（**10 选项**，`10c` 即扩到 10 个候选）| ~1730 | 学科 / 子领域（`subject`） | 分层抽 ~500 |
| 视频理解 | `Video-MME` | 单选（A–D，每视频 3 题）| 2700（900 视频×3） | 视频时长（`duration`） | 按 `video` 抽 ~100 个视频（~300 题） |

> 题型来源（已核实）：[MME-RealWorld](https://github.com/MME-Benchmarks/MME-RealWorld)（5 选项）、[MMMU-Pro 论文](https://arxiv.org/pdf/2409.02813)（选项 4→10）、[Video-MME](https://github.com/MME-Benchmarks/Video-MME)（4 选项 A–D）；MMBench 为单选+circular 循环评测。**四个集全是单选题**——所以 `temperature=0`（贪心）最合适、可复现，无需大 `max_tokens`（模型只需吐出选项字母/短答）。

### 5.1 各数据集要传的专属参数

前三个是**图片集**，跑法一致、无专属参数；只有 `Video-MME` 是**视频集**，要额外开 `video_llm` 并可调帧/字幕参数。

| 数据集 | 类型 | 必传/专属参数 | 放在哪 |
|---|---|---|---|
| `MMBench_DEV_EN_V11` | 图片 | 无（`video_llm=False`，model 内 `temperature/max_tokens/img_size` 用默认即可） | model dict |
| `MME-RealWorld-Lite` | 图片 | 无（同上） | model dict |
| `MMMU_Pro_10c` | 图片 | 无（同上）。⚠️ 若换 COT 变体 `MMMU_Pro_10c_COT`，需把 `max_tokens` 调大（要输出思维链） | model dict |
| `Video-MME` | 视频 | **`video_llm=True`**（model dict）；可选 `nframe`（默 8）/ `fps`（默 -1，>0 时按帧率取帧，覆盖 nframe）/ `use_subtitle`（默 False）| `video_llm` 在 model dict；`nframe/fps/use_subtitle` 在 `eval_config` 顶层（与 `data/mode/limit/nproc` 同级，见 [vlmevalkit_backend.md](../../docs/zh/user_guides/backend/vlmevalkit_backend.md) 参数说明）|

> Video-MME 取帧示例（在 `run_vlm` 的 `eval_config` 顶层加）：`'nframe': 8`（默认）或 `'fps': 1`（按 1 帧/秒，长视频帧数随时长增多）；要带字幕设 `'use_subtitle': True`。这些只对视频集生效，图片集忽略。

> 运行前务必执行 0.1 的 `list_supported_datasets()` 核对本地 `ms-vlmeval` 版本是否包含上述名字。
