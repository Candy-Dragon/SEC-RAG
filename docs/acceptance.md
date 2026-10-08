# 框架验收

目的：检查输入、阶段替换、生成、评价和结果导出的连接，不比较方法分数。

## 离线检查

从Git克隆的干净副本安装requirements.txt，运行env、unittest、experiment_a/b及evaluate --check-only。仓库.gitattributes固定LF换行，避免知识库哈希因系统换行而改变。GitHub Actions分别验证Windows和Linux；状态见仓库Actions，不以本地测试代替。

## 用户运行：默认与替换方法

准备.env中的模型配置及本地Ollama。下列生成会调用模型；评价使用本地模型。两组同为examples/questions.csv与knowledge_a、Top5，只替换第二阶段，分别输出。

```bat
python -s scripts/run.py experiment --experiment examples/experiment_full.json --check-only
python -s scripts/run.py experiment --experiment examples/experiment_sentence_units.json --check-only
python -s scripts/run.py experiment --experiment examples/experiment_full.json
python -s scripts/run.py experiment --experiment examples/experiment_sentence_units.json
python -s scripts/run.py evaluate --source-dir storage/experiments/examples/full_pipeline --output-base storage/experiments/evaluation/acceptance/default --workers 2
python -s scripts/run.py evaluate --source-dir storage/experiments/examples/sentence_units --output-base storage/experiments/evaluation/acceptance/sentence_units --workers 2
```

每组1题、四方法，各产生4份答案；SEC-RAG保存01到06、run_manifest和artifacts。替换组02使用确定性原句单元，默认组使用模型组合；后续阶段不改。合成文本可能没有适用医学证据而触发拒答，这不影响接口检查，但只能验证实际经过的分支。

## 验收规则

- 两组输入及初始检索一致，第二阶段组件记录不同。
- 每组progress显示4份答案完成；SEC阶段文件和来源哈希完整。
- 评价各4份完成，输出汇总CSV、同题CSV和逐步JSON。N/A允许，失败不算完成。
- 不据此证明所有组件/分支或医学判断都正确；后续接入新实现需增加对应测试。
- 此轮不重跑已有真实数据实验、不覆盖历史结果。若输出目录已有其他配置，先改新output_dir。

真实模型验收需由用户运行以上命令；在尚未查看输出前，不能标为完成。
