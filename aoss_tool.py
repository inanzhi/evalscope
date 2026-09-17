# -*- coding: utf-8 -*-
"""AOSS (SenseCore S3-compatible object storage) helper.

Usage:
  AOSS_AK=xxx AOSS_SK=yyy python aoss_tool.py ls-models
  AOSS_AK=xxx AOSS_SK=yyy python aoss_tool.py ls --prefix "nova-export/research-v2/model=glm-5.1/" --max 100
  AOSS_AK=xxx AOSS_SK=yyy python aoss_tool.py download --prefix "nova-export/research-v2/model=glm-5.1/" --out ./data

Ends points may be overridden via AOSS_ENDPOINT / AOSS_BUCKET (see defaults below).
"""

from __future__ import annotations

import argparse
import os
import sys

import boto3
from botocore.config import Config

DEFAULT_ENDPOINT = 'https://aoss.cn-sh-01b.sensecoreapi-oss.cn'
DEFAULT_BUCKET = 'aoss_nova_sh01b'


def _client() -> boto3.client:
    endpoint = os.environ.get('AOSS_ENDPOINT', DEFAULT_ENDPOINT)
    ak = os.environ.get('AOSS_AK')
    sk = os.environ.get('AOSS_SK')
    if not ak or not sk:
        print('Error: set AOSS_AK and AOSS_SK environment variables.', file=sys.stderr)
        sys.exit(2)
    return boto3.client(
        's3',
        endpoint_url=endpoint,
        aws_access_key_id=ak,
        aws_secret_access_key=sk,
        config=Config(s3={'addressing_style': 'path'}, connect_timeout=10, read_timeout=30),
    )


def _bucket() -> str:
    return os.environ.get('AOSS_BUCKET', DEFAULT_BUCKET)


def cmd_list_models(args: argparse.Namespace) -> None:
    s3 = _client()
    bucket = _bucket()
    prefix = args.prefix
    models: list[str] = []
    token = None
    while True:
        kw = dict(Bucket=bucket, Prefix=prefix, Delimiter='/')
        if token:
            kw['ContinuationToken'] = token
        r = s3.list_objects_v2(**kw)
        models.extend(cp['Prefix'] for cp in r.get('CommonPrefixes', []))
        if r.get('IsTruncated'):
            token = r.get('NextContinuationToken')
        else:
            break
    base = len(prefix)
    for m in models:
        print(m[base:].rstrip('/'))
    print(f'\n{len(models)} entries', file=sys.stderr)


def cmd_list(args: argparse.Namespace) -> None:
    s3 = _client()
    bucket = _bucket()
    token = None
    count = 0
    while True:
        kw = dict(Bucket=bucket, Prefix=args.prefix, MaxKeys=1000)
        if token:
            kw['ContinuationToken'] = token
        r = s3.list_objects_v2(**kw)
        for o in r.get('Contents', []):
            print(f'{o["Size"]:>14}  {o["Key"]}')
            count += 1
            if args.max and count >= args.max:
                print('... (truncated by --max)', file=sys.stderr)
                return
        if r.get('IsTruncated'):
            token = r.get('NextContinuationToken')
        else:
            break
    print(f'{count} objects', file=sys.stderr)


def cmd_download(args: argparse.Namespace) -> None:
    s3 = _client()
    bucket = _bucket()
    os.makedirs(args.out, exist_ok=True)
    token = None
    count = 0
    while True:
        kw = dict(Bucket=bucket, Prefix=args.prefix, MaxKeys=1000)
        if token:
            kw['ContinuationToken'] = token
        r = s3.list_objects_v2(**kw)
        for o in r.get('Contents', []):
            key = o['Key']
            if key.endswith('/'):
                continue
            # Preserve the directory structure under the prefix.
            rel = key[len(args.prefix):] if key.startswith(args.prefix) else os.path.basename(key)
            dst = os.path.join(args.out, rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            s3.download_file(bucket, key, dst)
            count += 1
            print(f'downloaded {key} -> {dst}')
        if r.get('IsTruncated'):
            token = r.get('NextContinuationToken')
        else:
            break
    print(f'{count} files downloaded to {args.out}', file=sys.stderr)


def main() -> None:
    p = argparse.ArgumentParser(description='AOSS S3 helper')
    sub = p.add_subparsers(dest='cmd', required=True)

    pm = sub.add_parser('ls-models', help='List first-level prefixes (e.g. model= partitions).')
    pm.add_argument('--prefix', default='nova-export/research-v2/')
    pm.set_defaults(func=cmd_list_models)

    pl = sub.add_parser('ls', help='List objects under a prefix.')
    pl.add_argument('--prefix', required=True)
    pl.add_argument('--max', type=int, default=0)
    pl.set_defaults(func=cmd_list)

    pd = sub.add_parser('download', help='Download objects under a prefix.')
    pd.add_argument('--prefix', required=True)
    pd.add_argument('--out', required=True)
    pd.set_defaults(func=cmd_download)

    args = p.parse_args()
    args.func(args)


if __name__ == '__main__':
    main()