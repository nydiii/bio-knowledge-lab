# 生物科学知识建模实训操作手册

本实训要解决一个具体问题：读过多篇生物医学摘要后，怎样查到“哪些文献提到了同一个对象、各自报告了什么关系、这些判断依据在哪里”，并在发现问题或加入新文献时保留修改记录？你将把同一批 BioRED 文献从原文整理成可查询的知识库，完成 **原文信息抽取 → 实体对齐与跨文献融合 → 证据核查、修订和增量更新**。这里的 BioRED 是带有人工标注的公开生物医学文献数据集，本课使用其中 50 篇摘要。

第一次接触这些术语，请先读第 0 节，再安装和运行。第 1—8 节是免费主线，其中第 5.5 节的方法对照可跳过，第 9 节真实 API 也是进阶内容。资料规模、原文来源、跨文献关联及实际运行指标分别见 [DATA_SOURCES.md](DATA_SOURCES.md) 和 [VERIFICATION.md](VERIFICATION.md)。

默认路径读取本项目保存的真实模型响应。安装完成后，免费回放不调用模型、不需要 API Key。后半部分提供重新调用 DeepSeek 的路径；模型输出可能变化，不能要求真实调用逐字等于回放。

## 0. 先弄懂我们在处理什么

### 0.1 从一段文字到可以查询的记录

阅读论文时，人能认出研究对象、理解简称、比较结论。计算机要按这些内容查询，需要先把它们写成字段明确的记录。下面用一个**虚构的句子**解释步骤，它不来自课程文献，也不表示真实的生物学结论：

> 本研究发现，蛋白甲（PA）与疾病乙有关。

1. **找实体。** “实体”是我们要记录的研究对象，例如基因、蛋白、疾病、药物或物种。句中的“蛋白甲”“PA”“疾病乙”都是值得识别的名称。某个名称在原文某个位置出现一次，叫一次“实体提及”；“蛋白甲”和“PA”可以是同一对象的两次提及。
2. **抽取信息。** 把名称、类别、原文位置记录下来，再判断原文是否支持对象之间的关系。例如记下“蛋白甲—有关联—疾病乙”，并保存依据。这里的“抽取”是把文字转成规定格式的记录，关系部分需要模型理解文本，可能发生错抽、漏抽。
3. **对齐身份。** 根据“蛋白甲（PA）”这个写法、实体类型和上下文，查独立标准词典，判断全称与简称是否指向同一个标准实体。标准 ID 像数据库中的对象编号，让不同文献里的不同写法能连接起来。若找不到可靠对应，应保留未解决状态。
4. **融合文献。** 如果另一篇文献也提到同一标准实体，就通过这个 ID 把文献关联起来；两篇文献的原文、关系和证据仍分别保存。这样才能问“哪些文献涉及这个对象”，并比较各篇说法。
5. **核查和更新。** 回到原文检查关系是否被准确表达，有依据时提交修订并保存历史；以后加入新文献，再看它带来了哪些新记录和关联。

如果句子只说“我们分别研究了蛋白甲和疾病乙”，两个名称同时出现，仍不足以抽出它们有某种生物学关系。“有关联”也不能直接改写成“蛋白甲导致疾病乙”。

### 0.2 容易混淆的概念

| 概念 | 本课中的意思 | 阅读结果时注意什么 |
|---|---|---|
| 实体提及 | 名称在某篇原文中的一次出现，有文字和位置 | 一个对象出现多次，会有多个提及；2603 个提及不等于 2603 种对象 |
| 实体抽取 | 找出名称，并判断属于基因／基因产物、疾病等哪一类 | 找到字符串不代表类型判断一定正确 |
| 关系抽取 | 判断这篇文献如何描述两个对象之间的关系 | 同时出现不等于存在关系；关系候选仍可能出错 |
| 实体对齐／链接 | 将提及连接到独立标准词典中的对象 ID | 不同名字可能指同物；同名基因来自不同物种时不能直接合并 |
| 跨文献融合 | 按标准 ID 关联多篇文献，同时保留各自来源 | 不能把多篇不同说法覆盖成一个没有出处的“最终答案” |
| 候选 | 模型或方法给出的待核对结果 | `resolved` 只表示方法已选出链接，不等于人工审阅通过 |
| 金标／参考答案 | 数据集作者按标注规范制作的人工参考 | 用于评价指定字段；不是每个新增字段都有答案，也不是不可质疑的定论 |
| 知识库 | 保存文献、实体、关系、来源和历史的数据库 | 本课使用 SQLite 文件；库里也保存不确定和待审内容 |
| 增量更新 | 在已有库中加入本次尚未导入的文献 | 本课的“新增”指导入顺序，不表示论文发表时间更近 |

实体类型、标准 ID、关系标签和证据属于不同字段，需要分别判断。`Association` 表示关联；`Negative_Correlation` 表示负相关，不能解释为“没有关系”。字段的完整定义见 [SCHEMA.md](SCHEMA.md)。

### 0.3 模型、程序和你各自做什么

**模型**是已经训练好的语言模型，本课主线使用 DeepSeek 已生成的回答。它根据文本和提示判断名称、关系、候选身份及证据支持情况；这些判断可能出错。**程序**是本仓库的 Python 代码，负责组织步骤、读取或请求模型回答、处理数据、检查格式、计算指标和保存知识库。你在终端执行的是程序命令。本课不要求训练一个新模型。

| 环节 | 模型承担的判断 | 程序承担的操作 | 学生需要理解和检查的事 |
|---|---|---|---|
| `extract` 抽取 | 给出实体名称和类型，再提出关系及证据候选 | 读取原文和回答，定位文字，编提及编号，检查输出并保存 | 名称能否在原文找到；关系是否忠于原文 |
| `align` 对齐 | `contextual` 路径中，根据上下文从提供的候选 ID 中选择或弃答 | 查独立词典、处理明确别名和缩写、保存 ID 与歧义状态 | 为什么选这个 ID；物种和名称是否匹配 |
| `evaluate` 评价 | 不需要模型评分 | 按固定规则，把预测和人工金标逐项比较 | 分数评价了什么；错误来自哪个环节 |
| `fuse`、`query` 融合与查询 | 不新增模型判断 | 写入数据库，按标准 ID 找到跨文献关联 | 同一对象关联了哪些文献；出处是否还在 |
| `check`、`check-evidence` 检查 | 后者判断原文是否支持关系候选 | 前者核对结构；后者组织核查并检查模型证据能否定位 | 格式正确与语义正确有什么区别 |
| `revise`、`history`、`update` 修订与更新 | 不自动决定哪些科学结论应被接受 | 按提案及版本执行修改、保留历史、处理新增和重复记录 | 修改依据是什么；变化是否可追溯 |

**免费回放与真实调用的区别：** 真实调用把输入发给模型服务，得到一次回答并可能产生费用；免费回放读取教师事先保存的真实回答，重新执行定位、对齐中的规则处理、入库、评价等本地步骤。因此免费路径仍能练习完整的数据处理过程，但这次运行没有让 DeepSeek 重新推理。修改文献或提示后，旧回答不能当作新输入的模型结果。

你另外用来询问术语、解释命令的聊天 AI，是学习助手。它的解释不自动写入本课知识库，也不构成实验结果或人工金标。可以请它讲解，但最后要能指着自己的原文、输出字段和日志说明理由。

### 0.4 每一步怎样接起来

```text
文献标题和摘要
  → extract：原文 + 实体提及 + 关系候选
  → align：为提及补上标准 ID，或保留歧义和未解决状态
  → fuse：存入知识库 → query：查看跨文献关联和来源
  → check / check-evidence：找出结构问题和需要核对的判断
  → revise：按有依据的提案修改 → history：查看修改过程
  → update：加入新文献 → query：比较加入前后的变化

align 的输出 + 人工金标 → evaluate：得到评价报告
```

评价是旁边的一次比较，不会把参考答案填回模型预测。新增文献也要先抽取和对齐，才能进入 `update`。运行每组命令前，先回答“它读什么、产生什么、为什么需要这一步”；运行后打开指定结果，找一个例子验证自己的解释。

## 1. 准备与安装

**这一步的目的：** 让电脑能运行本课程序。输入是下载的项目文件，结果是可用的 Python 环境和命令入口；此时还没有处理文献。虚拟环境 `.venv` 用于隔离本课依赖，VS Code 是查看和编辑文件的工具，终端才是输入下面命令的位置。

准备普通电脑，推荐 Python 3.12。无需独立显卡。仓库已公开，可直接下载 ZIP 解压，或使用 Git：

```bash
git clone https://github.com/nydiii/bio-knowledge-lab.git
cd bio-knowledge-lab
```

如果使用 ZIP，进入包含 `pyproject.toml`、`src`、`data`、`docs` 的目录再执行命令。所有相对路径都从这里开始。

macOS／Linux：

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[test]"
python -m bio_knowledge_lab --help
```

Windows PowerShell：

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[test]"
.\.venv\Scripts\python.exe -m bio_knowledge_lab --help
```

以下用 `python` 统一书写。Windows 用户可以始终将它替换为 `.\.venv\Scripts\python.exe`，不必修改 PowerShell 执行策略。帮助输出应列出 `extract`、`align`、`fuse`、`query`、`check`、`revise`、`update` 等命令。

读命令时，`python -m bio_knowledge_lab` 表示启动本课程序，紧随其后的 `extract` 等词表示执行哪个步骤。`--input` 指输入文件，`--output` 指输出文件，`--db` 指要操作的数据库，`--workdir` 指本次实验的结果目录，`--mode replay` 表示读取保存的模型回答。

**操作检查：** 在 VS Code 中打开整个 `bio-knowledge-lab` 文件夹，再打开终端。仅在编辑器中打开某个文件，不会自动改变终端所在目录。下面命令可确认当前目录和实际使用的 Python：

```bash
python -c "import sys; from pathlib import Path; print('目录:', Path.cwd()); print('Python:', sys.executable); print('项目根目录:', Path('pyproject.toml').is_file())"
```

最后一项应为 `True`，Python 路径应指向本项目的 `.venv`。这里仍适用上面的 Windows 命令替换方式。不要把 Markdown 的三个反引号或终端提示符一起复制。只有程序命令要在终端执行，JSON 输出示例是供阅读的内容。

## 2. 查看资料并验证来源

**这一步的目的：** 分清“要处理的原文”“用于查身份的词典”“用于评分的参考答案”和“保存的模型回答”。这些材料作用不同，混在一起会导致看似高分却没有真正完成抽取。来源检查读取 manifest（资料清单）和随项目提供的数据，核对文件哈希；哈希可用于判断文件内容是否与指定版本一致。

| 文件 | 用途 |
|---|---|
| `data/corpus/documents.jsonl` | 每行一篇文献，含标题、摘要、完整定位文本、文献编号及课程分组 |
| `data/reference/gold.jsonl` | 原数据集人工标注；只用于评价和教师参考 |
| `data/kb/entities.jsonl` | 独立标准数据库提供的实体候选 |
| `data/replay/` | 真实 API 响应、提示、用量等回放材料 |
| `data/manifest.json` | 数据版本、哈希与来源 |

先核查 manifest 中固定的语料、参考和候选词典文件：

```bash
python -m bio_knowledge_lab fetch --verify-only
```

需要重新下载官方原始资料、重建并核对数据时：

```bash
python -m bio_knowledge_lab fetch
```

完整原始资料下载需要网络，可能明显大于课程子集。NCBI 等上游原始词典会更新；下载内容与 manifest 锁定哈希不一致时，程序拒绝替换课程数据。此时先保存报错，继续使用随仓库提供并已通过 `--verify-only` 的冻结数据，不改 manifest 绕过版本检查。原文定位采用 `title + 换行 + abstract` 的字符位置，不能在抽取前随意改空格或换行。

**看什么、解释什么：** 打开 `documents.jsonl`，读一篇记录的 `title`、`abstract` 和 `doc_id`。JSON 是带字段名的数据格式；JSONL 是每行一条 JSON 记录，本文件每行一篇文献，并非每行一句话。`gold.jsonl` 用于后面的评分，不要把它作为自己的抽取输出。能说明这几个文件的用途后再继续。

## 3. 先完整体验一次

**这一步的目的：** 先看到整条流程的最终产物，再在第 4—7 节逐步拆开。`demo` 读取随项目提供的语料、词典和回放，自动执行全流程，把结果写入 `runs/demo`；不需要模型重新回答。`verify` 读取这次 demo 的产物，检查流程是否符合预期。

```bash
python -m bio_knowledge_lab demo --workdir runs/demo
python -m bio_knowledge_lab verify --workdir runs/demo
```

`demo` 串联初始导入、教学故障、恢复、增量文献及再次导入检查；默认使用免费回放。`verify` 检查已经生成的结果。重新开始完整实验请使用新的目录，例如 `runs/demo-2`，避免把前一次数据库和新结果混在一起。

重点打开：

- `runs/demo/report.json`：整条流程验收。
- `runs/demo/query_initial.json`、`query_injected.json`、`query_corrected.json`、`query_updated.json`：各阶段查询结果。
- `runs/demo/evaluation_initial.json`：与原数据金标的比较。
- `runs/demo/verification_candidates.jsonl`：模型证据核查候选，不是人工金标。
- `runs/demo/knowledge.sqlite`：带历史的知识库。

软件验收通过与科学内容审阅完成是不同的结果。具体如何解释各项检查，见本手册第 8 节。

**看什么、解释什么：** 在 `report.json` 中找到 `passed`、`documents` 和 `scientific_review_complete`。固定回放应有 50 篇文献；`passed: true` 与 `scientific_review_complete: false` 可以同时成立。前者说明流程检查通过，后者说明科学内容仍有待审。能解释这两个字段后，继续分步操作；自动 demo 成功还不能证明你已理解每一步。

## 4. 自己执行科学信息抽取

以下分步实验使用新的 `runs/manual` 目录，与 demo 相互独立。

**这一步的目的：** 把人读的摘要整理成程序可处理的实体和关系记录。输入是初始 40 篇标题与摘要，以及保存的两阶段模型回答；输出是 `extracted_initial.jsonl`，仍然每篇文献一条记录。实体名称和关系判断来自模型回答，原文定位、编号与格式检查由程序完成。

```bash
python -m bio_knowledge_lab extract --mode replay --split initial --output runs/manual/extracted_initial.jsonl
```

每篇原文经过两个阶段：识别实体的原文名称和类别，再利用这些候选识别关系。课程后处理把精确原文名称定位为字符跨度，并记录无效候选；它是明确的课程适配，不是作者原始模型直接给出的金标跨度。

检查输出中的三个部分：

1. `entities`：名称、类型、原文位置和文内提及编号。
2. `relations`：关系两端的提及编号、标签、novelty、候选证据和上下文。
3. `provenance`、`extraction_issues`：真实响应来源、提示哈希及被发现的格式／定位问题。

选一条实体，检查 `text[start:end]` 是否与实体名称相同。选一条关系，阅读完整摘要，解释它为何可能需要跨句判断。

**怎样读一条结果：** 在 VS Code 打开输出文件，找一条记录。外层 `text` 是该篇文献的定位原文；`entities` 中的 `text` 是抽出的名称，`start`、`end` 是在外层原文中的字符位置，从 0 开始、包含起点而不包含终点。`mention_id` 如 `m1` 只是本篇内部编号，不是标准数据库 ID；`relations` 中的 `head` 和 `tail` 用这些编号指向两个提及。编号的先后不表示生物学因果方向。

记录一个实体的名称、类型和位置，再根据一条关系的两个编号找到名称，读它的 `evidence`，用自己的话解释“原文为什么支持或不足以支持这个关系”。不要仅因命令完成，就把所有关系写成正确。

**跟着一条真实记录读：** 在 `extracted_initial.jsonl` 中搜索文献编号 `28846666`，标题开头是 `Interleukin 6 (IL-6)`。本次固定回放有如下两条提及：

| `mention_id` | `text` | `type` | `start` | `end` |
|---|---|---|---|---|
| `m1` | `Interleukin 6` | `GeneOrGeneProduct` | 0 | 13 |
| `m2` | `IL-6` | `GeneOrGeneProduct` | 15 | 19 |

它们在不同位置出现，所以有两个提及编号；此时先记录“原文写了什么”，下一步再查“指向哪个标准对象”。同一篇的 `r2` 是模型提出的 IL-6 与 GDM 的 `Association` 候选；顺着 `head: m32` 和 `tail: m43` 找到对应名称与证据，注意它使用的是正文中的另两次提及。这里没有声称 IL-6 导致 GDM。

## 5. 对齐并融合跨文献记录

主线使用 `contextual`：先查独立词典，再读取模型根据原文从候选 ID 中选择的真实保存结果。这条免费回放路径不下载大模型，也不产生 API 费用。上下文候选选择是课程扩展，不是 MDKG 原方法。

### 5.1 对齐名称与标准身份

**为什么做：** 如果只按文字搜索，“Interleukin 6”和“IL-6”可能被当成两个对象；但只凭字面相同又可能误合并不同物种的基因。`align` 读取刚抽出的记录和独立候选词典，输出带有 `links`、`link_status` 等字段的对齐记录。程序先处理明确匹配和缩写；需要上下文判断的部分读取模型的候选选择。

```bash
python -m bio_knowledge_lab align --input runs/manual/extracted_initial.jsonl --output runs/manual/aligned_initial.jsonl --method contextual --mode replay
```

对齐候选来自独立实体词典。一个明确匹配可进入 `links`；上下文模型只能选择提供的 ID，并给出原文中的证据。不能解决的歧义和未解析项保留原状态。模型选择的 ID 即使进入 `links`，仍带 `model_candidate` 审阅状态，不能当作人工确认。不能因为某名称看起来熟悉，就手填金标 ID 让评价上升。

**接着看同一条记录：** 在 `aligned_initial.jsonl` 找到 `28846666` 的 `m1`、`m2`。固定回放为两者选出的链接都是 `namespace: NCBIGene`、`id: 3569`，但其 `link_review_status` 仍为 `model_candidate`。`NCBIGene:3569` 是标准对象身份，`m1`、`m2` 是文内位置身份，不能互换。候选列表中还有其他物种的 IL6，因此不能把所有写着 IL-6 的名称直接连到同一 ID。这里展示的是方法选出的结果，不是新增的人工确认。

再找一个 `unresolved`（尚未找到可接受链接）或 `ambiguous`（存在多个难以区分的候选），查看它的名称和候选。保留这种状态有助于避免误合并。

### 5.2 用人工参考评价结果

**为什么做：** 程序能运行、记录能保存，不能告诉我们抽取质量。`evaluate` 读取对齐结果和 `data/reference/gold.jsonl`，由程序按固定规则计算评价报告；它不会调用模型给自己打分，也不会修正输入文件。

```bash
python -m bio_knowledge_lab evaluate --input runs/manual/aligned_initial.jsonl --output runs/manual/evaluation_initial.json
```

| 指标 | 问的是什么 |
|---|---|
| precision（精确率） | 给出的预测里，有多少符合本项金标匹配规则？ |
| recall（召回率） | 金标中应找到的项目，有多少被找到了？ |
| F1 | 综合精确率和召回率的调和平均值，范围为 0—1 |

例如某项预测 10 条、其中 8 条匹配金标，而金标共 20 条，则精确率为 0.8，召回率为 0.4，F1 约为 0.533。这只是计算示例，不是本次实验分数。

评价报告分别给出 `ner_strict`（实体位置和类型）、`linking_strict`（还要求标准 ID 一致）、`relation_end_to_end`（从实体链接到关系标签的完整结果）、`relation_with_novelty`（再比较新发现／背景知识角色）。端到端关系指标受到前面实体识别与链接错误的影响。证据句和完整上下文没有相应金标的部分不会编造准确率。

**看什么、解释什么：** 从自己的报告记录实体识别、实体链接和端到端关系三个 F1，解释它们为什么可能不同。它们评价模型和方法的输出，不是你的作业分数。不同阶段的文献数不同，不要要求初始 40 篇的报告与完整 50 篇的报告数值一致。各方法完整结果见 [VERIFICATION.md](VERIFICATION.md)。

### 5.3 把各篇记录保存到知识库

**为什么做：** 对齐文件已经说明各提及指向谁，但跨多篇文献查询、修订和保存历史还需要数据库。`fuse` 将对齐后的 40 篇记录写入 `knowledge.sqlite`；这一步由程序完成，不让模型重新生成结论。

```bash
python -m bio_knowledge_lab fuse --input runs/manual/aligned_initial.jsonl --db runs/manual/knowledge.sqlite
```

第一次向新的数据库导入应新增 40 篇。融合保留每篇文献的记录，通过标准 ID 建立关联；同一对象被多篇提及，不意味着这些文献的关系和证据应该相互覆盖。

### 5.4 查询跨文献关联

**为什么做：** 用实际查询检验“对齐和融合带来了什么”。`query` 读取数据库，输出当前状态的 JSON 快照；快照便于稍后比较修改前后变化，它本身不是数据库。

```bash
python -m bio_knowledge_lab query --db runs/manual/knowledge.sqlite --output runs/manual/query_initial.json
```

在查询结果里观察：

- `cross_document_entities`：同一标准标识连接了哪些文献和原文名称。
- `link_status_counts`：已解析、歧义及未解析提及的分布。
- `relations`：每条记录仍有自己的 `doc_id`，不能只剩一个覆盖后的“最终事实”。

**看什么、解释什么：** 在 `cross_document_entities` 中选一个标准实体，读出它关联的文献编号和不同名称，再回到相关文献看各自的关系。只有出现关联仍不足以判断科学内容正确，关系及证据还需要下一步核查。

### 5.5 进阶对照 词典和 SapBERT

这一小节用于比较“换一种身份匹配方法会怎样”，首次学习可先完成第 6—8 节。各路径使用同一份抽取结果，只改变对齐方法，便于分析哪些差异来自对齐。`lexical` 是程序按词典和规则匹配；`sapbert` 在候选短名单上运行本地表示模型，比较名称向量相似度，不等于重新做文本抽取。

先独立运行不含上下文模型的词典基线，查看它保留了多少歧义：

```bash
python -m bio_knowledge_lab align --input runs/manual/extracted_initial.jsonl --output runs/manual/aligned_lexical.jsonl --method lexical
python -m bio_knowledge_lab evaluate --input runs/manual/aligned_lexical.jsonl --output runs/manual/evaluation_lexical.json
```

需要下载模型和额外依赖，仍在 CPU 上运行。先阅读 [METHODS.md](METHODS.md) 了解它与原 MDKG 的差异：本课程在候选短名单上进行语义比较，加入歧义和物种处理，未声称重建原论文全部本体索引。

```bash
python -m pip install -e ".[semantic]"
python -m bio_knowledge_lab align --input runs/manual/extracted_initial.jsonl --output runs/manual/aligned_sapbert.jsonl --method sapbert
python -m bio_knowledge_lab evaluate --input runs/manual/aligned_sapbert.jsonl --output runs/manual/evaluation_sapbert.json
```

模型第一次下载需要网络。比较 contextual、lexical、sapbert 三份评价报告，同时查看新增匹配是否可信；相似度高不代表科学身份必然相同。不要把下载失败后的词典结果写成 SapBERT 结果。具体已经验证的语义路径范围见发布验证记录。

## 6. 检查结构与核查证据

**为什么做：** 记录既可能有结构问题，也可能格式完全正确却解释错了原文。例如关系指向不存在的提及属于结构问题；把“未发现关联”读成“存在关联”属于语义问题。两类检查使用不同依据。

`check` 由程序读取数据库，检查端点、类型、原文位置等规则，输出 `check_initial.json`。它也会列出待审事项，不能把“需要审阅”全部当作已证实错误。

```bash
python -m bio_knowledge_lab check --db runs/manual/knowledge.sqlite --output runs/manual/check_initial.json
```

`check-evidence` 读取对齐文件和课程文献，回放模型对来源证据的判断，再由程序检查返回的标签与引文，输出 `verification_initial.jsonl`。它回答“这篇原文是否支持这条候选”，不使用金标给模型评分，也不自动执行修订。

```bash
python -m bio_knowledge_lab check-evidence --mode replay --input runs/manual/aligned_initial.jsonl --output runs/manual/verification_initial.jsonl
```

结构检查报告会列出错误、警告、待审记录及跨文献标签差异。证据核查则读取已保存的真实模型结果：判断候选关系是否忠于其来源摘要，其他文献用于比较，不能替本篇原文补不存在的证据。

核查标签的含义：

| 标签 | 含义 |
|---|---|
| `supported_text` | 模型认为原文支持该候选关系；仍是模型判断 |
| `contradicted_text` | 模型认为候选与原文不符，需核对原因 |
| `insufficient_text` | 原文支持不足，保留不确定性 |
| `invalid_judgment`／`missing_judgment` | 输出或证据检查未通过，不能视为已完成核查 |

核查结果不会自动删除或改写知识库。跨论文标签不同也不自动等于有人错误，可能来自研究对象、条件或叙述角色不同。

**看什么、解释什么：** 找一条核查候选，回到它自己的摘要，读证据所在句和前后文。说明“模型判断是什么、原文说了什么、我还有什么不能确定”。即使引文确实出现在原文，也要核对它是否支持关系、涉及哪些对象及条件；有疑问可以保留“待审”。

## 7. 修订、保留历史并加入新文献

### 7.1 生成一个明确标注的教学故障

**为什么做：** 用一个已知改动观察“修订是否生效、旧内容能否追溯”。`prepare-revision` 由程序读取当前数据库与金标，选出一条原预测和参考一致的关系，生成故意改错的提案及恢复提案；它没有让模型自动找出并修复全部真实错误。此处使用金标是为了准备教学案例，与第 4—5 节不读金标的预测过程分开。

```bash
python -m bio_knowledge_lab prepare-revision --db runs/manual/knowledge.sqlite --output-dir runs/manual/revisions
```

打开生成的 `teaching_injection.json` 和 `correction.json`。它们包含目标文献、期望版本、完整替换记录、操作类型、原因和证据。教学故障明确标记为 `teaching_injection`，不能混入真实模型错误统计。

提案是“请求怎样改、为什么改”的文件，生成提案尚未改库。下面两次 `revise` 才由程序按提案执行修改；夹在中间的 `query` 保存各阶段的状态，`history` 导出修改记录。实际科学修订是否有充分依据，需要人审阅，程序检查版本和格式不能替代这种判断。

```bash
python -m bio_knowledge_lab revise --db runs/manual/knowledge.sqlite --proposal runs/manual/revisions/teaching_injection.json
python -m bio_knowledge_lab query --db runs/manual/knowledge.sqlite --output runs/manual/query_injected.json
python -m bio_knowledge_lab revise --db runs/manual/knowledge.sqlite --proposal runs/manual/revisions/correction.json
python -m bio_knowledge_lab query --db runs/manual/knowledge.sqlite --output runs/manual/query_corrected.json
python -m bio_knowledge_lab history --db runs/manual/knowledge.sqlite --output runs/manual/history.json
```

比较修改前后的关系和版本号。再次提交过期提案应被拒绝：这是为了防止旧修改覆盖新结果。不要修改 `expected_version` 来强行套用不同状态的提案，应重新检查当前记录和依据。

实际科学修订同样使用带来源证据的提案。未经人工确认，不给记录加上 `human_confirmed` 状态；恢复一个教学故障也不等于全部模型预测已经审定。

**看什么、解释什么：** 按提案中的文献与关系编号，比较 `query_initial.json`、`query_injected.json`、`query_corrected.json`。指出哪个关系标签改变又恢复，再到 `history.json` 找到对应修改。只编辑 JSON 查询快照不会修改数据库；不要用改写原始回放或金标来“修好”结果。

### 7.2 增量导入

**为什么做：** 验证知识库能否接收新文献，又不丢掉旧证据。输入是预先留出的另外 10 篇，先重复已学过的抽取、对齐和评价，得到这批文献的独立结果。

```bash
python -m bio_knowledge_lab extract --mode replay --split incremental --output runs/manual/extracted_incremental.jsonl
python -m bio_knowledge_lab align --input runs/manual/extracted_incremental.jsonl --output runs/manual/aligned_incremental.jsonl --method contextual --mode replay
python -m bio_knowledge_lab evaluate --input runs/manual/aligned_incremental.jsonl --output runs/manual/evaluation_incremental.json
```

`update` 将新记录加入**原来的** `runs/manual/knowledge.sqlite`，不另建数据库；`query` 保存更新后的状态，用于与初始快照比较。

```bash
python -m bio_knowledge_lab update --input runs/manual/aligned_incremental.jsonl --db runs/manual/knowledge.sqlite
python -m bio_knowledge_lab query --db runs/manual/knowledge.sqlite --output runs/manual/query_updated.json
```

然后检查更新后的库，并为新增文献保留模型证据核查结果：

```bash
python -m bio_knowledge_lab check --db runs/manual/knowledge.sqlite --output runs/manual/check_updated.json
python -m bio_knowledge_lab check-evidence --mode replay --input runs/manual/aligned_incremental.jsonl --output runs/manual/verification_incremental.jsonl
```

新增文献同样需要来源证据核查。初始和增量两份 `verification_*.jsonl` 应分别覆盖 40 篇和 10 篇，并为全部 690 条关系候选保留核查状态；证据不足或输出无效不能被算作“已证实”。核查不会自动修订事实，有疑点的新增记录仍按原文和审阅流程处理。

再次运行同一条 `update` 命令，再查询。相同记录应被识别为重复，不应无限增加文献或关系；若同一文献内容不同，必须走有历史的修订流程。

```bash
python -m bio_knowledge_lab update --input runs/manual/aligned_incremental.jsonl --db runs/manual/knowledge.sqlite
python -m bio_knowledge_lab query --db runs/manual/knowledge.sqlite --output runs/manual/query_repeated.json
```

本次固定回放的初始结果为 40 篇文献、2074 个实体提及、573 条关系、54 个跨文献标准实体；加入增量后为 50 篇、2603 个提及、690 条关系、84 个跨文献标准实体。重复导入应显示 `added: 0`、`unchanged: 10`，两份增量后查询应一致。教学关系恢复后，查询内容恢复原值，而该文献版本由 1 变为 3，不应要求版本号也倒退。

回答：新增文献增加了哪些共享实体？原来的文献证据是否仍在？哪些关系标签需要结合上下文比较？

可以继续追踪 `NCBIGene:3569`。本次固定回放的更新后查询中，它连接 `22859398`、`26270232`、`27860244`、`28512644`、`28846666` 五篇文献，名称包括 `IL-6`、`IL6`、`Interleukin 6`。对照初始快照，找出哪个文献是本次新增的，并解释为什么要保留每篇独立证据。这里的跨文献连接仍来自方法候选，不能跳过来源和身份审阅。

## 8. 怎样判断自己完成了

**这一步的目的：** 分别检查“流程能运行”和“自己能解释结果”。`verify` 读取 demo 产物做流程验收，`pytest` 检查项目实现是否符合已有测试；二者都不代替你的科学判断或学习自述。下面 `verify` 指向的是第 3 节的 `runs/demo`，不是第 4—7 节的手工目录。

分步实验至少保留抽取、对齐、评价、初始查询、核查候选、故障／恢复提案、历史、增量后的查询与结构检查。demo 的自动验收另外检查发布定义的回归条件：

```bash
python -m bio_knowledge_lab verify --workdir runs/demo
python -m pytest -q
```

| 检查 | 通过意味着什么 | 不代表什么 |
|---|---|---|
| 文件与定位检查 | 输入版本一致，实体／证据能定位到原文 | 关系语义一定正确 |
| 结构校验 | 引用端点、类型、跨度等满足实现规则 | 没有漏抽或不当解释 |
| 原数据金标评价 | 在已提交且有金标的文献上得到可重复的任务分数 | 达到了原论文所有实验指标 |
| 修订及增量验收 | 历史保留、查询变化、重复导入规则正确 | 新科学内容已通过专家审定 |
| `scientific_review_complete` | 实现记录的科学审阅状态是否全部完成 | 不能由软件测试强行置为完成 |

教师或学生在独立电脑验证后，填写 [REVIEW_RETURN.md](REVIEW_RETURN.md)，按 [MANUAL_REVIEW.md](MANUAL_REVIEW.md) 汇总仍需人工处理的事项。

**用自己的结果自查理解：** 找出一个实体提及及其原文位置，说明它与标准 ID 的区别；展示一次对齐为何成立或为何保留歧义；根据查询和历史解释一次修订及一次增量变化。每项都引用自己的文件或文献编号。若需要 AI 帮助，记录它解释了什么、你怎样核对、还有哪里不懂；不要求把不理解的地方写成已经掌握。

## 9. 真实 API 路径

**进阶目的：** 让模型服务重新生成回答，比较新结果与固定回放。程序仍负责同样的文件处理和评价，区别是模型判断来自本次调用。完成免费主线不要求运行这一节，也不需要购买调用额度。

这条路径需要自己的 DeepSeek API Key，且会产生费用。先查看 [官方价格](https://api-docs.deepseek.com/zh-cn/quick_start/pricing/)；课程代码按记录的保守价格预留费用，模型和价格变化时应先核对配置。

下面命令交互读取密钥，输入不会回显，也不会写入命令历史。不要把密钥直接写进手册、脚本、Notebook 或截图。

```bash
python -c "import getpass,os; from bio_knowledge_lab.cli import main; os.environ['DEEPSEEK_API_KEY']=getpass.getpass('DeepSeek API Key: '); raise SystemExit(main(['extract','--mode','api','--split','all','--output','runs/my-api/extracted.jsonl','--cache','runs/my-api/cache','--ledger','runs/my-api/budget.json','--budget-cny','5']))"
```

上下文对齐和证据核查使用**同一预算账本**，不得通过换账本绕过本次总上限：

```bash
python -c "import getpass,os; from bio_knowledge_lab.cli import main; os.environ['DEEPSEEK_API_KEY']=getpass.getpass('DeepSeek API Key: '); raise SystemExit(main(['align','--method','contextual','--mode','api','--input','runs/my-api/extracted.jsonl','--output','runs/my-api/aligned.jsonl','--cache','runs/my-api/cache','--ledger','runs/my-api/budget.json','--budget-cny','5']))"
python -m bio_knowledge_lab evaluate --input runs/my-api/aligned.jsonl --output runs/my-api/evaluation.json
python -c "import getpass,os; from bio_knowledge_lab.cli import main; os.environ['DEEPSEEK_API_KEY']=getpass.getpass('DeepSeek API Key: '); raise SystemExit(main(['check-evidence','--mode','api','--input','runs/my-api/aligned.jsonl','--output','runs/my-api/verification.jsonl','--cache','runs/my-api/cache','--ledger','runs/my-api/budget.json','--budget-cny','5']))"
```

成功缓存可用于后续免费回放：

```bash
python -m bio_knowledge_lab extract --mode replay --split all --cache runs/my-api/cache --output runs/my-api/replayed.jsonl
python -m bio_knowledge_lab align --method contextual --mode replay --input runs/my-api/replayed.jsonl --output runs/my-api/aligned_replayed.jsonl --cache runs/my-api/cache
```

预算控制包含请求前预留、已完成用量和结果未知的请求。超时后可能已发生服务方计费，因此程序不自动重试，也不自动退回全部预留。先检查 `budget.json` 和已保存响应；不要删除账本重新开始。若预算不足，保留已完成内容并报告未完成步骤。

## 10. 常见问题

| 现象 | 处理 |
|---|---|
| 找不到模块 | 确认在仓库根目录、已激活正确虚拟环境，并执行了 `pip install -e .` |
| 仓库克隆失败 | 核对仓库地址、网络连接和 Git 安装，或使用仓库页面的 Code → Download ZIP；公开查看和下载无需写入权限 |
| 回放文件缺失或提示哈希不一致 | 检查代码和数据是否同一发布版本；不要复制金标伪装回放 |
| 输出文件已存在 | 保留原输出，换新实验目录；避免混淆不同运行 |
| VS Code 中看到的结果与终端不符 | 先核对打开文件的完整路径、命令的 `--output`／`--db` 和当前目录；区分 `runs/demo` 与 `runs/manual`、initial 与 updated。重新打开对应文件，记录实际命令和输出，不先改数据去凑预期值 |
| JSONL 一行很长，不知从哪里看 | 开启编辑器自动换行，先搜索 `doc_id` 的具体编号，再看该记录的 `entities`、`relations`；不要把 JSONL 行数当作实体数 |
| 提示 `1/40`、`2/40` 等文献进度 | 这是处理进度，部分命令写到标准错误流便于显示；日志所在的流不等于发生错误，应结合具体内容、最终结果和退出状态判断 |
| `unresolved` 或 `ambiguous` 较多 | 先看候选库覆盖、原文物种和名称歧义；这不是程序必然崩溃，也不能全部强行配一个 ID |
| 结构检查通过但有 pending | 查看待审种类；结构通过不能替代语义审阅 |
| `expected_version` 过期 | 重新查看当前记录及历史，重新生成提案，不覆盖已有更新 |
| API 超时或预算不足 | 保存账本和日志，停止付费步骤；回放路径仍可用于已有完整结果 |
| SapBERT 下载慢或依赖失败 | 先记录错误和环境，使用已验证的免费基线完成其他步骤；语义模块按实际运行状态报告 |

## 11. 提交作业

按 [TEACHER_GUIDE.md](TEACHER_GUIDE.md) 提交实验结果及解释，注明使用免费回放还是自己的真实调用。附自己的环境、数据版本和方法参数。提交真实错误和待审项，不需要把指标改成“全部正确”。

把第 4—7 节选出的实例写进说明：原文中的名称与位置、对齐的 ID 或未解决原因、一个关系的证据、修订与增量前后的变化。这样教师既能看到程序跑通，也能看出你理解到哪一步。回传单允许写“不明白”，请尽量标出具体步骤、术语或文件字段，便于得到针对性的解释。
