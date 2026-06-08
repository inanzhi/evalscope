from run_vlm import run_vlm

PROFILE = 'kimi-k2.6_aliyun'   # 下载与厂商无关，随便用一个已登记的 profile 触发即可
for ds in ['MMBench_DEV_EN_V11', 'MME-RealWorld-Lite', 'MMMU_Pro_10c']:
    run_vlm(PROFILE, ds, limit=1)
run_vlm(PROFILE, 'Video-MME', limit=1, video_llm=True)