"""Generate a five-model deepseek-v4-flash comparison report (2026-08-20).

Format strictly follows SenseChat-Character-Max-v2-Flash_腾讯云_20260623.html
(no SWE section), with the best value in each metric column highlighted via
the .best CSS class.

Data sources:
- deepseek-v4-flash-0731_aliyun  : today's (2026-08-20) outputs
- deepseek-v4-flash-0731_tencent  : today's (2026-08-20) outputs
- deepseek-v4-flash_aliyun        : values already in the 2026-06 report
- deepseek-v4-flash_tencent       : values already in the 2026-06 report
- deepseek-v4-flash-202605_tencent: values already in the 2026-06 report
"""

import json
import math
from datetime import datetime
from html import escape
from pathlib import Path

ROOT = Path(r"D:\MyCodes\Trae\evalscope")
REPORT_PATH = ROOT / "outputs" / "deepseek_v4_flash_series_comparison_report_20260820.html"

MODEL_ORDER = [
    "deepseek-v4-flash_aliyun",
    "deepseek-v4-flash_tencent",
    "deepseek-v4-flash-202605_tencent",
    "deepseek-v4-flash-0731_aliyun",
    "deepseek-v4-flash-0731_tencent",
]


def read_json(path):
    with Path(path).open("r", encoding="utf-8-sig") as f:
        return json.load(f)


def finite(value):
    return value is not None and math.isfinite(float(value))


def fmt_num(value, digits=2):
    if value is None:
        return ""
    if finite(value):
        return f"{float(value):,.{digits}f}"
    return str(value)


def fmt_pct(value, digits=2):
    if value is None:
        return ""
    return f"{float(value) * 100:.{digits}f}%"


def fmt_pct1(value):
    if value is None:
        return ""
    return f"{float(value) * 100:.1f}%"


def cell(display, raw=None):
    return (display, raw)


class _RawHTML:
    def __init__(self, html):
        self.html = html

    def __str__(self):
        return self.html


def raw_html(html):
    return _RawHTML(html)


def model_name(key):
    return key.rsplit("_", 1)[0]


def load_longalpaca(long_dir):
    rows = {}
    for parallel, number in [(1, 20), (8, 80), (16, 160)]:
        path = long_dir / f"parallel_{parallel}_number_{number}" / "benchmark_summary.json"
        js = read_json(path)
        rows[parallel] = {
            "gen_tps": js["Output Throughput (tok/s)"],
            "rps": js["Req Throughput (req/s)"],
            "success_rate": js["Success Requests"] / js["Total Requests"],
            "latency": js["Avg Latency (s)"],
            "ttft": js["TTFT (ms)"],
            "tpot": js["TPOT (ms)"],
            "avg_out": js["Avg Output Tokens"],
        }
    return rows


def load_metric(path):
    data = read_json(path)
    metric = data["metrics"][0]
    perf = data.get("perf_metrics", {}).get("summary", {})
    latency = perf.get("latency", {})
    throughput = perf.get("throughput", {})
    return {
        "score": metric.get("score"),
        "macro": metric.get("macro_score"),
        "num": metric.get("num") or data.get("num"),
        "latency_mean": latency.get("mean"),
        "latency_p50": latency.get("50%"),
        "latency_p99": latency.get("99%"),
        "output_tps": throughput.get("avg_output_tps"),
    }


def collect_models():
    today = {
        "deepseek-v4-flash-0731_aliyun": {
            "vendor": "阿里云",
            "longalpaca": ROOT / r"outputs\20260820_141559\longalpaca_deepseek-v4-flash-0731_阿里云",
            "cmmlu": ROOT / r"outputs\20260820_115003\reports\deepseek-v4-flash-0731_aliyun\cmmlu.json",
            "humaneval": ROOT / r"outputs\20260820_152756\reports\deepseek-v4-flash-0731_aliyun\humaneval_plus.json",
        },
        "deepseek-v4-flash-0731_tencent": {
            "vendor": "腾讯云",
            "longalpaca": ROOT / r"outputs\20260820_112251\longalpaca_deepseek-v4-flash-0731_腾讯云",
            "cmmlu": ROOT / r"outputs\20260820_115021\reports\deepseek-v4-flash-0731_tencent\cmmlu.json",
            "humaneval": ROOT / r"outputs\20260820_173729\reports\deepseek-v4-flash-0731_tencent\humaneval_plus.json",
        },
    }

    existing = {
        "deepseek-v4-flash_aliyun": {
            "vendor": "阿里云",
            "longalpaca": {
                1: {"gen_tps": 84.37, "rps": 0.1205, "success_rate": 1.0, "latency": 8.30, "ttft": 764.67, "tpot": 10.83},
                8: {"gen_tps": 593.27, "rps": 0.8889, "success_rate": 1.0, "latency": 8.42, "ttft": 729.58, "tpot": 11.43},
                16: {"gen_tps": 1242.65, "rps": 1.9116, "success_rate": 1.0, "latency": 7.90, "ttft": 748.56, "tpot": 10.97},
            },
            "cmmlu": {"score": 0.9170, "macro": 0.9173, "num": 3348, "latency_mean": 10.88, "latency_p50": 4.36, "latency_p99": 124.69, "output_tps": 67.73},
            "humaneval": {"score": 0.9268, "num": 164, "latency_mean": 9.98, "latency_p50": 5.45, "latency_p99": 83.85, "output_tps": 66.38},
        },
        "deepseek-v4-flash_tencent": {
            "vendor": "腾讯云",
            "longalpaca": {
                1: {"gen_tps": 78.66, "rps": 0.1521, "success_rate": 1.0, "latency": 6.53, "ttft": 838.17, "tpot": 11.08},
                8: {"gen_tps": 598.09, "rps": 1.1219, "success_rate": 1.0, "latency": 6.74, "ttft": 902.71, "tpot": 10.92},
                16: {"gen_tps": 1222.60, "rps": 2.3006, "success_rate": 1.0, "latency": 6.55, "ttft": 849.58, "tpot": 10.79},
            },
            "cmmlu": {"score": 0.9087, "macro": 0.9102, "num": 3350, "latency_mean": 9.44, "latency_p50": 4.31, "latency_p99": 107.05, "output_tps": 77.27},
            "humaneval": {"score": 0.9207, "num": 164, "latency_mean": 8.63, "latency_p50": 4.99, "latency_p99": 39.95, "output_tps": 77.65},
        },
        "deepseek-v4-flash-202605_tencent": {
            "vendor": "腾讯云",
            "longalpaca": {
                1: {"gen_tps": 77.40, "rps": 0.1636, "success_rate": 1.0, "latency": 6.07, "ttft": 833.14, "tpot": 11.06},
                8: {"gen_tps": 622.27, "rps": 1.3152, "success_rate": 1.0, "latency": 5.88, "ttft": 710.93, "tpot": 10.97},
                16: {"gen_tps": 1184.72, "rps": 2.5520, "success_rate": 1.0, "latency": 5.74, "ttft": 688.85, "tpot": 10.90},
            },
            "cmmlu": {"score": 0.9164, "macro": 0.9175, "num": 3350, "latency_mean": 9.40, "latency_p50": 4.33, "latency_p99": 98.70, "output_tps": 75.63},
            "humaneval": {"score": 0.9390, "num": 164, "latency_mean": 8.57, "latency_p50": 4.89, "latency_p99": 75.29, "output_tps": 72.08},
        },
    }

    models = {}
    for name in MODEL_ORDER:
        if name in today:
            cfg = today[name]
            models[name] = {
                "vendor": cfg["vendor"],
                "longalpaca": load_longalpaca(cfg["longalpaca"]),
                "cmmlu": load_metric(cfg["cmmlu"]),
                "humaneval": load_metric(cfg["humaneval"]),
            }
        else:
            cfg = existing[name]
            models[name] = {
                "vendor": cfg["vendor"],
                "longalpaca": cfg["longalpaca"],
                "cmmlu": cfg["cmmlu"],
                "humaneval": cfg["humaneval"],
            }
    return models


def td(value, cls=""):
    cls = (cls or "").strip()
    attr = f' class="{cls}"' if cls else ""
    content = value.html if isinstance(value, _RawHTML) else escape(str(value))
    return f"<td{attr}>{content}</td>"


def th(value, cls=""):
    cls = (cls or "").strip()
    attr = f' class="{cls}"' if cls else ""
    return f"<th{attr}>{escape(str(value))}</th>"


def render_table(headers, rows, numeric_cols=None, best_spec=None):
    numeric_cols = set(numeric_cols or [])
    best_cells = set()

    for col, mode in (best_spec or {}).items():
        vals = []
        for row in rows:
            c = row[col]
            v = c[1] if isinstance(c, tuple) else None
            vals.append(v)
        valid = [v for v in vals if v is not None and finite(v)]
        if not valid:
            continue
        target = max(valid) if mode == "max" else min(valid)
        for i, v in enumerate(vals):
            if v is not None and finite(v) and float(v) == float(target):
                best_cells.add((i, col))

    head = "<thead><tr>" + "".join(th(h, "num" if i in numeric_cols else "") for i, h in enumerate(headers)) + "</tr></thead>"
    body = []
    for i, row in enumerate(rows):
        tds = []
        for j, c in enumerate(row):
            display = c[0] if isinstance(c, tuple) else c
            cls = "num" if j in numeric_cols else ""
            if (i, j) in best_cells:
                cls = (cls + " best").strip()
            tds.append(td(display, cls))
        body.append("<tr>" + "".join(tds) + "</tr>")
    return f"<table>{head}<tbody>{''.join(body)}</tbody></table>"


def model_display(name):
    return raw_html(f'<span class="model">{escape(model_name(name))}</span>')


def badge(name, models):
    return raw_html(f'<span class="badge">{escape(model_name(name))}_{escape(models[name]["vendor"])}</span>')


def best_vals(vals, mode):
    valid = [(n, v) for n, v in vals if finite(v)]
    target = max(v for _, v in valid) if mode == "max" else min(v for _, v in valid)
    return [(n, v) for n, v in valid if float(v) == float(target)][0]


def build_html(models):
    rows = {name: (
        models[name]["longalpaca"][1],
        models[name]["longalpaca"][8],
        models[name]["longalpaca"][16],
    ) for name in MODEL_ORDER}

    # Overview table.
    overview_rows = []
    for name in MODEL_ORDER:
        m = models[name]
        r1, r8, r16 = rows[name]
        overview_rows.append([
            m["vendor"],
            model_display(name),
            cell(fmt_num(r1["gen_tps"], 2), r1["gen_tps"]),
            cell(fmt_num(r8["gen_tps"], 2), r8["gen_tps"]),
            cell(fmt_num(r16["gen_tps"], 2), r16["gen_tps"]),
            cell(fmt_num(r16["gen_tps"] / r1["gen_tps"], 2), r16["gen_tps"] / r1["gen_tps"]),
            cell(fmt_num(r16["latency"], 2), r16["latency"]),
            cell(fmt_num(r16["ttft"], 2), r16["ttft"]),
            cell(fmt_pct1(r16["success_rate"]), r16["success_rate"]),
        ])
    overview = render_table(
        ["部署方式", "模型", "并发1吞吐", "并发8吞吐", "并发16吞吐", "16/1 扩展倍率", "并发16平均延迟", "并发16 TTFT", "并发16成功率"],
        overview_rows,
        numeric_cols={2, 3, 4, 5, 6, 7, 8},
        best_spec={2: "max", 3: "max", 4: "max", 5: "max", 6: "min", 7: "min", 8: "max"},
    )

    # Key findings.
    findings = [
        ("LongAlpaca 并发16吞吐最高",
         lambda: best_vals([(n, r[2]["gen_tps"]) for n, r in rows.items()], "max"),
         lambda v: f"{fmt_num(v, 2)} tok/s"),
        ("LongAlpaca 并发扩展倍率最高",
         lambda: best_vals([(n, r[2]["gen_tps"] / r[0]["gen_tps"]) for n, r in rows.items()], "max"),
         lambda v: f"{fmt_num(v, 2)}x"),
        ("LongAlpaca 并发16平均延迟最低",
         lambda: best_vals([(n, r[2]["latency"]) for n, r in rows.items()], "min"),
         lambda v: f"{fmt_num(v, 2)} s"),
        ("LongAlpaca 并发16 TTFT 最低",
         lambda: best_vals([(n, r[2]["ttft"]) for n, r in rows.items()], "min"),
         lambda v: f"{fmt_num(v, 2)} ms"),
        ("C-MMLU 准确率最高",
         lambda: best_vals([(n, models[n]["cmmlu"]["score"]) for n in MODEL_ORDER], "max"),
         lambda v: fmt_pct(v, 2)),
        ("HumanEval Plus Pass@1 最高",
         lambda: best_vals([(n, models[n]["humaneval"]["score"]) for n in MODEL_ORDER], "max"),
         lambda v: fmt_pct(v, 2)),
        ("HumanEval Plus 输出 TPS 最高",
         lambda: best_vals([(n, models[n]["humaneval"]["output_tps"]) for n in MODEL_ORDER], "max"),
         lambda v: f"{fmt_num(v, 2)} tok/s"),
    ]
    findings_rows = ""
    for label, pick, fmt in findings:
        name, value = pick()
        findings_rows += f"<tr><th>{escape(label)}</th><td>{badge(name, models)} {fmt(value)}</td></tr>"

    # LongAlpaca metric tables.
    metric_specs = [
        ("输出吞吐 Gen/s（tok/s）", "gen_tps", 2, "", "max", False),
        ("请求吞吐 RPS", "rps", 4, "", "max", False),
        ("成功率", "success_rate", 1, "%", "max", True),
        ("平均延迟（秒）", "latency", 2, "", "min", False),
        ("TTFT（毫秒）", "ttft", 2, "", "min", False),
        ("TPOT（毫秒）", "tpot", 2, "", "min", False),
    ]
    long_tables = ""
    for title, key, digits, suffix, mode, is_pct in metric_specs:
        trows = []
        for name in MODEL_ORDER:
            m = models[name]
            r1, r8, r16 = rows[name]
            if is_pct:
                vals = [cell(fmt_pct1(r[key]), r[key]) for r in (r1, r8, r16)]
            else:
                vals = [cell(f"{fmt_num(r[key], digits)}{suffix}", r[key]) for r in (r1, r8, r16)]
            trows.append([m["vendor"], model_display(name), *vals])
        long_tables += (
            f'<div class="card"><h3>{escape(title)}</h3>'
            + render_table(["部署方式", "模型", "并发 1", "并发 8", "并发 16"], trows, numeric_cols={2, 3, 4}, best_spec={2: mode, 3: mode, 4: mode})
            + "</div>"
        )

    # CMMLU table.
    cmmlu_rows = []
    for name in MODEL_ORDER:
        m = models[name]
        c = m["cmmlu"]
        cmmlu_rows.append([
            m["vendor"],
            model_display(name),
            "C-MMLU",
            raw_html('<span class="badge">EvalScope</span>'),
            cell(fmt_pct(c["score"], 2), c["score"]),
            cell(fmt_pct(c["macro"], 2), c["macro"]),
            fmt_num(c["num"], 0),
            cell(fmt_num(c["latency_mean"], 2), c["latency_mean"]),
            cell(fmt_num(c["latency_p50"], 2), c["latency_p50"]),
            cell(fmt_num(c["latency_p99"], 2), c["latency_p99"]),
            cell(fmt_num(c["output_tps"], 2), c["output_tps"]),
        ])
    cmmlu_table = render_table(
        ["厂商", "模型", "测试集", "来源", "准确率", "Macro", "样本数", "平均延迟(s)", "P50延迟(s)", "P99延迟(s)", "输出TPS"],
        cmmlu_rows,
        numeric_cols={4, 5, 6, 7, 8, 9, 10},
        best_spec={4: "max", 5: "max", 7: "min", 8: "min", 9: "min", 10: "max"},
    )

    # HumanEval table.
    he_rows = []
    for name in MODEL_ORDER:
        m = models[name]
        c = m["humaneval"]
        he_rows.append([
            m["vendor"],
            model_display(name),
            "HumanEvalPlus",
            raw_html('<span class="badge">EvalScope</span>'),
            cell(fmt_pct(c["score"], 2), c["score"]),
            fmt_num(c["num"], 0),
            cell(fmt_num(c["latency_mean"], 2), c["latency_mean"]),
            cell(fmt_num(c["latency_p50"], 2), c["latency_p50"]),
            cell(fmt_num(c["latency_p99"], 2), c["latency_p99"]),
            cell(fmt_num(c["output_tps"], 2), c["output_tps"]),
        ])
    he_table = render_table(
        ["厂商", "模型", "测试集", "来源", "Pass@1", "样本数", "平均延迟(s)", "P50延迟(s)", "P99延迟(s)", "输出TPS"],
        he_rows,
        numeric_cols={4, 5, 6, 7, 8, 9},
        best_spec={4: "max", 6: "min", 7: "min", 8: "min", 9: "max"},
    )

    compare_objects = "、".join(f"{models[n]['vendor']} {model_name(n)}" for n in MODEL_ORDER)

    generated = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>deepseek-v4-flash 系列五模型对比_20260820</title>
<style>
  :root{{
    --bg:#f6f8fc; --card:#ffffff; --card2:#eef2f9; --line:#dde3ec;
    --txt:#1f2733; --mut:#6b7686; --accent:#2f6bff; --accent2:#0f9d77;
    --warn:#c8821a; --off:#eef2f7;
  }}
  *{{box-sizing:border-box}}
  body{{margin:0;font-family:-apple-system,"Segoe UI","Microsoft YaHei",Roboto,sans-serif;background:var(--bg);color:var(--txt);line-height:1.7;font-size:15px}}
  .wrap{{max-width:1080px;margin:0 auto;padding:0 24px 80px}}
  header{{padding:56px 0 26px;border-bottom:1px solid var(--line);margin-bottom:8px}}
  h1{{font-size:30px;margin:0 0 8px;letter-spacing:0;overflow-wrap:anywhere}}
  .sub{{color:var(--mut);font-size:15px}}
  .toc{{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin:28px 0 8px}}
  .toc a{{display:block;background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px 16px;text-decoration:none;color:var(--txt);transition:.15s;box-shadow:0 1px 3px rgba(20,40,80,.04)}}
  .toc a:hover{{border-color:var(--accent);transform:translateY(-2px);box-shadow:0 6px 18px rgba(47,107,255,.12)}}
  .toc .k{{font-size:12px;color:var(--accent2);font-weight:700;letter-spacing:1px}}
  .toc .t{{font-size:15px;margin-top:4px;font-weight:600}}
  section{{margin:46px 0}}
  h2{{font-size:22px;margin:0 0 4px;display:flex;align-items:center;gap:10px}}
  h2 .num{{display:inline-flex;width:30px;height:30px;align-items:center;justify-content:center;background:linear-gradient(135deg,var(--accent),var(--accent2));border-radius:8px;font-size:14px;color:#fff;font-weight:700}}
  .lead{{color:var(--mut);margin:6px 0 18px}}
  .card{{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:20px 22px;margin:14px 0;box-shadow:0 1px 3px rgba(20,40,80,.04);overflow-x:auto}}
  h3{{font-size:16px;margin:2px 0 10px;color:var(--accent)}}
  table{{width:100%;border-collapse:collapse;margin:12px 0;font-size:13px}}
  th,td{{border:1px solid var(--line);padding:7px 9px;text-align:left;vertical-align:top}}
  th{{background:var(--card2);color:#0c1320;font-weight:700}}
  .num{{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}}
  .model, code{{font-family:"JetBrains Mono",Consolas,monospace;color:#0c1320;font-size:13px}}
  .best{{background:rgba(47,107,255,.13);color:#1647c7;font-weight:700}}
  .note{{border-left:3px solid var(--warn);background:rgba(200,130,26,.08);padding:10px 14px;border-radius:0 8px 8px 0;margin:12px 0;color:#7a5410;font-size:14px}}
  .key{{border-left:3px solid var(--accent2);background:rgba(15,157,119,.08);padding:10px 14px;border-radius:0 8px 8px 0;margin:12px 0;font-size:14px}}
  .badge{{display:inline-block;border:1px solid rgba(15,157,119,.28);background:rgba(15,157,119,.08);color:#08704f;border-radius:999px;padding:2px 8px;font-size:12px;font-weight:700;white-space:nowrap}}
  ul{{padding-left:20px}}
  footer{{margin-top:60px;padding-top:20px;border-top:1px solid var(--line);color:var(--mut);font-size:13px}}
  @media(max-width:760px){{.toc{{grid-template-columns:1fr 1fr}}.wrap{{padding:0 16px 56px}}table{{display:block;overflow-x:auto;white-space:nowrap}}}}
  @media(max-width:560px){{.toc{{grid-template-columns:1fr}}h1{{font-size:24px}}}}
</style>
</head>
<body>
<div class="wrap">
<header><h1>deepseek-v4-flash 系列五模型对比_20260820</h1><div class="sub">在 DeepSeek-V4-Flash 对比报告基础上，纳入 <b>deepseek-v4-flash-0731_阿里云</b> 与 <b>deepseek-v4-flash-0731_腾讯云</b> 的 2026-08-20 最新结果，对比 <b>{compare_objects}</b> 在长文本性能和知识、代码评测上的表现。蓝色单元格表示同表最佳值。</div><div class="toc"><a href="#s1"><div class="k">结论总览</div><div class="t">五模型效果摘要</div></a><a href="#s2"><div class="k">性能压测</div><div class="t">LongAlpaca 单轮</div></a><a href="#s3"><div class="k">效果评测</div><div class="t">知识与代码评测</div></a></div></header>

<section id="s1"><h2><span class="num">1</span>核心结论</h2>
<div class="lead">先看五个模型在 LongAlpaca 并发 1 / 8 / 16 下的横向对比，再展开各项指标。蓝色单元格表示同表最佳值。</div>
<div class="card"><h3>模型与部署方式总览</h3>{overview}</div>
<div class="card"><h3>结论速览</h3><table><tbody>
{findings_rows}
</tbody></table></div></section>

<section id="s2"><h2><span class="num">2</span>LongAlpaca 单轮长文本性能压测</h2>
<div class="lead">目标：对比长上下文单轮生成能力。并发档位为 1 / 8 / 16，请求量分别为 20 / 80 / 160，核心关注输出吞吐、RPS、成功率、平均延迟、TTFT 与 TPOT。</div>
<div class="card"><h3>测试口径</h3><table><tr><th>项目</th><th>口径</th></tr><tr><td>数据集</td><td><b>longalpaca</b>，真实长文本输入</td></tr><tr><td>对比对象</td><td>{compare_objects}</td></tr><tr><td>并发梯队</td><td>1 / 8 / 16</td></tr><tr><td>输出上限</td><td>max_tokens=512</td></tr></table></div>
{long_tables}
</section>

<section id="s3"><h2><span class="num">3</span>知识评测</h2>
<div class="lead">目标：对比五个模型在中文知识与代码生成上的效果及性能。数据来自各自的 EvalScope reports。</div>
<div class="card"><h3>CMMLU 汇总</h3>{cmmlu_table}</div>
<div class="card"><h3>HumanEval Plus 汇总</h3>{he_table}</div></section>

<footer><div><b>数据来源</b></div><ul><li>deepseek-v4-flash_阿里云 / deepseek-v4-flash_腾讯云 / deepseek-v4-flash-202605_腾讯云：原 DeepSeek Flash 对比报告（2026-06）</li><li>deepseek-v4-flash-0731_阿里云 / deepseek-v4-flash-0731_腾讯云：2026-08-20 的 results / outputs</li></ul><div>生成日期：2026-08-20 · {generated}</div></footer>
</div>
</body>
</html>"""


def main():
    models = collect_models()
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(build_html(models), encoding="utf-8")
    print(REPORT_PATH)


if __name__ == "__main__":
    main()
