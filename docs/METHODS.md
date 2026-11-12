# 论文、方法模块与复现边界

本项目完整覆盖文献到知识资源的三个实训环节。论文贡献、课程实现和实际运行结果分别报告：完整教学流程不自动代表复现全部论文数据、训练、基线与排行榜指标。具体已运行内容以 [VERIFICATION.md](VERIFICATION.md) 为准。

## 方法对应

| 环节 | 论文与发表信息 | 可借鉴内容 | 必须说明的适配 |
|---|---|---|---|
| 实体识别 | [Refining and Reusing Annotation Guidelines for LLM Annotation](https://aclanthology.org/2026.acl-long.1760/)，ACL 2026 主会长文 | 以明确标注指南约束实体类型与边界，按人工参考评价 | 课程固定指南和结构化输出；若未运行作者多轮指南优化，就不称已复现该优化实验 |
| 关系抽取 | [Benchmarking large language models for biomedical natural language processing applications and recommendations](https://www.nature.com/articles/s41467-025-56989-2)，Nature Communications 2025，16:3280 | 公开的零／少样本关系分类实验及评价设计 | 原实验包含句级 ChemProt、DDI；课程迁到 BioRED 摘要级关系并使用 DeepSeek，属于数据、提示和模型适配 |
| 实体对齐与融合 | [Large language model powered knowledge graph construction for mental health exploration](https://www.nature.com/articles/s41467-025-62781-z)，Nature Communications 2025，16:7526 | 将术语表示与标准概念候选比较，统一跨来源实体 | 原 MDKG 链接涉及 HPO/GO/MONDO/UBERON/UMLS；课程换为本项目的独立实体词典。词典精确匹配不等于已经运行 SapBERT 模块 |
| 上下文候选选择 | 课程新增模块 | 利用来源摘要区分候选标准实体，给出原文证据并允许弃答 | `contextual` 主线在独立候选库上增加 DeepSeek 选择和真实回放，不是 MDKG 论文提出或开源的原始算法 |
| 证据核查 | [Combining Evidence and Reasoning for Biomedical Fact-Checking](https://doi.org/10.1145/3726302.3729931)，SIGIR 2025 Full Paper | 检索相关证据、生成核查理由、判断支持情况 | 课程使用有限文献集及 API 核查，不复现全 PubMed 检索和大型模型训练；核查候选不直接裁决世界范围的生物学真相 |
| 修订与增量 | 课程新增工程 | 保存独立来源、记录历史、重新查询、回归验收 | SQLite、修订接口和教学故障不是上述论文原有的完整版本管理系统 |

ACL 与 SIGIR 在这里指正式主会长文／Full Paper；Nature Communications 是 Nature 旗下期刊，不是《Nature》本刊。

## 原始实现入口

核查日期：2026-11-12。下面是作者入口，教学代码的固定输入、模型及数据版本由仓库 manifest 和真实响应元数据记录。作者仓库的引用快照已通过 GitHub API 核查如下；这些版本用于说明阅读依据，不表示四套原始代码全部已执行。

| 作者仓库 | 引用 commit |
|---|---|
| ACL 2026 指南方法 | [33d58d6603ab2c6cfd5aa98e4b14ae17b1ed2ac4](https://github.com/KonWooKim/llm-guideline-moderation/tree/33d58d6603ab2c6cfd5aa98e4b14ae17b1ed2ac4) |
| NC 2025 BioNLP benchmark | [e607a812d87df151f310a9dd3677cfc21924f192](https://github.com/BIDS-Xu-Lab/Biomedical-NLP-Benchmarks/tree/e607a812d87df151f310a9dd3677cfc21924f192) |
| MDKG | [b6b745aa3789cca430240489151826e9a2b21e41](https://github.com/MonsterTea/MDKG/tree/b6b745aa3789cca430240489151826e9a2b21e41) |
| CER | [5c6544b41f7a722c3fb0c98757017f79a80d524d](https://github.com/PRAISELab-PicusLab/CER/tree/5c6544b41f7a722c3fb0c98757017f79a80d524d) |

| 作者仓库 | 优先阅读的位置 | 公开实现的实际边界 |
|---|---|---|
| [KonWooKim/llm-guideline-moderation](https://github.com/KonWooKim/llm-guideline-moderation) | `data/guidelines/`、`data/schemas/`、`scripts/run_iterative_refinement.py` | 主要是 NER 指南优化及预测导出；不能作为关系和证据句金标来源 |
| [BIDS-Xu-Lab/Biomedical-NLP-Benchmarks](https://github.com/BIDS-Xu-Lab/Biomedical-NLP-Benchmarks) | `GPT/extractive_tasks/run_gpt.py`、`benchmarks/`、`run_eval.py` | 旧 Azure API 需适配；原评价入口含其他任务的 GPU 依赖，不能直接当作 CPU 教学入口 |
| [MonsterTea/MDKG](https://github.com/MonsterTea/MDKG) | `Entity_linking.py` | 已有 CPU 分支；原本体索引及 NCBI Gene 接口需另行准备，不是下载脚本即可完成我们的任务 |
| [PRAISELab-PicusLab/CER](https://github.com/PRAISELab-PicusLab/CER) | `Code/Code.ipynb`、`Datasets/` | 提供核查框架；原训练及模型规模不能直接当作学生 CPU 要求 |

课程的抽取、实体对齐和模型证据核查只读取原文及独立词典，不读取评分金标。`evaluate` 使用金标评分，`prepare-revision` 也读取金标以选出一条原预测与参考一致的关系，供教学故障与恢复实验使用；这两类操作不计作首次预测。参考记录导入若作为教师对照实验，必须另建目录并标明模式。

## 三条对齐路径

- `lexical`：独立词典别名、文内有明确依据的名称对应和保守物种规则，属于课程基线。
- `sapbert`：在课程候选短名单上使用 SapBERT 嵌入比较，借鉴 MDKG 的实体表示匹配。候选库、短名单、阈值和歧义规则均需作为适配记录；不能称作原 MDKG 全量对齐指标复现。
- `contextual`：词典基线加来源上下文中的候选选择，作为完整教学主线。真实模型只能选择提供的 ID；证据子串通过检查并不自动证明实体身份正确，结果保留模型候选状态。

三种路径的实际评价已保存在 [metrics.json](../reports/metrics.json)。默认主线加入上下文选择，是为处理词典覆盖和歧义暴露的问题；不通过给预测填入 gold ID 提升指标。免费回放保存真实的上下文选择响应，学生无需独立显卡或付费。

可选语义路径使用作者发布的 [cambridgeltl/SapBERT-from-PubMedBERT-fulltext](https://huggingface.co/cambridgeltl/SapBERT-from-PubMedBERT-fulltext)，模型卡标示 **Apache-2.0**。下载固定在 revision `090663c3ae57bf35ffe4d0d468a2a88d03051a4d`，实测文件 SHA256 见 [model_manifest.json](../data/model_manifest.json)。SapBERT 本身发表于 NAACL 2021；这里将其作为 2025 年 MDKG 所借鉴的生物实体表示组件，不把基础模型说成 2025／2026 年新模型。

作者模型卡使用末层 `[CLS]` 表示；本课程实现采用带 attention mask 的均值池化和 L2 归一化，最大长度 64、批量 32、CPU 推理。因此本仓库的 SapBERT 对照成绩属于这套课程配置，不能冒充作者标准推理协议或原 MDKG 的整套实验结果。模型卡说明其训练使用 UMLS 2020AA，本课程不分发 UMLS 原始词典；外部候选词典的来源与许可另见 [DATA_SOURCES.md](DATA_SOURCES.md)。

## 怎样填写自己的实验报告

每个模块记录：输入文件哈希、数据划分、模型／方法名称、参数、输出文件、评价范围、错误示例。只填实际运行结果：

- 使用原始实现和数据，但更换模型：报告“模型替换复现”。
- 修改数据、标签、上下文粒度或候选库：报告“方法迁移／教学适配”。
- 读取本项目真实保存响应：报告“真实结果回放”，API 调用次数为 0。
- 选择一条原预测与金标一致的关系，再向预测副本注入已知错误：报告“教学故障实验”，不能计入模型真实错误率。
- 无独立证据句金标：报告核查覆盖率和待审数量，不编造证据句准确率。

## 延伸阅读

[ACL 2025 关系评价论文](https://aclanthology.org/2025.acl-long.1238/) 的裁判输入包含已有参考关系。裁判可以辅助解释别名和格式差异，不能给没有金标的新文献制造权威答案。

[BioREDirect](https://doi.org/10.1093/bioinformatics/btaf226) 是 Bioinformatics 2025 的方向标注扩展。它可作为后续数据规范参考，但没有被包装为 CCF A 会议论文；未显式导入这一版本时，课程不能假定 BioRED 原版具备方向标签。
