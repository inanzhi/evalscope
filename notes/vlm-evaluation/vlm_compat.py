"""
vlm_compat.py —— VLM 评测的运行时兼容补丁集中处。

任何要 import evalscope / vlmeval 的脚本，都必须在最顶部先 `import vlm_compat`。
它解决四件「本机环境 + ms-vlmeval」不匹配、不打补丁就跑不通 / 抽样被覆盖 / 视频传不上去的问题：

1) transformers>=5 删掉了 AutoModelForVision2Seq（改名 AutoModelForImageTextToText），
   而本机 ms-vlmeval 的部分本地模型 wrapper 仍按旧名 eager 导入 → `import vlmeval` 直接 ImportError。
   API 模式根本用不到这些本地模型，把旧名别名回去即可。

2) 图片集：抽样改写 TSV 后，其 md5 与内置常量不符，VLMEvalKit 会「重新下载全量、覆盖抽样」
   （image_base.ImageBaseDataset.prepare_tsv）。这里改成「本地已存在 TSV 就直接采用」，
   让抽样结果稳定生效。

3) 视频集 Video-MME：TSV 存在 HF/modelscope 缓存里，抽样后 md5 不符会「从 parquet 重新生成
   全量 TSV、覆盖抽样」（videomme 内的 check_integrity / generate_tsv）。这里让 check_integrity
   对 Video-MME.tsv 的 md5 比对恒等通过（其它文件仍走真实 md5），从而保留抽样。

4) 视频集 video_llm=True 时，vlmeval 把本地 .mp4 路径当 video_url 直发，商业 API（DashScope/腾讯）
   只认公网 URL 或 base64 → 报 <400> "invalid URL"。这里重写 OpenAIWrapper.prepare_itlist 的 video
   分支：本地 mp4 → data:video/mp4;base64,... 整段发（带官方 fps 字段），让原生整段视频真正可用。
   图片分支与原版逐字一致，不影响图片集；仅 video_llm=True 时触发。
   同时顺手跳过【空文本】条目：Video-MME 的系统提示 SYS 是空串，腾讯等会报 400001 "text content
   is empty"（DashScope 容忍，腾讯不容忍），连带 vlmeval 抛 KeyError: 'choices'。丢掉空串对两家都安全。

注意：补丁 1~3 只影响「是否信任本地 TSV / 是否重新下载」，补丁 4 只改视频的传输编码，均不改评测逻辑、不影响分数。
另有两处 import/运行期的 Windows bug 必须直接改 site-packages（不在本文件，重装 vlmeval 后需重打）：
  - vlmeval/dataset/utils/hipho_verifier.py   timeout 装饰器在非 POSIX 返回 None
  - vlmeval/dataset/utils/multiple_choice.py  硬编码 /tmp（Windows 无此目录）
"""

# Windows 控制台默认 GBK，打印 ✅/❌ 等 emoji 会 UnicodeEncodeError，这里切到 UTF-8 兜底
import sys

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

# --- 补丁 1：transformers 别名，必须在 import vlmeval 之前 ---
import transformers

if not hasattr(transformers, 'AutoModelForVision2Seq') and hasattr(transformers, 'AutoModelForImageTextToText'):
    transformers.AutoModelForVision2Seq = transformers.AutoModelForImageTextToText

# 下面要 import vlmeval 子模块来打补丁（别名已先做完，导入不会再报错）
from vlmeval.dataset import image_base as _image_base
from vlmeval.dataset import videomme as _videomme

# --- 补丁 2：图片集信任本地 TSV（抽样后不再因 md5 不符而重下全量） ---
_orig_prepare_tsv = _image_base.ImageBaseDataset.prepare_tsv


def _prepare_tsv_trust_local(self, url, file_md5=None):
    # 本地已存在 TSV（含抽样版本）时一律采用本地版本；仅当本地缺失才下载。
    return _orig_prepare_tsv(self, url, file_md5=None)


_image_base.ImageBaseDataset.prepare_tsv = _prepare_tsv_trust_local

# --- 补丁 3：Video-MME 信任本地 TSV（抽样后不再被 parquet 重新生成覆盖） ---
_real_md5 = _videomme.md5


def _md5_trust_videomme(path, *args, **kwargs):
    # 对 Video-MME.tsv 的 md5 校验恒等通过，避免抽样被覆盖；其它文件仍返回真实 md5。
    try:
        if str(path).replace('\\', '/').endswith('Video-MME.tsv'):
            return _videomme.VideoMME.MD5
    except Exception:
        pass
    return _real_md5(path, *args, **kwargs)


_videomme.md5 = _md5_trust_videomme

# --- 补丁 4：视频走原生 video_url（本地 mp4 → base64 Data URL），让 video_llm=True 真正可用 ---
# vlmeval 原版在 video 分支只把【本地路径】塞进 url（gpt.py: dict(url=msg['value'])），
# DashScope/腾讯等商业 API 只认公网 URL 或 base64 Data URL → 报 <400> "invalid URL"。
# 这里重写 OpenAIWrapper.prepare_itlist：video 分支改成官方方法——读本地文件 base64 成
# data:video/mp4;base64,...，并按官方格式带上同级 fps 字段。图片分支与原版逐字一致，不影响图片集。
# 仅当 video_llm=True（数据集发 type='video' 的本地 mp4 路径）时此分支才触发。
import base64 as _base64

import numpy as _np
from vlmeval.api import gpt as _gpt

# 视频抽帧率（DashScope video_url 的 fps 字段）。调大=时序更密、更准，但请求体更大、更费 token。
VIDEO_FPS = 2


def _prepare_itlist_video_dataurl(self, inputs):
    assert _np.all([isinstance(x, dict) for x in inputs])
    has_media = _np.sum([x['type'] in ['image', 'video'] for x in inputs])
    if not has_media:
        assert all(x['type'] == 'text' for x in inputs)
        return '\n'.join(x['value'] for x in inputs)
    content_list = []
    for msg in inputs:
        if msg['type'] == 'text':
            # 跳过空文本：Video-MME 的系统提示 SYS 是空串，腾讯等会报 400001 "text content is empty"
            # （DashScope 容忍空文本，腾讯不容忍）。空串无意义，丢掉对两家都安全。
            if not str(msg['value']).strip():
                continue
            content_list.append(dict(type='text', text=msg['value']))
        elif msg['type'] == 'image':  # 与原版逐字一致
            from PIL import Image
            img = Image.open(msg['value'])
            b64 = _gpt.encode_image_to_base64(img, target_size=self.img_size)
            content_list.append(dict(
                type='image_url',
                image_url=dict(url=f'data:image/jpeg;base64,{b64}', detail=self.img_detail)))
        elif msg['type'] == 'video':  # ← 改这里：本地 mp4 → base64 Data URL + fps
            with open(msg['value'], 'rb') as f:
                vb64 = _base64.b64encode(f.read()).decode('utf-8')
            content_list.append(dict(
                type='video_url',
                video_url=dict(url=f'data:video/mp4;base64,{vb64}'),
                fps=VIDEO_FPS))
    return content_list


_gpt.OpenAIWrapper.prepare_itlist = _prepare_itlist_video_dataurl
