"""
单次运行多轮对话 KV 缓存命中率压测的专属脚本 (run_perf_one.py)

设计目标：为了让你在切换测试不同厂商或模型时，只需要修改且仅修改一行代码（下方的 `ACTIVE`）。
所有为了保证跨模型公平对比的“死规定”参数都放在了 `FIXED` 里面，绝对不能动。

配套文档：请参阅 notes/perf-multi-turn-cache/cache_strategy.md

如何运行：
    python scripts/perf/run_perf_one.py
无需改代码，通过命令行直接覆盖要测的模型（推荐）：
    python scripts/perf/run_perf_one.py v32-bailian
    python scripts/perf/run_perf_one.py v32-bailian 10   # 第2个参数传 dataset_offset (防缓存污染复测专用)

关于防缓存作弊的数据集自动切换逻辑：
    - offset == 0 -> 自动使用 `outputs/agentic_dataset.json` (小池子, 10条对话) -> 落盘到 `results/<profile>`
                     这是为了横向对比不同厂商/模型（大家第一把都用这个保证绝对公平）。
    - offset > 0  -> 自动使用 `outputs/agentic_pool.json` (万级大池子) -> 落盘到 `results/<profile>-off<N>`
                     这是为了【复测同一个模型】，每次传不同的 offset 取完全不重叠的 10 条数据，防止第一把的残留缓存导致命中率虚高。
"""

import os
import sys
from datetime import datetime

from evalscope.perf.arguments import Arguments
from evalscope.perf.main import run_perf_benchmark

# ============================================================================
# 1) 唯一需要改动的地方：指定本次压测要跑哪个模型/厂商组合
# ============================================================================
ACTIVE = 'v32-bailian'

# ============================================================================
# 2) 厂商与模型配置字典库 (Profiles)
#    如果要测新模型，直接在这里加一项。
#    - `session_cache=True`: 仅对腾讯云等需要显式靠 `X-Session-ID` 路由来复用缓存的厂商开启。
#                            阿里百炼是隐式自动缓存，不需要这个注入功能，设为 False。
#    - `api_key_env`: 这里只配环境变量名，千万不要把真实的 API Key 硬编码写在代码里！
# ============================================================================
PROFILES = {
    'v32-tencent': dict(
        model='deepseek-v3.2',
        url='https://tokenhub.tencentmaas.com/v1/chat/completions',
        api_key_env='TENCENT_API_KEY',
        session_cache=True,
    ),
    'v32-bailian': dict(
        model='glm-5',
        url='https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions',
        api_key_env='DASHSCOPE_API_KEY',
        session_cache=False,
    ),
    'v4pro-tencent': dict(
        model='deepseek-v4-pro',
        url='https://tokenhub.tencentmaas.com/v1/chat/completions',
        api_key_env='TENCENT_API_KEY',
        session_cache=True,
    ),
    'v4flash-tencent': dict(
        model='deepseek-v4-flash',
        url='https://tokenhub.tencentmaas.com/v1/chat/completions',
        api_key_env='TENCENT_API_KEY',
        session_cache=True,
    ),
}

# 数据集双轨制（由下面的 offset 自动决定用哪个）
#   offset == 0  -> 跨模型横向对比，用标准小集 (10条对话)
#   offset >  0  -> 复测同模型，用大池子抽完全不重叠的子集，杜绝服务端缓存作弊
COMPARE_DATASET = 'outputs/agentic_dataset.json'
POOL_DATASET = 'outputs/agentic_pool.json'

# ============================================================================
# 3) 控制变量法的核心地带 (FIXED) ———— 绝对禁止修改！
#    只有保证所有厂商吃到的参数和数据一模一样，性能对比才有说服力。
# ============================================================================
FIXED = dict(
    api='openai',                                   # 必须是 openai 兼容模式，才能保住咱们的特殊请求体注入
    dataset='swe_smith',
    multi_turn=True,                                # 开启多轮压测
    parallel=1,                                     # 单线程顺序发包（测单点极致缓存性能）
    number=10,                                      # 每次只跑 10 条独立的对话 Session
    max_tokens=16384,                               # 配合长文本自然截断，不用商业模型不支持的 ignore_eos
    seed=42,                                        # 锁死随机种子
    temperature=0.0,
    stream=True,                                    # 必须开启流式，否则算不出首字延迟 TTFT
    extra_args={'reasoning_effort': 'high'},        # 开启深度思考模式，云厂商都认这个字段
    read_timeout=300,                               # 读超时 300s：reasoning=high 单轮常需数十秒~分钟，60s 会误杀
    no_test_connection=True,
    no_timestamp=True,
)


def main():
    # 命令行参数覆盖逻辑：
    # argv[1] = 你要测的 profile 名字
    # argv[2] = 你要指定的 offset 游标（用于防缓存污染复测）
    active = sys.argv[1] if len(sys.argv) > 1 else ACTIVE
    offset = int(sys.argv[2]) if len(sys.argv) > 2 else 0

    if active not in PROFILES:
        sys.exit(f"未知的模型配置 '{active}'。请从以下选项中挑一个: {', '.join(PROFILES)}")
    p = PROFILES[active]

    # 从环境变量里取 API Key
    api_key = os.environ.get(p['api_key_env'])
    if not api_key:
        sys.exit(f"没找到环境变量 {p['api_key_env']} (跑 '{active}' 必须要有这个配置)。")

    # 根据 offset 决定数据源和输出目录
    # 如果 offset == 0，说明是初测，走标准比对集
    # 如果 offset > 0，说明是复测，走大池子，并且目录带上 off<N> 防止覆盖上一次的结果
    if offset > 0:
        dataset_path = POOL_DATASET
        outputs_dir = f'results/{active}-off{offset}'
    else:
        dataset_path = COMPARE_DATASET
        outputs_dir = f'results/{active}'

    if not os.path.exists(dataset_path):
        sys.exit(f"找不到数据集文件: {dataset_path} (请先看文档把数据生成出来)。")

    # EvalScope 框架遇到已有的 SQLite 数据库会拒绝覆写并报错退出。
    # 为了防止你反复跑同个命令时程序崩溃，如果发现目录已经存在了，
    # 就自动在目录名后面加一个当前时间戳，保持干净独立。
    if os.path.isdir(outputs_dir):
        outputs_dir = f"{outputs_dir}-{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    # 拼装最终传给底层的参数对象
    task = Arguments(
        model=p['model'],
        url=p['url'],
        api_key=api_key,
        name=active,                                  # profile 名(含厂商)做结果库名：同模型跨厂商也唯一，不撞
        multi_turn_session_cache=p['session_cache'],  # 最关键的 Session 缓存路由隔离注入开关
        dataset_path=dataset_path,
        outputs_dir=outputs_dir,
        dataset_offset=offset,
        **FIXED,                                      # 把上面的不可变参数强塞进来
    )

    print(f"[run_perf_one] 准备发车！\n"
          f"配置={active} | 模型={p['model']} | 腾讯云Session注入={p['session_cache']} | 游标Offset={offset}\n"
          f"数据源={dataset_path} -> 结果存放至={outputs_dir}")
    
    # 拉起框架正式开跑
    run_perf_benchmark(task)


if __name__ == '__main__':
    main()
