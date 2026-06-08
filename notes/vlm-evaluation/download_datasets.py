#!/usr/bin/env python
"""
download_datasets.py —— 下载 VLM 评测数据集到本地（不调用任何模型 API、不计费）。

原理：调用 vlmeval 的 build_dataset(name)，它会触发该数据集的 prepare 流程，把 TSV / 视频拉到本地：
  - 图片集 → ~/LMUData/{name}.tsv
  - 视频集 Video-MME → HF/modelscope 缓存目录（注意：是整包视频，体积可达几十~上百 GB）

用法：
    python notes/vlm-evaluation/download_datasets.py --dataset MMBench_DEV_EN_V11
    python notes/vlm-evaluation/download_datasets.py --dataset MMBench_DEV_EN_V11 MME-RealWorld-Lite MMMU_Pro_10c
    python notes/vlm-evaluation/download_datasets.py --all
    python notes/vlm-evaluation/download_datasets.py --all --nframe 8
"""
import argparse

import vlm_compat  # noqa: F401  必须最先 import：打补丁后才能 import vlmeval
from vlmeval.dataset import build_dataset

DEFAULT_DATASETS = ['MMBench_DEV_EN_V11', 'MME-RealWorld-Lite', 'MMMU_Pro_10c', 'Video-MME']
VIDEO_DATASETS = {'Video-MME'}


def download_one(name: str, nframe: int):
    print(f'\n==== 下载 {name} ====')
    kwargs = {'nframe': nframe} if name in VIDEO_DATASETS else {}
    ds = build_dataset(name, **kwargs)
    if ds is None:
        print(f'❌ {name} 构建失败（名称可能不被支持）')
        return
    path = getattr(ds, 'data_file', None) or getattr(ds, 'data_path', None)
    print(f'✅ {name} 就绪 -> {path}')


def main():
    p = argparse.ArgumentParser(description='下载 VLM 评测数据集（不调用模型 API）')
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument('--dataset', nargs='+', help='要下载的数据集名（可多个，空格分隔）')
    g.add_argument('--all', action='store_true', help=f'下载全部默认数据集: {DEFAULT_DATASETS}')
    p.add_argument('--nframe', type=int, default=8, help='视频集构建对象所需帧数（默认 8，仅用于构建，不影响下载内容）')
    args = p.parse_args()

    datasets = DEFAULT_DATASETS if args.all else args.dataset
    for name in datasets:
        download_one(name, args.nframe)
    print('\n全部完成。')


if __name__ == '__main__':
    main()
