# SEC-RAG 框架与目录对应说明

更新：2026-10-06。现有数据和历史结果不移动；历史结果不代表已用此次代码重新生成。

## 1. 系统目标

输入外部问答数据和外部指南知识库，对同题运行裸模型、普通RAG、提示词约束RAG及SEC-RAG，保存过程、答案，再独立评价。SEC-RAG在检索后、最终生成前约束证据，研究减少没有依据的回答。没有新增生成后语义审核或改写步骤。

标准化是固定模块间的输入输出约定，允许选择符合约定的不同实现；不代表任意代码可以直接替换，也不保证换方法后的效果。

## 2. 与期望框架对应

保留configs、src/sec_rag和storage的实际名称，避免破坏已有记录中的路径及哈希。

```text
SEC-RAG/
├── configs/                       对应config：参数、实验选择、提示词
├── storage/
│   ├── datasets/raw/              对应data/raw：原始数据
│   ├── datasets/processed/        对应data/processed：按数据集保存处理产物
│   ├── knowledge_base/            对应data/knowledge_base：指南、文本、片段、索引
│   └── experiments/               对应runs和results：一次实验的过程及结果
├── src/sec_rag/
│   ├── data/                      数据集专用预处理、字段适配
│   ├── knowledge/                 PDF提取、清洗、分块、索引构建
│   ├── retriever/                 检索阶段
│   ├── structurer/                构建原文证据单元
│   ├── filter/                    完整性、适用性、回答边界
│   ├── generator/                 基于获准证据生成答案
│   ├── evaluation/                对应evaluator：独立评价
│   ├── llm/                       模型请求、JSON输出与调用留痕
│   ├── utils/                     公共文件读写、哈希和并发工具
│   ├── method/                    阶段选择、接口检查、顺序执行、续跑
│   ├── experiments/               基线方法及完整方法扩展
│   └── pipeline.py                实验总调度
├── scripts/                       用户运行入口
├── examples/                      合成数据、知识库和配置示例
├── tests/                         离线回归及接口测试
├── docs/                          当前说明
└── README.md                      安装运行入口
```

没有人工标注任务，不预建annotations；没有Notebook任务，不预建notebooks。runs与results合并在一次实验自己的目录，避免重复保存不同版本。archive中的历史PPT不是运行依赖。

## 3. 配置放什么

- configs/experiment_cmedqa2.json：数据文件及字段、知识库位置、范围配置、Top-N、对比方法、六阶段实现、输出目录。
- configs/experiment_scope.json：实验允许的疾病范围。
- configs/knowledge_chunking.json和configs/bm25.json：分块及BM25参数。
- configs/sec_rag_v5_context_v1.json：当前方法设置，包括阶段内部并发。
- configs/tasks.json：任务名到运行脚本的对应关系。
- configs/prompts：baselines、sec_rag_v5、evaluation分别保存真实使用的模板。不同阶段输入输出不同，提示词不能随意合并。
- .env：本地模型服务和密钥，不发布；requirements.txt：总环境依赖。

没有新增default.yaml/models.yaml等平行参数副本。文件名不必照搬示例树，职责要明确。

## 4. 数据和知识库准备

数据：data/cmedqa2负责专用读取、疾病筛选、去重和问题池构建。输入原始问答，输出按数据集保存的候选及问题池。新数据集的特殊清洗应新增独立模块。

data/adapters.py读取实验指定CSV或JSONL，按配置识别问题ID、原问题、疾病范围，保留原记录。不强制把不同数据集重新保存成统一磁盘中间表。

知识库：knowledge接收PDF，依次产生提取文本、清洗文本、片段和BM25索引。来源文档、页码、片段ID保留。不同指南集使用不同知识库根目录，通过实验配置选择。回答时读取已建索引，不重复解析PDF。

## 5. 单题六阶段：实现、输入、输出、用途

下列输出均位于本次实验的questions/<问题ID>/。阶段记录包含原始输入、状态、上游文件路径/哈希；通用入口还记录组件源码路径/哈希。模型阶段保存实际提示词和模型响应。

### 01 检索

实现：retriever/bm25.py。
输入：原问题、疾病范围、Top-N、已建知识库。
输出：01_retrieval.json，retrieval_results保存原文片段、排名、文档与页码。
用途：三种RAG共享初始片段，默认不增加重排。

### 02 证据结构化

实现：structurer/evidence.py。
输入：01检索片段。
输出：02_evidence_units.json。candidate_chunks保存原片段句子；evidence_units保存由相邻原句组成的单元；excluded_sentences保存排除项。
用途：形成可单独判断的证据。模型选择组合，程序从原文取文字，不自由改写证据。

### 03 完整性

实现：filter/integrity.py。
输入：02证据单元。
输出：03_integrity.json，记录检查结果、可用/暂不使用的证据及恢复过程。
用途：避免残缺片段直接进入生成。恢复文字必须是可核验的连续原文。

### 04 适用性

实现：filter/applicability.py。
输入：03可用证据、原问题及02原片段上下文。
输出：04_applicability.json，保存信息需求标注、每条证据对应的需求、支持内容、适用条件和不能延伸的结论。
用途：判断证据与原问题的关系。保留原问题，不把需求改写成独立检索问题。上下文不自动成为获准证据。

### 05 回答边界

实现：filter/coverage.py。
输入：04信息需求和适配证据。
输出：05_coverage.json，coverage_analysis说明可回答部分、缺失部分、允许的证据及必须保留的条件。
用途：约束下一阶段回答；此阶段不生成最终答案。

### 06 回答生成

实现：generator/constrained.py。
输入：原问题、获准证据和05边界。
输出：06_final_answer.json。final_answer.answer是展示答案，claims是陈述和引用ID，insufficient_information说明证据不足。
用途：形成最终回答。格式/引用ID检查不是新增的生成后语义评价。

run_manifest.json是单题阶段索引，记录状态和文件位置。method/v5.py仅保留兼容导入，没有第二套旧算法；实际代码已拆到上述目录。

## 6. 对比和评价保存在哪里

同题三个基线保存在baselines/<方法名>.json。
实验根目录input_questions.json保存输入；experiment_manifest.json保存配置与代码/数据指纹；progress.json保存进度。
评价独立读取已保存答案，结果按评价输出配置保存，不回灌修改答案。当前指标定义和公式见evaluation.md。本次没有修改评分公式、提示词或医学判断规则。

## 7. 怎样更换方法

实验配置components显式选择六阶段实现。仅覆盖要替换的阶段，其他阶段用默认值。例如：

```json
"components": {
  "02_evidence_units": "sec_rag.structurer.sentences:stage02_sentences"
}
```

附带的sentences示例用一个原句形成一个单元，只供接口验证或另行设计的消融；不是默认方法，没有宣称效果更好。

第一阶段函数接收question及关键字参数question_id/source_dataset/disease_scope/top_n/output_path；后五阶段接收input_path、output_path。所有函数返回阶段字典。

公共字段检查在method/components.py；详细标签和嵌套字段规则由各阶段校验器负责。新实现必须同时满足下游所需字段，保留原问题、来源、唯一证据ID，不能仅输出一段文字。缺字段或篡改原问题会失败并留痕，不能当成功结果。

源码放在当前项目以记录来源；只加载自己信任的组件配置。新增完整对比方法用plugins，和更换SEC-RAG内部阶段不同。

修改数据、组件或配置后使用新的output_dir，不能混入旧结果。已有运行若检测到指纹改变会拒绝续跑。

## 8. 当前边界必须知道

- 已支持CSV/JSONL字段适配、知识库位置选择、完整方法扩展、六阶段实现选择。
- 默认知识库预检仍要求BM25 corpus/index_manifest。换向量库需配套索引构建、预检和检索适配，不能只改名称。
- PDF清洗、分块由知识库准备入口执行，尚未纳入六阶段插件配置。
- 生成和本地评价客户端仍有不同协议；不是所有模型厂商都能无改动互换。
- 结构检查不能证明医学判断正确，替换组件后仍需实验验证。
- 同一进程的settings选择知识库，不应同时启动不同知识库实验；分开进程运行。
- 新的组件选择使用scripts/experiment.py；旧单阶段脚本为兼容保留，不读取实验components选择。

## 9. 验证与运行

离线测试覆盖两种数据格式、两个知识库、错误接口、替换第二阶段后六阶段串联及续跑隔离。接口测试用合成模型响应，不调用付费API，不属于医学效果结果。

先预检（不调用模型）：

```bat
python -s scripts/experiment.py --experiment configs/experiment_cmedqa2.json --check-only
```

通过后由使用者运行生成（调用配置的模型）：

```bat
python -s scripts/experiment.py --experiment configs/experiment_cmedqa2.json
```

若输出目录属于旧配置，选择新output_dir，不要通过清空历史结果跳过检查。先用少量数据确认运行，再开展固定开发/验证/测试集实验。


## 10. 本轮接口与续跑补充（2026-10-08）

公共接口现在核对：02保留初始片段及句子ID；03保留来源关系；04的信息需求必须引用原问题、证据不得改写；05保留需求并只允许已映射证据；06引用必须属于允许证据。

04仍要回读02的candidate_chunks，这属于明确保留的上下文依赖。替换02/03时必须保留原句结构及source_record链，不能只交付证据文本。接口实现见method/components.py的validate_links。

实验总入口新增每题artifacts.json完整性清单，续跑检查文件哈希，拒绝缺失、篡改及未登记结果。主方法直接入口也核对运行清单中已完成阶段的哈希。因强制终止而未写完清单的运行可能需要新建目录，不承诺任意时刻中断都自动恢复。

旧结果未补写新清单，保持不变；仍可用于独立评价。算法、提示词、评价公式未因接口整理改变。

README已区分新experiment入口与历史generate兼容入口。所有新组件实验应使用experiment；不自动将旧任务指向新的付费运行。
