"""
单次运行多轮对话 KV 缓存命中率压测的专属脚本 (run_perf_one.py)

设计目标：为了让你在切换测试不同厂商或模型时，只需要修改且仅修改一行代码（下方的 `ACTIVE`）。
所有为了保证跨模型公平对比的“死规定”参数都放在了 `FIXED` 里面，绝对不能动。

配套文档：请参阅 notes/perf-multi-turn-cache/cache_strategy.md

【本仓库厂商凭证的唯一填写处】
    每个厂商的 API Key 和 URL 只在本文件下方的 `VENDORS` 里填一次。
    兄弟脚本（如 run_longalpaca_bench.py）都 `from run_perf_one import VENDORS` 复用同一份，
    所以新增/更换厂商或换 key 只改这里一处即可，不需要再去设环境变量。

【怎么加一个要测的模型】（理解这点就够用了）
    profile 名固定写成 `<模型名>_<厂商名>`（厂商名 = 最后一个下划线之后那段，必须是 VENDORS 里登记过的）。
    往下面的 `PROFILES` 列表里加一行字符串即可，例如要测腾讯云上的新模型 foo-bar：
        'foo-bar_tencent',
    模型名(foo-bar)、厂商(tencent)、URL、Key、是否注入 Session 缓存——全部自动从 profile 名 + VENDORS 推导出来，
    命令直接 `python scripts/perf/run_perf_one.py foo-bar_tencent`，结果目录也自动按 profile 名生成，无需另改。

如何运行：
    python scripts/perf/run_perf_one.py
无需改代码，通过命令行直接覆盖要测的模型（推荐）：
    python scripts/perf/run_perf_one.py deepseek-v4-pro_tencent
    python scripts/perf/run_perf_one.py deepseek-v4-pro_tencent 10   # 第2个参数传 dataset_offset (防缓存污染复测专用)
    python scripts/perf/run_perf_one.py deepseek-v4-pro_tencent 0 on # 第3个参数覆盖 session_cache (on/off, 不传则用 VENDORS 登记值)

关于 session_cache (Session 缓存路由注入) 的命令行覆盖与落盘：
    - 默认取 VENDORS[厂商] 里登记的值；可用第3个参数临时覆盖：on/1/true/yes 开，其余(off/0/...)关。
    - 它的实际生效状态会写进结果目录名后缀 `_cache-on` / `_cache-off`，方便同模型对比开/关缓存两种跑法不互相覆盖。
      目录命名形如 `results/<profile>_cache-off`，复测时再带上 offset 段：`results/<profile>_offset-<N>_cache-off`。

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
# 0) 厂商凭证与接入点 ———— 全仓库唯一填写处！填一次，处处引用。
#    新增厂商 / 换 key / 换 URL 都只动这里。其它脚本 import 这个 VENDORS 复用。
#    - `session_cache`: 该厂商是否需要显式靠 `X-Session-ID` 路由来复用 KV 缓存。
#                       腾讯云需要(True)；阿里百炼是隐式自动缓存(False)。多轮缓存压测用得到。
#    ⚠️ 这里是明文 API Key，注意别把本文件推到公开仓库。
# ============================================================================
VENDORS = {
    'tencent': dict(
        url='https://tokenhub.tencentmaas.com/v1/chat/completions',
        api_key='',
        session_cache=False,
    ),

    'sensetime-prod': dict(
        url='https://api.sensenova.cn/compatible-mode/v2/chat/completions',
        api_key='',
        session_cache=False,
    ),

    'sensetime-stage': dict(
        url='https://api.stage.sensenova.cn/compatible-mode/v2/chat/completions',
        api_key='',
        session_cache=False,
    ),

    'aliyun': dict(
        url='https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions',
        api_key='',
        session_cache=False,
    ),

    'aliyun-juyunkeji': dict(
        url='https://ws-fv27qx1qcocc0gpl.cn-beijing.maas.aliyuncs.com/compatible-mode/v1/chat/completions',
        api_key='',
        session_cache=False,
    ),
     'aliyun-test': dict(
        url='https://llm-2uvmqf1kext46chd.cn-beijing.maas.aliyuncs.com/compatible-mode/v1/chat/completions',
        api_key='',
        session_cache=False,
    ),

    'tencent-test': dict(
        url='https://tokenhub.tencentmaas.com/v1/chat/completions',
        api_key='',
        session_cache=False,
    ),
}

# ============================================================================
# 1) 唯一需要改动的地方：指定本次压测默认跑哪个 profile（也可由命令行 argv[1] 覆盖）
# ============================================================================
ACTIVE = 'deepseek-v4-pro_tencent'

# ============================================================================
# 2) 要测的 profile 清单。profile 名 = "<模型名>_<厂商名>"。
#    加模型 = 在这里加一行字符串即可；模型名/厂商/URL/Key/session_cache 全自动推导(见 _resolve)。
#    厂商名(最后一个下划线之后那段)必须已在上面的 VENDORS 里登记。
# ============================================================================
PROFILES = [
    'deepseek-v4-pro_tencent',
    'deepseek-v4-pro-202606_tencent',
    'deepseek-v4-flash_tencent',
    'deepseek-v4-flash-202605_tencent',
    'deepseek-v4-pro_aliyun',
    'deepseek-v4-flash_aliyun',
    'glm-5.1_tencent',
    'kimi-k2.6_tencent',
    'glm-5.2_tencent',
    'glm-5.1_aliyun',
    'kimi-k2.6_aliyun',
    'glm-5.2_aliyun',
    'glm-5.2_aliyun-juyunkeji',
    'SenseChat-Character-Max-v2-Cache_sensetime-stage',
    'SenseChat-Character-Max-v2-Flash-Cache_sensetime-stage',
    'SenseChat-Character-Agt-v2-Cache_sensetime-stage',
    'SenseChat-Character-Dev-v2-Cache_sensetime-stage',

    'SenseChat-Character-Max-v2_sensetime-prod',
    'SenseChat-Character-Max-v2-Flash_sensetime-prod',
    'SenseChat-Character-Agt-v3_sensetime-prod',
]


def _resolve(profile):
    """把 profile 名("<模型名>_<厂商名>")拆成 (模型名, 厂商名, 厂商配置)。
    厂商名取最后一个下划线之后的部分(模型名内部允许含连字符/点号)，其余为模型名；
    URL / api_key / session_cache 全部来自 VENDORS[厂商名]。"""
    if profile not in PROFILES:
        sys.exit(f"未知的模型配置 '{profile}'。请从以下选项中挑一个: {', '.join(PROFILES)}")
    model, _, vendor = profile.rpartition('_')
    if vendor not in VENDORS:
        sys.exit(f"profile '{profile}' 的厂商 '{vendor}' 没在 VENDORS 里登记。可选厂商: {', '.join(VENDORS)}")
    return model, vendor, VENDORS[vendor]

# 数据集双轨制（由下面的 offset 自动决定用哪个）
#   offset == 0  -> 跨模型横向对比，用标准小集 (10条对话)
#   offset >  0  -> 复测同模型，用大池子抽完全不重叠的子集，杜绝服务端缓存作弊
COMPARE_DATASET = 'outputs/agentic_dataset.json'
POOL_DATASET = 'outputs/agentic_pool.json'

# ============================================================================
# 3) 控制变量法的核心地带 (FIXED) ———— 绝对禁止修改！
#    只有保证所有厂商吃到的参数和数据一模一样，性能对比才有说服力。
#    【不传时 perf 内部默认 (Arguments)】temperature=0.0 / max_tokens=2048 / stream=True / total_timeout=6h;
#       top_p / top_k / seed / reasoning_effort 默认 None = 不发送, 由服务端自有默认决定。下面显式写出是为锁死可复现。
# ============================================================================
FIXED = dict(
    api='openai',                                   # 必须是 openai 兼容模式，才能保住咱们的特殊请求体注入
    dataset='swe_smith',
    multi_turn=True,                                # 开启多轮压测
    parallel=5,                                     # 会话级并发：10 条会话同时跑(会话内 turn 仍串行)；命中率不受影响，但 TTFT/TPOT 会因争抢变大，横向对比延迟须各厂商同档
    number=10,                                      # 每次只跑 10 条独立的对话 Session
    max_tokens=16384,                               # 配合长文本自然截断，不用商业模型不支持的 ignore_eos
    seed=42,                                        # 锁死随机种子
    temperature=1.0,                                # 采样温度；0=贪心(可复现)。要调就改这里
    top_p=0.95,                                      # 核采样；temperature=0 时为空操作，留作可调旋钮
    stream=True,                                    # 必须开启流式，否则算不出首字延迟 TTFT
    extra_args={'reasoning_effort': 'high'},        # 深度思考档位(low/medium/high)；非原生字段，走 extra_args 注入请求体。非推理模型请删掉此行
    #extra_args={'thinking': {'type': 'enabled'}} ,    #(glm-5.1 Kimi-k2.6等) 思考档位；非原生字段，走 extra_args 注入请求体。非推理模型请删掉
    read_timeout=300,                               # 读超时 300s：reasoning=high 单轮常需数十秒~分钟，60s 会误杀
    no_test_connection=True,
    no_timestamp=True,
)


def main():
    # 命令行参数覆盖逻辑：
    # argv[1] = 你要测的 profile 名字
    # argv[2] = 你要指定的 offset 游标（用于防缓存污染复测）
    # argv[3] = 覆盖 session_cache（on/off；不传则用 VENDORS 登记值）
    active = sys.argv[1] if len(sys.argv) > 1 else ACTIVE
    offset = int(sys.argv[2]) if len(sys.argv) > 2 else 0

    # 从 profile 名自动拆出 模型/厂商，并取出该厂商的 URL / Key / session_cache
    model, vendor, v = _resolve(active)

    # session_cache：默认取该厂商登记值，第3个命令行参数可临时覆盖（on/1/true/yes 为开，其余为关）
    session_cache = v['session_cache']
    if len(sys.argv) > 3:
        session_cache = sys.argv[3].strip().lower() in ('1', 'true', 'on', 'yes')

    # session_cache 的实际生效状态落进目录名后缀，开/关两种跑法各自独立、不互相覆盖
    cache_tag = 'cache-on' if session_cache else 'cache-off'

    # 根据 offset 决定数据源和输出目录
    # 如果 offset == 0，说明是初测，走标准比对集
    # 如果 offset > 0，说明是复测，走大池子，并且目录带上 offset-<N> 防止覆盖上一次的结果
    if offset > 0:
        dataset_path = POOL_DATASET
        outputs_dir = f'results/{active}_offset-{offset}_{cache_tag}'
    else:
        dataset_path = COMPARE_DATASET
        outputs_dir = f'results/{active}_{cache_tag}'

    if not os.path.exists(dataset_path):
        sys.exit(f"找不到数据集文件: {dataset_path} (请先看文档把数据生成出来)。")

    # EvalScope 框架遇到已有的 SQLite 数据库会拒绝覆写并报错退出。
    # 为了防止你反复跑同个命令时程序崩溃，如果发现目录已经存在了，
    # 就自动在目录名后面加一个当前时间戳，保持干净独立。
    if os.path.isdir(outputs_dir):
        outputs_dir = f"{outputs_dir}_{datetime.now().strftime('%Y%m%d-%H%M%S')}"

    # 拼装最终传给底层的参数对象
    task = Arguments(
        model=model,
        url=v['url'],
        api_key=v['api_key'],
        name=active,                                  # profile 名(含厂商)做结果库名：同模型跨厂商也唯一，不撞
        multi_turn_session_cache=session_cache,       # 最关键的 Session 缓存路由隔离注入开关(可由 argv[3] 覆盖)
        dataset_path=dataset_path,
        outputs_dir=outputs_dir,
        dataset_offset=offset,
        **FIXED,                                      # 把上面的不可变参数强塞进来
    )

    print(f"[run_perf_one] 准备发车！\n"
          f"配置={active} | 模型={model} | 厂商={vendor} | Session注入={session_cache} | 游标Offset={offset}\n"
          f"数据源={dataset_path} -> 结果存放至={outputs_dir}")
    
    # 拉起框架正式开跑
    run_perf_benchmark(task)


if __name__ == '__main__':
    main()
