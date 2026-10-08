# 数据与知识库准备

## 问答数据

原始资料自行从授权来源获取；仓库只包含合成示例。cMedQA2原项目：https://github.com/zhangsheng93/cMedQA2 。使用前检查来源许可。

将question.csv、answer.csv置于storage/datasets/raw/cMedQA2-master/，依次运行：

```bat
python -s scripts/run.py data.inspect
python -s scripts/run.py data.candidates
python -s scripts/run.py data.pool
python -s scripts/run.py data.split
```

问题池保存在storage/datasets/processed/cmedqa2/，默认划分在其splits/default/。划分采用按疾病分组的固定种子70/15/15，是可修改的实验预设，不是最优比例结论。样本量不足默认每病10题开发样本时，传 --dev-per-disease 较小值。已用于开发的题可通过 --exclude-config 指定JSON questions列表（元素含qid）；默认不使用作者的历史题号。划分文件不可覆盖。

其他数据集建立自己的预处理模块，输出CSV或JSONL；通过dataset.columns映射qid/question/disease_scope，不需要把不同数据集重写到同一个中间表。参考答案等额外列保留在source_record。现有评价不以社区答案为医学金标准。

## 指南

目录storage/knowledge_base/documents/<疾病key>/存放可提取文本的PDF。疾病key与configs/experiment_scope.json匹配。扫描件需要另行OCR；不要假定空白提取页已被正确识别。

```bat
python -s scripts/run.py knowledge.extract
python -s scripts/run.py knowledge.check-text
python -s scripts/run.py knowledge.clean
python -s scripts/run.py knowledge.chunk
python -s scripts/run.py knowledge.check-chunks
python -s scripts/run.py knowledge.index
```

按extracted、cleaned、chunks、indexes保存过程与来源。检查报告应在后续实验前阅读。新增指南需要重新生成受影响的索引并使用新的实验目录，不必重写问答方法。

更换独立知识库，在Anaconda Prompt设置 `set KNOWLEDGE_BASE_ROOT=storage/knowledge_base_new`，再执行上述准备步骤；实验JSON中的knowledge_base也设为这个目录。恢复默认时执行 `set KNOWLEDGE_BASE_ROOT=`。PowerShell使用对应的环境变量语法。

完整路径与输入输出约定见structure.md、extensions.md。知识库不必包含每个问题的答案；缺少适用证据应留痕，不通过为测试题补答案来追求分数。
