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
                'temperature': 0.0,
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

> VLMEvalKit 后端**没有**顶层的 per-request 超时参数，超时沿用 VLMEvalKit 默认（由其底层 API wrapper 控制），故本方案不显式设 timeout。

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

| 能力 | 数据集代号 | 原集题量 | 分层维度 | 抽样方式 |
|---|---|---|---|---|
| 基础视力 | `MMBench_DEV_EN_V11` | ~1164 | 能力类别（`category`） | 分层抽 ~500 |
| 实景理解 | `MME-RealWorld-Lite` | ~2150 | 场景 / 任务类型 | 分层抽 ~500 |
| 极限推理 | `MMMU_Pro_10c` | ~1730 | 学科 / 子领域（`subject`） | 分层抽 ~500 |
| 视频理解 | `Video-MME` | 2700（900 视频×3） | 视频时长（`duration`） | 按 `video` 抽 ~100 个视频（~300 题） |

> 运行前务必执行 0.1 的 `list_supported_datasets()` 核对本地 `ms-vlmeval` 版本是否包含上述名字。
