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

## 已检查的运行（2026-10-08）

- 默认组生成3/4完成；提示约束RAG返回数字字符串引用，原解析器拒绝。已兼容无歧义数字字符串并用原响应离线复验通过；原失败记录保留，不计为重新生成成功。
- 替换组生成4/4完成，SEC-RAG六阶段完成。与默认组输入、初始检索一致，第二阶段实现不同。
- 替换组评价运行 `20261008T084015541273Z`：4/4完成，0失败，已生成summary.json、汇总CSV、same_question_comparison.csv和逐方法JSON。
- 本例不含医学内容，四方法医学主张数均为0，忠实度与引用召回率均为N/A（CSV中为空）。这是不适用，不是零分或高分，也未验证有医学主张时的评分分支。
- 本地64项离线测试通过，包括引用格式兼容和非法编号拒绝检查。

### 医学结果评价验收

复用已有3道cMedQA2问题的12份回答，评价运行 `20261008T101413597665Z` 已完成12/12，0失败，未重新生成回答。逐份核对支持数/总数与评分、汇总有效样本数及均值、同题对照的12份答案，均一致。

本次实际经过医学主张抽取、证据支持判断、引用支持判断和无医学内容记N/A的分支。SEC-RAG仅1题计入有效评分（主张7/7，引用句2/2），另2题被评价器判为无医学内容的证据拒答；提示词约束RAG的3题均为N/A。因此不能依据SEC-RAG的100%判定其优于其他方法。这里验证记录和算术一致性，不证明模型语义判断可靠或临床正确。

结论：已验证替换第二阶段后的生成、评价与导出链路，以及上述医学评价分支；不能据此宣称所有模块替换、所有评价分支或医学有效性均已验证。默认组合成示例已于2026-10-10完成完整复验；未另行对该合成默认组重复评分，评价验收依据上面的替换组及真实医学结果。

运行记录保留在本地storage目录，不随公共源码发布。修改实现后如需重新生成，应使用新的output_dir，避免覆盖旧实验或混用代码版本。

## 默认流程复验（2026-10-10）

本地目录 `storage/experiments/examples/full_pipeline_recheck_20261010`：四方法4/4完成，SEC-RAG六阶段均completed；artifacts.json登记的10份文件SHA-256全部匹配。原失败记录不覆盖。

发布代码提交 `90b452e` 的GitHub Actions已成功：[自动检查记录](https://github.com/Candy-Dragon/SEC-RAG/actions/runs/37766848354)。本次收尾仅更新验收说明，不改变算法。后续以独立数据划分开展正式实验，不再依据这些验收样例调整方法。
