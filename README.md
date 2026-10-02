# BTC 市场状态的马尔可夫性检验与短期风险预测

进行中。目标是检验固定三状态表示下的 Markov 近似，并评价五日风险概率预测；10 月 10 日开始投递，不以项目取得正结果为前提。

- [冲刺安排与范围](research/sprint_plan_2026_10.md)
- [研究协议草案，尚未冻结](research/protocol_2026_holdout_draft.md)
- [当前进度与下一步](research/status.md)
- [10 月 2 日数据对账结论](research/data_audit_2026_10_02.md)
- [可重跑的数据审计 notebook](notebooks/00_data_audit.ipynb)

研究问题：BTC 的固定离散状态是否与齐次一阶 Markov 模型的若干可检验含义相容？按预先规定的局部估计规则，Markov 模型的五日首次风险到达概率能否优于直接历史频率？检验没有拒绝并不证明 Markov 性；结构偏离与预测价值分别评价。

## 数据隔离

原始来源为 Binance 官方 `data.binance.vision` 的 spot `1d` 文件。2020—2023 年是已经使用过的开发数据。2024-01-01 至 2026-09-30 是计划保留的测试区间；在协议与代码提交冻结前，只允许下载封存、校验文件和核对行数、日期缺口，不读取价格、计算收益或画图。

下载器默认仅处理开发期。显式选择测试期时只保存经过 SHA-256 校验的 ZIP，并读取每行的时间戳字段生成日历覆盖记录；不会导出测试期价格 CSV。这里的封存是工作流程隔离，不是不可绕过的访问控制。

```sh
# 不联网、不写文件，仅列出计划
python3 tools/download_binance.py --dry-run

# 执行开发期下载
python3 tools/download_binance.py --partition development

# 显式下载封存测试期，仅核对时间戳覆盖
python3 tools/download_binance.py --partition holdout

# 假数据单元测试，不接触任何真实行情
python3 -m unittest discover -s tests -p 'test_download_binance.py' -v
```

新数据保存于 `data/development/`、`data/holdout_sealed/`，日历记录在 `data/metadata/`；`data/` 整体不进入 Git。缺月、缺日或校验失败会报告为未完成。SOL 上线前的空档必须与上市后的数据缺口区分；首次出现数据之前的缺失只标记为待确认，不自行认定上市日期。

Binance 文档称月包通常在每月第一个周一发布，因此 2026 年 9 月月包可能要到 10 月 5 日才齐。若尚未发布，先完成开发期工作，之后补齐同一来源的月包，不静默缩短测试期。2025-01-01 起的 spot 时间戳改为微秒，下载器需同时验证量级、日期分界和 UTC 日边界。[官方数据说明](https://github.com/binance/binance-public-data)

## 参考工作

数据下载与对账 CLI 仅需 Python 标准库。可选 notebook 环境使用 `requirements-notebook.txt`；安装后运行 `python tools/build_data_audit_notebook.py` 重建已执行 notebook 和 HTML。数据审计 notebook 会重新读取开发期 CSV，测试期仅读取安全的日期汇总 JSON。开发 CSV 文件名带明确日期范围，单月下载不会覆盖完整开发文件。

旧实现见本地的 [参考项目](../../ChatGPT/bitcoin/btcdyn_research/README.md)。其 2023 年 BTC Markov Brier 约 0.2495，历史频率约 0.2481；这是已使用的旧结果，不是本次新测试成绩。旧交易策略、期权信号和 Sharpe 优化不进入本次主项目。
