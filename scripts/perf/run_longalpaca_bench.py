"""
单轮长文本(longalpaca)商业 API 性能基准测试入口脚本 (run_longalpaca_bench.py)

用途：横向对比不同商业大模型 API 的单轮推理性能，核心观测 TTFT(首字延迟) 和 TPOT(单 token 生成耗时)。
配套文档：notes/perf-commercial-apis/benchmark_strategy.md

设计目标：定时智能体只需运行一条命令即可，无需改代码。所有保证公平对比的"死规定"参数放在 FIXED 里，别动。

【为什么用 (厂商,模型) 双维度的 profile 而不是只传模型名】
    同一款模型常常在多家厂商都能跑(如 deepseek-v3.2 在腾讯云和阿里百炼都有)。
    若输出目录/结果名只带模型名，两家厂商并发跑同一模型会落到同一路径 → 撞车
    (evalscope 发现 benchmark_data.db 已存在会直接退出)。
    因此这里用 "<model>-<vendor>" 作为 profile key，并据此拼 name 与输出目录，
    保证 (厂商,模型) 维度唯一，哪怕同一秒并发启动也不冲突。

如何运行：
    python scripts/perf/run_longalpaca_bench.py                                # 用默认 profile ACTIVE
    python scripts/perf/run_longalpaca_bench.py deepseek-v4-flash-bailian      # 指定 profile(模型-厂商)
    python scripts/perf/run_longalpaca_bench.py deepseek-v4-flash-bailian 600  # 第2个参数覆盖 dataset_offset

前置要求：
    - 对应厂商的 API Key 环境变量已设置(见各 profile 的 api_key_env)。
    - 已安装 evalscope，且本机能联通目标 API。

输出：
    每次运行落盘到 results/longalpaca/<时间戳>/longalpaca_<profile>/，目录内含
    benchmark.log、HTML 报告、以及各并发档(parallel_*/)的 benchmark_data.db。
    profile 里带了厂商名，所以不同厂商跑同一模型也各自独立、互不覆盖。
"""

import os
import sys

from evalscope.perf.arguments import Arguments
from evalscope.perf.main import run_perf_benchmark

# ============================================================================
# 1) 厂商 × 模型配置库 (Profiles)
#    key 用 "<model>-<vendor>"，会直接进结果名和输出目录，保证 (厂商,模型) 唯一。
#    测新组合就在这里加一项；api_key_env 只配环境变量名，千万别硬编码真实 key！
# ============================================================================
ACTIVE = 'deepseek-v4-flash-bailian'                                 # 默认跑哪个 profile

PROFILES = {
    'deepseek-v4-flash-bailian': dict(
        vendor='bailian',
        model='deepseek-v4-flash',
        url='https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions',
        api_key_env='DASHSCOPE_API_KEY',
    ),
    'deepseek-v4-flash-tencent': dict(
        vendor='tencent',
        model='deepseek-v4-flash',
        url='https://tokenhub.tencentmaas.com/v1/chat/completions',
        api_key_env='TENCENT_API_KEY',
    ),
    'deepseek-v3.2-bailian': dict(
        vendor='bailian',
        model='deepseek-v3.2',
        url='https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions',
        api_key_env='DASHSCOPE_API_KEY',
    ),
    'deepseek-v3.2-tencent': dict(
        vendor='tencent',
        model='deepseek-v3.2',
        url='https://tokenhub.tencentmaas.com/v1/chat/completions',
        api_key_env='TENCENT_API_KEY',
    ),
}

# ============================================================================
# 2) 控制变量法的核心地带 (FIXED) ———— 绝对禁止修改！
#    只有保证所有厂商/时段吃到的参数和数据一模一样，性能对比才有说服力。
# ============================================================================
FIXED = dict(
    dataset='longalpaca',                           # 真实长文本语料(>6000 tokens)，不用 random 避免乱码触发 EOS
    dataset_offset=500,                             # 跳过前 500 条，杜绝服务端 KV-Cache 命中(复测可命令行覆盖)
    max_tokens=512,                                 # 强制截断天花板，拉齐各模型输出量级，保证 TPOT 公平
    parallel=[1, 8, 16],                            # 并发梯队：单点极限速度 / 8 并发 / 16 并发吞吐
    number=[20, 80, 160],                           # 各梯队总请求量；梯队间数据也不重复
    stream=True,                                    # 必须开启流式，否则算不出首字延迟 TTFT
    warmup_num=2,                                    # 预热 2 条排除冷启动，不计入报告
    read_timeout=300,                               # 读超时 300s：长上下文 prefill 慢，给足余量；perf 不自动重试
    outputs_dir='results/longalpaca',               # 根输出目录(框架会自动追加时间戳子目录)
)


def main():
    # 命令行参数覆盖：argv[1]=profile 名，argv[2]=dataset_offset(复测防缓存污染用)
    active = sys.argv[1] if len(sys.argv) > 1 else ACTIVE
    offset = int(sys.argv[2]) if len(sys.argv) > 2 else FIXED['dataset_offset']

    if active not in PROFILES:
        sys.exit(f"未知的 profile '{active}'。请从以下选项中挑一个: {', '.join(PROFILES)}")
    p = PROFILES[active]

    api_key = os.environ.get(p['api_key_env'])
    if not api_key:
        sys.exit(f"没找到环境变量 {p['api_key_env']}(跑 '{active}' 必须先设置好这个 API Key)。")

    fixed = dict(FIXED)
    fixed['dataset_offset'] = offset

    task = Arguments(
        model=p['model'],
        url=p['url'],
        api_key=api_key,
        name=f'longalpaca_{active}',                # active=<model>-<vendor>，进结果名/输出子目录，保证 (厂商,模型) 唯一
        **fixed,
    )

    print(f"[run_longalpaca_bench] 准备发车！\n"
          f"profile={active} | 模型={p['model']} | 厂商={p['vendor']} | URL={p['url']} | 游标Offset={offset}\n"
          f"结果落盘根目录={fixed['outputs_dir']}/<时间戳>/longalpaca_{active}/")

    run_perf_benchmark(task)


if __name__ == '__main__':
    main()
