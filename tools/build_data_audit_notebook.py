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
    md('''# 开发期数据对账与封存日历检查

本 notebook 重做开发期对账，并查看已生成的纯日期覆盖审计。它不读取测试期 ZIP 或价格 CSV，不运行收益、状态或模型评分。价格差异以原始十进制比较，不通过四舍五入隐藏差异。

## 方法和边界

输入限定为三个 `*_1d_2020-01_2023-12.csv` 和导师 CSV。对账模块先验证日期再转换数值，拒绝 2024 年及以后的行。源码是 `tools/reconcile_development.py`；下载覆盖代码是 `tools/audit_download_coverage.py`。下面保留原始字段名，便于回查。
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
    md('''## 日期和收盘价是否一致

先确认比较对象是同一资产、同一天；重复键不任意保留第一行或最后一行。日历覆盖和数值比较分别报告。
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
    md('''## 不能忽略的非收盘价差异

下表列出所有非精确匹配字段。固定容差仅用于描述差异大小，不把“容差内”改写成“完全一样”。因此工具返回状态 1 可以表示如实发现差异，并非程序崩溃。
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
    md('''## 新测试期只查看日期审计

以下读取的是下载器与覆盖工具生成的 JSON，不包含价格。未完成的尾部必须保持为未完成，不能为了方便改动测试终点。SOL 上线前的排除依据单列在覆盖审计中。
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
    md('''## 保存的输入摘要

对账摘要可用于检查后续是否更换输入；它不能替代正确的方法或证明没人看过数据。
'''),
    code('''show_table([{'source': name, 'bytes': info['bytes'], 'rows': info['rows'],
             'sha256': info['sha256']} for name, info in report['inputs'].items()])
'''),
    md('''## 解读边界

在本次已执行结果中，开发期的日期及三个资产的收盘价一致，部分开盘价和成交量字段不同。既定主模型只用收盘价，故可以继续；成交量研究需要另查差异原因。结构假设、预测能力、未发布测试尾部和实验协议冻结都不是这次对账能够证明的事。

详细解释见 `research/data_audit_2026_10_02.md`。HTML 已从执行结果导出；本轮未作浏览器排版验收。
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
