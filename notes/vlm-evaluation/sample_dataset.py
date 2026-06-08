#!/usr/bin/env python
"""
sample_dataset.py —— 对【单个】数据集做抽样（原地覆盖 vlmeval 实际读取的 TSV，首次自动备份 *_FULL.tsv）。

- 图片集（MMBench_DEV_EN_V11 / MME-RealWorld-Lite / MMMU_Pro_10c）：等比例分层抽样到 --target 题。
- 视频集（Video-MME）：按「视频」抽样 --num-videos 个；可用 --duration short 只取短视频。

用法：
    # 图片集：分层抽到 ~500 题
    python notes/vlm-evaluation/sample_dataset.py --dataset MMBench_DEV_EN_V11 --target 500

    # 视频集：抽 100 个短视频（每个 3 题 → ~300 题）
    python notes/vlm-evaluation/sample_dataset.py --dataset Video-MME --num-videos 100 --duration short

    # 视频集：跨全时长抽 100 个视频
    python notes/vlm-evaluation/sample_dataset.py --dataset Video-MME --num-videos 100

    # 还原全量
    python notes/vlm-evaluation/sample_dataset.py --dataset MMBench_DEV_EN_V11 --restore
"""
import argparse

from sample_utils import VIDEO_DATASETS, locate_tsv, restore_full, stratified_sample, video_sample


def main():
    p = argparse.ArgumentParser(description='对单个 VLM 数据集抽样')
    p.add_argument('--dataset', required=True, help='数据集名，如 MMBench_DEV_EN_V11 / Video-MME')
    p.add_argument('--target', type=int, default=500, help='[图片集] 分层抽样目标题数（默认 500）')
    p.add_argument('--num-videos', type=int, default=100, help='[视频集] 抽取的视频个数（默认 100）')
    p.add_argument('--duration', default=None, help='[视频集] 只保留某时长: short/medium/long（默认全部）')
    p.add_argument('--strata-col', default=None, help='[图片集] 手动指定分层列（默认自动探测）')
    p.add_argument('--seed', type=int, default=42, help='随机种子（默认 42，可复现）')
    p.add_argument('--restore', action='store_true', help='用 *_FULL.tsv 还原全量后退出')
    args = p.parse_args()

    tsv = locate_tsv(args.dataset)
    print(f'[tsv] {args.dataset} -> {tsv}')

    if args.restore:
        restore_full(tsv)
        return

    if args.dataset in VIDEO_DATASETS:
        video_sample(tsv, num_videos=args.num_videos, duration=args.duration, seed=args.seed)
    else:
        stratified_sample(tsv, target=args.target, seed=args.seed, strata_col=args.strata_col)


if __name__ == '__main__':
    main()
