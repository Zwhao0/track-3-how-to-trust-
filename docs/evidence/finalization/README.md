# 中文证据工作台检查

Chrome 在 1440×900、1920×1080、1280×720 和 390×844 下检查了导航、表格溢出和澄清回放。页面无外部请求，回放结束后才显示最终文件差异。

- [概览](home-1440.png) · [写入对照](comparison-1440.png) · [受控验证](controls-1440.png)
- [澄清暂停](clarification-hold-1440.png) · [澄清结果](clarification-result-1440.png)
- [正式结果](formal-1440.png) · [手机正式结果](formal-390.png) · [试跑](pilot-1440.png) · [任务清单](benchmark-1440.png) · [探索结果](stress-1440.png)
- [浏览器记录](browser.json) · [独立评分的受控验证记录](controls.json)

本地运行 `PYTHONPATH=src python3 -m scopeguard demo verify` 和 `PYTHONPATH=src python3 -m scopeguard demo serve` 可复查显示内容。旧界面截图可在[此前归档](../m7/overview.png)查看。
