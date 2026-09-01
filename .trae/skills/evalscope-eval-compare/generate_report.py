#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Generate an HTML comparison report from a runs_manifest.json.

Reads the manifest produced by ``run_eval_compare.py`` and renders a report in
the same style as outputs/glm-5.2_aliyun_vs_huoshan_comparison_report_20260828.html.
Sections are rendered only when the corresponding data is present:

    1. 核心结论        (LongAlpaca 并发 1/8/16 汇总)
    2. LongAlpaca 单轮 (输出吞吐 / RPS / 延迟 / TTFT / TPOT / 平均输出 Token)
    3. SWE-Smith 多轮  (请求级 + Trace 级缓存命中)
    4. 知识与代码      (CMMLU + HumanEval Plus)

Usage:
    python generate_report.py --manifest runs_manifest.json
    python generate_report.py --manifest runs_manifest.json --output outputs/foo.html
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime
from html import escape
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]

CSS = """
  :root{
    --bg:#f6f8fc; --card:#ffffff; --card2:#eef2f9; --line:#dde3ec;
    --txt:#1f2733; --mut:#6b7686; --accent:#2f6bff; --accent2:#0f9d77;
    --warn:#c8821a; --best:#e9f8f2; --bestText:#08704f;
  }
  *{box-sizing:border-box}
  body{margin:0;font-family:-apple-system,"Segoe UI","Microsoft YaHei",Roboto,sans-serif;background:var(--bg);color:var(--txt);line-height:1.7;font-size:15px}
  .wrap{max-width:1080px;margin:0 auto;padding:0 24px 80px}
  header{padding:56px 0 26px;border-bottom:1px solid var(--line);margin-bottom:8px}
  h1{font-size:30px;margin:0 0 8px;letter-spacing:.5px}
  .sub{color:var(--mut);font-size:15px}
  .toc{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:28px 0 8px}
  .toc a{display:block;background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px 16px;text-decoration:none;color:var(--txt);transition:.15s;box-shadow:0 1px 3px rgba(20,40,80,.04)}
  .toc a:hover{border-color:var(--accent);transform:translateY(-2px);box-shadow:0 6px 18px rgba(47,107,255,.12)}
  .toc .k{font-size:12px;color:var(--accent2);font-weight:700;letter-spacing:1px}
  .toc .t{font-size:15px;margin-top:4px;font-weight:600}
  section{margin:46px 0}
  h2{font-size:22px;margin:0 0 4px;display:flex;align-items:center;gap:10px}
  h2 .num{display:inline-flex;width:30px;height:30px;align-items:center;justify-content:center;background:linear-gradient(135deg,var(--accent),var(--accent2));border-radius:8px;font-size:14px;color:#fff;font-weight:700}
  .lead{color:var(--mut);margin:6px 0 18px}
  .card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:20px 22px;margin:14px 0;box-shadow:0 1px 3px rgba(20,40,80,.04);overflow-x:auto}
  h3{font-size:16px;margin:2px 0 10px;color:var(--accent)}
  table{width:100%;border-collapse:collapse;margin:12px 0;font-size:13px}
  th,td{border:1px solid var(--line);padding:4px 6px;text-align:left;vertical-align:top;white-space:nowrap}
  th{background:var(--card2);color:#0c1320;font-weight:700}
  .num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
  .muted,.hint{color:var(--mut);font-size:13px}
  .model{font-family:"JetBrains Mono",Consolas,monospace;color:#0c1320;font-size:13px}
  .best{background:rgba(47,107,255,.13);color:#1647c7;font-weight:700}
  .note{border-left:3px solid var(--warn);background:rgba(200,130,26,.08);padding:10px 14px;border-radius:0 8px 8px 0;margin:12px 0;color:#7a5410;font-size:14px}
  .key{border-left:3px solid var(--accent2);background:rgba(15,157,119,.08);padding:10px 14px;border-radius:0 8px 8px 0;margin:12px 0;font-size:14px}
  .badge{display:inline-block;border:1px solid rgba(15,157,119,.28);background:rgba(15,157,119,.08);color:#08704f;border-radius:999px;padding:2px 8px;font-size:12px;font-weight:700}
  .two{display:grid;grid-template-columns:1fr 1fr;gap:14px}
  .chart{width:100%;max-width:100%;border:1px solid var(--line);border-radius:12px;background:#fff;margin:12px 0}
  ul{margin:8px 0 0 20px;padding:0}
  @media(max-width:760px){.toc,.two{grid-template-columns:1fr 1fr}.wrap{padding:0 16px 56px}table{display:block;overflow-x:auto;white-space:nowrap}}
  @media(max-width:560px){.toc,.two{grid-template-columns:1fr}}
  footer{margin-top:60px;padding-top:20px;border-top:1px solid var(--line);color:var(--mut);font-size:13px}
"""


# --------------------------------------------------------------------------- #
# Formatting helpers (ported from scripts/perf/generate_deepseek_v4_flash_0731_report.py)
# --------------------------------------------------------------------------- #
def finite(value: Any) -> bool:
    return value is not None and math.isfinite(float(value))


def fmt_num(value: Any, digits: int = 2) -> str:
    if value is None:
        return ""
    if finite(value):
        return f"{float(value):,.{digits}f}"
    return str(value)


def fmt_pct(value: Any, digits: int = 2) -> str:
    if value is None:
        return ""
    return f"{float(value) * 100:.{digits}f}%"


def fmt_pct1(value: Any) -> str:
    if value is None:
        return ""
    return f"{float(value) * 100:.1f}%"


def fmt_pct_raw(value: Any, digits: int = 1) -> str:
    if value is None:
        return ""
    return f"{float(value):.{digits}f}%"


def cell(display: Any, raw: Any = None) -> tuple:
    return (display, raw)


class _RawHTML:
    def __init__(self, html: str):
        self.html = html

    def __str__(self) -> str:
        return self.html


def raw_html(html: str) -> _RawHTML:
    return _RawHTML(html)


# --------------------------------------------------------------------------- #
# Data loading
# --------------------------------------------------------------------------- #
def read_json(path: str | Path) -> dict:
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def load_metric(path: str | None) -> dict | None:
    if not path or not Path(path).exists():
        return None
    try:
        data = read_json(path)
        metric = data['metrics'][0]
        perf = data.get('perf_metrics', {}).get('summary', {})
        latency = perf.get('latency', {})
        throughput = perf.get('throughput', {})
        usage = perf.get('usage', {})
        return {
            'score': metric.get('score'),
            'macro': metric.get('macro_score'),
            'num': metric.get('num') or data.get('num'),
            'latency_mean': latency.get('mean'),
            'latency_p50': latency.get('50%'),
            'latency_p90': latency.get('90%'),
            'latency_p99': latency.get('99%'),
            'output_tps': throughput.get('avg_output_tps'),
            'avg_output_tokens': (usage.get('output_tokens') or {}).get('mean'),
        }
    except (KeyError, IndexError, TypeError, json.JSONDecodeError):
        return None


def load_longalpaca(long_dir: str | None) -> dict | None:
    if not long_dir or not Path(long_dir).exists():
        return None
    try:
        rows = {}
        for parallel, number in [(1, 20), (8, 80), (16, 160)]:
            js = read_json(Path(long_dir) / f'parallel_{parallel}_number_{number}' / 'benchmark_summary.json')
            rows[parallel] = {
                'gen_tps': js['Output Throughput (tok/s)'],
                'rps': js['Req Throughput (req/s)'],
                'latency': js['Avg Latency (s)'],
                'ttft': js['TTFT (ms)'],
                'tpot': js['TPOT (ms)'],
                'avg_out': js['Avg Output Tokens'],
            }
        return rows
    except (KeyError, json.JSONDecodeError, FileNotFoundError):
        return None


def load_swe(swe_dir: str | None) -> dict | None:
    if not swe_dir or not Path(swe_dir).exists():
        return None
    try:
        b = read_json(Path(swe_dir) / 'benchmark_summary.json')
        t = read_json(Path(swe_dir) / 'trace_summary.json')
        metrics = {r['metric']: r for r in t.get('rows', [])}
        return {
            'requests': b['Total Requests'],
            'success_rate': b['Success Requests'] / b['Total Requests'],
            'gen_tps': b['Output Throughput (tok/s)'],
            'latency': b['Avg Latency (s)'],
            'ttft': b['TTFT (ms)'],
            'tpot': b['TPOT (ms)'],
            'kv': b.get('KV Cache Hit Rate (%)'),
            'first_ttft': b.get('First-Turn TTFT (ms)'),
            'sub_ttft': b.get('Subsequent-Turn TTFT (ms)'),
            'decoded_iter': b.get('Decoded Tok/Iter'),
            'spec_accept': b.get('Spec. Accept Rate'),
            'n_traces': t.get('n_traces'),
            'lat_mean': metrics.get('Latency (s)', {}).get('mean'),
            'lat_p50': metrics.get('Latency (s)', {}).get('p50'),
            'lat_p99': metrics.get('Latency (s)', {}).get('p99'),
            'first_ttft_mean': metrics.get('First-Turn TTFT (s)', {}).get('mean'),
            'ttfat_mean': metrics.get('TTFAT (s)', {}).get('mean'),
            'decode_tps_mean': metrics.get('Decode TPS', {}).get('mean'),
            'decode_tps_p99': metrics.get('Decode TPS', {}).get('p99'),
            'cache_mean': metrics.get('Cache Hit Rate (%)', {}).get('mean'),
            'cache_p50': metrics.get('Cache Hit Rate (%)', {}).get('p50'),
            'cache_p99': metrics.get('Cache Hit Rate (%)', {}).get('p99'),
            'eligible_mean': metrics.get('Eligible Cache Hit Rate (%)', {}).get('mean'),
        }
    except (KeyError, IndexError, ZeroDivisionError, json.JSONDecodeError, FileNotFoundError):
        return None


# --------------------------------------------------------------------------- #
# Rendering
# --------------------------------------------------------------------------- #
def td(value: Any, cls: str = '') -> str:
    cls = (cls or '').strip()
    attr = f' class="{cls}"' if cls else ''
    content = value.html if isinstance(value, _RawHTML) else escape(str(value))
    return f'<td{attr}>{content}</td>'


def th(value: Any, cls: str = '') -> str:
    cls = (cls or '').strip()
    attr = f' class="{cls}"' if cls else ''
    return f'<th{attr}>{escape(str(value))}</th>'


def render_table(headers: list[str], rows: list[list], numeric_cols: set | None = None,
                 best_spec: dict | None = None) -> str:
    numeric_cols = set(numeric_cols or [])
    best_cells: set[tuple[int, int]] = set()

    for col, mode in (best_spec or {}).items():
        vals = []
        for row in rows:
            c = row[col]
            vals.append(c[1] if isinstance(c, tuple) else None)
        valid = [v for v in vals if v is not None and finite(v)]
        if not valid:
            continue
        target = max(valid) if mode == 'max' else min(valid)
        for i, v in enumerate(vals):
            if v is not None and finite(v) and float(v) == float(target):
                best_cells.add((i, col))

    head = '<thead><tr>' + ''.join(th(h, 'num' if i in numeric_cols else '') for i, h in enumerate(headers)) + '</tr></thead>'
    body = []
    for i, row in enumerate(rows):
        tds = []
        for j, c in enumerate(row):
            display = c[0] if isinstance(c, tuple) else c
            cls = 'num' if j in numeric_cols else ''
            if (i, j) in best_cells:
                cls = (cls + ' best').strip()
            tds.append(td(display, cls))
        body.append('<tr>' + ''.join(tds) + '</tr>')
    return f'<table>{head}<tbody>{"".join(body)}</tbody></table>'


def model_display(entry: dict) -> _RawHTML:
    return raw_html(f'<span class="model">{escape(entry["model"])}</span>')


def label_display(entry: dict) -> str:
    return escape(entry['label'])


# --------------------------------------------------------------------------- #
# Sections
# --------------------------------------------------------------------------- #
def section_overview(entries: list[dict]) -> str:
    lp_entries = [e for e in entries if e['longalpaca']]
    if not lp_entries:
        return ''
    rows = []
    for e in lp_entries:
        r1, r8, r16 = e['longalpaca'][1], e['longalpaca'][8], e['longalpaca'][16]
        rows.append([
            label_display(e), model_display(e),
            cell(fmt_num(r1['gen_tps'], 2), r1['gen_tps']),
            cell(fmt_num(r8['gen_tps'], 2), r8['gen_tps']),
            cell(fmt_num(r16['gen_tps'], 2), r16['gen_tps']),
            cell(fmt_num(r16['gen_tps'] / r1['gen_tps'], 2), r16['gen_tps'] / r1['gen_tps']),
            cell(fmt_num(r16['latency'], 2), r16['latency']),
            cell(fmt_num(r16['ttft'], 2), r16['ttft']),
            cell(fmt_num(r16['avg_out'], 2), r16['avg_out']),
        ])
    table = render_table(
        ['部署方式', '模型', '并发1吞吐', '并发8吞吐', '并发16吞吐', '16/1扩展倍率',
         '并发16平均延迟', '并发16 TTFT', '并发16平均输出Token'],
        rows, numeric_cols={2, 3, 4, 5, 6, 7, 8},
        best_spec={2: 'max', 3: 'max', 4: 'max', 5: 'max', 6: 'min', 7: 'min'},
    )
    return (
        '<section id="s1"><h2><span class="num">1</span>核心结论</h2>'
        '<div class="lead">各模型在 LongAlpaca 并发 1 / 8 / 16 档位的主要指标汇总，蓝色单元格为同表最优。</div>'
        f'<div class="card"><h3>并发 16 摘要</h3>{table}</div></section>'
    )


LONGALPACA_METRICS = [
    ('输出吞吐 Gen/s（tok/s）', 'gen_tps', 2, '', 'max', '越高越好，但需结合平均输出 Token 一起解读。'),
    ('请求吞吐 RPS', 'rps', 4, '', 'max', '越高越好，表示单位时间完成的请求数。'),
    ('平均延迟（秒）', 'latency', 2, '', 'min', '越低越好。'),
    ('TTFT（毫秒）', 'ttft', 2, '', 'min', '越低越好，体现首 token 响应速度。'),
    ('TPOT（毫秒）', 'tpot', 2, '', 'min', '越低越好，体现后续 token 生成间隔。'),
    ('平均输出 Token', 'avg_out', 2, '', None, '实际完成的输出长度；它会影响延迟与吞吐解读。'),
]


def section_longalpaca(entries: list[dict]) -> str:
    lp_entries = [e for e in entries if e['longalpaca']]
    if not lp_entries:
        return ''
    cards = ''
    for title, key, digits, suffix, mode, hint in LONGALPACA_METRICS:
        trows = []
        for e in lp_entries:
            r1, r8, r16 = e['longalpaca'][1], e['longalpaca'][8], e['longalpaca'][16]
            vals = [cell(f'{fmt_num(r[key], digits)}{suffix}', r[key]) for r in (r1, r8, r16)]
            trows.append([label_display(e), model_display(e), *vals])
        best = {2: mode, 3: mode, 4: mode} if mode else None
        cards += (
            f'<div class="card"><h3>{escape(title)}</h3><div class="hint">{escape(hint)}</div>'
            + render_table(['部署方式', '模型', '并发 1', '并发 8', '并发 16'], trows,
                           numeric_cols={2, 3, 4}, best_spec=best)
            + '</div>'
        )
    return (
        '<section id="s2"><h2><span class="num">2</span>LongAlpaca 单轮长文本性能压测</h2>'
        '<div class="lead">并发档位为 1 / 8 / 16，请求量分别为 20 / 80 / 160。</div>'
        f'{cards}</section>'
    )


def section_swe(entries: list[dict]) -> str:
    swe_entries = [e for e in entries if e['swe']]
    if not swe_entries:
        return ''
    swe_rows = []
    trace_rows = []
    for e in swe_entries:
        s = e['swe']
        swe_rows.append([
            label_display(e), model_display(e), s['requests'],
            cell(fmt_pct1(s['success_rate']), s['success_rate']),
            cell(f'{fmt_num(s["gen_tps"], 2)} tok/s', s['gen_tps']),
            cell(f'{fmt_num(s["latency"], 2)} s', s['latency']),
            cell(f'{fmt_num(s["ttft"], 2)} ms', s['ttft']),
            cell(f'{fmt_num(s["tpot"], 2)} ms', s['tpot']),
            cell(fmt_pct_raw(s['kv'], 1), s['kv']),
            cell(f'{fmt_num(s["first_ttft"], 2)} ms', s['first_ttft']),
            cell(f'{fmt_num(s["sub_ttft"], 2)} ms', s['sub_ttft']),
            cell(fmt_num(s['decoded_iter'], 2), s['decoded_iter']),
            cell(fmt_pct1(s['spec_accept']), s['spec_accept']),
        ])
        trace_rows.append([
            label_display(e), model_display(e), s['n_traces'],
            cell(f'{fmt_num(s["lat_mean"], 2)} s', s['lat_mean']),
            cell(f'{fmt_num(s["lat_p50"], 2)} s', s['lat_p50']),
            cell(f'{fmt_num(s["lat_p99"], 2)} s', s['lat_p99']),
            cell(f'{fmt_num(s["first_ttft_mean"], 2)} s', s['first_ttft_mean']),
            cell(f'{fmt_num(s["ttfat_mean"], 2)} s', s['ttfat_mean']),
            cell(fmt_num(s['decode_tps_mean'], 2), s['decode_tps_mean']),
            cell(fmt_num(s['decode_tps_p99'], 2), s['decode_tps_p99']),
            cell(fmt_pct_raw(s['cache_mean'], 1), s['cache_mean']),
            cell(fmt_pct_raw(s['cache_p50'], 1), s['cache_p50']),
            cell(fmt_pct_raw(s['cache_p99'], 1), s['cache_p99']),
            cell(fmt_pct_raw(s['eligible_mean'], 1), s['eligible_mean']),
        ])
    swe_table = render_table(
        ['厂商', '模型', '请求数', '成功率', '输出吞吐', '平均延迟', 'TTFT', 'TPOT',
         'KV缓存命中', '首轮TTFT', '后续TTFT', 'Decoded Tok/Iter', 'Spec接受率'],
        swe_rows, numeric_cols={2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12},
        best_spec={3: 'max', 4: 'max', 5: 'min', 6: 'min', 7: 'min', 8: 'max', 9: 'min', 10: 'min', 11: 'max', 12: 'max'},
    )
    trace_table = render_table(
        ['厂商', '模型', 'Trace数', 'Trace延迟均值', 'Trace P50', 'Trace P99', '首轮TTFT均值', 'TTFAT均值',
         'Decode TPS均值', 'Decode TPS P99', 'Cache均值', 'Cache P50', 'Cache P99', 'Eligible均值'],
        trace_rows, numeric_cols=set(range(2, 14)),
        best_spec={3: 'min', 4: 'min', 5: 'min', 6: 'min', 7: 'min', 8: 'max', 9: 'max', 10: 'max', 11: 'max', 12: 'max', 13: 'max'},
    )
    return (
        '<section id="s3"><h2><span class="num">3</span>SWE-Smith 多轮性能及缓存命中率</h2>'
        '<div class="lead">该组读取 outputs 中 swe_&lt;model_id&gt;_offset-10_cache-off 结果，对比各模型的多轮缓存命中与解码性能。</div>'
        f'<div class="card"><h3>请求级性能汇总</h3>{swe_table}</div>'
        f'<div class="card"><h3>Trace 级分布</h3>{trace_table}</div></section>'
    )


def section_knowledge(entries: list[dict]) -> str:
    cmmlu_entries = [e for e in entries if e['cmmlu']]
    he_entries = [e for e in entries if e['humaneval']]
    if not cmmlu_entries and not he_entries:
        return ''

    cards = ''
    if cmmlu_entries:
        rows = []
        for e in cmmlu_entries:
            c = e['cmmlu']
            rows.append([
                label_display(e), model_display(e), 'CMMLU', cell(fmt_num(c['num'], 0), c['num']),
                cell(fmt_pct(c['score'], 2), c['score']),
                cell(fmt_pct(c['macro'], 2), c['macro']),
                cell(f'{fmt_num(c["latency_mean"], 2)} s', c['latency_mean']),
                cell(f'{fmt_num(c["latency_p50"], 2)} s', c['latency_p50']),
                cell(f'{fmt_num(c["latency_p90"], 2)} s', c['latency_p90']),
                cell(f'{fmt_num(c["output_tps"], 2)} tok/s', c['output_tps']),
                cell(fmt_num(c['avg_output_tokens'], 2), c['avg_output_tokens']),
            ])
        table = render_table(
            ['厂商', '模型', '测试集', '题量', '准确率', 'Macro', '平均延迟', 'P50延迟', 'P90延迟', '输出吞吐', '平均输出Token'],
            rows, numeric_cols={3, 4, 5, 6, 7, 8, 9, 10},
            best_spec={4: 'max', 5: 'max', 6: 'min', 7: 'min', 8: 'min', 9: 'max'},
        )
        cards += f'<div class="card"><h3>CMMLU 汇总</h3>{table}</div>'

    if he_entries:
        rows = []
        for e in he_entries:
            c = e['humaneval']
            rows.append([
                label_display(e), model_display(e), 'HumanEval Plus', cell(fmt_num(c['num'], 0), c['num']),
                cell(fmt_pct(c['score'], 2), c['score']),
                cell(f'{fmt_num(c["latency_mean"], 2)} s', c['latency_mean']),
                cell(f'{fmt_num(c["latency_p50"], 2)} s', c['latency_p50']),
                cell(f'{fmt_num(c["latency_p90"], 2)} s', c['latency_p90']),
                cell(f'{fmt_num(c["latency_p99"], 2)} s', c['latency_p99']),
                cell(f'{fmt_num(c["output_tps"], 2)} tok/s', c['output_tps']),
                cell(fmt_num(c['avg_output_tokens'], 2), c['avg_output_tokens']),
            ])
        table = render_table(
            ['厂商', '模型', '测试集', '有效题量', 'Pass@1', '平均延迟', 'P50延迟', 'P90延迟', 'P99延迟', '输出吞吐', '平均输出Token'],
            rows, numeric_cols={3, 4, 5, 6, 7, 8, 9, 10},
            best_spec={4: 'max', 5: 'min', 6: 'min', 7: 'min', 8: 'min', 9: 'max'},
        )
        cards += f'<div class="card"><h3>HumanEval Plus 汇总</h3>{table}</div>'

    return (
        '<section id="s4"><h2><span class="num">4</span>知识与代码效果评测</h2>'
        '<div class="lead">分数来自 EvalScope reports，蓝色单元格为同表最优。</div>'
        f'{cards}</section>'
    )


# --------------------------------------------------------------------------- #
# Build HTML
# --------------------------------------------------------------------------- #
def build_html(entries: list[dict], generated: str) -> str:
    labels = [e['label'] for e in entries]
    model = entries[0]['model'] if entries else ''
    title = f"{' 与 '.join(f'{l} {model}' for l in labels)} 对比报告"
    compare_objects = '、'.join(f'{e["label"]} {e["model"]}' for e in entries)

    sections = [
        section_overview(entries),
        section_longalpaca(entries),
        section_swe(entries),
        section_knowledge(entries),
    ]
    toc_items = [
        ('结论总览', '部署效果摘要', '#s1'),
        ('性能压测', 'LongAlpaca 单轮', '#s2'),
        ('多轮压测', 'SWE-Smith 与缓存', '#s3'),
        ('效果评测', '知识与代码', '#s4'),
    ]
    toc = ''.join(
        f'<a href="{anchor}"><div class="k">{k}</div><div class="t">{t}</div></a>'
        for k, t, anchor in toc_items
    )
    body_sections = '\n'.join(s for s in sections if s)

    header = (
        f'<header><h1>{escape(title)}</h1>'
        f'<div class="sub">基于 EvalScope 本地结果重新整理，对比 <b>{escape(compare_objects)}</b> '
        f'在 LongAlpaca 单轮长文本、SWE-Smith 多轮 Agent 负载、CMMLU 与 HumanEval Plus 上的表现。'
        f'每个维度最优数值以蓝色高亮标注。</div>'
        f'<div class="toc">{toc}</div></header>'
    )
    source_labels = {'cmmlu': 'CMMLU', 'humaneval_plus': 'HumanEval Plus', 'longalpaca': 'LongAlpaca', 'swe': 'SWE-Smith'}
    source_rows = []
    for e in entries:
        src = e.get('sources', {})
        parts = [f'{source_labels[k]}: {escape(str(v))}' for k, v in src.items() if v]
        if parts:
            source_rows.append(f'<li><b>{escape(e["label"])} {escape(e["model"])}</b> — {"；".join(parts)}</li>')
    sources_html = ('<div><b>数据来源</b></div><ul>' + ''.join(source_rows) + '</ul>') if source_rows else ''
    footer = (
        f'<footer>{sources_html}<div>生成时间：{escape(generated)} · 统一原则：优先使用 EvalScope summary/report JSON，'
        f'不展示密钥、URL 等敏感运行参数。</div></footer>'
    )

    return (
        '<!DOCTYPE html>\n<html lang="zh-CN">\n<head>\n<meta charset="UTF-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1.0">\n'
        f'<title>{escape(title)}</title>\n'
        f'<style>{CSS}</style>\n'
        '</head>\n<body>\n<div class="wrap">\n'
        f'{header}\n{body_sections}\n{footer}\n'
        '</div>\n</body>\n</html>'
    )


def main() -> int:
    parser = argparse.ArgumentParser(description='Generate an HTML comparison report from a runs manifest.')
    parser.add_argument('--manifest', default='runs_manifest.json', help='Manifest JSON path (relative to repo root).')
    parser.add_argument('--output', default=None, help='Output HTML path (default: auto-generated).')
    args = parser.parse_args()

    manifest_path = ROOT / args.manifest
    if not manifest_path.exists():
        sys.exit(f'Manifest not found: {manifest_path}')

    data = json.loads(manifest_path.read_text(encoding='utf-8'))
    entries = []
    for e in data.get('entries', []):
        runs = e.get('runs', {})
        entry = {
            'model': e['model'], 'vendor': e['vendor'], 'label': e.get('label', e['vendor']),
            'model_id': e['model_id'],
            'cmmlu': load_metric(runs.get('cmmlu', {}).get('json')),
            'humaneval': load_metric(runs.get('humaneval_plus', {}).get('json')),
            'longalpaca': load_longalpaca(runs.get('longalpaca', {}).get('dir')),
            'swe': load_swe(runs.get('swe', {}).get('dir')),
            'sources': {
                'cmmlu': runs.get('cmmlu', {}).get('json'),
                'humaneval_plus': runs.get('humaneval_plus', {}).get('json'),
                'longalpaca': runs.get('longalpaca', {}).get('dir'),
                'swe': runs.get('swe', {}).get('dir'),
            },
        }
        entries.append(entry)

    generated = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    html = build_html(entries, generated)

    if args.output:
        out = Path(args.output)
    else:
        model = entries[0]['model'] if entries else 'model'
        vendors = '_vs_'.join(e['vendor'] for e in entries)
        date = datetime.now().strftime('%Y%m%d')
        out = ROOT / 'outputs' / f'{model}_{vendors}_comparison_report_{date}.html'

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding='utf-8')
    print(out)
    return 0


if __name__ == '__main__':
    sys.exit(main())
