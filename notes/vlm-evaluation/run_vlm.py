"""
VLM (多模态) 微缩均衡评测通用运行器 (run_vlm.py)

设计目标：切换厂商 / 模型时，只改一行 `ACTIVE`（或命令行传 profile 名）。
所有为了跨模型公平对比的固定参数都放在 `FIXED_MODEL` 里，不要随意动。

配套文档：notes/vlm-evaluation/vlm_mini_sampling_strategy.md

【厂商凭证唯一填写处】
    每个厂商的 URL / API Key 只在下方 `VENDORS` 里填一次（结构搬自 scripts/perf/run_perf_one.py）。
    VLMEvalKit 后端的 api_base 需要「完整」的 /v1/chat/completions —— VENDORS 里的 url 正好就是这个形态。

【怎么加一个要测的模型】
    profile 名固定写成 `<模型名>_<厂商名>`（厂商名 = 最后一个下划线之后那段，必须在 VENDORS 里登记过）。
    往 `PROFILES` 列表加一行字符串即可，例如测阿里云上的 qwen-vl-plus：
        'qwen-vl-plus_aliyun',
    模型名 / 厂商 / URL / Key / 输出目录全部从 profile 名 + VENDORS 自动推导。

【输出目录隔离逻辑（本脚本核心）】
    VLMEvalKit 的结果文件名只由 model 的 `type`（= 模型名）决定，且 `type` 同时是请求体里发给 API
    的 model 名，不能塞厂商后缀。又因为 VLMEvalKit 不像 native eval 那样自动加时间戳目录，
    所以同名模型打不同厂商若共用一个 work_dir 会互相覆盖。
    解决：每个 profile 用独立 work_dir = `outputs/<模型名>_<厂商名>`，天然按「模型_厂商」隔离。
    最终落盘：outputs/<模型名>_<厂商名>/<模型名>/<模型名>_<数据集>*.{xlsx,csv}

如何运行：
    python notes/vlm-evaluation/run_vlm.py                       # 跑默认 ACTIVE 的全部数据集
    python notes/vlm-evaluation/run_vlm.py qwen-vl-max_aliyun    # 指定 profile
    python notes/vlm-evaluation/run_vlm.py qwen-vl-max_aliyun MMBench_DEV_EN_V11   # 再指定单个数据集
    DOWNLOAD=1 python notes/vlm-evaluation/run_vlm.py qwen-vl-max_aliyun           # limit=1 仅触发下载
"""

import os
import sys

from evalscope import TaskConfig, run_task

# ============================================================================
# 0) 厂商凭证与接入点 ———— 唯一填写处（结构与凭证搬自 scripts/perf/run_perf_one.py）。
#    新增厂商 / 换 key / 换 URL 都只动这里。url 必须是完整的 /v1/chat/completions。
#    ⚠️ 明文 API Key，别把本文件推到公开仓库。
# ============================================================================
VENDORS = {
    'tencent': dict(
        url='https://tokenhub.tencentmaas.com/v1/chat/completions',
        api_key='sk-9k79zoqAsREeYag1xUDT0WKVPLdvORdgh3FR0OTfsGtamvfN',
    ),
    'aliyun': dict(
        url='https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions',
        api_key='sk-8a5e067144f5451c9aad99f58fefdffd',
    ),
}

# ============================================================================
# 1) 唯一需要改动的地方：本次默认跑哪个 profile（也可由命令行 argv[1] 覆盖）。
# ============================================================================
ACTIVE = 'qwen-vl-max_aliyun'

# ============================================================================
# 2) 要测的 profile 清单。profile 名 = "<模型名>_<厂商名>"。
#    加模型 = 加一行字符串；厂商名（最后一个下划线之后那段）必须已在 VENDORS 里登记。
# ============================================================================
PROFILES = [
    'qwen-vl-max_aliyun',
    'qwen-vl-max_tencent',
]

# ============================================================================
# 3) 数据集清单。图片集与视频集分开（视频集要开 video_llm 并按视频抽样，见文档 4.4）。
#    抽样请先用 sample_utils.resample_tsv(...) 处理本地 TSV，这里只管「跑」。
# ============================================================================
IMAGE_DATASETS = ['MMBench_DEV_EN_V11', 'MME-RealWorld-Lite', 'MMMU_Pro_10c']
VIDEO_DATASETS = ['Video-MME']

# ============================================================================
# 4) 跨模型公平对比的固定生成参数 ———— 尽量别动。
#    四个集全是单选题：temperature=0（贪心、可复现）最合适；max_tokens 不用大。
#    （换 COT 变体如 MMMU_Pro_10c_COT 才需调大 max_tokens 输出思维链。）
# ============================================================================
FIXED_MODEL = dict(
    temperature=0.0,   # 采样温度；0=贪心（可复现）
    top_p=0.95,        # 核采样；非具名参数→透传成请求体顶层字段；temperature=0 时为空操作
    max_tokens=8192,
    img_size=-1,       # -1=原图；设具体值会缩放
    # reasoning_effort='high',  # 思考型 VLM 才开；透传进请求体，目标 API 认才生效
    # timeout=300,              # OpenAIWrapper 具名参数，默认 300s
)

# 并发与容错（VLMEvalKit 默认就是多并发，不是单并发）
NPROC = 16          # 并发调用 API 数；商业 API 限并发，从 8~16 起步，报 429 就调小（视频集建议 4~8）
RETRY = 3           # 单条失败重试次数


def _resolve(profile: str):
    """把 profile 名("<模型名>_<厂商名>")拆成 (模型名, 厂商名, 厂商配置)。
    厂商名取最后一个下划线之后的部分（模型名内部允许含连字符/点号），其余为模型名。"""
    if profile not in PROFILES:
        sys.exit(f"未知的模型配置 '{profile}'。请从以下选项中挑一个: {', '.join(PROFILES)}")
    model, _, vendor = profile.rpartition('_')
    if vendor not in VENDORS:
        sys.exit(f"profile '{profile}' 的厂商 '{vendor}' 没在 VENDORS 里登记。可选厂商: {', '.join(VENDORS)}")
    return model, vendor, VENDORS[vendor]


def run_vlm(profile: str, dataset: str, limit=None, video_llm: bool = False):
    """跑单个 (profile, dataset)。输出目录按 `outputs/<模型名>_<厂商名>` 隔离。"""
    model, vendor, v = _resolve(profile)
    work_dir = f'outputs/{profile}'   # ← 隔离核心：每个 模型_厂商 独立目录，不互相覆盖

    run_task(TaskConfig(
        eval_backend='VLMEvalKit',
        work_dir=work_dir,
        eval_config={
            'data': [dataset],
            'mode': 'all',          # 推理 + 评测
            'limit': limit,         # None=全量（或抽样后的子集）；下载链路时设 1
            'reuse': False,
            'nproc': NPROC,
            'ignore': True,         # 跳过失败样本, 不中断整场
            'retry': RETRY,
            'model': [{
                'type': model,              # API 请求体里的 model 名，同时也是结果文件名前缀
                'name': 'CustomAPIModel',   # 固定值，必须是 CustomAPIModel
                'api_base': v['url'],
                'key': v['api_key'],
                'video_llm': video_llm,     # 视频集且要传 video_url 时设 True
                **FIXED_MODEL,
            }],
        },
    ))
    print(f'[run_vlm] 完成 profile={profile} 模型={model} 厂商={vendor} 数据集={dataset} -> {work_dir}/{model}/')


def main():
    profile = sys.argv[1] if len(sys.argv) > 1 else ACTIVE
    only_dataset = sys.argv[2] if len(sys.argv) > 2 else None
    limit = 1 if os.environ.get('DOWNLOAD') else None   # DOWNLOAD=1 时 limit=1 仅触发下载

    if only_dataset:
        video = only_dataset in VIDEO_DATASETS
        run_vlm(profile, only_dataset, limit=limit, video_llm=video)
        return

    for ds in IMAGE_DATASETS:
        run_vlm(profile, ds, limit=limit)
    for ds in VIDEO_DATASETS:
        run_vlm(profile, ds, limit=limit, video_llm=True)


if __name__ == '__main__':
    main()
