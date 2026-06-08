# VLM 评测：下载 / 抽样 / 跑分 一条龙

目的：把动辄上千题的 VLM 测试集压到几百题，省时间省 API 钱，同时保证各能力维度占比不失衡。

所有脚本都在本目录，**直接 `python 脚本名 --参数` 执行**。唯一可能要设的环境变量是 `MODELSCOPE_CACHE`（数据集缓存放哪，系统盘小就得指到大盘，详见下方专节）；本机已永久设好，新开终端无需再管。

---

## 命令行脚本

| 脚本 | 干什么 | 怎么跑 |
|---|---|---|
| `download_datasets.py` | 下载数据集（不调模型、不花钱） | `python download_datasets.py --dataset MMBench_DEV_EN_V11` |
| `sample_dataset.py` | 切分**单个**数据集 | `python sample_dataset.py --dataset MMBench_DEV_EN_V11 --target 500` |
| `sample_all.py` | 一键切分**全部**数据集 | `python sample_all.py` |
| `run_eval.py` | 跑评测（**真实调 API、计费**） | `python run_eval.py --profile kimi-k2.6_aliyun --dataset MMBench_DEV_EN_V11` |
| `compress_videos.py` | （视频原生模式可选）压缩超 data-uri 上限的视频 | `python compress_videos.py`（详见坑 #2） |

> 命令前面带不带 `notes/vlm-evaluation/` 都行；从仓库根目录跑就写全路径，如 `python notes/vlm-evaluation/run_eval.py ...`。

另有 3 个支撑文件不用直接调：`run_vlm.py`（**配置中心**：厂商/密钥/profile/生成参数都改这）、`sample_utils.py`（抽样函数）、`vlm_compat.py`（运行时补丁：transformers 别名 + 信任本地抽样 TSV + 视频本地 mp4→base64 Data URL，详见其顶部注释与坑 #2/#6）。

---

## 标准流程（三步）

**1. 下载** —— 把原始数据拉到本地：
```bash
python download_datasets.py --all
```

**2. 抽样**（可选，想跑全量就跳过）—— 把每个集压小：
```bash
python sample_all.py                       # 图片集各抽 ~500 题，Video-MME 抽 100 个短视频

# 只切【图片集】—— 用 --target 控题数：
python sample_dataset.py --dataset MMMU_Pro_10c --target 500

# 只切【视频集 Video-MME】—— 用 --num-videos 控视频个数，--duration 选时长：
python sample_dataset.py --dataset Video-MME --num-videos 100 --duration short   # 抽 100 个短视频（每视频 3 题 → ~300 题）
python sample_dataset.py --dataset Video-MME --num-videos 100                     # 跨全时长抽 100 个视频（不加 --duration）
```
> 视频集**不吃 `--target`**（抽的是「视频」不是「题」）；图片集**不吃 `--num-videos` / `--duration`**。两类参数互不通用，传错会被忽略。`--duration` 可选 `short` / `medium` / `long`。

**3. 跑分**：
```bash
python run_eval.py --profile kimi-k2.6_aliyun --all                          # 跑全部（图片集 + 视频集）

# 跑单个【图片集】：
python run_eval.py --profile kimi-k2.6_aliyun --dataset MMBench_DEV_EN_V11

# 跑单个【视频集】—— 默认走「原生整段视频」，跑前必须先压缩超标视频（见下）：
python compress_videos.py                                   # ① 压缩 base64 后会超 20MB 的视频（一次性）
python run_eval.py --profile kimi-k2.6_aliyun --dataset Video-MME   # ② 跑分
```
> **视频集比图片集多一步 `compress_videos.py`**：默认是「原生整段视频」模式（`run_eval.py` 检测到 `VIDEO_DATASETS` 自动设 `video_llm=True`，由 `vlm_compat.py` 补丁 4 把本地 mp4 → base64 Data URL 整段发）。但商业 API 对单个 data-uri 有 20MB 上限，原始 >~15MB 的视频会破限报错（详见坑 #2），所以**跑分前先 `compress_videos.py` 把超标的压小**。
>
> 视频集并发重，`run_vlm.py` 里 `NPROC` 建议降到 4~8，报 429 再调小。
> （不想压缩 / 想省 token，可改用「抽帧」模式，见坑 #2 第二种。）

**看结果**：`outputs/<模型_厂商>/<模型>/*_acc.csv` 就是准确率汇总。

**想还原全量**：`python sample_dataset.py --dataset XXX --restore`（首次抽样会自动备份 `*_FULL.tsv`）。

---

## 环境变量 `MODELSCOPE_CACHE`（数据集缓存放哪）

它告诉 modelscope **把数据集/模型缓存下到哪个目录**。默认落在系统盘 `~/.cache/modelscope`；**系统盘小（比如本机 C 盘被 Video-MME 撑爆过）就必须指到大盘**，否则解压时报 `No space left on device`。本机已指到 **`D:\ms_cache\modelscope`**。

设它有两种方式，区别在「生效范围」：

```powershell
# 方式 A：只对【当前这个终端窗口】临时生效，关掉就没了
$env:MODELSCOPE_CACHE = "D:\ms_cache\modelscope"

# 方式 B：永久写进系统（推荐，一次到位）。只对【之后新开的】终端生效，当前已开的窗口不认
setx MODELSCOPE_CACHE "D:\ms_cache\modelscope"
```

> `$env:XXX` 是 PowerShell 读/写环境变量的写法（≈ bash 的 `export XXX=...`）。
>
> **实操**：本机已 `setx` 过，所以**新开一个终端**跑分时**不用再敲** `$env:...`，直接 `python notes\vlm-evaluation\run_eval.py ...` 即可。只有在「`setx` 之前就开着的旧窗口」里才需要临时补一句方式 A。
>
> **验证**：新开终端里 `echo $env:MODELSCOPE_CACHE`，能打印出 `D:\ms_cache\modelscope` 就说明永久设置已生效。
>
> ⚠️ 没设它、或指错盘 → modelscope 找不到已下的数据会**重新下载**（Video-MME 又是上百 GB），还可能把系统盘再撑爆。

---

## ⭐ `--limit` 到底跑多少题？（每次跑分前先想清楚，直接关系花多少钱）

`run_eval.py --limit N` 控制**这次跑前 N 题**，默认 `None`。它和「抽样」是**两件独立的事**，最容易混：

| `--limit` 取值 | 实际跑多少题 | 用途 |
|---|---|---|
| **不传**（默认 `None`） | **当前 TSV 的全部行** | 正式跑分。⚠️ 这个「全量」= **抽样后的子集**（你抽过样就是几百题），**不是**原始全量 |
| `--limit 1` | 只跑第 1 题 | 触发下载 / 冒烟验证链路，几乎不花钱 |
| `--limit N` | 跑前 N 题（TSV 前 N 行，**不分层**） | 临时小样试跑 |

**`--limit` ≠ 抽样，关键区别：**
- **抽样**（`sample_dataset.py`）：按能力维度**分层均衡**缩小，把结果**固化进 TSV**（原始全量备份成 `*_FULL.tsv`），可复现、跨模型同一批题。正式对比就靠它。
- **`--limit N`**：只是临时**截前 N 行**，不分层、维度可能不均衡，**别拿它的分数做正式横向对比**——它是给冒烟/试跑用的。

**「全量」具体多少题，取决于本地 TSV 现在是抽样子集还是原始全量**，跑前可以先数一眼（以 MMBench 为例）：
```bash
wc -l ~/LMUData/MMBench_DEV_EN_V11.tsv        # 实际会跑这个（行数-1=题数）
wc -l ~/LMUData/MMBench_DEV_EN_V11_FULL.tsv   # 原始全量备份，带 _FULL，不会被跑
```
> 例：抽样后 `MMBench_DEV_EN_V11.tsv` ≈760 题、`_FULL` 备份 ≈8105 题。此时**不传 `--limit` = 跑这 760 题全量**（不是 8105）。VLMEvalKit 只读不带 `_FULL` 的那个文件名。

> 💡 想正式跑分但又嫌「抽样后全量」还是太多，可临时叠 `--limit`：`--limit 100` 就在抽样子集里再截前 100 题。但记住截出来的不分层，仅供试跑。

---

## 数据集速查

| 能力 | 数据集 | 原题量 | 抽样方式 |
|---|---|---|---|
| 基础视力 | `MMBench_DEV_EN_V11` | 4876 行 | 按「题组」分层抽（保 circular 完整），`--target` 控题数 |
| 实景理解 | `MME-RealWorld-Lite` | ~2150 | 按场景/任务分层抽，`--target` 控题数 |
| 极限推理 | `MMMU_Pro_10c` | ~1730 | 按学科分层抽，`--target` 控题数 |
| 视频理解 | `Video-MME` | 2700（900 视频×3） | 按视频抽，`--num-videos` 控视频个数，`--duration short/medium/long` 选时长（不传=全时长）；**不吃 `--target`** |

抽样用固定随机种子（默认 42），**任何机器抽到的都是同一批题**，方便对比不同模型/厂商。

---

## 几个要知道的坑

1. **Video-MME 下载是整包全量视频**（实测：约 90 GB zip + 解压出 ~190 GB，解压时两者并存，**至少备 200~280 GB 空闲**），抽样只省「推理花的钱」，**省不了下载/解压**。跑前先装解码依赖：`pip install av decord`。
   - **缓存默认落在系统盘**（modelscope → `~/.cache/modelscope`），系统盘小的话会在解压时报 `OSError: [Errno 28] No space left on device`。**下载前先把缓存重定向到大盘**，靠环境变量 `MODELSCOPE_CACHE` 指定缓存目录（详见下方「环境变量 MODELSCOPE_CACHE」）。
   - ⚠️ 已下到一半才发现盘满时，别把旧缓存按 `…\modelscope\hub\datasets` 结构搬过去——这版 modelscope 实际下载到 `$MODELSCOPE_CACHE\datasets`（**没有 `hub`**），路径对不上会触发**重新下载**。最稳妥是设好 `MODELSCOPE_CACHE` 后让它重下一份，再删掉旧的废缓存。
2. **视频怎么传给商业 API（两种模式）**。vlmeval 原版在 `video_llm=True` 时把**本地 `.mp4` 路径**当 `video_url` 直发，DashScope/腾讯等只认公网 URL 或 base64，会报 `<400> InvalidParameter: The provided URL does not appear to be valid`。`vlm_compat.py` 的**补丁 4** 已修这个 bug，于是有两种可选模式：
   - **原生整段视频（默认，`video_llm=True`）**：补丁把本地 mp4 → `data:video/mp4;base64,...` 整段发（带 `fps`，默认 2），模型看完整视频、最忠实。抽帧密度调 `vlm_compat.py` 里的 `VIDEO_FPS`。
     - ⚠️ **单个 data-uri 有大小上限**（DashScope = 20 MB；报错 `Exceeded limit on max bytes per data-uri item : 20971520`，并连带 vlmeval 抛 `KeyError: 'choices'`）。base64 膨胀 ~33%，**原始 >~15 MB 的视频会破限**。我们抽的 short 视频里有 18 个超标 → 约 54 题会失败。
     - **解决**：先跑 `python compress_videos.py` 把超标视频压到 ~12 MB（原件备份到 `video/_orig_oversized/`，可 `--restore` 还原；只动超标的）。压完所有视频 base64 后都 <20 MB，全量可跑。
   - **抽帧成图片（省钱，`video_llm=False`）**：按 `nframe`（默认 8）抽帧编码成 base64 图片发，请求体小、token 省，但丢时序细节。改 `run_eval.py` 里视频分支的 `True→False` 即可；想多抽帧在 `eval_config` 加 `'nframe': 16`。
   - ⚠️ **空文本会被腾讯拒（厂商校验差异）**：Video-MME 的系统提示 `SYS` 是**空串**，vlmeval 原样塞进 `content` 发出去。DashScope 容忍，**腾讯（tokenhub）报 `400001 "Invalid request: text content is empty"`** → 连带 vlmeval 抛 `KeyError: 'choices'`。`vlm_compat.py` 补丁 4 已**自动跳过空文本条目**（对两家都安全），无需手动处理。换别的厂商若也卡空文本，是同一回事。
3. **`run_eval.py` 每次跑都会重新推理、重新计费**（输出目录带时间戳，不复用上次结果），别手滑重跑。
4. **思考模式（关键调用事项）**：`run_vlm.py` 里 `FIXED_MODEL` 默认 `thinking={'type': 'disabled'}`（**已关**——单选题开思考又慢又费 token）。想开就改成 `{'type': 'enabled'}`（按目标 API 的 schema）。
   - ⚠️ **必须「平铺」成顶层非具名参数**（直接写 `thinking=...`），**别用 `extra_body={'thinking':...}`**：VLMEvalKit 是手搓 `requests.post`（见 `vlmeval/api/gpt.py`），不解包 `extra_body`，会把它当请求体里一个字面字段塞进去→服务端忽略→**开/关思考静默失效**。`top_p` 同理，平铺才透传。
   - ⚠️ **`temperature` 必须跟思考开关匹配**：kimi-k2.6 思考模式用 `temperature=1.0`、非思考用 `0.6`，传错值服务端直接 **400 拒绝**。开/关思考时记得**同步改 `temperature`**。
5. **换模型/厂商**：在 `run_vlm.py` 的 `VENDORS` 填密钥、`PROFILES` 加一行 `<模型名>_<厂商名>` 即可。
6. **Windows 兼容**：`vlm_compat.py` 自动打了几个补丁；另有两处必须改 `site-packages` 的 bug（`hipho_verifier.py` 的 timeout、`multiple_choice.py` 的 `/tmp`），**重装 vlmeval 后需重打**，细节见 `vlm_compat.py` 顶部注释。

---

## 跑前自检：核对数据集名

不同版本 `ms-vlmeval` 支持的集略有差异，跑前可先核对：
```python
from evalscope.backend.vlm_eval_kit import VLMEvalKitBackendManager
print(VLMEvalKitBackendManager.list_supported_datasets())
```

本机这版 `ms-vlmeval` 共支持 **400 个数据集**，下面 4 个是**脚本默认在用的**（`run_vlm.py` 里 `IMAGE_DATASETS` / `VIDEO_DATASETS`）：

| 能力 | 数据集名 |
|---|---|
| 基础视力 | `MMBench_DEV_EN_V11` ✅ |
| 实景理解 | `MME-RealWorld-Lite` ✅ |
| 极限推理 | `MMMU_Pro_10c` ✅ |
| 视频理解 | `Video-MME` ✅ |

要换别的集，直接把名字填进 `run_eval.py --dataset <名字>`（或改 `run_vlm.py` 的清单）即可。常用近亲：`MMMU_Pro_10c_COT`（带思维链）、`MMMU_Pro_V`（截图版）、`MME-RealWorld`（全量）、`MMBench_DEV_CN_V11`（中文）、`Video-TT` / `LongVideoBench` / `MLVU`（其他视频集）。

<details>
<summary><b>点开看全部 400 个支持的数据集</b>（✅ = 代码默认在用）</summary>

`3DSRBench` · `A-Bench_TEST` · `A-Bench_VAL` · `A-OKVQA` · `A4Bench` · `AesBench_TEST` · `AesBench_VAL` · `AI2D_MINI` · `AI2D_TEST` · `AI2D_TEST_NO_MASK` · `AMBER` · `APhO_2025` · `atomic_dataset` · `AyaVisionBench` · `BLINK` · `BLINK_circular` · `BMMR` · `BMMR_mini` · `CCBench` · `CCOCR` · `CCOCR_DocParsing_DocPhotoChn` · `CCOCR_DocParsing_DocPhotoEng` · `CCOCR_DocParsing_DocScanChn` · `CCOCR_DocParsing_DocScanEng` · `CCOCR_DocParsing_FormulaHandwriting` · `CCOCR_DocParsing_MolecularHandwriting` · `CCOCR_DocParsing_TablePhotoChn` · `CCOCR_DocParsing_TablePhotoEng` · `CCOCR_DocParsing_TableScanChn` · `CCOCR_DocParsing_TableScanEng` · `CCOCR_Kie_ColdCell` · `CCOCR_Kie_ColdSibr` · `CCOCR_Kie_Cord` · `CCOCR_Kie_EphoieScut` · `CCOCR_Kie_Poie` · `CCOCR_Kie_Sroie2019Word` · `CCOCR_MultiLanOcr_Arabic` · `CCOCR_MultiLanOcr_French` · `CCOCR_MultiLanOcr_German` · `CCOCR_MultiLanOcr_Italian` · `CCOCR_MultiLanOcr_Japanese` · `CCOCR_MultiLanOcr_Korean` · `CCOCR_MultiLanOcr_Portuguese` · `CCOCR_MultiLanOcr_Russian` · `CCOCR_MultiLanOcr_Spanish` · `CCOCR_MultiLanOcr_Vietnamese` · `CCOCR_MultiSceneOcr_Cord` · `CCOCR_MultiSceneOcr_Funsd` · `CCOCR_MultiSceneOcr_Hieragent` · `CCOCR_MultiSceneOcr_Iam` · `CCOCR_MultiSceneOcr_Ic15` · `CCOCR_MultiSceneOcr_Inversetext` · `CCOCR_MultiSceneOcr_Totaltext` · `CCOCR_MultiSceneOcr_UgcLaion` · `CCOCR_MultiSceneOcr_ZhDense` · `CCOCR_MultiSceneOcr_ZhDoc` · `CCOCR_MultiSceneOcr_ZhHandwriting` · `CCOCR_MultiSceneOcr_ZhScene` · `CCOCR_MultiSceneOcr_ZhVertical` · `CG-Bench_MCQ_Grounding` · `CG-Bench_MCQ_Grounding_Mini` · `CG-Bench_OpenEnded` · `CG-Bench_OpenEnded_Mini` · `CGAVCounting` · `ChartMimic_v1_customized` · `ChartMimic_v1_direct` · `ChartMimic_v2_customized` · `ChartMimic_v2_customized_1800` · `ChartMimic_v2_customized_600` · `ChartMimic_v2_direct` · `ChartMimic_v2_direct_1800` · `ChartMimic_v2_direct_600` · `ChartMuseum_dev` · `ChartMuseum_test` · `ChartQA_TEST` · `ChartQAPro` · `ChartQAPro_CoT` · `ChartQAPro_PoT` · `CharXiv_descriptive_val` · `CharXiv_reasoning_val` · `CMMMU_VAL` · `CMMU_MCQ` · `COCO_VAL` · `CountBenchQA` · `Creation_MMBench` · `CRPE_EXIST` · `CRPE_RELATION` · `CV-Bench-2D` · `CV-Bench-3D` · `CVQA_EN` · `CVQA_LOC` · `Detailed_Difference` · `DocVQA_TEST` · `DocVQA_VAL` · `DUDE` · `DUDE_MINI` · `DynaMath` · `DynaMath_noprompt` · `EgoExoBench_MCQ` · `electro_dataset` · `EMMA` · `EMMA_COT` · `EuPhO_2024` · `EuPhO_2025` · `F_MA_2024` · `F_MA_2025` · `GMAI-MMBench_TEST` · `GMAI-MMBench_VAL` · `GOBench` · `GQA_TestDev_Balanced` · `GSM8K-V` · `HallusionBench` · `hle` · `HRBench4K` · `HRBench8K` · `InfoVQA_TEST` · `InfoVQA_VAL` · `Instance_Comparison` · `IPhO_2024` · `IPhO_2025` · `K-DTCBench` · `LEGO` · `LEGO_circular` · `LiveMMBench_Creation` · `LiveMMBench_Infographic` · `LiveMMBench_Perception` · `LiveMMBench_Reasoning` · `LiveMMBench_Reasoning_circular` · `LLaVABench` · `LLaVABench_KO` · `LogicVista` · `LongVideoBench` · `M4Bench` · `MATBench` · `MathCanvas-Bench` · `MathVerse_MINI` · `MathVerse_MINI_Text_Dominant` · `MathVerse_MINI_Text_Lite` · `MathVerse_MINI_Vision_Dominant` · `MathVerse_MINI_Vision_Intensive` · `MathVerse_MINI_Vision_Only` · `MathVerse_MINI_Vision_Only_cot` · `MathVision` · `MathVision_MINI` · `MathVista_MINI` · `mechanics_dataset` · `MedqbenchCaption` · `MedqbenchCaption_dev` · `MedqbenchCaption_test` · `MedqbenchMCQ` · `MedqbenchMCQ_dev` · `MedqbenchMCQ_test` · `MedqbenchPairedDescription_dev` · `MedqbenchPairedDescription_test` · `MedXpertQA_MM_test` · `MEGABench` · `MIA-Bench` · `MicroBench` · `MicroVQA` · `MLLMGuard_DS` · `MLVU` · `MLVU_MCQ` · `MLVU_OpenEnded` · `MM-HELIX` · `MM-HELIX_lang` · `MM-IFEval` · `MM-Math` · `MM_NIAH_TEST` · `MM_NIAH_VAL` · `MMAlignBench` · `MMBench` · `MMBench-Video` · `MMBench_CN` · `MMBench_CN_V11` · `MMBench_dev_ar` · `MMBench_DEV_CN` · `MMBench_dev_cn` · `MMBench_DEV_CN_V11` · `MMBench_dev_en` · `MMBench_DEV_EN` · `MMBench_DEV_EN_V11` ✅ · `MMBench_DEV_KO` · `MMBench_dev_pt` · `MMBench_dev_ru` · `MMBench_dev_tr` · `MMBench_TEST_CN` · `MMBench_TEST_CN_V11` · `MMBench_TEST_EN` · `MMBench_TEST_EN_V11` · `MMBench_V11` · `MMBench_V11_MINI` · `MMCR` · `MMDU` · `MME` · `MME-RealWorld` · `MME-RealWorld-CN` · `MME-RealWorld-Lite` ✅ · `MME-Reasoning` · `MME_CoT_TEST` · `MMGenBench-Domain` · `MMGenBench-Test` · `MMLongBench_DOC` · `MMMB` · `MMMB_ar` · `MMMB_cn` · `MMMB_en` · `MMMB_pt` · `MMMB_ru` · `MMMB_tr` · `MMMU_DEV_VAL` · `MMMU_Pro_10c` ✅ · `MMMU_Pro_10c_COT` · `MMMU_Pro_V` · `MMMU_Pro_V_COT` · `MMMU_TEST` · `MMSci_DEV_Captioning_image_only` · `MMSci_DEV_Captioning_with_abs` · `MMSci_DEV_MCQ` · `MMSIBench_circular` · `MMStar` · `MMStar_KO` · `MMStar_MINI` · `MMStar_TR` · `MMT-Bench_ALL` · `MMT-Bench_ALL_MI` · `MMT-Bench_VAL` · `MMT-Bench_VAL_MI` · `MMVet` · `MMVet_Hard` · `MMVMBench` · `MMVP` · `MOAT` · `MovieChat1k` · `MSEarthMCQ` · `MTL_MMBench_DEV` · `MTVQA_TEST` · `MUIRBench` · `MVBench` · `MVBench_MP4` · `MVTamperBench` · `MVTamperBenchEnd` · `MVTamperBenchStart` · `NaturalBenchDataset` · `NBPhO_2024` · `NBPhO_2025` · `OceanOCRBench` · `OCR_Reasoning` · `OCRBench` · `OCRBench_MINI` · `OCRBench_v2` · `OCRVQA_TEST` · `OCRVQA_TESTCORE` · `olmOCRBench` · `OlympiadBench` · `OlympiadBench_CN` · `OlympiadBench_EN` · `Omni3DBench` · `OmniDocBench` · `OmniEarth-Bench` · `OmniMedVQA` · `optics_dataset` · `OST` · `PanMechanics_2024` · `PanMechanics_2025` · `PanPhO_2024` · `PanPhO_2025` · `PathMMU_TEST` · `PathMMU_VAL` · `PathVQA_TEST` · `PathVQA_VAL` · `Physics` · `Physics_blankim` · `PhyX_MC` · `PhyX_mini_MC` · `PhyX_mini_OE` · `PhyX_OE` · `POPE` · `Q-Bench1_TEST` · `Q-Bench1_VAL` · `QBench_Video` · `QBench_Video_MCQ` · `QBench_Video_VQA` · `QSpatial_plus` · `QSpatial_scannet` · `quantum_dataset` · `R-Bench-Dis` · `R-Bench-Ref` · `RealWorldQA` · `ReasonMap-Plus` · `RefCOCO` · `SCAM` · `ScienceQA_TEST` · `ScienceQA_VAL` · `ScreenSpot` · `ScreenSpot_Desktop` · `ScreenSpot_Mobile` · `ScreenSpot_Pro` · `ScreenSpot_Pro_CAD` · `ScreenSpot_Pro_Creative` · `ScreenSpot_Pro_Development` · `ScreenSpot_Pro_Office` · `ScreenSpot_Pro_OS` · `ScreenSpot_Pro_Scientific` · `ScreenSpot_v2` · `ScreenSpot_v2_Desktop` · `ScreenSpot_v2_Mobile` · `ScreenSpot_v2_Web` · `ScreenSpot_Web` · `SEEDBench2` · `SEEDBench2_Plus` · `SEEDBench_IMG` · `SEEDBench_IMG_KO` · `SeePhys` · `SeePhys_vo` · `SFE` · `SFE-zh` · `SimpleVQA` · `SLIDEVQA` · `SLIDEVQA_MINI` · `Spatial457` · `Spatial_Perception` · `SpatialEval` · `State_Comparison` · `State_Invariance` · `StaticEmbodiedBench` · `StaticEmbodiedBench_circular` · `statistics_dataset` · `TableVQABench` · `TallyQA` · `TaskMeAnything_v1_imageqa_random` · `tdbench_cs_depth` · `tdbench_cs_height` · `tdbench_cs_integrity` · `tdbench_cs_zoom` · `tdbench_grounding_rot0` · `tdbench_grounding_rot180` · `tdbench_grounding_rot270` · `tdbench_grounding_rot90` · `tdbench_rot0` · `tdbench_rot180` · `tdbench_rot270` · `tdbench_rot90` · `TempCompass` · `TempCompass_Captioning` · `TempCompass_MCQ` · `TempCompass_YorN` · `TextVQA_VAL` · `TopViewRS` · `TreeBench` · `VCR-Bench` · `VCR_EN_EASY_100` · `VCR_EN_EASY_500` · `VCR_EN_EASY_ALL` · `VCR_EN_HARD_100` · `VCR_EN_HARD_500` · `VCR_EN_HARD_ALL` · `VCR_ZH_EASY_100` · `VCR_ZH_EASY_500` · `VCR_ZH_EASY_ALL` · `VCR_ZH_HARD_100` · `VCR_ZH_HARD_500` · `VCR_ZH_HARD_ALL` · `VDC` · `VGRPBench` · `Video-MME` ✅ · `Video-TT` · `Video_Holmes` · `Video_MMLU_CAP` · `Video_MMLU_QA` · `VisFactor` · `VisFactor_CoT` · `VisFactor_GE` · `VisFactor_GE_CoT` · `VisFactor_GH` · `VisFactor_GH_CoT` · `VisFactor_GN` · `VisFactor_GN_CoT` · `VisOnlyQA-VLMEvalKit` · `VisuLogic` · `VizWiz` · `VL-RewardBench` · `VLM2Bench` · `VLMBias` · `VLMBlind` · `VLRMBench` · `VLRMBench_Foresight` · `VLRMBench_MultiSolution` · `VMCBench_DEV` · `VMCBench_TEST` · `VSR-zeroshot` · `VStarBench` · `WeMath` · `WeMath_COT` · `WildDoc` · `WildVision` · `WorldMedQA-V` · `WorldSense` · `XLRS-Bench-lite` · `ZEROBench` · `ZEROBench_sub`

</details>
