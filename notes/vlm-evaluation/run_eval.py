#!/usr/bin/env python
"""
run_eval.py —— 跑 VLM 评测（真实调用模型 API、按 token 计费）。

模型 / 厂商 / 凭证 / 固定生成参数都在 run_vlm.py 里配置；本文件只是它的命令行入口。
profile 名 = "<模型名>_<厂商名>"，须已登记在 run_vlm.PROFILES（厂商须在 run_vlm.VENDORS）。
输出目录按 outputs/<模型名>_<厂商名> 隔离，不同厂商不会互相覆盖。

用法：
    # 跑单个数据集
    python notes/vlm-evaluation/run_eval.py --profile kimi-k2.6_aliyun --dataset MMBench_DEV_EN_V11

    # 跑该 profile 的全部数据集（图片集 + 视频集）
    python notes/vlm-evaluation/run_eval.py --profile kimi-k2.6_aliyun --all

    # 只跑前 N 题（=1 可用于触发下载 / 冒烟测试，几乎不花钱）
    python notes/vlm-evaluation/run_eval.py --profile kimi-k2.6_aliyun --dataset MMBench_DEV_EN_V11 --limit 1
"""
import argparse

import vlm_compat  # noqa: F401  必须最先 import：打补丁后才能跑 vlmeval
from run_vlm import IMAGE_DATASETS, PROFILES, VIDEO_DATASETS, run_vlm


def main():
    p = argparse.ArgumentParser(description='跑 VLM 评测（调用模型 API、计费）')
    p.add_argument('--profile', required=True, help=f'模型_厂商，可选: {PROFILES}')
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument('--dataset', help='单个数据集名')
    g.add_argument('--all', action='store_true', help='跑全部数据集（图片集 + 视频集）')
    p.add_argument('--limit', type=int, default=None,
                   help='只跑前 N 题（默认全量 / 抽样后的子集；=1 可触发下载 / 冒烟）')
    args = p.parse_args()

    # 视频集走原生整段视频：video_llm=True 让数据集发本地 .mp4 路径，vlm_compat.py 补丁 4 会把它
    # base64 成 data:video/mp4;base64,... 再发（带 fps），DashScope 等可直接吃完整视频。
    # （想退回「抽 nframe 帧成图片」的省钱模式，把下面的 True 改成 False 即可，无需动补丁。）
    video = args.dataset in VIDEO_DATASETS if not args.all else None
    if args.all:
        for ds in IMAGE_DATASETS:
            run_vlm(args.profile, ds, limit=args.limit)
        for ds in VIDEO_DATASETS:
            run_vlm(args.profile, ds, limit=args.limit, video_llm=True)
    else:
        run_vlm(args.profile, args.dataset, limit=args.limit, video_llm=video)


if __name__ == '__main__':
    main()
