from evalscope import run_task, TaskConfig

# =======================================================
# LLM 极简均衡测试执行脚本 (EvalScope 原生后端)
#   - CMMLU: 每个学科取 50 题 (--limit 按 subset 生效 → 67×50 = 3350)
#   - HumanEvalPlus: 全量 164 题, 建议开 Docker 沙盒执行生成代码
# 关键: 用 TaskConfig 的扁平字段 (model/api_url/api_key/datasets/limit),
#       不要用 eval_backend='OpenCompass' 那套嵌套 eval_config.
# =======================================================


def eval_one_vendor(model_name: str, api_url: str, api_key: str):
    # 生成参数(可自行修改); 键名见 evalscope/api/model/generate_config.py
    #   单次请求超时 60s; retries/retry_interval 收紧为 3 次 / 5s(见下方"嵌套重试坑")
    # 【不传 generation_config 时内部默认(API评测)】仅注入 temperature=0.0; top_p/max_tokens/seed/reasoning_effort 不发,走服务端默认。
    #   ⚠️ 一旦传 generation_config 就整体替换、不合并, 必须把 temperature 一起带上。
    gen_cfg = {
        'temperature': 0,      # 采样温度; 0=贪心(可复现)
        'top_p': 1.0,          # 核采样; temperature=0 时为空操作, 留作可调旋钮
        # 'reasoning_effort': 'high',  # 思考档位 low/medium/high; 仅推理模型可开, Qwen2.5 等非推理模型开了会报错
        'timeout': 60,         # 单次请求超时(秒); 超时本身会触发重试
        'retries': 3,          # 外层重试次数(默认5); 配合 max_retries=0 避免尾部样本长时间假死
        'retry_interval': 5,   # 重试间隔(秒, 默认10)
    }

    # ⚠️ 嵌套重试坑(最后一题"卡死"的根因): OpenAI SDK 客户端自带 max_retries(默认2),
    #   会在 evalscope 外层 retries 之外, 再对 超时/429/5xx 重试一遍, 二者相乘:
    #       最坏耗时 ≈ retries × (1 + max_retries) × timeout = 5×3×60s ≈ 15 分钟。
    #   并发池跑到只剩最后 1 题时没有别的请求掩盖它, 进度条死停在 N-1/N 像卡死;
    #   阿里云(DashScope)限并发时把尾部请求挂队列(而非秒回 429), 最易反复 60s 超时触发整条阶梯。
    #   model_args 会透传给 OpenAI(**model_args)(见 evalscope/models/openai_compatible.py:62),
    #   设 max_retries=0 关掉内层重试, 只保留 evalscope 外层 retries → 最坏降到 3×60s。
    client_args = {'max_retries': 0}

    # ---- CMMLU 微缩版: 每科 50 题, 自动 3350 题, 可复现 ----
    run_task(TaskConfig(
        model=model_name,
        api_url=api_url,
        api_key=api_key,
        datasets=['cmmlu'],
        limit=50,  # 按学科逐个生效, 非全局前 50
        eval_batch_size=16,  # 并发请求数; 默认 1(单并发), 商业 API 报 429 就调小
        generation_config=gen_cfg,
        model_args=client_args,  # 关掉 OpenAI SDK 内层重试, 避免重试套重试
        ignore_errors=True,  # 某条样本重试耗尽仍失败就跳过, 不中断整场评测
    ))

    # ---- HumanEvalPlus: 全量 164 题 (不加 limit), 开沙盒执行代码 ----
    #   review_timeout: 单条样本「沙盒执行代码」的超时(秒), humaneval_plus 默认 300
    #     (humanevalplus_adapter.py:61)。这是沙盒侧硬超时(实际 review_timeout+10 秒强制中断,
    #     见 sandbox_mixin.py:148), 与上面 API 的 timeout 是两套、互不影响。
    #   模型若吐出死循环代码, 不调小会让最后一题卡到 ~5 分钟(默认300+10); HumanEval 题计算量小、
    #     正确解通常 <10s, 设 60 既兜底死循环又不误杀慢解。dataset_args 经 registry._update→setattr 覆盖默认。
    run_task(TaskConfig(
        model=model_name,
        api_url=api_url,
        api_key=api_key,
        datasets=['humaneval_plus'],
        sandbox={'enabled': True, 'engine': 'docker'},
        dataset_args={'humaneval_plus': {'review_timeout': 60}},  # 沙盒执行超时(秒), 默认300
        eval_batch_size=8,  # 沙盒会并行起多个 docker, 本地核少就调小
        generation_config=gen_cfg,
        model_args=client_args,
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
