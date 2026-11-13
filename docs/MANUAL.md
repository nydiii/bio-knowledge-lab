# 生物科学知识建模实训操作手册

本手册使用同一批 BioRED 文献完成：**原文信息抽取 → 实体对齐与跨文献融合 → 证据核查、修订和增量更新**。资料规模、原文来源、跨文献关联及实际运行指标分别见 [DATA_SOURCES.md](DATA_SOURCES.md) 和 [VERIFICATION.md](VERIFICATION.md)。

默认路径读取本项目保存的真实模型响应。安装完成后，免费回放不调用模型、不需要 API Key。后半部分提供重新调用 DeepSeek 的路径；模型输出可能变化，不能要求真实调用逐字等于回放。

## 1. 准备与安装

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

## 2. 查看资料并验证来源

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

## 3. 先完整体验一次

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

## 4. 自己执行科学信息抽取

以下分步实验使用新的 `runs/manual` 目录，与 demo 相互独立。

```bash
python -m bio_knowledge_lab extract --mode replay --split initial --output runs/manual/extracted_initial.jsonl
```

每篇原文经过两个阶段：识别实体的原文名称和类别，再利用这些候选识别关系。课程后处理把精确原文名称定位为字符跨度，并记录无效候选；它是明确的课程适配，不是作者原始模型直接给出的金标跨度。

检查输出中的三个部分：

1. `entities`：名称、类型、原文位置和文内提及编号。
2. `relations`：关系两端的提及编号、标签、novelty、候选证据和上下文。
3. `provenance`、`extraction_issues`：真实响应来源、提示哈希及被发现的格式／定位问题。

选一条实体，检查 `text[start:end]` 是否与实体名称相同。选一条关系，阅读完整摘要，解释它为何可能需要跨句判断。

## 5. 对齐并融合跨文献记录

主线使用 `contextual`：先查独立词典，再读取模型根据原文从候选 ID 中选择的真实保存结果。这条免费回放路径不下载大模型，也不产生 API 费用。上下文候选选择是课程扩展，不是 MDKG 原方法。

```bash
python -m bio_knowledge_lab align --input runs/manual/extracted_initial.jsonl --output runs/manual/aligned_initial.jsonl --method contextual --mode replay
python -m bio_knowledge_lab evaluate --input runs/manual/aligned_initial.jsonl --output runs/manual/evaluation_initial.json
python -m bio_knowledge_lab fuse --input runs/manual/aligned_initial.jsonl --db runs/manual/knowledge.sqlite
python -m bio_knowledge_lab query --db runs/manual/knowledge.sqlite --output runs/manual/query_initial.json
```

对齐候选来自独立实体词典。一个明确匹配可进入 `links`；上下文模型只能选择提供的 ID，并给出原文中的证据。不能解决的歧义和未解析项保留原状态。模型选择的 ID 即使进入 `links`，仍带 `model_candidate` 审阅状态，不能当作人工确认。不能因为某名称看起来熟悉，就手填金标 ID 让评价上升。

跨文献查询出现连接，只证明关联操作发生，不能据此认定候选已经适合作为模型训练数据；还要查看端到端评价和待审内容。各方法的实际结果见 [VERIFICATION.md](VERIFICATION.md)。

在查询结果里观察：

- `cross_document_entities`：同一标准标识连接了哪些文献和原文名称。
- `link_status_counts`：已解析、歧义及未解析提及的分布。
- `relations`：每条记录仍有自己的 `doc_id`，不能只剩一个覆盖后的“最终事实”。

评价报告分别给出 `ner_strict`、`linking_strict`、`relation_end_to_end`、`relation_with_novelty`。端到端关系指标受到前面实体识别与链接错误的影响。证据句和完整上下文没有相应金标的部分不会编造准确率。

### 对照实验：词典和 SapBERT

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

```bash
python -m bio_knowledge_lab check --db runs/manual/knowledge.sqlite --output runs/manual/check_initial.json
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

## 7. 修订、保留历史并加入新文献

### 7.1 生成一个明确标注的教学故障

```bash
python -m bio_knowledge_lab prepare-revision --db runs/manual/knowledge.sqlite --output-dir runs/manual/revisions
```

打开生成的 `teaching_injection.json` 和 `correction.json`。它们包含目标文献、期望版本、完整替换记录、操作类型、原因和证据。教学故障明确标记为 `teaching_injection`，不能混入真实模型错误统计。

```bash
python -m bio_knowledge_lab revise --db runs/manual/knowledge.sqlite --proposal runs/manual/revisions/teaching_injection.json
python -m bio_knowledge_lab query --db runs/manual/knowledge.sqlite --output runs/manual/query_injected.json
python -m bio_knowledge_lab revise --db runs/manual/knowledge.sqlite --proposal runs/manual/revisions/correction.json
python -m bio_knowledge_lab query --db runs/manual/knowledge.sqlite --output runs/manual/query_corrected.json
python -m bio_knowledge_lab history --db runs/manual/knowledge.sqlite --output runs/manual/history.json
```

比较修改前后的关系和版本号。再次提交过期提案应被拒绝：这是为了防止旧修改覆盖新结果。不要修改 `expected_version` 来强行套用不同状态的提案，应重新检查当前记录和依据。

实际科学修订同样使用带来源证据的提案。未经人工确认，不给记录加上 `human_confirmed` 状态；恢复一个教学故障也不等于全部模型预测已经审定。

### 7.2 增量导入

```bash
python -m bio_knowledge_lab extract --mode replay --split incremental --output runs/manual/extracted_incremental.jsonl
python -m bio_knowledge_lab align --input runs/manual/extracted_incremental.jsonl --output runs/manual/aligned_incremental.jsonl --method contextual --mode replay
python -m bio_knowledge_lab evaluate --input runs/manual/aligned_incremental.jsonl --output runs/manual/evaluation_incremental.json
python -m bio_knowledge_lab update --input runs/manual/aligned_incremental.jsonl --db runs/manual/knowledge.sqlite
python -m bio_knowledge_lab query --db runs/manual/knowledge.sqlite --output runs/manual/query_updated.json
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

## 8. 怎样判断自己完成了

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

## 9. 真实 API 路径

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
| `unresolved` 或 `ambiguous` 较多 | 先看候选库覆盖、原文物种和名称歧义；这不是程序必然崩溃，也不能全部强行配一个 ID |
| 结构检查通过但有 pending | 查看待审种类；结构通过不能替代语义审阅 |
| `expected_version` 过期 | 重新查看当前记录及历史，重新生成提案，不覆盖已有更新 |
| API 超时或预算不足 | 保存账本和日志，停止付费步骤；回放路径仍可用于已有完整结果 |
| SapBERT 下载慢或依赖失败 | 先记录错误和环境，使用已验证的免费基线完成其他步骤；语义模块按实际运行状态报告 |

## 11. 提交作业

按 [TEACHER_GUIDE.md](TEACHER_GUIDE.md) 提交实验结果及解释，注明使用免费回放还是自己的真实调用。附自己的环境、数据版本和方法参数。提交真实错误和待审项，不需要把指标改成“全部正确”。
