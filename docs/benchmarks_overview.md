# EvalScope 数据集总览

EvalScope 内置 144 个数据集（benchmark），分布在 `evalscope/benchmarks/` 目录下，每个数据集都有 `_meta/<name>.json` 缓存（含描述、标签、样本统计、论文链接）和对应的 `<name>_adapter.py`。

本文按**原始大类（数据集家族 / 领域来源）**归类。下载链接统一用 EvalScope 实际拉取的 `dataset_id`（默认走 ModelScope 镜像，`https://modelscope.cn/datasets/<id>/summary`），少数 GitHub 仓库保留原始 URL。`格式`列说明任务形态，`内容`列列出该大类下归属的 EvalScope 数据集名（括号内为样本数）。

## 数学推理（Math Reasoning）

| 原始数据集 / 下载链接 | 格式 | 介绍 | EvalScope 内容 |
|---|---|---|---|
| [openai/GSM8K](https://modelscope.cn/datasets/AI-ModelScope/gsm8k/summary) | 数值问答 | 小学多步算术应用题，CoT 推理 | `gsm8k`(1319)、`gsm8k_v`(视觉版,1319) |
| [hendrycks/MATH](https://modelscope.cn/datasets/AI-ModelScope/MATH-500/summary) | 数值问答 | 高中竞赛数学，含 500 题精简版与全量竞赛集 | `math_500`(500)、`competition_math`(5000) |
| [AIME](https://modelscope.cn/datasets/evalscope/aime24/summary) | 数值问答 | 美国数学邀请赛各年份 | `aime24`/`aime25`/`aime26`(各 30)、`amc`(134)、`hmmt25`(30) |
| [Google MGSM](https://modelscope.cn/datasets/evalscope/mgsm/summary) | 数值问答 | GSM8K 的 11 语言翻译版 | `mgsm`(2750)、`poly_math`(9000) |
| [MathQA](https://modelscope.cn/datasets/extraordinarylab/math-qa/summary) | MCQ | 数学应用题+选项 | `math_qa`(2985) |
| [Minerva-Math](https://modelscope.cn/datasets/knoveleng/Minerva-Math/summary) | 数值问答 | 竞赛级数学 | `minerva_math`(272) |
| [DocMath-Eval](https://modelscope.cn/datasets/yale-nlp/DocMath-Eval/summary) | 数值问答 | 长文档数学推理 | `docmath`(800) |
| [Qwen/ProcessBench](https://modelscope.cn/datasets/Qwen/ProcessBench/summary) | 过程判定 | 检查数学解题步骤对错 | `process_bench`(3400) |
| [OlympiadBench](https://modelscope.cn/datasets/AI-ModelScope/OlympiadBench/summary) | 数值/视觉 | 奥赛多模态数学 | `olympiad_bench`(8476) |

## 学科知识 / 选择题（Knowledge & MCQ）

| 原始数据集 / 下载链接 | 格式 | 介绍 | EvalScope 内容 |
|---|---|---|---|
| [cais/MMLU](https://modelscope.cn/datasets/cais/mmlu/summary) | 4 选 1 | 57 学科多任务知识，默认 5-shot | `mmlu`(14042)、`mmlu_pro`(12032)、`mmlu_redux`(5700)、`mmmlu`(多语言,196588) |
| [C-Eval](https://modelscope.cn/datasets/evalscope/ceval/summary) | 4 选 1 | 中文多学科评估 | `ceval`(1346)、`cmmlu`(11582) |
| [SuperGPQA](https://modelscope.cn/datasets/m-a-p/SuperGPQA/summary) | 5 选 1 | 研究生级跨学科 | `super_gpqa`(26529)、`gpqa_diamond`(198) |
| [allenai/ARC](https://modelscope.cn/datasets/allenai/ai2_arc/summary) | 4 选 1 | 科学推理选择题 | `arc`(3548) |
| [HellaSwag](https://modelscope.cn/datasets/evalscope/hellaswag/summary) | 4 选 1 | 常识完形 | `hellaswag`(10042) |
| [CommonsenseQA](https://modelscope.cn/datasets/extraordinarylab/commonsense-qa/summary) | 5 选 1 | 常识推理 | `commonsense_qa`(1221)、`piqa`(1838)、`siqa`(1954) |
| [Winogrande](https://modelscope.cn/datasets/AI-ModelScope/winogrande_val/summary) | 2 选 1 | 共指消解 | `winogrande`(1267) |
| [RACE](https://modelscope.cn/datasets/evalscope/race/summary) | 4 选 1 | 英语阅读理解 | `race`(4934) |
| [SciQ](https://modelscope.cn/datasets/extraordinarylab/sciq/summary) | 4 选 1 | 科学问答 | `sciq`(1000)、`qasc`(926) |
| [LogiQA](https://modelscope.cn/datasets/extraordinarylab/logiqa/summary) | 4 选 1 | 逻辑推理 | `logi_qa`(651)、`musr`(756) |
| [BIG-Bench-Hard](https://modelscope.cn/datasets/evalscope/bbh/summary) | 多种 | 23 项硬推理 | `bbh`(6511) |
| [DROP](https://modelscope.cn/datasets/AI-ModelScope/DROP/summary) | 数值问答 | 离散推理阅读 | `drop`(9536)、`coin_flip`(3333)、`zebralogicbench`(1000) |
| [ArxivRollBench](https://modelscope.cn/datasets/liangzid/arxivrollbench/summary) | MCQ | 论文派生题 | `arxivrollbench`(3254)、`arxivrollbench_full`(245433) |
| [IQuiz](https://modelscope.cn/datasets/AI-ModelScope/IQuiz/summary) | MCQ | 中文常识 | `iquiz`(120)、`maritime_bench`(1888) |
| [TruthfulQA](https://modelscope.cn/datasets/evalscope/truthful_qa/summary) | QA | 真实性/幻觉 | `truthful_qa`(817)、`trivia_qa`(7993) |
| [SimpleQA](https://modelscope.cn/datasets/evalscope/SimpleQA/summary) | 简答 | 事实短答 | `simple_qa`(4326)、`chinese_simpleqa`(3000) |
| [HLE](https://modelscope.cn/datasets/cais/hle/summary) | QA | Humanity's Last Exam | `hle`(2500) |

## 医学 / 专业问答（Medical & Professional QA）

| 原始数据集 / 下载链接 | 格式 | 介绍 | EvalScope 内容 |
|---|---|---|---|
| [PubMedQA](https://modelscope.cn/datasets/extraordinarylab/pubmed-qa/summary) | Yes/No | 生物医学研究问答 | `pubmedqa`(1000) |
| [HealthBench](https://modelscope.cn/datasets/openai-mirror/healthbench/summary) | QA | OpenAI 健康问答 | `health_bench`(3671) |
| [Med-MCQA](https://modelscope.cn/datasets/extraordinarylab/medmcqa/summary) | MCQ | 医学选择题 | `med_mcqa`(4183)、`mri_mcqa`(563)、`biomix_qa`(306) |
| [MusicTrivia](https://modelscope.cn/datasets/extraordinarylab/music-trivia/summary) | MCQ | 音乐问答 | `music_trivia`(512) |

## 指令遵循 / 竞技场（Instruction Following & Arena）

| 原始数据集 / 下载链接 | 格式 | 介绍 | EvalScope 内容 |
|---|---|---|---|
| [IFEval](https://modelscope.cn/datasets/opencompass/ifeval/summary) | 生成 | 可验证指令约束 | `ifeval`(541)、`ifbench`(300) |
| [Multi-IF](https://modelscope.cn/datasets/facebook/Multi-IF/summary) | 生成 | 多语言多轮指令 | `multi_if`(4501)、`eq_bench`(171) |
| [AlpacaEval2.0](https://modelscope.cn/datasets/AI-ModelScope/alpaca_eval/summary) | Arena | LLM 比胜率 | `alpaca_eval`(805)、`arena_hard`(500) |
| [CL-bench](https://modelscope.cn/datasets/tencent-community/CL-bench/summary) | 生成 | 指令+推理 | `cl_bench`(1899) |
| [HaluEval](https://modelscope.cn/datasets/evalscope/HaluEval/summary) | Yes/No | 幻觉检测 | `halueval`(30000) |

## 代码生成（Code Generation）

| 原始数据集 / 下载链接 | 格式 | 介绍 | EvalScope 内容 |
|---|---|---|---|
| [openai/HumanEval](https://modelscope.cn/datasets/opencompass/humaneval/summary) | 函数补全 | 164 题 Python，pass@1 | `humaneval`(164)、`humaneval_plus`(164) |
| [Google MBPP](https://modelscope.cn/datasets/google-research-datasets/mbpp/summary) | 函数补全 | 974 题 Python | `mbpp`(500)、`mbpp_plus`(378) |
| [MultiPL-E](https://modelscope.cn/datasets/evalscope/MultiPL-E/summary) | 函数补全 | 多语言移植版 | `multiple_humaneval`(2864)、`multiple_mbpp`(6987) |
| [LiveCodeBench](https://modelscope.cn/datasets/evalscope/livecodebench_code_generation_lite_parquet/summary) | 函数补全 | 滚动更新的竞赛编程 | `live_code_bench`(1055) |
| [SciCode](https://modelscope.cn/datasets/evalscope/SciCode/summary) | 代码+执行 | 科学计算编程 | `scicode`(65) |
| [Terminal-Bench](https://hub.harborframework.com/datasets/terminal-bench/terminal-bench-2/latest) | 终端任务 | 真实 shell 任务 | `terminal_bench_v2`、`terminal_bench_v2_1` |

## 软件工程 Agent（SWE-bench 家族）

| 原始数据集 / 下载链接 | 格式 | 介绍 | EvalScope 内容 |
|---|---|---|---|
| [princeton-nlp/SWE-bench_Lite](https://modelscope.cn/datasets/princeton-nlp/SWE-bench_Lite/summary) | 仓库修复 | GitHub issue 修复 | `swe_bench_lite`、`swe_bench_lite_agentic`(300) |
| [princeton-nlp/SWE-bench_Verified](https://modelscope.cn/datasets/princeton-nlp/SWE-bench_Verified/summary) | 仓库修复 | 人工校验版 | `swe_bench_verified`、`swe_bench_verified_agentic`(500)、`swe_bench_verified_mini*`(50) |
| [ScaleAI/SWE-bench_Pro](https://modelscope.cn/datasets/ScaleAI/SWE-bench_Pro/summary) | 仓库修复 | 专业级 | `swe_bench_pro`(731) |

## 多模态理解（VLM 综合知识）

| 原始数据集 / 下载链接 | 格式 | 介绍 | EvalScope 内容 |
|---|---|---|---|
| [MMMU](https://modelscope.cn/datasets/AI-ModelScope/MMMU/summary) | MCQ/QA | 大学科多模态 | `mmmu`(900)、`mmmu_pro`(1730) |
| [MMBench](https://modelscope.cn/datasets/lmms-lab/MMBench/summary) | MCQ/QA | 多模态能力综合 | `mm_bench`(8658)、`cc_bench`(2040) |
| [MMStar](https://modelscope.cn/datasets/evalscope/MMStar/summary) | MCQ | 去偏多模态推理 | `mm_star`(1500) |
| [CMMMU](https://modelscope.cn/datasets/lmms-lab/CMMMU/summary) | QA | 中文多模态 | `cmmmu`(900)、`cmmu`(1800) |
| [A-OKVQA](https://modelscope.cn/datasets/HuggingFaceM4/A-OKVQA/summary) | MCQ | 视觉常识问答 | `a_okvqa`(1145) |
| [ScienceQA](https://modelscope.cn/datasets/AI-ModelScope/ScienceQA/summary) | MCQ | 多模态科学 | `science_qa`(4241) |
| [AI2D](https://modelscope.cn/datasets/lmms-lab/ai2d/summary) | MCQ | 科学图示问答 | `ai2d`(3088) |
| [RealWorldQA](https://modelscope.cn/datasets/lmms-lab/RealWorldQA/summary) | QA | 真实世界图像 | `real_world_qa`(765) |
| [SimpleVQA](https://modelscope.cn/datasets/m-a-p/SimpleVQA/summary) | QA | 简单视觉问答 | `simple_vqa`(2025)、`micro_vqa`(1042) |
| [MIA-Bench](https://modelscope.cn/datasets/lmms-lab/MIA-Bench/summary) | 生成 | 多模态指令遵循 | `mia_bench`(400) |
| [BLINK](https://modelscope.cn/datasets/evalscope/BLINK/summary) | MCQ | 视觉基础任务 | `blink`(1901) |
| [SEED-Bench-2-Plus](https://modelscope.cn/datasets/evalscope/SEED-Bench-2-Plus/summary) | MCQ | 多模态综合 | `seed_bench_2_plus`(2277) |
| [ZeroBench](https://modelscope.cn/datasets/evalscope/zerobench/summary) | QA | 低成本多模态 | `zerobench`(100) |

## 视觉数学 / 图表 / 文档（Visual Math / Chart / Doc）

| 原始数据集 / 下载链接 | 格式 | 介绍 | EvalScope 内容 |
|---|---|---|---|
| [MathVista](https://modelscope.cn/datasets/evalscope/MathVista/summary) | MCQ | 视觉数学综合 | `math_vista`(1000)、`math_vision`(3040)、`math_verse`(3940)、`visulogic`(1000) |
| [DocVQA](https://modelscope.cn/datasets/lmms-lab/DocVQA/summary) | QA | 文档问答 | `docvqa`(5349)、`infovqa`(2801) |
| [ChartQA](https://modelscope.cn/datasets/lmms-lab/ChartQA/summary) | QA | 图表问答 | `chartqa`(2500) |
| [OCRBench](https://modelscope.cn/datasets/evalscope/OCRBench/summary) | QA | 文本识别 | `ocr_bench`(1000)、`ocr_bench_v2`(10000)、`omni_doc_bench`(981) |

## 视频 / 全模态（Video & Omni）

| 原始数据集 / 下载链接 | 格式 | 介绍 | EvalScope 内容 |
|---|---|---|---|
| [MVBench](https://modelscope.cn/datasets/PKU-Alignment/MVBench/summary) | MCQ | 视频理解 | `mvbench`(4000) |
| [Video-MME-v2](https://modelscope.cn/datasets/MME-Benchmarks/Video-MME-v2/summary) | MCQ | 视频综合 | `videomme_v2`(3200) |
| [OmniBench](https://modelscope.cn/datasets/m-a-p/OmniBench/summary) | MCQ | 全模态 | `omni_bench`(1142)、`tir_bench`(1215) |

## 多模态幻觉 / 定位（Hallucination & Grounding）

| 原始数据集 / 下载链接 | 格式 | 介绍 | EvalScope 内容 |
|---|---|---|---|
| [POPE](https://modelscope.cn/datasets/lmms-lab/POPE/summary) | Yes/No | 物体存在幻觉 | `pope`(9000) |
| [HallusionBench](https://modelscope.cn/datasets/lmms-lab/HallusionBench/summary) | Yes/No | 视觉幻觉 | `hallusion_bench`(951) |
| [V*Bench](https://modelscope.cn/datasets/lmms-lab/vstar-bench/summary) | MCQ | 视觉指向 | `vstar_bench`(191) |
| [RefCOCO](https://modelscope.cn/datasets/lmms-lab/RefCOCO/summary) | 生成 | 指代表达分割 | `refcoco`(17596) |

## Agent / 函数调用（Agent & Function Calling）

| 原始数据集 / 下载链接 | 格式 | 介绍 | EvalScope 内容 |
|---|---|---|---|
| [GAIA](https://modelscope.cn/datasets/gaia-benchmark/GAIA/summary) | 多轮 | 通用助手多步推理 | `gaia`(165) |
| [BFCL](https://modelscope.cn/datasets/AI-ModelScope/bfcl_v3/summary) | 函数调用 | Berkeley 函数调用排行榜 | `bfcl_v3`(4441)、`bfcl_v4`(5106) |
| [General-FC](https://modelscope.cn/datasets/evalscope/GeneralFunctionCall-Test/summary) | 函数调用 | 自定义函数调用 | `general_fc`(2000) |
| [Vendor-Verifier](https://modelscope.cn/datasets/evalscope/K2VendorVerifier/summary) | 参数合规 | 厂商模型参数遵循 | `k2_verifier`(2000)、`kimi_verifier`(55)、`minimax_verifier`(102) |
| [τ-bench](https://github.com/sierra-research/tau-bench) | 多轮 | 多轮工具调用 | `tau_bench`、`tau2_bench`(278)、`tau3_bench`(375) |
| [ToolBench-Static](https://modelscope.cn/datasets/AI-ModelScope/ToolBench-Static/summary) | 函数调用 | 工具调用推理 | `tool_bench`(2369) |

## 音频 / 语音（Audio & Speech）

| 原始数据集 / 下载链接 | 格式 | 介绍 | EvalScope 内容 |
|---|---|---|---|
| [FLEURS](https://modelscope.cn/datasets/lmms-lab/fleurs/summary) | ASR/分类 | 多语言语音 | `fleurs`(2411) |
| [LibriSpeech](https://modelscope.cn/datasets/lmms-lab/Librispeech-concat/summary) | ASR | 英文朗读 | `librispeech`(87)、`torgo`(5553,病理语音) |
| [AIR-Bench](https://modelscope.cn/datasets/evalscope/AIR-Bench/summary) | MCQ/对话 | 音频理解 | `air_bench_foundation`(21426)、`air_bench_chat`(2200) |

## 机器翻译（Machine Translation）

| 原始数据集 / 下载链接 | 格式 | 介绍 | EvalScope 内容 |
|---|---|---|---|
| [WMT2024++](https://modelscope.cn/datasets/extraordinarylab/wmt24pp/summary) | 翻译 | 多语言翻译评测 | `wmt24pp`(52800) |

## 命名实体识别（NER）

| 原始数据集 / 下载链接 | 格式 | 介绍 | EvalScope 内容 |
|---|---|---|---|
| [extraordinarylab 系列](https://modelscope.cn/datasets/extraordinarylab/conll2003/summary) | 序列标注 | 通用/生物医学/推特等 NER | `anat_em`、`bc2gm`、`bc4chemd`、`bc5cdr`、`broad_twitter_corpus`、`conll2003`、`conllpp`、`copious`、`cross_ner`、`fin_ner`、`genia_ner`、`harvey_ner`、`jnlpba`、`jnlpba_rare`、`mit_movie_trivia`、`mit_restaurant`、`multi_nerd`(167993)、`ncbi`、`ontonotes5`、`tweebank_ner`、`tweet_ner_7`、`wnut2017` |

## 长上下文 / 检索（Long Context & Retrieval）

| 原始数据集 / 下载链接 | 格式 | 介绍 | EvalScope 内容 |
|---|---|---|---|
| [FRAMES](https://modelscope.cn/datasets/iic/frames/summary) | QA | 多跳检索+长上下文 | `frames`(824)、`aa_lcr`(100) |
| [LongBench-v2](https://modelscope.cn/datasets/ZhipuAI/LongBench-v2/summary) | MCQ | 长文本理解 | `longbench_v2`(503) |
| [Needle-in-a-Haystack](https://modelscope.cn/datasets/AI-ModelScope/Needle-in-a-Haystack-Corpus/summary) | 抽取 | 大海捞针 | `needle_haystack`(200) |
| [OpenAI MRCR](https://modelscope.cn/datasets/openai-mirror/mrcr/summary) | 抽取 | 多轮多文档检索 | `openai_mrcr`(2400) |

## AIGC 文生图 / 图像编辑（Text-to-Image & Editing）

| 原始数据集 / 下载链接 | 格式 | 介绍 | EvalScope 内容 |
|---|---|---|---|
| [T2V-Eval-Prompts](https://modelscope.cn/datasets/AI-ModelScope/T2V-Eval-Prompts/summary) | 文生图 | 通用文生图提示集 | `hpdv2`(3200)、`tifa160`(160)、`genai_bench`(1600)、`evalmuse`(199) |
| [GEdit-Bench](https://modelscope.cn/datasets/stepfun-ai/GEdit-Bench/summary) | 图像编辑 | 细粒度图像编辑 | `gedit`(606) |

## 叙事分类（Drivelology）

| 原始数据集 / 下载链接 | 格式 | 介绍 | EvalScope 内容 |
|---|---|---|---|
| [drivel-hub](https://modelscope.cn/datasets/extraordinarylab/drivel-hub/summary) | 二分类/MCQ/写作 | 叙事质量评估 | `drivel_binary`(1200)、`drivel_multilabel`(600)、`drivel_selection`(1200)、`drivel_writing`(600) |

## 通用自定义占位（Custom，需自行提供数据）

| 原始数据集 / 下载链接 | 格式 | 介绍 | EvalScope 内容 |
|---|---|---|---|
| 本地/自定义 | 多种 | 占位适配器，加载用户自有数据 | `data_collection`、`general_arena`、`general_mcq`、`general_qa`、`general_t2i`、`general_vmcq`、`general_vqa` |

---

## 使用说明

- 上表下载链接即 EvalScope 在 `dataset_id` 中记录的原始来源，默认从 ModelScope 拉取（`https://modelscope.cn/datasets/<id>/summary`）；少数为 GitHub 仓库（BFCL-v4、τ-bench、Terminal-Bench）。
- 在代码中用 `from evalscope import run_task, TaskConfig; run_task(TaskConfig(model=..., datasets=['<name>']))` 即可触发对应适配器自动下载；CLI 用 `evalscope eval --datasets <name>`。
- 想看某个数据集的 prompt 模板 / 子集 / 统计，读 `evalscope/benchmarks/_meta/<name>.json`；适配器源码在 `evalscope/benchmarks/<name>/<name>_adapter.py`。
- 注册机制与新增数据集流程见 `AGENTS.md` 的「Adding a benchmark」与 `evalscope/api/registry.py`。
