# cMedQA2 下一步：固定划分与首批开发实验

## 当前执行入口（2026-09-24，覆盖下文历史命令）

下一步直接运行固定随机开发30题，不再扩展9题诊断。v1旧30题保留为历史诊断；新批次采用splits/v2清单与当前sec-rag-v5-context-v1主方法。输入检查已通过。生成会调用DeepSeek并产生费用，由用户运行。

```bat
python -s scripts/development/06_run_development_first_batch.py --limit 30 --split-dir storage/datasets/processed/cmedqa2/splits/v2 --output-dir storage/experiments/development/cmedqa2/first_batch_v2
```

确认30题四方法均生成完成后，先检查再评价：

```bat
python -s scripts/evaluation/03_evaluate_four_methods_pilot.py --check-only --source-dir storage/experiments/development/cmedqa2/first_batch_v2
python -s scripts/evaluation/03_evaluate_four_methods_pilot.py --workers 2 --source-dir storage/experiments/development/cmedqa2/first_batch_v2 --output-base storage/experiments/evaluation/development/cmedqa2/four-methods-v4
```

评价使用本地Ollama qwen3:4b-instruct；沿用两项公开指标的医学适配，不是官方ragas程序原样复现。结果用于开发分析，不是独立测试结论。评价输出目录内：main_quality_evidence_table.csv为汇总；same_question_comparison.csv为同题四方法答案及分数；questions为逐项输入、判断、分子分母；implementation_snapshot保存该次代码、提示词及指标文档。run_manifest.json记录模型、输入哈希与选择范围。

生成中断后重跑原生成命令，已完成答案跳过。评价中断后使用原评价命令并加 --resume 后跟本次输出的时间目录；不能续跑旧版v3。输入缺失或不同方法问题不一致会在联系模型之前报错。


## 2026-09-24 抽样修正

首批30题跑完后发现，v1 脚本先按 qid 排序，再取每种疾病前10题，实际落在 `CMEDQA2_00002` 到 `CMEDQA2_00059`；因此它不是预期的随机开发样本。**已产生的30题/120份回答保留为诊断批次，不当作代表性开发结果，亦不删除。** v2 保持开发/验证/测试主体划分不变，只对开发集重新用独立固定种子、每病随机抽10题；保存于 `storage/datasets/processed/cmedqa2/splits/v2/`。v2 不覆盖 v1 结果，也未调用模型。下文旧命令和目录描述属于 v1 诊断批次。

## 评价缓存路径修复

首次运行30题本地评价时，缓存临时文件在 Windows 上超过路径长度限制，已写出的逐题结果均为 `failed`。修复将缓存放在更短的 `storage/experiments/evaluation/_cache/<评价器指纹>/`，不会改变评价提示词、判断规则或公式。旧失败目录保留；修复后请重新执行文末评价命令，生成新的运行目录。离线缓存写入检查与44项测试已通过，本地模型完整评价仍需由实际运行确认。

这一步只整理已经预处理的 `question_pool_all.csv`，不重新处理原始数据、不生成医学或“指南可回答”标签，也不调用模型。9道人工挑选的流程试跑题保持独立，不参与随机划分；76道同时命中多个疾病的题暂不进入当前单疾病实验。

运行 `python -s scripts/development/05_create_cmedqa2_splits.py` 后，在 `storage/datasets/processed/cmedqa2/splits/v1/` 生成：

- `development.csv`：开发集1349题，用于分析系统问题和修改方法。
- `validation.csv`：验证集288题，只用于后续预先确定的参数选择。
- `test.csv`：测试集292题，保留到方法、指标和参数冻结后评估。
- `development_first_batch.csv`：从开发集每种疾病各取10题，共30题。它不是“指南覆盖题”样本，也不代表全部开发集。
- `manifest.json`：记录原数据哈希、排除原因、固定种子、划分规则、题数和每份清单哈希。已有文件时脚本拒绝覆盖。

70%/15%/15% 是本轮预先声明的操作性划分，不能写成公认最优比例；目前是**按预处理时的单疾病词汇域分层随机**，疾病域也不是临床诊断。划分前原池2014题，排除9道手选题及76道多疾病题后，1929题进入三个互不重叠的清单。

下一步可先运行 `python -s scripts/development/06_run_development_first_batch.py --limit 3` 检查首批三题的四方法输出。确认成本和逐步输出后，运行同一命令的 `--limit 30`；完成的题会跳过，失败可重新运行。这个脚本按题保存SEC-RAG六阶段JSON，以及同题三种基线的独立JSON；进度在 `storage/experiments/development/cmedqa2/first_batch_v1/progress.json`。每种RAG都用同一题的BM25 Top-5，裸模型不使用指南。

首批30题是开发诊断，不是正式测试；如果这些题大多无法由现有指南覆盖，应据实报告，不能事后只留下有利于SEC-RAG的题。四方法答案生成后，还需要将评价入口扩展到此批次，并保存逐题判断与同题对照。评价器/提示词保持当前冻结版本，若必须修改则所有方法须在同题重新评价。

四方法答案全部完成后，再运行同一冻结评价器：

```bat
python -s scripts/evaluation/03_evaluate_four_methods_pilot.py --workers 2 --source-dir storage/experiments/development/cmedqa2/first_batch_v1 --output-base storage/experiments/evaluation/development/cmedqa2/four-methods-v3
```

每道题、每种方法的评价输入、模型判定及公式结果保存在新目录的 `questions/<qid>/<method>.json`；`summary.json` 和 `main_quality_evidence_table.csv` 是汇总。未完成全部四方法输出前不要启动这一步。该入口文件名保留旧称，但 `--source-dir` 会明确指定本次30题来源，输出与9题试跑完全分开。
