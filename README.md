# SEC-RAG

用于医学问答的证据约束 RAG 实验项目。研究的是生成前证据约束能否减少缺乏给定指南依据的回答内容；不将自动评分称为临床正确率。

## 项目入口

- [目录与模块职责](docs/structure.md)：每部分放什么，输入输出在哪里。
- [开发实验步骤](docs/development.md)：当前随机30题四方法实验。
- [评价定义](docs/evaluation.md)：公开来源、公式、适配与结果位置。
- [证据适用性设计](docs/evidence_alignment.md)：信息需求与证据的关系。

## 目录

```text
SEC-RAG/
├── configs/                 # 参数、任务配置和版本化提示词
├── src/sec_rag/             # 可复用核心代码
│   ├── data/                # 每个数据集独立的处理逻辑
│   ├── knowledge/           # PDF提取、清洗、分块、索引与检索
│   ├── retriever/           # 检索阶段
│   ├── structurer/          # 原文证据单元
│   ├── filter/              # 完整性、适用性、回答边界
│   ├── generator/           # 受约束回答生成
│   ├── utils/               # 公共工具
│   ├── method/              # 组件接口、顺序执行与续跑核验
│   ├── experiments/         # 三个基线方法与公共输出校验
│   ├── evaluation/          # 自动评价、公式计算与评价记录
│   └── llm/                 # 生成模型接口
├── scripts/                 # 运行入口；run.py为推荐入口
├── docs/                    # 当前说明；history/为历史设计
├── tests/                   # 离线自动测试
├── storage/                 # 本地数据和实验产物，不随代码发布
│   ├── datasets/            # raw/原始数据；processed/按数据集保存
│   ├── knowledge_base/      # 原指南、提取文本、分块、索引
│   └── experiments/         # 逐次运行、评价和同题对照
├── archive/                 # PPT工作区与停用脚本，本地归档
├── environment.yml          # 一步创建conda环境
├── requirements.txt         # 总依赖清单
├── .env.example             # 模型配置示例，不含密钥
└── README.md
```

保留 `configs` 和 `storage` 命名是为了兼容已有结果中的路径和哈希。这里的 storage/experiments 承担 runs 的职责；汇总结果保存在所属运行中，不再复制出另一套 results。没有人工标注时不预建 annotations，没有分析笔记时不预建 notebooks。

## 安装

在项目根目录运行（Windows Anaconda Prompt）：

```bat
conda env create -f environment.yml
conda activate sec-rag
set PYTHONNOUSERSITE=1
python -s scripts/run.py env
```

总依赖由 environment.yml 引用 requirements.txt。本次整理未安装或升级依赖。复制 .env.example 为 .env，填写生成模型名称和API密钥；不要提交 .env。评价使用本地Ollama qwen3:4b-instruct，Ollama程序和模型权重需要另行安装。总依赖已移除停用的语义相似度实验专用包（torch、transformers等）；这不会卸载你本机已有包。

原始数据和指南需自行准备：cMedQA2 的 question.csv、answer.csv 放在 storage/datasets/raw/cMedQA2-master/；指南按疾病目录放在 storage/knowledge_base/documents/。配置中的疾病范围应与资料一致。外部数据和指南的再分发须遵循原来源条件，本仓库不直接打包它们。

## 统一运行入口

```bat
python -s scripts/run.py --list
python -s scripts/run.py generate --dry-run
```

`--dry-run`只展示命令，不调用模型、不写实验结果。任务及默认参数在 configs/tasks.json；额外参数传给实际运行脚本。原编号脚本仍可使用，避免中断现有工作。

数据处理依次运行：

```bat
python -s scripts/run.py data.inspect
python -s scripts/run.py data.candidates
python -s scripts/run.py data.pool
```

知识库依次运行：knowledge.extract、knowledge.check-text、knowledge.clean、knowledge.chunk、knowledge.check-chunks、knowledge.index。各步骤会保存自己的中间产物。已有知识库无需因本次目录整理重建。

历史30题兼容入口（不读取新实验的components选择；新实验使用下文experiment入口）：

```bat
python -s scripts/run.py generate --check-only
python -s scripts/run.py generate
python -s scripts/run.py evaluate --check-only
python -s scripts/run.py evaluate
```

旧generate入口会调用DeepSeek并产生费用；历史30题已保存，不要为框架升级重跑。evaluate 调用本地Ollama，耗时取决于机器。两种 check-only 都不调用模型。评价结果按时间另建目录；中断后可通过 evaluate --resume <原输出目录> 续跑，代码或提示词变化后应新开评价运行。

## 方法与结果

三个RAG方法使用同题同一批BM25 Top5；Top5是当前预设而非最优结论。SEC-RAG按以下六阶段保存：检索、证据单元、完整性、适用性、回答范围、最终答案。不增加生成后验证模块。

历史30题回答位置：storage/experiments/development/cmedqa2/first_batch_v2/questions/<qid>/。基线放在baselines/，SEC-RAG中间结果为01至06的JSON。

评价运行包含：main_quality_evidence_table.csv（汇总）、same_question_comparison.csv（同题对照）、questions/（逐条输入判断和分子分母）、implementation_snapshot/（代码和提示词副本）、run_manifest.json（模型与输入版本）。

## 标准实验接口

新实验统一使用 `python -s scripts/run.py experiment --experiment <配置文件>`。它支持不同CSV/JSONL字段映射、独立知识库目录、方法选择、自定义RAG方法注册和components阶段选择。原始数据不必统一为同一中间表；只在读取时映射问题编号、问题和领域。

无需API或真实医学数据的两组入门演示：

```bat
python -s scripts/run.py experiment --experiment examples/experiment_a.json
python -s scripts/run.py experiment --experiment examples/experiment_b.json
```

两组示例采用不同数据格式、不同字段名与两份合成知识库，调用无模型的抽取式演示插件；只能证明接口运行，不是SEC-RAG医学效果测试。

现有cMedQA2标准配置（仅检查，不重新生成已完成回答）：

```bat
python -s scripts/run.py experiment --experiment configs/experiment_cmedqa2.json --check-only
```

去掉check-only会启动一个新的付费实验，输出standardized_v1目录，不复用旧批次答案。旧30题仍可通过evaluate入口评分。

完整接入协议见[扩展说明](docs/extensions.md)。当前方法内部算法未改，但支持选择不同知识库根目录和范围配置；不同知识库仍须先完成提取、清洗、分块和索引。不是任意原始文件都能直接输入。

## 测试与发布

```bat
python -s -m unittest discover -s tests
```

离线测试不证明医学判断正确。archive/和storage/下的本地内容由.gitignore排除；但.gitignore不会取消Git既有跟踪，正式发布前还需检查已跟踪的数据和密钥，并由项目作者确定开源许可证。暂未加入LICENSE，因此当前发布准备不等于已授予开源使用许可。本次没有推送或发布仓库。

发布准备：`python -s scripts/package_release.py`导出仅含代码、配置、文档和合成示例的ZIP；不打包旧Git历史。GitHub账号与仓库由用户确定，不能根据邮箱代为登录。

## 框架核验与续跑（2026-10-08）

新运行在每道题下保存artifacts.json，记录阶段文件、运行清单和基线答案的哈希。续跑前发现缺失、修改或未登记文件会停止，不会将它们直接当作已完成，也不会自动调用模型替你覆盖。保留原运行并使用新输出目录。没有该清单的旧结果仍可读取、评价，但不直接接续为新运行。

主方法必须实际保存最终答案才记为成功。阶段接口检查覆盖原问题、证据来源、信息需求引用及允许证据之间的关系，不是医学语义评分。

真实3题历史结果：storage/experiments/testing/framework/cmedqa2_smoke3_20261006/。重构后只读验证了其18个阶段记录；没有重新生成答案。

只更新代码不要求重跑历史结果。今后启动新的真实实验应先指定新的output_dir，再运行check-only；接口测试使用合成输入且不调用API。

仍未完成的通用化范围：非BM25索引、任意厂商模型协议、任意新方法的评价输出适配。开放源码发布还需确定许可证、仓库，并在新环境验证安装；本轮未安装环境、下载模型或发布仓库。
