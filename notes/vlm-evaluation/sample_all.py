#!/usr/bin/env python
"""
sample_all.py —— 一键对【所有】数据集抽样（图片集分层抽样 + Video-MME 按视频抽样）。

默认方案（与 vlm_mini_sampling_strategy.md 一致）：
    MMBench_DEV_EN_V11 / MME-RealWorld-Lite / MMMU_Pro_10c → 各分层抽到 --img-target（默认 500）题
    Video-MME → 抽 --num-videos（默认 100）个、--duration（默认 short）的视频

用法：
    python notes/vlm-evaluation/sample_all.py                                       # 全用默认
    python notes/vlm-evaluation/sample_all.py --img-target 500 --num-videos 100 --duration short
    python notes/vlm-evaluation/sample_all.py --num-videos 100 --duration all       # 视频跨全时长
    python notes/vlm-evaluation/sample_all.py --restore                             # 全部还原全量
"""
import argparse

from sample_utils import locate_tsv, restore_full, stratified_sample, video_sample

IMAGE_DATASETS = ['MMBench_DEV_EN_V11', 'MME-RealWorld-Lite', 'MMMU_Pro_10c']
VIDEO_DATASETS = ['Video-MME']


def main():
    p = argparse.ArgumentParser(description='一键抽样所有 VLM 数据集')
    p.add_argument('--img-target', type=int, default=500, help='图片集分层抽样目标题数（默认 500）')
    p.add_argument('--num-videos', type=int, default=100, help='Video-MME 抽取视频个数（默认 100）')
    p.add_argument('--duration', default='short', help='Video-MME 时长: short/medium/long/all（默认 short）')
    p.add_argument('--seed', type=int, default=42, help='随机种子（默认 42）')
    p.add_argument('--restore', action='store_true', help='全部还原全量后退出')
    args = p.parse_args()

    for name in IMAGE_DATASETS:
        print(f'\n==== {name} ====')
        try:
            tsv = locate_tsv(name)
            if args.restore:
                restore_full(tsv)
            else:
                stratified_sample(tsv, target=args.img_target, seed=args.seed)
        except Exception as e:
            print(f'❌ {name} 失败: {e}')

    for name in VIDEO_DATASETS:
        print(f'\n==== {name} ====')
        try:
            tsv = locate_tsv(name)
            if args.restore:
                restore_full(tsv)
            else:
                dur = None if args.duration == 'all' else args.duration
                video_sample(tsv, num_videos=args.num_videos, duration=dur, seed=args.seed)
        except Exception as e:
            print(f'❌ {name} 失败: {e}')

    print('\n全部完成。')


if __name__ == '__main__':
    main()
