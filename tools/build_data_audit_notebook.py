"""Execute a development-only audit notebook; holdout input is metadata JSON only."""
from pathlib import Path
import json
import os
import sys

import nbformat as nbf
from nbclient import NotebookClient
from nbconvert import HTMLExporter

ROOT = Path(__file__).resolve().parents[1]
cache = ROOT / '.cache'
for key, sub in [('IPYTHONDIR', 'ipython'), ('JUPYTER_RUNTIME_DIR', 'runtime')]:
    path = cache / sub
    path.mkdir(parents=True, exist_ok=True)
    os.environ[key] = str(path)
kernel_root = cache / 'jupyter'
kernel = kernel_root / 'kernels' / 'btc-audit-local'
kernel.mkdir(parents=True, exist_ok=True)
(kernel / 'kernel.json').write_text(json.dumps({
    'argv': [sys.executable, '-m', 'ipykernel_launcher', '-f', '{connection_file}'],
    'display_name': 'BTC data audit', 'language': 'python'}))
os.environ['JUPYTER_PATH'] = str(kernel_root)
md, code = nbf.v4.new_markdown_cell, nbf.v4.new_code_cell
cells = [
    md('''# Development data reconciliation and sealed calendar checks

This notebook reruns the development data reconciliation and reads the existing date-only coverage audit. It does not read holdout ZIPs or price CSVs, calculate returns or states, or score models. Prices are compared as exact decimal values; rounding is not used to conceal differences.

## Methods and boundaries

Inputs are limited to the three `*_1d_2020-01_2023-12.csv` files and the mentor's CSV. The reconciliation module validates dates before converting numerical values and rejects rows from 2024 onward. Its source is `tools/reconcile_development.py`; download coverage is audited by `tools/audit_download_coverage.py`. Original field names are retained below for traceability.
'''),
    code('''from pathlib import Path
import json, sys, html
from IPython.display import display, HTML
ROOT = Path.cwd() if (Path.cwd() / 'tools').exists() else Path.cwd().parent
sys.path.insert(0, str(ROOT))
from tools.reconcile_development import AuditConfig, reconcile
mentor = ROOT.parent.parent / 'ChatGPT' / 'bitcoin' / 'CTA_public' / 'AFP_binance_spots.csv'
config = AuditConfig(ROOT / 'data/development', mentor, ROOT / 'results/data_audit')
status, report, differences = reconcile(config)

def show_table(rows):
    if not rows:
        print('No rows'); return
    columns = list(rows[0])
    header = ''.join('<th>' + html.escape(str(x)) + '</th>' for x in columns)
    body = ''.join('<tr>' + ''.join('<td>' + html.escape(str(r[c])) + '</td>' for c in columns) + '</tr>' for r in rows)
    display(HTML('<table><thead><tr>' + header + '</tr></thead><tbody>' + body + '</tbody></table>'))
'''),
    md('''## Date and closing-price agreement

First confirm that each comparison concerns the same asset and date. Duplicate keys are not resolved by arbitrarily retaining the first or last row. Calendar coverage and numerical agreement are reported separately.
'''),
    code('''rows = []
for asset, result in report['assets'].items():
    coverage = result['coverage']['development']
    close = result['fields']['close']
    rows.append({'asset': asset, 'start': coverage['first_date'], 'end': coverage['last_date'],
                 'rows': coverage['rows'], 'common_dates': result['compared_unique_dates'],
                 'close_exact_matches': close['exact_matches'],
                 'duplicate_dates': len(coverage['duplicates']),
                 'internal_gaps': len(coverage['gaps_within_observed_span'])})
show_table(rows)
print('All columns exactly reconciled:', report['exact_reconciliation'])
'''),
    md('''## Differences in other fields

The table below lists every field with an exact mismatch. Fixed tolerances describe the size of differences; a value within tolerance is not relabeled as exactly equal. A tool exit status of 1 can therefore indicate a faithfully reported discrepancy rather than a program crash.
'''),
    code('''field_rows = []
for asset, result in report['assets'].items():
    for field, item in result['fields'].items():
        if item['exact_mismatches']:
            field_rows.append({'asset': asset, 'field': field,
                               'nonidentical_dates': item['exact_mismatches'],
                               'outside_fixed_tolerance': item['outside_fixed_tolerance'],
                               'max_absolute_difference': item['maximum_absolute_difference']})
show_table(field_rows)
'''),
    md('''## Date-only checks for the new holdout

The following inputs are JSON files produced by the downloader and coverage tool. They contain no prices. An incomplete tail must remain marked incomplete; the test endpoint must not be changed for convenience. The coverage audit separately records the basis for excluding SOL dates before listing.
'''),
    code('''coverage_path = ROOT / 'results/data_audit/download_coverage_audit.json'
coverage_audit = json.loads(coverage_path.read_text())
# Show six bounded, price-free aggregate rows; archive receipts remain separate.
coverage_rows = []
for partition, part in coverage_audit['partitions'].items():
    for asset, entry in part['symbols'].items():
        coverage_rows.append({'partition': partition, 'asset': asset,
                              'rows': entry['observed_rows'],
                              'first': entry['first_observed_date'],
                              'last': entry['last_observed_date'],
                              'missing_eligible_days': len(entry['missing_eligible_dates']),
                              'interior_gaps': len(entry['interior_missing_dates']),
                              'complete': entry['eligible_requested_range_complete']})
show_table(coverage_rows)
print('Target remains 2026-09-30; available prefix is not a completed holdout.')
'''),
    md('''## Saved input hashes

The reconciliation hashes help detect changes to inputs. They do not replace sound methodology or prove that nobody inspected the data.
'''),
    code('''show_table([{'source': name, 'bytes': info['bytes'], 'rows': info['rows'],
             'sha256': info['sha256']} for name, info in report['inputs'].items()])
'''),
    md('''## Interpretation limits

In this executed audit, development dates and closing prices agree for all three assets, while some opening prices and volume fields differ. The predefined main model uses closing prices only, so that work can continue. Research using volume requires a separate investigation of the discrepancies. This reconciliation does not establish structural assumptions, predictive ability, availability of the unpublished holdout tail, or protocol freeze status.

See `research/data_audit_2026_10_02.md` for details. HTML was exported from the executed results; browser layout has not been visually reviewed.
'''),
]
nb = nbf.v4.new_notebook(cells=cells, metadata={
    'kernelspec': {'display_name': 'Python 3', 'name': 'python3', 'language': 'python'},
    'language_info': {'name': 'python', 'version': sys.version.split()[0]}})
path = ROOT / 'notebooks' / '00_data_audit.ipynb'
path.parent.mkdir(exist_ok=True)
print('Executing development-only audit notebook', flush=True)
NotebookClient(nb, timeout=120, kernel_name='btc-audit-local',
               resources={'metadata': {'path': str(ROOT)}}).execute()
nbf.validate(nb)
nbf.write(nb, path)
html_body, _ = HTMLExporter(template_name='lab').from_notebook_node(nb)
path.with_suffix('.html').write_text(html_body, encoding='utf-8')
print('Saved executed notebook and HTML', flush=True)
