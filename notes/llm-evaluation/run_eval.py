from evalscope import run_task, TaskConfig

# =======================================================
# LLM 极简均衡测试执行脚本 (EvalScope 原生后端)
#   - CMMLU: 每个学科取 50 题 (--limit 按 subset 生效 → 67×50 = 3350)
#   - HumanEvalPlus: 全量 164 题, 建议开 Docker 沙盒执行生成代码
# 关键: 用 TaskConfig 的扁平字段 (model/api_url/api_key/datasets/limit),
#       不要用 eval_backend='OpenCompass' 那套嵌套 eval_config.
# =======================================================


def eval_one_vendor(model_name: str, api_url: str, api_key: str):
    # 单次请求超时 60s; retries/retry_interval 沿用默认 5 次 / 10s
    gen_cfg = {'timeout': 60}

    # ---- CMMLU 微缩版: 每科 50 题, 自动 3350 题, 可复现 ----
    run_task(TaskConfig(
        model=model_name,
        api_url=api_url,
        api_key=api_key,
        datasets=['cmmlu'],
        limit=50,  # 按学科逐个生效, 非全局前 50
        eval_batch_size=16,  # 并发请求数; 默认 1(单并发), 商业 API 报 429 就调小
        generation_config=gen_cfg,
        ignore_errors=True,  # 某条样本重试耗尽仍失败就跳过, 不中断整场评测
    ))

    # ---- HumanEvalPlus: 全量 164 题 (不加 limit), 开沙盒执行代码 ----
    run_task(TaskConfig(
        model=model_name,
        api_url=api_url,
        api_key=api_key,
        datasets=['humaneval_plus'],
        sandbox={'enabled': True, 'engine': 'docker'},
        eval_batch_size=8,  # 沙盒会并行起多个 docker, 本地核少就调小
        generation_config=gen_cfg,
        ignore_errors=True,
    ))


def main():
    # 替换为你要测试的模型和 API 配置
    model_name = 'qwen/Qwen2.5-72B-Instruct'
    api_url = 'https://dashscope.aliyuncs.com/compatible-mode/v1'
    api_key = 'YOUR_API_KEY'

    print('🚀 开始运行 CMMLU 和 HumanEvalPlus 评测...')
    eval_one_vendor(model_name, api_url, api_key)
    print('✅ 评测任务执行完毕！')


if __name__ == '__main__':
    main()
