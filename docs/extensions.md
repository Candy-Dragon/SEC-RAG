# 数据、知识库和方法接入协议

## 新数据集

保留独立预处理。将处理后的CSV或JSONL路径写到实验配置dataset.path，指定format、name，以及columns中qid/question/disease_scope对应的原字段名。运行时映射必要字段，source_record保留原始行（包括参考答案等其他字段）；不改写输入文件，不要求所有预处理产物采用同一张中间表。qid只允许字母、数字、下划线和连字符，且不重复。

当前仍是按领域检索的实验；disease_scope是路由标签，不是自动医学诊断。其他格式需在data/adapters.py增加读取器。

## 新知识库

配置knowledge_base为项目内的独立目录，目录结构与storage/knowledge_base相同。运行现有知识构建命令前可在Anaconda Prompt设置KNOWLEDGE_BASE_ROOT为这个目录；执行完切回原值。PDF放在该目录documents/<领域>/。分块及BM25参数仍由configs中的对应配置定义。

新库必须具备indexes/bm25/corpus.jsonl和index_manifest.json；manifest内corpus_sha256必须匹配。每个片段需有chunk_id、document_id、disease、source_file、page_start、page_end、text和tokens，建议保留section_heading。现有知识库构建脚本会生成这些字段。scope_config指定允许领域的JSON。所有实验路径目前限定在项目目录内，便于追溯与移植。

示例knowledge_a、knowledge_b为人工合成的软件测试资料，不是指南、真实问答或实验数据。

## 新方法

内置方法为llm_only、traditional_rag、prompt_constrained_rag、sec_rag。在实验配置methods中选择组合。自定义RAG方法通过plugins中的“方法名: 模块路径:函数名”注册；参考examples/experiment_a.json和src/sec_rag/experiments/extractive_demo.py。

函数接收question，以及关键字参数top_k、disease、retrieval。必须返回包含原始question和非空answer的字典；应同时保存messages、模型版本、调用原始响应、用量、retrieval等实验留痕。引用使用[证据1]等检索排序编号。不得覆盖内置方法名。配置可导入Python函数，属于可信代码配置，不应运行陌生来源配置。

SEC-RAG内部仍走六阶段，不强迫其他方法经过这些阶段。同一问题的方法共享初始检索内容。现在可通过实验配置的components选择六阶段实现，入口和字段约定在method/components.py；各阶段实现已分到retriever、structurer、filter、generator目录。替换实现必须满足下游字段要求，不能任意改变结构。目录、输入输出和替换示例见[框架说明](structure.md)。默认知识库预检仍依赖BM25索引格式，接入其他索引需要配套适配。

## 输出和评价

运行前保存experiment_manifest.json（配置、数据/知识库/代码哈希、模型参数）和input_questions.json。每题保留01_retrieval.json；SEC有六阶段JSON，其他方法为baselines/<method>.json。progress.json记录成功、失败和续跑。失败重试前另存原记录。输入或代码变化拒绝复用旧输出目录。

评价入口加--source-dir指向实验目录，会从experiment_manifest.json读取方法列表。自定义方法按RAG引用格式评价；裸模型仅llm_only按无引用方法处理。当前尚不支持用配置声明任意新方法的其他引用协议。

```bat
python -s scripts/evaluate.py --source-dir storage/experiments/examples/demo_a --check-only
```

此命令只校验生成产物；实际评价仍需要本地Ollama。合成示例无需评分，也不能混入论文结果。

## 当前边界

支持CSV/JSONL数据字段适配、BM25知识库目录替换及RAG方法函数注册；不宣称支持全部数据格式、向量检索器、所有模型提供商或任意内部阶段插拔。DeepSeek生成调用和Ollama评价调用仍分别封装。将新提供商接入它们需要遵守现有请求响应协议。


## 六阶段插件契约

components键固定为01_retrieval、02_evidence_units、03_integrity、04_applicability、05_coverage、06_final_answer；值为当前仓库内module:function。缺省项使用默认实现。首阶段签名为(question, *, question_id, source_dataset, disease_scope, top_n, output_path)，其他阶段为(input_path, output_path)，均返回完成记录字典。

公共记录必须含stage、status=completed、input（保持问题身份）及阶段内容。执行器写入component来源和source_record。内置阶段另保存method_version与调用轨迹。字段检查代码以method/components.py为准：

- 01：retrieval_results，连续rank、唯一chunk_id、document_id、disease、source_file、page_start/end、text。
- 02：candidate_chunks（原句sentence_id/text）、evidence_units（evidence_id/text、source_chunk_id、source_file/pages、sentence_ids、section_heading）、excluded_sentences。保留初始片段集合。
- 03：usable_evidence_units、withheld_evidence_units。恢复证据用recovered_from_evidence_id追溯，保留原句位置。
- 04：information_need_annotation（original_question、information_needs中的need_id/source_span/description）和mapped_evidence_units（含need_mapping）。原文位置必须来自原问题，证据不得改写。
- 05：同一信息需求、mapped_evidence_units、coverage_analysis。后者包含coverage_items、overall_coverage和generation_boundaries；allowed_evidence_ids仅含已有证据。
- 06：approved_evidence、coverage_analysis、final_answer（answer、claims、insufficient_information）。claims需包含claim_id/text/evidence_ids/claim_type；引用仅限获准证据。

原始问题始终不变。04为了理解适用条件，明确通过03来源链读取02的candidate_chunks；这是接口依赖。新模块不能省略它。公共校验不等于医学语义正确验证。

可直接参考structurer/sentences.py及examples/experiment_sentence_units.json替换02。先check-only，再小样本完整运行，然后再设计科学比较。所有API方法用量与原始响应应保存到阶段记录。不能以插件接口为由绕过追溯。
