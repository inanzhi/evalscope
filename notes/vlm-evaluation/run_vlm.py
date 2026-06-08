"""
run_vlm.py —— VLM 评测的【配置中心 + 核心函数】（不是命令行入口）。

命令行入口是 run_eval.py / download_datasets.py / sample_dataset.py / sample_all.py。
本文件只负责：厂商凭证、profile 清单、固定生成参数，以及核心函数 run_vlm()。
要换模型 / 厂商 / key / 生成参数，改这里。

【厂商凭证唯一填写处】
    每个厂商的 URL / API Key 只在 VENDORS 里填一次。
    VLMEvalKit 后端的 api_base 需要「完整」的 /v1/chat/completions —— VENDORS 里的 url 正好是这个形态。
    ⚠️ 明文 API Key，别把本文件推到公开仓库。

【怎么加一个要测的模型】
    profile 名固定写成 "<模型名>_<厂商名>"（厂商名 = 最后一个下划线之后那段，须在 VENDORS 里登记过）。
    往 PROFILES 列表加一行字符串即可，模型名 / 厂商 / URL / Key / 输出目录全自动推导。

【输出目录隔离逻辑】
    VLMEvalKit 的结果文件名只由 model 的 `type`（= 模型名）决定，且 `type` 同时是请求体里发给 API
    的 model 名，不能塞厂商后缀。因此每个 profile 用独立 work_dir = outputs/<模型名>_<厂商名> 隔离。
"""
import vlm_compat  # noqa: F401  必须最先 import：transformers 别名等补丁，之后 import evalscope/vlmeval 才不报错

from evalscope import TaskConfig, run_task

# ============================================================================
# 0) 厂商凭证与接入点 ———— 唯一填写处。新增厂商 / 换 key / 换 URL 都只动这里。
#    url 必须是完整的 /v1/chat/completions。
# ============================================================================
VENDORS = {
    'tencent': dict(
        url='https://tokenhub.tencentmaas.com/v1/chat/completions',
        api_key='sk-9k79zoqAsREeYag1xUDT0WKVPLdvORdgh3FR0OTfsGtamvfN',
    ),
    'aliyun': dict(
        url='https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions',
        api_key='sk-2f1a437b944f477aa996a3de09daaeb5',
    ),
}

# ============================================================================
# 1) 要测的 profile 清单。profile 名 = "<模型名>_<厂商名>"。
#    加模型 = 加一行字符串；厂商名（最后一个下划线之后那段）必须已在 VENDORS 里登记。
# ============================================================================
PROFILES = [
    'kimi-k2.6_aliyun',
    'kimi-k2.6_tencent',
]

# ============================================================================
# 2) 数据集清单。图片集与视频集分开（视频集要开 video_llm 并按视频抽样）。
#    抽样请先用 sample_dataset.py / sample_all.py 处理本地 TSV，这里只管「跑」。
# ============================================================================
IMAGE_DATASETS = ['MMBench_DEV_EN_V11', 'MME-RealWorld-Lite', 'MMMU_Pro_10c']
VIDEO_DATASETS = ['Video-MME']

# ============================================================================
# 3) 跨模型公平对比的固定生成参数 ———— 尽量别动。
#    四个集全是单选题：temperature=0（贪心、可复现）最合适；max_tokens 不用大。
#    （换 COT 变体如 MMMU_Pro_10c_COT 才需调大 max_tokens 输出思维链。）
# ============================================================================
FIXED_MODEL = dict(
    temperature=0.6,     # ⚠️ kimi-k2.6 的 temperature 必须与思考开关匹配：思考模式用 1.0、非思考用 0.6，
                         #    传错值服务端会 400 拒绝。当前 thinking=disabled（非思考）→ 用 0.6。开思考记得同时改成 1.0。
    top_p=0.95,        # 核采样；非具名参数→透传成请求体顶层字段；temperature=0 时为空操作
    max_tokens=8192,
    img_size=-1,       # -1=原图；设具体值会缩放
    # reasoning_effort='high',  # 思考型 VLM 才开；透传进请求体，目标 API 认才生效
    # ⚠️ 别用 extra_body={...}：那是 OpenAI 官方 SDK 的参数，VLMEvalKit 是手搓 requests.post（见 vlmeval/api/gpt.py），
    #    不会解包 extra_body，只会把它当成请求体里一个字面字段塞进去，服务端忽略 → 关思考失效。
    #    思考开关要「平铺」成顶层非具名参数，才会被透传进请求体顶层。       # 关闭思考模式（DashScope/Qwen 系列顶层字段）
    thinking={'type': 'disabled'},  # 若目标 API 用的是 thinking.type 这套 schema，改用这行
    # timeout=300,              # OpenAIWrapper 具名参数，默认 300s
)

# 并发与容错（VLMEvalKit 默认就是多并发，不是单并发）
NPROC = 4          # 并发调用 API 数；商业 API 限并发，从 8~16 起步，报 429 就调小（视频集建议 4~8）
RETRY = 3           # 单条失败重试次数


def _resolve(profile: str):
    """把 profile 名("<模型名>_<厂商名>")拆成 (模型名, 厂商名, 厂商配置)。
    厂商名取最后一个下划线之后的部分（模型名内部允许含连字符/点号），其余为模型名。"""
    if profile not in PROFILES:
        raise SystemExit(f"未知的模型配置 '{profile}'。请从以下选项中挑一个: {', '.join(PROFILES)}")
    model, _, vendor = profile.rpartition('_')
    if vendor not in VENDORS:
        raise SystemExit(f"profile '{profile}' 的厂商 '{vendor}' 没在 VENDORS 里登记。可选厂商: {', '.join(VENDORS)}")
    return model, vendor, VENDORS[vendor]


def run_vlm(profile: str, dataset: str, limit=None, video_llm: bool = False):
    """跑单个 (profile, dataset)。输出目录按 outputs/<模型名>_<厂商名> 隔离。"""
    model, vendor, v = _resolve(profile)
    work_dir = f'outputs/{profile}'   # ← 隔离核心：每个 模型_厂商 独立目录，不互相覆盖

    run_task(TaskConfig(
        eval_backend='VLMEvalKit',
        work_dir=work_dir,
        eval_config={
            'data': [dataset],
            'mode': 'all',          # 推理 + 评测
            'limit': limit,         # None=全量（或抽样后子集）；=1 触发下载/冒烟
            'reuse': False,
            'nproc': NPROC,
            'ignore': True,         # 跳过失败样本，不中断整场
            'retry': RETRY,
            'model': [{
                'type': model,              # API 请求体里的 model 名，同时也是结果文件名前缀
                'name': 'CustomAPIModel',   # 固定值，必须是 CustomAPIModel
                'api_base': v['url'],
                'key': v['api_key'],
                'video_llm': video_llm,     # True=原生整段视频（vlm_compat.py 补丁 4 把本地 mp4 → base64 Data URL，
                                            #   跑前需 compress_videos.py 压超 20MB 上限的视频）；False=抽 nframe 帧成图片发。
                                            # run_eval.py 对 VIDEO_DATASETS 默认传 True。
                **FIXED_MODEL,
            }],
        },
    ))
    print(f'[run_vlm] 完成 profile={profile} 模型={model} 厂商={vendor} 数据集={dataset} -> {work_dir}/{model}/')


if __name__ == '__main__':
    raise SystemExit('run_vlm.py 是配置/库文件，不直接运行。请用：python notes/vlm-evaluation/run_eval.py --profile <P> --dataset <D>')
