#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Generate and sequentially run the full eval pipeline for each model/vendor entry.

For every entry in the YAML config, build and run (in order):
    1. cmmlu          — evalscope eval  (knowledge)
    2. humaneval_plus — evalscope eval  (code, Docker sandbox)
    3. longalpaca     — evalscope perf  (single-turn long-context)
    4. swe            — evalscope perf --multi-turn (SWE-Smith session cache)

After each command the output path is detected (glob + mtime filter) and recorded
into a manifest JSON, which ``generate_report.py`` then consumes to build the
comparison HTML report.

Usage:
    python run_eval_compare.py --config config.yaml --dry-run
    python run_eval_compare.py --config config.yaml
    python run_eval_compare.py --config config.yaml --force --only glm-5.2
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    sys.exit('PyYAML is required (pip install pyyaml). It is already a dependency of evalscope.')

# Repo root: .trae/skills/evalscope-eval-compare/run_eval_compare.py -> parents[3]
ROOT = Path(__file__).resolve().parents[3]

SECTIONS = ('cmmlu', 'humaneval_plus', 'longalpaca', 'swe')


def redact_key(cmd: list[str]) -> list[str]:
    """Mask --api-key value so it never leaks to console or logs."""
    out: list[str] = []
    i = 0
    while i < len(cmd):
        token = cmd[i]
        if token == '--api-key' and i + 1 < len(cmd):
            out += ['--api-key', '***']
            i += 2
        elif token.startswith('--api-key='):
            out.append('--api-key=***')
            i += 1
        else:
            out.append(token)
            i += 1
    return out


def deep_merge(base: dict, override: dict) -> dict:
    out = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def load_config(path: str) -> tuple[dict, list[dict]]:
    with open(path, 'r', encoding='utf-8') as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        sys.exit(f'Invalid config: top-level must be a mapping, got {type(data).__name__}.')
    return data.get('defaults') or {}, data.get('models') or []


def entry_cfg(defaults: dict, entry: dict) -> dict:
    cfg = {
        'model': entry['model'],
        'vendor': entry['vendor'],
        'label': entry.get('label', entry['vendor']),
        'url': entry['url'],
        'api_key': entry['api_key'],
    }
    cfg['model_id'] = f"{entry['model']}_{entry['vendor']}"
    for section in SECTIONS:
        cfg[section] = deep_merge(defaults.get(section) or {}, entry.get(section) or {})
    return cfg


def _max_token_flag(d: dict, default: int) -> list[str]:
    """Emit --max-completion-tokens if set (takes precedence), else --max-tokens."""
    if d.get('max_completion_tokens') is not None:
        return ['--max-completion-tokens', str(d['max_completion_tokens'])]
    return ['--max-tokens', str(d.get('max_tokens', default))]


def cmd_cmmlu(cfg: dict, evalscope: str) -> list[str]:
    d = cfg['cmmlu']
    cmd = [evalscope, 'eval', '--model', cfg['model'],
           '--api-url', cfg['url'], '--api-key', cfg['api_key'], '--datasets', 'cmmlu']
    if d.get('limit') is not None:
        cmd += ['--limit', str(d['limit'])]
    cmd += [
        '--eval-batch-size', str(d.get('eval_batch_size', 8)),
        '--generation-config', json.dumps(d.get('generation_config') or {}, ensure_ascii=False),
        '--model-args', 'max_retries=0',
        '--ignore-errors',
        '--model-id', cfg['model_id'],
    ]
    return cmd


def cmd_humaneval(cfg: dict, evalscope: str) -> list[str]:
    d = cfg['humaneval_plus']
    return [
        evalscope, 'eval', '--model', cfg['model'],
        '--api-url', cfg['url'], '--api-key', cfg['api_key'],
        '--datasets', 'humaneval_plus',
        '--sandbox', json.dumps(d.get('sandbox') or {'enabled': True, 'engine': 'docker'}, ensure_ascii=False),
        '--eval-batch-size', str(d.get('eval_batch_size', 4)),
        '--generation-config', json.dumps(d.get('generation_config') or {}, ensure_ascii=False),
        '--model-args', 'max_retries=0',
        '--ignore-errors',
        '--dataset-args', json.dumps(d.get('dataset_args') or {}, ensure_ascii=False),
        '--model-id', cfg['model_id'],
    ]


def cmd_longalpaca(cfg: dict, evalscope: str) -> list[str]:
    d = cfg['longalpaca']
    cmd = [
        evalscope, 'perf',
        '--url', cfg['url'], '--api-key', cfg['api_key'], '--model', cfg['model'],
        '--dataset', 'longalpaca',
        '--dataset-offset', str(d.get('dataset_offset', 500)),
        *_max_token_flag(d, 512),
        '--parallel', *[str(x) for x in d.get('parallel', [1, 8, 16])],
        '--number', *[str(x) for x in d.get('number', [20, 80, 160])],
        '--temperature', str(d.get('temperature', 0)),
        '--top-p', str(d.get('top_p', 1.0)),
    ]
    if d.get('extra_args'):
        cmd += ['--extra-args', json.dumps(d['extra_args'], ensure_ascii=False)]
    cmd += ['--stream' if d.get('stream', True) else '--no-stream']
    cmd += [
        '--warmup-num', str(d.get('warmup_num', 2)),
        '--read-timeout', str(d.get('read_timeout', 300)),
        '--name', f"longalpaca_{cfg['model_id']}",
    ]
    return cmd


def cmd_swe(cfg: dict, evalscope: str) -> list[str]:
    d = cfg['swe']
    offset = d.get('dataset_offset', 10)
    cache_on = str(d.get('session_cache', 'off')).strip().lower() in ('1', 'true', 'on', 'yes')
    cache_tag = 'cache-on' if cache_on else 'cache-off'
    dataset_path = d.get('dataset_path')
    if not dataset_path or dataset_path == 'auto':
        dataset_path = 'outputs/agentic_dataset.json' if offset == 0 else 'outputs/agentic_pool.json'
    name = f"swe_{cfg['model_id']}_offset-{offset}_{cache_tag}"
    cmd = [
        evalscope, 'perf',
        '--url', cfg['url'], '--api-key', cfg['api_key'], '--model', cfg['model'],
        '--dataset', d.get('dataset', 'swe_smith'),
        '--dataset-path', dataset_path,
        '--dataset-offset', str(offset),
        '--name', name,
    ]
    if d.get('multi_turn', True):
        cmd += ['--multi-turn']
    if cache_on:
        cmd += ['--multi-turn-session-cache']
    cmd += [
        '--parallel', str(d.get('parallel', 5)),
        '--number', str(d.get('number', 10)),
        *_max_token_flag(d, 16384),
        '--seed', str(d.get('seed', 42)),
        '--temperature', str(d.get('temperature', 1.0)),
        '--top-p', str(d.get('top_p', 0.95)),
    ]
    cmd += ['--stream' if d.get('stream', True) else '--no-stream']
    if d.get('extra_args'):
        cmd += ['--extra-args', json.dumps(d['extra_args'], ensure_ascii=False)]
    cmd += ['--read-timeout', str(d.get('read_timeout', 300))]
    if d.get('no_test_connection'):
        cmd += ['--no-test-connection']
    return cmd


BUILDERS = {'cmmlu': cmd_cmmlu, 'humaneval_plus': cmd_humaneval,
            'longalpaca': cmd_longalpaca, 'swe': cmd_swe}


def marker_patterns(cfg: dict, section: str) -> list[str]:
    mid = cfg['model_id']
    if section == 'cmmlu':
        return [f'outputs/*/reports/{mid}/cmmlu.json']
    if section == 'humaneval_plus':
        return [f'outputs/*/reports/{mid}/humaneval_plus.json']
    if section == 'longalpaca':
        return [f'outputs/*/longalpaca_{mid}/parallel_1_number_20/benchmark_summary.json']
    offset = cfg['swe'].get('dataset_offset', 10)
    return [f'outputs/*/swe_{mid}_offset-{offset}_cache-*/parallel_5_number_10/benchmark_summary.json']


def newest_match(patterns: list[str], after: float) -> str | None:
    best: Path | None = None
    best_mtime = after
    for pat in patterns:
        for p in ROOT.glob(pat):
            try:
                mtime = p.stat().st_mtime
            except OSError:
                continue
            if mtime >= after and (best is None or mtime > best_mtime):
                best = p
                best_mtime = mtime
    return str(best) if best else None


def run_command(cmd: list[str], log_path: Path) -> int:
    display = ' '.join(redact_key(cmd))
    header = '\n' + '=' * 90 + '\n$ ' + display + '\n' + '=' * 90
    print(header, flush=True)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, 'w', encoding='utf-8') as f:
        f.write(display + '\n\n')
        proc = subprocess.Popen(
            cmd, cwd=str(ROOT), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding='utf-8', errors='replace', bufsize=1,
        )
        assert proc.stdout is not None
        for line in proc.stdout:
            sys.stdout.write(line)
            sys.stdout.flush()
            f.write(line)
            f.flush()
        return proc.wait()


def _write_manifest(manifest_path: Path, results: list[dict[str, Any]]) -> None:
    manifest = {'generated_at': time.strftime('%Y-%m-%d %H:%M:%S'), 'entries': results}
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')


def main() -> int:
    parser = argparse.ArgumentParser(description='Run the full eval pipeline for multiple model configs.')
    parser.add_argument('--config', required=True, help='Path to the YAML config file.')
    parser.add_argument('--cmd', default='evalscope', help='Base evalscope command (default: evalscope).')
    parser.add_argument('--dry-run', action='store_true', help='Print commands without running them.')
    parser.add_argument('--force', action='store_true', help='Re-run benchmarks even if manifest already has results.')
    parser.add_argument('--only', default='', help='Comma-separated model names to run (skip all others).')
    parser.add_argument('--skip', default='', help='Comma-separated model names to skip.')
    parser.add_argument('--manifest', default='runs_manifest.json', help='Output manifest path (relative to repo root).')
    parser.add_argument('--log-dir', default='logs/eval-compare', help='Directory for per-run log files.')
    args = parser.parse_args()

    defaults, models = load_config(args.config)
    only = {x.strip() for x in args.only.split(',') if x.strip()}
    skip = {x.strip() for x in args.skip.split(',') if x.strip()}

    manifest_path = ROOT / args.manifest
    existing: dict[str, dict[str, Any]] = {}
    if manifest_path.exists():
        try:
            prev = json.loads(manifest_path.read_text(encoding='utf-8'))
            existing = {e['model_id']: e for e in prev.get('entries', [])}
        except (json.JSONDecodeError, KeyError, TypeError):
            existing = {}

    results: list[dict[str, Any]] = []
    for entry in models:
        cfg = entry_cfg(defaults, entry)
        mid = cfg['model_id']
        if only and cfg['model'] not in only:
            continue
        if cfg['model'] in skip:
            continue

        if args.dry_run:
            for section in SECTIONS:
                print(f"[{mid}/{section}] " + ' '.join(redact_key(BUILDERS[section](cfg, args.cmd))))
            continue

        record = existing.get(mid, {}).copy()
        record.update({'model': cfg['model'], 'vendor': cfg['vendor'],
                       'label': cfg['label'], 'model_id': mid})
        record.setdefault('runs', {})
        results.append(record)

        for section in SECTIONS:
            cmd = BUILDERS[section](cfg, args.cmd)
            log_path = ROOT / args.log_dir / f'{mid}_{section}.log'
            if not args.force and record['runs'].get(section, {}).get('status') == 'ok':
                print(f'[SKIP] {mid}/{section} (already done)')
                continue
            start = time.time()
            rc = run_command(cmd, log_path)
            elapsed = time.time() - start
            marker = newest_match(marker_patterns(cfg, section), start)
            run_rec: dict[str, Any] = {'status': 'ok' if rc == 0 else f'fail(rc={rc})',
                                       'elapsed': round(elapsed, 1)}
            if marker:
                if section in ('cmmlu', 'humaneval_plus'):
                    run_rec['json'] = marker
                elif section == 'longalpaca':
                    run_rec['dir'] = str(Path(marker).parent.parent)
                else:
                    run_rec['dir'] = str(Path(marker).parent)
            record['runs'][section] = run_rec
            print(f"[{mid}/{section}] {run_rec['status']} ({elapsed:.1f}s) -> {marker or 'no marker found'}")
            _write_manifest(manifest_path, results)

    if args.dry_run:
        return 0

    _write_manifest(manifest_path, results)
    print(f'\nManifest written to {manifest_path}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
