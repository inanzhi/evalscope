---
name: "evalscope-eval-compare"
description: "给定 url/api_key/模型名/厂商后缀，生成并顺序执行 cmmlu、humaneval_plus、longalpaca 与 SWE-Smith 多轮压测，再按模板生成 HTML 对比报告。当用户要跑多模型/多厂商效果+性能对比并出报告时调用。"
---

# EvalScope 模型评测 + 对比报告

一个 (模型 × 厂商) 条目只给 5 个字段：`url`、`api_key`、`model`、`vendor`、`label`，
本 skill 负责生成全部命令、**严格串行**执行、并在跑完后按模板生成 HTML 对比报告。

每个条目跑 4 条命令（默认 `--order benchmark` 按评测项维度跨条目执行、更利于对比公平；`--order model` 则按条目依次跑完）：

| 顺序 | 评测项 | 命令来源 | 产出 |
| --- | --- | --- | --- |
| 1 | cmmlu（知识） | `evalscope eval` | `outputs/<ts>/reports/<model_id>/cmmlu.json` |
| 2 | humaneval_plus（代码） | `evalscope eval`（Docker sandbox） | `outputs/<ts>/reports/<model_id>/humaneval_plus.json` |
| 3 | longalpaca（单轮长文本） | `evalscope perf` | `outputs/<ts>/longalpaca_<model_id>/parallel_*/benchmark_summary.json` |
| 4 | swe（多轮会话缓存） | `evalscope perf`（`--multi-turn`） | `outputs/<ts>/swe_<model_id>_offset-<N>_cache-<tag>/parallel_5_number_10/benchmark_summary.json` |

## 输入契约

每个条目 5 个字段（可一次多个条目，串行执行，顺序见 `--order`）。**`api_key` 是敏感信息：请让用户自己写进本地 YAML，不要让他贴到聊天里**；`model` / `vendor` / `label` / `url` 可由用户口头/聊天提供、agent 代填 YAML，`api_key` 留占位符待用户填。

| 字段 | 说明 | 示例 |
| --- | --- | --- |
| `model` | 模型名 | `glm-5.2` |
| `vendor` | 厂商后缀，拼出 `model_id = <model>_<vendor>` | `tencent` |
| `label` | 报告里"部署方式/厂商"显示名（可选，默认=vendor） | `腾讯云` |
| `url` | OpenAI 兼容 chat/completions 端点 | `https://.../v1/chat/completions` |
| `api_key` | 该端点 API Key（**仅写入本地 YAML**） | `sk-xxx` |

## 配置文件

**做法：复制 [config.example.yaml](config.example.yaml) 的完整内容到仓库根目录，命名 `credentials.yaml`，只改 `models` 列表。** `defaults` 保持原样、别删——它含温度/思考/并发等四项测试的全部固定参数，删了会导致命令参数不完整。

`--config` 接受任意路径，放哪都行；约定放根目录 `credentials.yaml`。一个 `models` 条目 = 一个 (模型 × 厂商)，多个模型就写多条：

```yaml
models:
  - model: glm-5.2
    vendor: tencent
    label: 腾讯云
    url: https://tokenhub.tencentmaas.com/v1/chat/completions
    api_key: sk-你填这里

  - model: glm-5.2
    vendor: aliyun-juyunkeji
    label: 阿里云-矩云科技
    url: https://ws-fv27.../compatible-mode/v1/chat/completions
    api_key: sk-你填这里
```

- `api_key` 自己填、别贴聊天；`credentials.yaml` 已在 `.gitignore`，不会进 git。
- cmmlu 默认 `limit: 50`（每子集 50、共 3350 样本）；想全量跑改成 `null`。注意：cmmlu 的 `limit` 是「每个学科子集」的样本数（共 67 个子集），`50` 不是总共 50 个。

## 环境准备

本项目用 `.venv` 虚拟环境。合并上游后可能新增依赖（如 `filetype`、`rich`），先补齐并确认：

```bash
.venv\Scripts\python.exe -m pip install -e ".[perf]"
.venv\Scripts\evalscope --version   # 能打印版本号即 OK
```

下面的命令优先用 `.venv`：先激活（`.venv\Scripts\activate`）或用绝对路径；runner 也可加 `--cmd .venv/Scripts/evalscope` 直接指定。

## 执行流程

1. 按上方「配置文件」写好 `credentials.yaml`。
2. 先 dry-run 确认生成的命令无误：
   ```bash
   python .trae/skills/evalscope-eval-compare/run_eval_compare.py --config credentials.yaml --dry-run
   ```
3. 正式跑（耗时较长，用**非阻塞长任务**启动，再 `CheckCommandStatus` 轮询）：
   ```bash
   python .trae/skills/evalscope-eval-compare/run_eval_compare.py --config credentials.yaml
   ```
   - 每条命令实时打印并落盘到 `logs/eval-compare/<model_id>_<bench>.log`。
   - 每跑完一条把产物路径记进 `runs_manifest.json`（支持 `--force` 重跑、断点续跑跳过已完成项）。
4. 全部跑完后生成报告：
   ```bash
   python .trae/skills/evalscope-eval-compare/generate_report.py --manifest runs_manifest.json
   ```
   报告默认写到 `outputs/<model>_<vendorA>_vs_<vendorB>_comparison_report_<YYYYMMDD>.html`，
   样式沿用 `outputs/glm-5.2_aliyun_vs_huoshan_comparison_report_20260828.html`。

## 命令参数

`run_eval_compare.py`：

| 参数 | 默认 | 说明 |
| --- | --- | --- |
| `--config` | 必填 | YAML 配置路径 |
| `--cmd` | `evalscope` | 基础命令；用 `.venv` 时设为 `.venv/Scripts/evalscope`（Windows） |
| `--dry-run` | 关 | 只打印命令不执行 |
| `--force` | 关 | 强制重跑已完成的项 |
| `--order` | `benchmark` | 执行顺序：`benchmark`=按评测项逐个跑所有模型（对比更公平）；`model`=按模型逐个跑完所有评测项（旧行为） |
| `--only` / `--skip` | 全部 | 按模型名过滤 |
| `--manifest` | `runs_manifest.json` | 产物路径清单输出 |
| `--log-dir` | `logs/eval-compare` | 每条日志目录 |

`generate_report.py`：

| 参数 | 默认 | 说明 |
| --- | --- | --- |
| `--manifest` | `runs_manifest.json` | 读取的产物路径清单 |
| `--output` | 自动 | 覆盖输出 HTML 路径 |

## YAML schema 要点

- `defaults` 下分 `cmmlu` / `humaneval_plus` / `longalpaca` / `swe` 四段共享默认，单条目可整段或单字段覆盖。
- 关键差异参数（模型相关，别写死）：
  - `cmmlu.generation_config.extra_body`（如 glm-5.2 用 `thinking: {type: disabled}`）
  - `humaneval_plus.generation_config.extra_body`（如 `reasoning_effort: low`）
  - `longalpaca.extra_args`（注入请求体的非原生字段）
  - `cmmlu.limit`：**每个学科子集**的样本数（cmmlu 共 67 个子集）。默认 `50` = 每子集 50、共 3350 个样本；`null`/省略 = 每子集全量。
- `swe.dataset_offset` 默认 `10`、`swe.session_cache` 默认 `off`（`on` → 加 `--multi-turn-session-cache`）。
- `swe.dataset_path` 默认 `auto`：`dataset_offset==0` 用 `outputs/agentic_dataset.json`，否则 `outputs/agentic_pool.json`。
- **推理模型限长（可选）**：默认都用 `max_tokens`。想连 reasoning 一起限长：`swe` / `longalpaca`（perf）可改用 `max_completion_tokens`（优先于 `max_tokens`）；`cmmlu` / `humaneval_plus`（eval）没有该字段，改在 `generation_config.extra_body` 里写 `max_completion_tokens`、同时删掉顶层 `max_tokens`。配置模板里已留注释示例。

## 目录结构

所有结果统一落在 `outputs/` 下，框架自动加时间戳、防撞交给框架，`--name` 一次编码身份：

```
outputs/
  <ts>/reports/<model_id>/cmmlu.json
  <ts>/reports/<model_id>/humaneval_plus.json
  <ts>/longalpaca_<model_id>/parallel_1_number_20/...
  <ts>/swe_<model_id>_offset-10_cache-off/parallel_5_number_10/...
```

报告生成器读的是 `runs_manifest.json` 里记好的路径，不依赖具体目录名；四段按"有无数据"自动取舍。

## 注意事项

- **密钥安全**：`api_key` 只应写在本地 YAML 里，不要贴进聊天、不要写进 SKILL/仓库；runner 的 dry-run / 运行头 / 日志里 `--api-key` 已打码为 `***`、不落明文；报告也不展示密钥与 URL。
- humaneval_plus 依赖 Docker sandbox，跑前确认本机 Docker 可用。
- 报告四段（LongAlpaca / SWE-Smith / CMMLU / HumanEval）按"有无数据"自动取舍，某条失败不影响其它段渲染。
