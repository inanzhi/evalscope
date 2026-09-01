---
name: "evalscope-perf-batch"
description: "从 YAML 密钥配置文件批量运行 `evalscope perf`，依次跑多个模型/厂商的性能压测。当用户想用一份配置文件顺序跑多个模型的 perf 基准时调用。"
---

# EvalScope Perf 批量压测器

一次为多个模型 / 厂商运行 `evalscope perf`。每个模型的 `--model`、`--url`、
`--api-key`、`--name`（以及任意可选覆盖项）都来自同一个 YAML 文件；其余压测参数
为共享默认值。运行严格串行，每次运行的输出同时**实时打印到控制台**并**落盘到
各自的日志文件**。

## 快速开始

> 环境：本项目用 `.venv` 虚拟环境。合并上游后可能新增依赖，先 `.venv\Scripts\python.exe -m pip install -e ".[perf]"`；跑命令前先激活 `.venv`（`.venv\Scripts\activate`）或用绝对路径。

1. 按下方 schema 写一个密钥 YAML 文件。因含明文 API Key，请**不要纳入版本控制**
   （加入 `.gitignore`）。

2. 先 dry-run 确认生成的命令无误：

   ```bash
   python .trae/skills/evalscope-perf-batch/run_perf_batch.py --creds credentials.yaml --dry-run
   ```

3. 正式批量跑（耗时较长，按长任务运行并轮询状态）：

   ```bash
   python .trae/skills/evalscope-perf-batch/run_perf_batch.py --creds credentials.yaml
   ```

## 命令行参数

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `--creds` | （必填） | YAML 配置文件路径。 |
| `--cmd` | `evalscope` | 基础 evalscope 命令；用 `.venv` 时设为 `.venv/Scripts/evalscope`（Windows）。 |
| `--dry-run` | 关 | 只打印生成的命令、不实际执行。 |
| `--only` | （全部） | 逗号分隔的模型名，只跑这些、跳过其余。 |
| `--skip` | （无） | 逗号分隔的模型名，跳过这些。 |
| `--log-dir` | `logs/perf-batch` | 每次运行 `.log` 日志的存放目录。 |
| `--stop-on-error` | 关 | 首次失败即停止（默认：继续跑下一个模型）。 |

## YAML schema

```yaml
# 共享默认值，每条模型都可被单条覆盖。
defaults:
  dataset: longalpaca
  dataset_offset: 500
  max_tokens: 512                 # 整数，或 [min, max] 做均匀采样
  parallel: [1, 8, 16]            # nargs='+' — 每个值一轮 sweep
  number: [20, 80, 160]           # 长度必须与 parallel 一致
  temperature: 0
  top_p: 1.0
  extra_args:                      # 以 JSON 注入请求体
    thinking:
      type: enabled
  stream: true                    # -> --stream（用 false 即 --no-stream）
  warmup_num: 2
  read_timeout: 300

# 每条一个模型。只有 model / url / api_key 必填。
# name 省略时自动生成为 "<dataset>_<model>"。
# defaults 里的任意字段都可在单条中覆盖。
models:
  - model: glm-5.2
    url: https://tokenhub.tencentmaas.com/v1/chat/completions
    api_key: sk-xxxxxxxxxxxx
    name: "longalpaca_glm-5.2_腾讯云"

  - model: kimi-k2.6
    url: https://tokenhub.tencentmaas.com/v1/chat/completions
    api_key: sk-xxxxxxxxxxxx
    name: "longalpaca_kimi-k2.6_腾讯云"

  - model: deepseek-v4-flash
    url: https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions
    api_key: sk-yyyyyyyyyyyy
    name: "longalpaca_deepseek-v4-flash_阿里云"
    extra_args:                    # 覆盖该模型的 defaults.extra_args
      reasoning_effort: high
```

### 支持的覆盖字段

`dataset`, `dataset_offset`, `max_tokens`, `parallel`, `number`, `rate`,
`temperature`, `top_p`, `top_k`, `seed`, `warmup_num`, `read_timeout`,
`connect_timeout`, `total_timeout`, `outputs_dir`, `api`,
`max_prompt_length`, `min_prompt_length`, `prompt`, `query_template`,
`extra_args`, `stream`, `no_timestamp`, `no_test_connection`, `open_loop`,
`debug`, `name`。

> 提示：对**非推理模型**，在该条目里写 `extra_args: null`（或 `{}`），即可去掉从
> defaults 继承的 thinking / reasoning 注入。

## Agent 执行流程

当本 skill 被触发时：

1. 获取用户的密钥 YAML 路径；若还没有，按上方 schema 提供模板并帮其创建。
2. 先跑一次 `--dry-run`，把生成的命令展示给用户确认。
3. 以**长任务 / 非阻塞**方式启动正式批量跑（每次 `evalscope perf` 可能耗时数分钟
   到数小时）。用 `CheckCommandStatus` 轮询而非阻塞，并把每次运行的日志路径告诉
   用户以便跟进进度。
4. 批量跑完后，汇报汇总表（每个模型的成功 / 失败与耗时）。
