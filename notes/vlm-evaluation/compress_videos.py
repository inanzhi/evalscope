#!/usr/bin/env python
"""
compress_videos.py —— 压缩 Video-MME 里「整段视频 base64 后会超 API 单 data-uri 上限」的视频。

为什么需要：原生整段视频模式（run_eval.py 默认 video_llm=True，见 vlm_compat.py 补丁 4）把本地 mp4
base64 成 data:video/mp4;base64,... 整段发。DashScope 等对单个 data-uri 项有 20 MB 硬上限
（报错：Exceeded limit on max bytes per data-uri item : 20971520），base64 膨胀 ~33%，
原始 >~15 MB 的视频就会被拒、并连带 vlmeval 抛 KeyError: 'choices'。

本脚本扫描【当前抽样后的 Video-MME.tsv】引用到的视频，把超标的就地压到目标大小（默认 12 MB），
原件先备份到 video/_orig_oversized/，可还原。只动超标的，其它视频不碰。

用法：
    python notes/vlm-evaluation/compress_videos.py                 # 压缩超标视频（默认目标 12MB）
    python notes/vlm-evaluation/compress_videos.py --target-mb 10  # 压得更狠
    python notes/vlm-evaluation/compress_videos.py --dry-run       # 只列出哪些超标，不压
    python notes/vlm-evaluation/compress_videos.py --restore       # 用备份还原所有被压过的视频

前置：装好 ffmpeg / ffprobe（命令行可直接调用）。
"""
import argparse
import json
import os
import shutil
import subprocess
import sys

import pandas as pd

from sample_utils import locate_tsv

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

# data-uri 单项上限 20 MB（DashScope）。base64 长度 ≈ 原始字节 * 4/3，故原始须 < 20MB*3/4 ≈ 15.7MB。
DATAURI_LIMIT = 20 * 1024 * 1024
RAW_LIMIT = int(DATAURI_LIMIT * 3 / 4)   # ≈ 15.7 MB；超过它的视频 base64 后会破限
BACKUP_DIR = '_orig_oversized'


def _run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True)


def _duration_sec(path):
    r = _run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
              '-of', 'json', path])
    try:
        return float(json.loads(r.stdout)['format']['duration'])
    except Exception:
        return 0.0


def _video_dir():
    tsv = locate_tsv('Video-MME')
    vdir = os.path.join(os.path.dirname(tsv), 'video')
    if not os.path.isdir(vdir):
        raise FileNotFoundError(f'未找到 video 目录: {vdir}')
    return tsv, vdir


def _sampled_videos(tsv):
    df = pd.read_csv(tsv, sep='\t')
    col = 'video' if 'video' in df.columns else 'video_path'
    return list(pd.unique(df[col]))


def compress_one(src, target_mb):
    """就地压缩 src 到约 target_mb：先备份原件，再按时长算码率单遍 ABR 编码。"""
    vdir = os.path.dirname(src)
    backup_dir = os.path.join(vdir, BACKUP_DIR)
    os.makedirs(backup_dir, exist_ok=True)
    backup = os.path.join(backup_dir, os.path.basename(src))
    if not os.path.exists(backup):
        shutil.copy(src, backup)   # 只备份一次，保留最初的原件

    dur = _duration_sec(backup) or 1.0
    # 目标总码率 = 目标字节*8/时长；留 96k 给音频，其余给视频
    total_bps = target_mb * 1024 * 1024 * 8 / dur
    v_bps = max(200_000, int(total_bps - 96_000))
    tmp = src + '.tmp.mp4'
    cmd = [
        'ffmpeg', '-y', '-i', backup,
        '-c:v', 'libx264', '-b:v', str(v_bps),
        '-maxrate', str(int(v_bps * 1.4)), '-bufsize', str(int(v_bps * 2)),
        '-preset', 'veryfast',
        '-c:a', 'aac', '-b:a', '96k',
        '-movflags', '+faststart',
        tmp,
    ]
    r = _run(cmd)
    if r.returncode != 0 or not os.path.exists(tmp):
        raise RuntimeError(f'ffmpeg 失败: {os.path.basename(src)}\n{r.stderr[-800:]}')
    os.replace(tmp, src)
    return os.path.getsize(backup), os.path.getsize(src)


def restore_all(vdir):
    backup_dir = os.path.join(vdir, BACKUP_DIR)
    if not os.path.isdir(backup_dir):
        print('没有备份目录，无需还原。')
        return
    n = 0
    for name in os.listdir(backup_dir):
        shutil.copy(os.path.join(backup_dir, name), os.path.join(vdir, name))
        n += 1
    print(f'↩️  已用备份还原 {n} 个视频: {vdir}')


def main():
    p = argparse.ArgumentParser(description='压缩 Video-MME 超 data-uri 上限的视频')
    p.add_argument('--target-mb', type=float, default=12.0, help='压缩目标大小 MB（默认 12，留足 20MB 余量）')
    p.add_argument('--dry-run', action='store_true', help='只列出超标视频，不压缩')
    p.add_argument('--restore', action='store_true', help='用备份还原所有被压过的视频')
    args = p.parse_args()

    tsv, vdir = _video_dir()
    print(f'[video dir] {vdir}')

    if args.restore:
        restore_all(vdir)
        return

    vids = _sampled_videos(tsv)
    oversized = []
    for v in vids:
        f = os.path.join(vdir, str(v) + '.mp4')
        if os.path.exists(f) and os.path.getsize(f) > RAW_LIMIT:
            oversized.append((v, os.path.getsize(f)))

    print(f'抽样视频 {len(vids)} 个，超 data-uri 上限({RAW_LIMIT/1024/1024:.1f}MB)的 {len(oversized)} 个：')
    for v, s in sorted(oversized, key=lambda x: -x[1]):
        print(f'  {s/1024/1024:6.1f} MB  {v}')

    if args.dry_run or not oversized:
        return

    print(f'\n开始压缩到 ~{args.target_mb} MB ...')
    for v, _ in oversized:
        src = os.path.join(vdir, str(v) + '.mp4')
        before, after = compress_one(src, args.target_mb)
        flag = '✅' if after <= RAW_LIMIT else '⚠️仍超标'
        print(f'  {flag} {v}: {before/1024/1024:.1f} → {after/1024/1024:.1f} MB')
    print('\n完成。被压视频的原件在 video/_orig_oversized/，可 --restore 还原。')


if __name__ == '__main__':
    main()
