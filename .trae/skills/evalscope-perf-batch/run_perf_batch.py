#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Batch runner for ``evalscope perf`` across multiple model / provider configs.

Reads a YAML file with a ``defaults`` block and a ``models`` list, then runs the
``evalscope perf`` CLI once per model entry, substituting ``--model`` / ``--url``
/ ``--api-key`` / ``--name`` (and any per-model overrides) into a shared command
template. Runs are strictly sequential so providers are never hit concurrently
by accident. Live output is streamed to the console *and* captured to a per-run
log file.

Usage:
    python run_perf_batch.py --creds credentials.yaml
    python run_perf_batch.py --creds credentials.yaml --dry-run
    python run_perf_batch.py --creds credentials.yaml --only glm-5.2,kimi-k2.6
    python run_perf_batch.py --creds credentials.yaml --skip glm-5.2 --cmd evalscope

See SKILL.md for the full YAML schema.
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

# (cli_flag, yaml_key) for single-value scalar params emitted as `--flag value`.
_SINGLE_SCALAR = [
    ('--dataset', 'dataset'),
    ('--dataset-offset', 'dataset_offset'),
    ('--temperature', 'temperature'),
    ('--top-p', 'top_p'),
    ('--top-k', 'top_k'),
    ('--seed', 'seed'),
    ('--warmup-num', 'warmup_num'),
    ('--read-timeout', 'read_timeout'),
    ('--connect-timeout', 'connect_timeout'),
    ('--total-timeout', 'total_timeout'),
    ('--outputs-dir', 'outputs_dir'),
    ('--api', 'api'),
    ('--max-prompt-length', 'max_prompt_length'),
    ('--min-prompt-length', 'min_prompt_length'),
    ('--prompt', 'prompt'),
    ('--query-template', 'query_template'),
    ('--name', 'name'),
]
# (cli_flag, yaml_key) for nargs='+' list params emitted as `--flag v1 v2 v3`.
_LIST_SCALAR = [
    ('--max-tokens', 'max_tokens'),
    ('--parallel', 'parallel'),
    ('--number', 'number'),
    ('--rate', 'rate'),
]
# (cli_flag, yaml_key) for store_true boolean flags.
_BOOL_FLAG = [
    ('--no-timestamp', 'no_timestamp'),
    ('--no-test-connection', 'no_test_connection'),
    ('--open-loop', 'open_loop'),
    ('--debug', 'debug'),
]


def load_config(path: str) -> tuple[dict, list[dict]]:
    with open(path, 'r', encoding='utf-8') as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        sys.exit(f'Invalid credentials file: top-level must be a mapping, got {type(data).__name__}.')
    defaults = data.get('defaults') or {}
    models = data.get('models')
    if not models:
        sys.exit('No `models` list found in credentials file.')
    return defaults, models


def merge(defaults: dict, model: dict) -> dict:
    merged = dict(defaults)
    merged.update(model)
    return merged


def build_command(cmd: str, cfg: dict) -> list[str]:
    for key in ('model', 'url', 'api_key'):
        if not cfg.get(key):
            sys.exit(f'Missing required field `{key}` in model entry: {cfg}')
    args = [cmd, 'perf', '--url', str(cfg['url']), '--api-key', str(cfg['api_key']), '--model', str(cfg['model'])]

    for flag, key in _SINGLE_SCALAR:
        val = cfg.get(key)
        if val is not None and val != '':
            args += [flag, str(val)]

    for flag, key in _LIST_SCALAR:
        val = cfg.get(key)
        if val is None:
            continue
        if isinstance(val, (list, tuple)):
            args += [flag] + [str(v) for v in val]
        else:
            args += [flag, str(val)]

    # extra_args: dict -> JSON string (a falsy/empty value drops the flag).
    extra = cfg.get('extra_args')
    if extra:
        args += ['--extra-args', json.dumps(extra)]

    # stream: BooleanOptionalAction -> --stream / --no-stream.
    if cfg.get('stream') is not None:
        args += ['--stream' if cfg['stream'] else '--no-stream']

    for flag, key in _BOOL_FLAG:
        if cfg.get(key):
            args += [flag]

    return args


def run_one(cmd_list: list[str], log_path: Path | None) -> int:
    header = f'\n{"=" * 80}\n$ {" ".join(cmd_list)}\n{"=" * 80}'
    print(header, flush=True)
    if log_path is None:
        return subprocess.call(cmd_list)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, 'w', encoding='utf-8') as f:
        f.write(' '.join(cmd_list) + '\n\n')
        proc = subprocess.Popen(cmd_list, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
        assert proc.stdout is not None
        for line in proc.stdout:
            sys.stdout.write(line)
            sys.stdout.flush()
            f.write(line)
        return proc.wait()


def main() -> int:
    parser = argparse.ArgumentParser(description='Batch-run `evalscope perf` for multiple model configs.')
    parser.add_argument('--creds', required=True, help='Path to the YAML credentials/config file.')
    parser.add_argument('--cmd', default='evalscope', help='Base evalscope command (default: evalscope).')
    parser.add_argument('--dry-run', action='store_true', help='Print commands without running them.')
    parser.add_argument('--only', default='', help='Comma-separated model names to run (skip all others).')
    parser.add_argument('--skip', default='', help='Comma-separated model names to skip.')
    parser.add_argument('--log-dir', default='logs/perf-batch', help='Directory for per-run log files.')
    parser.add_argument('--stop-on-error', action='store_true', help='Stop after the first failing run (default: continue).')
    args = parser.parse_args()

    defaults, models = load_config(args.creds)
    only_set = {x.strip() for x in args.only.split(',') if x.strip()}
    skip_set = {x.strip() for x in args.skip.split(',') if x.strip()}

    results: list[tuple[str, int, float]] = []
    log_dir = Path(args.log_dir)

    for i, entry in enumerate(models, 1):
        if not isinstance(entry, dict):
            sys.exit(f'Model entry #{i} must be a mapping, got {type(entry).__name__}.')
        model_name = str(entry.get('model', f'#{i}'))
        if only_set and model_name not in only_set:
            continue
        if model_name in skip_set:
            continue

        cfg = merge(defaults, entry)
        if not cfg.get('name'):
            cfg['name'] = f"{cfg.get('dataset', 'perf')}_{model_name}"
        cmd_list = build_command(args.cmd, cfg)

        if args.dry_run:
            print(f'[{i}/{len(models)}] {model_name} ->\n  {" ".join(cmd_list)}')
            results.append((model_name, 0, 0.0))
            continue

        log_path = log_dir / f"{cfg['name']}.log"
        t0 = time.time()
        try:
            rc = run_one(cmd_list, log_path)
        except FileNotFoundError:
            print(f'ERROR: command not found: {args.cmd!r}. Is evalscope installed and on PATH?', flush=True)
            return 127
        elapsed = time.time() - t0
        results.append((model_name, rc, elapsed))

        status = 'OK' if rc == 0 else f'FAIL(rc={rc})'
        print(f'\n[{i}/{len(models)}] {model_name}: {status} ({elapsed:.1f}s, log: {log_path})', flush=True)
        if rc != 0 and args.stop_on_error:
            print('Stopping due to failure (--stop-on-error).')
            break

    print('\n' + '=' * 80)
    print('SUMMARY')
    print('=' * 80)
    for name, rc, secs in results:
        mark = 'OK  ' if rc == 0 else 'FAIL'
        print(f'  {mark}  {name:<32} {secs:8.1f}s')
    failed = sum(1 for _, rc, _ in results if rc != 0)
    print(f'\nTotal: {len(results)}  Success: {len(results) - failed}  Failed: {failed}')
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
