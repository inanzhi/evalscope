# Copyright (c) Alibaba, Inc. and its affiliates.
"""
sample_utils.py —— VLM 数据集抽样的纯函数库（只依赖 pandas/numpy）。

- locate_tsv(name): 定位 vlmeval 真正读取的 TSV 路径（图片集在 ~/LMUData，视频集在 HF 缓存），
  若尚未下载会触发下载。需要 vlmeval，故内部惰性 import 并先加载 vlm_compat 补丁。
- stratified_sample(...): 图片集等比例分层抽样。
- video_sample(...): 视频集按「视频」抽样（可选只取某 duration）。
- restore_full(...): 用首次备份的 *_FULL.tsv 还原全量。

被 sample_dataset.py / sample_all.py 复用。所有抽样都「始终从全量备份读、抽完原地覆盖」，
保证可复现且不会越抽越小。
"""
import os
import shutil
import sys

import numpy as np
import pandas as pd

# Windows 控制台默认 GBK，打印 ✅/❌ 等 emoji 会 UnicodeEncodeError，这里切到 UTF-8 兜底
try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

# 候选分层列，按优先级排列；取「存在且取值多于 1 种」的第一个
_STRATA_CANDIDATES = ['category', 'l2-category', 'sub_category', 'subject', 'subfield', 'task_type', 'split', 'domain']

# 视频集集合（判定走视频抽样还是分层抽样）
VIDEO_DATASETS = {'Video-MME'}


def locate_tsv(name: str, nframe: int = 8) -> str:
    """返回 vlmeval 实际读取的 {name}.tsv 绝对路径；若未下载则触发下载。

    图片集对象暴露 .data_path（~/LMUData/{name}.tsv）；
    视频集对象暴露 .data_file（HF/modelscope 缓存里的 {name}.tsv）。
    """
    import vlm_compat  # noqa: F401  先打补丁，再 import vlmeval
    from vlmeval.dataset import build_dataset

    kwargs = {'nframe': nframe} if name in VIDEO_DATASETS else {}
    ds = build_dataset(name, **kwargs)
    if ds is None:
        raise RuntimeError(f'无法构建数据集 {name}，请确认名称是否正确（可用 list_supported_datasets 核对）。')
    path = getattr(ds, 'data_file', None) or getattr(ds, 'data_path', None)
    if not path or not os.path.exists(path):
        raise FileNotFoundError(f'定位到的 TSV 不存在: {path}')
    return path


def _backup_path(tsv_path: str) -> str:
    return tsv_path[:-4] + '_FULL.tsv' if tsv_path.endswith('.tsv') else tsv_path + '_FULL'


def _backup_once(tsv_path: str) -> str:
    """首次备份全量为 *_FULL.tsv，避免反复抽样越缩越小。"""
    backup = _backup_path(tsv_path)
    if not os.path.exists(backup):
        shutil.copy(tsv_path, backup)
    return backup


def pick_strata_column(df: pd.DataFrame) -> str:
    print(f'[columns] {list(df.columns)}')
    for col in _STRATA_CANDIDATES:
        if col in df.columns and df[col].nunique() > 1:
            print(f'[strata] 使用分层列: {col} ({df[col].nunique()} 类)')
            return col
    raise KeyError(f'未找到合适的分层列，请用 --strata-col 从 {list(df.columns)} 中手动指定')


def _group_keys(df: pd.DataFrame) -> pd.Series:
    """为每行计算「题组键」。

    MMBench 等 circular 集：同一题会以旋转选项出现多次，图片只存在「基题」行，
    其余「变体行」的 image 字段是对基题 index 的字符串引用（如 1000250 行 image='250'）。
    必须把同一基题的所有行作为整体一起抽，否则拆散后图片引用断裂、加载即报错。
    无此引用结构的集（每行自带图片）里，每行自成一组 → 退化为普通按行抽样。
    """
    if 'image' not in df.columns or 'index' not in df.columns:
        return pd.Series(range(len(df)), index=df.index)
    idx = df['index'].astype(str)
    img = df['image'].astype(str)
    valid = set(idx)
    # 引用行：image 是短字符串且正好等于某行 index → 组键=被引用的基题 index(gv)；否则组键=自身 index(iv)
    keys = [gv if (len(gv) <= 64 and gv in valid) else iv
            for gv, iv in zip(img, idx)]
    return pd.Series(keys, index=df.index)


def stratified_sample(tsv_path: str, target: int, seed: int = 42, strata_col: str | None = None):
    """图片集按「题组」等比例分层抽样，原地覆盖（首次自动备份 *_FULL.tsv）。

    先把 circular 变体归并成题组（见 _group_keys），按 strata 列分层后整组抽样，
    保证 circular 结构与图片引用完整。target 以「行数」为准换算抽样比例。
    """
    backup = _backup_once(tsv_path)
    df = pd.read_csv(backup, sep='\t')  # 始终从全量备份抽
    col = strata_col or pick_strata_column(df)

    gkey = _group_keys(df)
    cat_of_group = df[col].groupby(gkey).first()        # 题组键 -> 分层类别（取组内首行）
    groups = cat_of_group.reset_index(name=col).rename(columns={'index': '_gkey'})
    groups.columns = ['_gkey', col]

    frac = min(1.0, target / len(df))                   # 按行数目标换算比例（组大小近似一致）
    # 用 GroupBy.sample 按类别分层抽「题组」（pandas 3.0 已移除 groupby.apply 的 include_groups）
    picked = set(groups.groupby(col, group_keys=False)
                       .sample(frac=frac, random_state=seed)['_gkey'])

    sampled = df[gkey.isin(picked).values].sort_index()
    sampled.to_csv(tsv_path, sep='\t', index=False)
    n_groups = len(picked)
    print(f'✅ {os.path.basename(tsv_path)}: {len(df)} → {len(sampled)} 行 / {n_groups} 题组 (分层列={col})')
    return sampled


def video_sample(tsv_path: str, num_videos: int, duration: str | None = None,
                 seed: int = 42, vid_col: str | None = None):
    """视频集按「视频」抽样，原地覆盖（首次自动备份 *_FULL.tsv）。

    duration: 只保留某时长（如 'short'）；None=全时长。
    """
    backup = _backup_once(tsv_path)
    df = pd.read_csv(backup, sep='\t')
    print(f'[columns] {list(df.columns)}')

    if duration is not None:
        if 'duration' not in df.columns:
            raise KeyError("TSV 无 'duration' 列，无法按时长过滤")
        df = df[df['duration'] == duration]
        print(f"[duration] 仅保留 duration=={duration}: {len(df)} 题")

    col = vid_col or ('video' if 'video' in df.columns else 'video_path')
    uniq = df[col].unique()
    np.random.seed(seed)
    pick = np.random.choice(uniq, size=min(num_videos, len(uniq)), replace=False)
    sampled = df[df[col].isin(pick)].sort_index()
    sampled.to_csv(tsv_path, sep='\t', index=False)
    print(f'✅ {os.path.basename(tsv_path)}: 抽中 {len(pick)} 个视频 → {len(sampled)} 题 (标识列={col})')
    return sampled


def restore_full(tsv_path: str):
    """用 *_FULL.tsv 还原全量。"""
    backup = _backup_path(tsv_path)
    if not os.path.exists(backup):
        raise FileNotFoundError(f'未找到全量备份 {backup}，无法还原（可能从未抽样过）')
    shutil.copy(backup, tsv_path)
    print(f'↩️  已还原全量: {tsv_path}')
