# 目录与阶段对应

项目把配置、核心代码、入口、数据与运行记录分开。configs对应常见config；src/sec_rag是Python包；storage/datasets对应data；storage/experiments同时承担runs和results职责，一次实验的记录放在一起。没有人工标注或Notebook任务时不预建空目录。

## 准备流程

- data：数据集专用预处理；adapters读取CSV/JSONL及字段映射。
- knowledge：PDF逐页提取、清洗、分块及BM25索引；保留文档、页码、片段ID。
- configs：实验配置、疾病范围、分块、检索、方法并发与提示词。
- scripts/run.py：任务入口；experiment执行生成，evaluate读取已有答案。

## SEC-RAG六阶段

1. retriever/bm25.py：原问题+范围+Top-N → 01_retrieval.json，保存原文片段与出处。各RAG方法共享初始检索。
2. structurer/evidence.py：检索片段 → 02_evidence_units.json，保存candidate_chunks原句、evidence_units原文组合及排除记录。模型组合，程序取原文。
3. filter/integrity.py：证据单元 → 03_integrity.json，保存可用/暂不使用证据；恢复内容须是连续原文。
4. filter/applicability.py：原问题+完整证据+原片段上下文 → 04_applicability.json。标注原问题的信息需求，映射支持内容、适用条件、禁止延伸；不改写问题分别检索。
5. filter/coverage.py：信息需求和适配证据 → 05_coverage.json。确定覆盖范围、允许证据及不足部分；不生成最终答案。
6. generator/constrained.py：原问题+获准证据+回答边界 → 06_final_answer.json。保存展示答案、医学陈述引用、证据不足说明；没有生成后语义验证。

每题run_manifest.json记录阶段文件及状态。method/components.py选择实现和检查结构关系；method/artifacts.py核对已存文件。method/v5.py是旧导入兼容层，没有另一套算法。utils保存公共函数，llm保存模型请求，experiments实现基线。

## 评价

evaluation读取最终答案和共同初始片段，保存逐步模型判断与公式分子分母；不回灌生成。指标定义见evaluation.md。评价需单独模型服务，生成成功不代表评价器语义判断正确。

## 追溯与限制

模型阶段保存实际输入、输出和提示词信息。artifacts.json检查文件哈希；来源路径+哈希连接上下游。源码或配置变更后选择新实验目录。旧结果未包含新完整性清单时只读保留，不直接续跑。强制中断在清单写入前可能需要新目录。

04明确依赖02的candidate_chunks，通过03的source_record读取。因此替换02/03必须保留上下文结构；详见extensions.md。默认索引格式仍为BM25；未知索引、模型协议须适配，不保证任意实现自动兼容。
