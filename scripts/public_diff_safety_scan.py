#!/usr/bin/env python3
"""Fail if public JSON diff adds real secrets/order-execution clues.

This scanner intentionally allows public analysis labels/fields such as
kisEnrichment, K-O-R, sale_account, and other financial statement field names.
It blocks credentials, account identifiers, bearer tokens, and order/trading
endpoints or TR IDs.
"""
import re
import subprocess
import sys

PATHS = ['data/dashboard-data.json', 'data/dashboard-history.json', 'data/test']
BLOCK_PATTERNS = [
    r'app[_-]?key\s*[:=]',
    r'app[_-]?secret\s*[:=]',
    r'client[_-]?secret\s*[:=]',
    r'private_key',
    r'client_email',
    r'authorization\s*[:=]',
    r'\bbearer\s+[A-Za-z0-9._~+/=-]{20,}',
    r'access[_-]?token\s*[:=]',
    r'refresh[_-]?token\s*[:=]',
    r'"?CANO"?\s*:',
    r'"?ACNT_PRDT_CD"?\s*:',
    r'계좌번호',
    r'uapi/domestic-stock/v1/trading/order',
    r'order-cash',
    r'VTTC0012U|VTTC0011U|TTTC0012U|TTTC0011U',
    r'ODNO|ORD_QTY|ORD_DVSN|KRX_FWDG_ORD_ORGNO',
]
ALLOW_SUBSTRINGS = [
    'kisEnrichment',
    'K-O-R',
    'sale_account',
    'accountPnlAvailable',
    'incomeStatement',
]


def added_lines():
    cmd = ['git', 'diff', '--', *PATHS]
    proc = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if proc.returncode not in (0, 1):
        print(proc.stderr, file=sys.stderr)
        sys.exit(proc.returncode)
    for line in proc.stdout.splitlines():
        if line.startswith('+++'):
            continue
        if line.startswith('+'):
            yield line[1:]


def main():
    hits = []
    compiled = [(pat, re.compile(pat, re.I)) for pat in BLOCK_PATTERNS]
    for line in added_lines():
        if any(token in line for token in ALLOW_SUBSTRINGS):
            # Still let hard credential/order patterns below catch if present on the same line.
            pass
        for pattern, rx in compiled:
            if rx.search(line):
                hits.append({'pattern': pattern, 'line': line[:260]})
                break
    if hits:
        print('ERROR: sensitive credential/account/order term detected in public JSON diff; aborting before commit/push', file=sys.stderr)
        for hit in hits[:30]:
            print(f"- pattern={hit['pattern']} line={hit['line']}", file=sys.stderr)
        sys.exit(23)
    print('public JSON safety scan ok')


if __name__ == '__main__':
    main()
