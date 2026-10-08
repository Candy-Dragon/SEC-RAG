# SEC-RAG

医学问答的生成前证据约束研究框架。输入外部问题与独立指南知识库，在检索后构建、检查和筛选证据，再生成带引用的回答。支持同题运行裸模型、普通RAG、提示词约束RAG和SEC-RAG，并独立评价已保存答案。

本项目提供研究代码，不是临床诊疗产品。运行成功不代表答案医学正确或SEC-RAG优于基线。代码使用许可尚待作者确认：计划允许非商业科研使用，尚未发布正式许可证；不要将仓库可见性理解为MIT/Apache许可。

## 1. 安装

需要Python 3.11。推荐在项目根目录通过Anaconda Prompt创建环境：

```bat
git clone https://github.com/Candy-Dragon/SEC-RAG.git
cd SEC-RAG
conda env create -f environment.yml
conda activate sec-rag
python -s scripts/run.py env
```

也可以在独立Python 3.11虚拟环境中执行 `python -m pip install -r requirements.txt`。所有Python运行依赖集中在requirements.txt；environment.yml引用它。请从仓库根目录运行命令。当前使用源码检出方式，不承诺安装wheel后脱离仓库运行。

## 2. 先运行不需要模型的示例

```bat
python -s scripts/run.py experiment --experiment examples/experiment_a.json
python -s scripts/run.py experiment --experiment examples/experiment_b.json
```

两组示例使用不同字段和CSV/JSONL格式、不同合成知识库，调用确定性抽取示例方法，无API费用。输出分别在storage/experiments/examples/demo_a和demo_b。它们检验读取、检索、方法注册和结果保存，不代表完整SEC-RAG语义判断。

## 3. 运行完整四方法流程

复制 `.env.example` 为 `.env`，填写有访问权限的MODEL_NAME、MODEL_API_KEY和兼容的MODEL_BASE_URL。模型需要支持Chat Completions和JSON输出；密钥只保存在本地。示例配置中的模型名称不是服务可用性承诺。

```bat
python -s scripts/run.py experiment --experiment examples/experiment_full.json --check-only
python -s scripts/run.py experiment --experiment examples/experiment_full.json
```

第一条只检查输入及组件，不验证API连通性。第二条调用你配置的模型，可能产生费用。示例使用合成问题与合成片段，用于贯通六阶段及四方法输出，不用于医学效果评价。结果位于storage/experiments/examples/full_pipeline。

评价需要另外安装Ollama并准备本地 `qwen3:4b-instruct`，Python依赖不包含Ollama程序或权重。服务默认地址http://127.0.0.1:11434：

```bat
python -s scripts/run.py evaluate --source-dir storage/experiments/examples/full_pipeline --check-only
python -s scripts/run.py evaluate --source-dir storage/experiments/examples/full_pipeline --workers 2
```

评价输出在storage/experiments/evaluation/<时间>/。check-only不调用模型；实际评价只读答案，不重新生成。Windows低资源机器可用workers=1。

## 4. 使用自己的真实数据和指南

按[数据准备说明](docs/data.md)独立预处理数据、构建指南库，复制实验配置并修改dataset、knowledge_base、scope_config和output_dir。cMedQA2的示例配置为configs/experiment_cmedqa2.json，必须先准备真实数据与索引，不能在空仓库直接运行。

```bat
python -s scripts/run.py experiment --experiment configs/experiment_cmedqa2.json --check-only
python -s scripts/run.py experiment --experiment configs/experiment_cmedqa2.json
```

后续任何新实验都使用experiment入口；evaluate只接受显式结果目录，不默认读取作者本机历史批次。其他脚本是数据、知识库和诊断工具，可用 `python -s scripts/run.py --list` 查看。

## 5. 框架与替换

```text
configs/               实验参数、任务目录、提示词
src/sec_rag/
  data/                各数据集预处理和读取适配
  knowledge/           PDF提取、清洗、分块、索引构建
  retriever/           01 检索
  structurer/          02 原文证据单元
  filter/              03 完整性 → 04 适用性 → 05 回答边界
  generator/           06 最终回答
  method/              阶段接口、顺序执行、文件完整性检查
  experiments/         基线与完整方法插件
  evaluation/          独立评分
  llm/                 模型请求和轨迹
  utils/               公共工具
scripts/               运行入口
examples/              可公开的合成示例
storage/               运行时创建的数据、中间产物和结果；不发布
tests/                自动测试代码（不是实验结果）
docs/                  数据、接口、评价和贡献说明
```

接口允许用components配置选择阶段实现，用plugins添加完整方法。替换第二阶段的示例为examples/experiment_sentence_units.json。实现必须满足接口及来源字段要求，不能随意删除下游字段。具体签名与限制见[接入协议](docs/extensions.md)和[目录/阶段说明](docs/structure.md)。

默认后端是BM25；接入向量库需实现配套索引与预检适配。生成客户端支持当前OpenAI兼容协议，评价使用Ollama；不能保证任意厂商无需适配。不同知识库实验请分别启动进程，不在同一进程并发切换全局配置。

## 6. 如何找到结果

每次生成目录包含experiment_manifest.json（配置与版本）、input_questions.json（输入）、progress.json（状态）。每题questions/<qid>/下保存：

- 01_retrieval至06_final_answer：SEC-RAG六阶段JSON，最后文件的final_answer.answer是最终文字。
- baselines/<方法名>.json：其他方法的答案与调用信息。
- run_manifest.json：SEC阶段目录；artifacts.json：保存文件的完整性清单。

每次评价目录包含main_quality_evidence_table.csv（汇总）、same_question_comparison.csv（同题对照）、questions/（逐步判断）、implementation_snapshot/（实现快照）。公开指标来源、公式和本项目适配见[评价定义](docs/evaluation.md)。拒答无医学内容时记N/A，失败单列，不能把拒答记满分。

同配置重跑生成会核验并复用记录。源码、数据、配置变化应选择新的output_dir；损坏记录不自动覆盖。评价中断时加 `--resume <原评价时间目录>`；评价代码或模型变化时新开运行。阶段文件可能含原始问题和模型响应，分享真实数据结果前自行核对内容。

## 7. 测试、贡献和许可

```bat
python -s -m unittest discover -s tests
```

测试不调用付费API。合成替换测试不能证明医学质量。GitHub Actions检查Windows和Linux上的安装与离线行为；实际结果以Actions页面为准。

请按[贡献与自检说明](CONTRIBUTING.md)提交修改。不要上传.env、真实问答、受限指南、模型权重、调试批次或PPT。第三方数据和依赖遵守各自许可。本项目正式代码许可仍待作者/课题组确认，当前不附带MIT等商用授权。
