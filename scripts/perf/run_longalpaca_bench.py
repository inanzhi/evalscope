"""
单轮长文本(longalpaca)商业 API 性能基准测试入口脚本 (run_longalpaca_bench.py)

用途：横向对比不同商业大模型 API 的单轮推理性能，核心观测 TTFT(首字延迟) 和 TPOT(单 token 生成耗时)。
配套文档：notes/perf-commercial-apis/benchmark_strategy.md

设计目标：定时智能体只需运行一条命令即可，无需改代码。所有保证公平对比的"死规定"参数放在 FIXED 里，别动。

【为什么用 (厂商,模型) 双维度的 profile 而不是只传模型名】
    同一款模型常常在多家厂商都能跑(如 deepseek-v4-pro 在腾讯云和阿里云都有)。
    若输出目录/结果名只带模型名，两家厂商并发跑同一模型会落到同一路径 → 撞车
    (evalscope 发现 benchmark_data.db 已存在会直接退出)。
    因此这里用 "<model>_<vendor>" 作为 profile key，并据此拼 name 与输出目录，
    保证 (厂商,模型) 维度唯一，哪怕同一秒并发启动也不冲突。

【输出目录带 offset，支持同模型多次/多档并发】
    结果名拼成 longalpaca_<profile>_offset-<offset>，把数据游标也写进目录名。
    这样即便同一 profile 用不同 offset 复测、或多档并发，也各自独立不撞目录。

【同时跑多个模型】
    每个 profile 各跑一条命令即可并发，互不干扰(name 带 profile+offset 唯一)。例如:
        python scripts/perf/run_longalpaca_bench.py deepseek-v4-pro_aliyun 10
        python scripts/perf/run_longalpaca_bench.py deepseek-v4-pro_tencent 10
    两条可同时(两个终端或后台)启动，分别落到各自目录。

如何运行：
    python scripts/perf/run_longalpaca_bench.py                              # 用默认 profile ACTIVE
    python scripts/perf/run_longalpaca_bench.py deepseek-v4-pro_aliyun       # 指定 profile(模型_厂商)
    python scripts/perf/run_longalpaca_bench.py deepseek-v4-pro_aliyun 10    # 第2个参数覆盖 dataset_offset

【怎么加一个要测的模型】
    profile 名固定写成 "<模型名>_<厂商名>"，往下面的 PROFILES 列表加一行字符串即可。
    模型名/厂商/URL/Key 全自动推导：模型名 = 最后一个下划线之前那段，厂商 = 之后那段，
    URL 和 API Key 来自 run_perf_one.py 里集中维护的 VENDORS(填一次处处引用)。
    例如要测腾讯云的新模型 foo-bar，加一行 'foo-bar_tencent' 即可。

前置要求：
    - 厂商 URL 与 API Key 已在 run_perf_one.py 的 VENDORS 里填好(本脚本直接 import 复用，无需设环境变量)。
    - 已安装 evalscope，且本机能联通目标 API。

输出：
    每次运行落盘到 results/longalpaca/<时间戳>/longalpaca_<profile>_offset-<offset>/，目录内含
    benchmark.log、HTML 报告、以及各并发档(parallel_*/)的 benchmark_data.db。
    name 带厂商名 + offset，所以不同厂商跑同一模型、或同模型不同 offset 都各自独立、互不覆盖。
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # 确保能 import 同目录的 run_perf_one

from evalscope.perf.arguments import Arguments
from evalscope.perf.main import run_perf_benchmark
from run_perf_one import VENDORS  # 厂商 URL+Key 集中在 run_perf_one.py 填一次，这里复用同一份

# ============================================================================
# 1) 要测的 profile 清单。profile 名 = "<模型名>_<厂商名>"。
#    加模型 = 在这里加一行字符串即可；模型名/厂商/URL/Key 全自动推导(见 _resolve)。
#    厂商名(最后一个下划线之后那段)必须已在 run_perf_one.py 的 VENDORS 里登记。
# ============================================================================
ACTIVE = 'deepseek-v4-pro_aliyun'                                    # 默认跑哪个 profile

PROFILES = [
    'deepseek-v4-pro_aliyun',
    'deepseek-v4-pro_tencent',
    'deepseek-v4-flash_aliyun',
    'deepseek-v4-flash_tencent',
    'deepseek-v3.2_aliyun',
    'deepseek-v3.2_tencent',
]


def _resolve(profile):
    """把 profile 名("<模型名>_<厂商名>")拆成 (模型名, 厂商名, 厂商配置)。
    厂商名取最后一个下划线之后的部分，其余为模型名；URL / api_key 来自 VENDORS[厂商名]。"""
    if profile not in PROFILES:
        sys.exit(f"未知的 profile '{profile}'。请从以下选项中挑一个: {', '.join(PROFILES)}")
    model, _, vendor = profile.rpartition('_')
    if vendor not in VENDORS:
        sys.exit(f"profile '{profile}' 的厂商 '{vendor}' 没在 VENDORS 里登记。可选厂商: {', '.join(VENDORS)}")
    return model, vendor, VENDORS[vendor]

# ============================================================================
# 2) 控制变量法的核心地带 (FIXED) ———— 绝对禁止修改！
#    只有保证所有厂商/时段吃到的参数和数据一模一样，性能对比才有说服力。
#    【不传时 perf 内部默认 (Arguments)】temperature=0.0 / max_tokens=2048 / stream=True / total_timeout=6h;
#       top_p / top_k / seed / reasoning_effort 默认 None = 不发送, 由服务端自有默认决定。下面显式写出是为锁死可复现。
# ============================================================================
FIXED = dict(
    dataset='longalpaca',                           # 真实长文本语料(>6000 tokens)，不用 random 避免乱码触发 EOS
    dataset_offset=500,                             # 跳过前 500 条，杜绝服务端 KV-Cache 命中(复测可命令行覆盖)
    max_tokens=512,                                 # 强制截断天花板，拉齐各模型输出量级，保证 TPOT 公平
    temperature=0.0,                                # 采样温度；0=贪心(可复现)。要调就改这里
    top_p=1.0,                                      # 核采样；temperature=0 时为空操作，留作可调旋钮
    # extra_args={'reasoning_effort': 'high'},      # 深度思考档位(low/medium/high)；非原生字段，走 extra_args 注入请求体。仅推理模型可开，非推理模型开了会报错
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

    # 从 profile 名自动拆出 模型/厂商，并取出该厂商的 URL / Key
    model, vendor, v = _resolve(active)

    fixed = dict(FIXED)
    fixed['dataset_offset'] = offset

    run_name = f'longalpaca_{active}_offset-{offset}'   # active=<model>_<vendor>，再带 offset，保证 (厂商,模型,offset) 唯一
    task = Arguments(
        model=model,
        url=v['url'],
        api_key=v['api_key'],
        name=run_name,
        **fixed,
    )

    print(f"[run_longalpaca_bench] 准备发车！\n"
          f"profile={active} | 模型={model} | 厂商={vendor} | URL={v['url']} | 游标Offset={offset}\n"
          f"结果落盘根目录={fixed['outputs_dir']}/<时间戳>/{run_name}/")

    run_perf_benchmark(task)


if __name__ == '__main__':
    main()
