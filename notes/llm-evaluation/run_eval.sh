#!/bin/bash

# =======================================================
# LLM 极简均衡测试执行脚本 (EvalScope 原生后端)
# 请在运行前替换下方的模型名称和 API 配置
# =======================================================

MODEL_NAME="deepseek-v4-pro"
API_URL="https://dashscope.aliyuncs.com/compatible-mode/v1" # 替换为实际供应商 API URL
API_KEY="YOUR_API_KEY" # 替换为实际 API KEY

# --- 生成参数(可自行修改) -------------------------------------------------
# 全部经 --generation-config 下发(native 后端唯一入口); 键名见 generate_config.py
# 【不传 --generation-config 时内部默认(API评测)】仅注入 temperature=0.0; top_p/max_tokens/seed/reasoning_effort 不发,走服务端默认;
#   retries=5/retry_interval=10。⚠️ 一旦传了 --generation-config 就整体替换、不合并, 所以必须把 temperature 一起带上(见下方拼接)。
TEMPERATURE=0          # 采样温度; 0=贪心(可复现)。accuracy 评测建议 0
TOP_P=1.0              # 核采样; temperature=0 时为空操作, 留作可调旋钮
REASONING_EFFORT="high"    # 思考档位 low/medium/high; 留空=不传。仅推理模型可设, Qwen2.5 等非推理模型设了会报错
# 拼出 generation-config: REASONING_EFFORT 非空时才追加 reasoning_effort 段
GEN_CONFIG="temperature=${TEMPERATURE},top_p=${TOP_P},timeout=60${REASONING_EFFORT:+,reasoning_effort=${REASONING_EFFORT}}"

echo "======================================================="
echo "🚀 开始测试 CMMLU (每科 50 题, 自动 3350 题) ..."
echo "======================================================="
# --limit 按学科 (subset) 逐个生效: 67 学科 × 50 = 3350 题, 无需任何抽样脚本
# --eval-batch-size 并发请求数: 默认 1(单并发), 商业 API 报 429 就调小
# --generation-config timeout=60: 单次请求超时 60s (重试次数默认 5、间隔 10s)
# --ignore-errors: 某条样本重试耗尽仍失败就跳过, 不中断整场评测
evalscope eval \
  --model "$MODEL_NAME" \
  --api-url "$API_URL" \
  --api-key "$API_KEY" \
  --datasets cmmlu \
  --limit 50 \
  --eval-batch-size 16 \
  --generation-config "$GEN_CONFIG" \
  --ignore-errors

echo ""
echo "======================================================="
echo "🚀 开始测试 HumanEvalPlus (全量 164 题) ..."
echo "======================================================="
# humaneval_plus 默认在本地执行生成代码, 建议开 Docker 沙盒
# 沙盒会并行起多个 docker, 本地核少就把 --eval-batch-size 调小
evalscope eval \
  --model "$MODEL_NAME" \
  --api-url "$API_URL" \
  --api-key "$API_KEY" \
  --datasets humaneval_plus \
  --sandbox '{"enabled": true, "engine": "docker"}' \
  --eval-batch-size 8 \
  --generation-config "$GEN_CONFIG" \
  --ignore-errors

echo "✅ 所有测试执行完毕！"
