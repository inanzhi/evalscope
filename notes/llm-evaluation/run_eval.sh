#!/bin/bash

# =======================================================
# LLM 极简均衡测试执行脚本 (EvalScope 原生后端)
# 请在运行前替换下方的模型名称和 API 配置
# =======================================================

MODEL_NAME="qwen/Qwen2.5-72B-Instruct"
API_URL="https://dashscope.aliyuncs.com/compatible-mode/v1" # 替换为实际供应商 API URL
API_KEY="YOUR_API_KEY" # 替换为实际 API KEY

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
  --generation-config timeout=60 \
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
  --generation-config timeout=60 \
  --ignore-errors

echo "✅ 所有测试执行完毕！"
