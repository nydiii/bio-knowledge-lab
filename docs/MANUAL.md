# 生物实训：跟着做一遍

这次实训做两件事：**先把文献整理成能查询的资料库，再看看程序哪里做错了、改过之后有没有变好。**

第一次做，从第1步开始；已经完成原教程的同学，更新项目并按第1步确认环境可用后，直接从[第8步](#8-重新生成一份旧方法的结果)继续。只用这份教程，不用再做另一份。

全程使用提前保存的真实 AI 回答，安装后不需要联网调用 AI、不收费。你运行的是 Python 程序：它读取回答、整理资料、计算结果。**AI 负责提出判断，程序负责处理和保存；判断仍可能出错。** 不需要训练模型，也不需要交表或报告。

先记住三个词就够了：

- **实体**：文献里的研究对象，例如一个基因、一种药物或疾病。
- **抽取**：把原文里的名称和对象之间的关系找出来。
- **对齐**：为名称找到标准编号（ID）。例如 `Interleukin 6` 和 `IL-6` 可能指同一个对象；不同物种的同名基因却可能需要不同编号。

每一步都按“运行命令 → 打开结果 → 对照说明看一个例子”的顺序做。不用看懂文件中的每一个字段。

## 1. 准备好程序

**做什么、为什么：** 下载最新版项目，准备运行环境。新下载的文件夹要做下面的安装；在原文件夹里更新代码的同学，可跳过创建环境，重新激活后执行安装命令。

从[仓库页面](https://github.com/nydiii/bio-knowledge-lab)点击 **Code → Download ZIP**，解压到一个新文件夹。用 VS Code 打开其中包含 `pyproject.toml` 的文件夹，再打开终端。需要预先安装 Python 3.12。

按自己的电脑选择一组命令。

**Windows：** 在 VS Code 终端右上方的下拉菜单选择 **Command Prompt／命令提示符**，不是 PowerShell。

```bat
py -3.12 -m venv .venv
.venv\Scripts\activate.bat
python -m pip install -e .
```

**macOS／Linux：**

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
```

**看什么结果：** 接着运行下面这条命令，看到帮助列表即可。

```bash
python -m bio_knowledge_lab --help
```

后面的命令都在这个终端、这个项目文件夹里运行。关闭终端再回来时，先重新运行自己系统对应的激活命令。只复制代码框内的命令。

已有旧结果时不要覆盖它：下载新版到新文件夹即可完整重做。只做第8—11步时，若已有 `runs/feedback`，把这四步中的路径统一改成 `runs/feedback-2`。

## 2. 看原文，再让程序找出名称和关系

**做什么、为什么：** 先认识输入，再看文字怎样变成一条条记录。资料来自 BioRED 公开数据集；先处理40篇，后面再加入另外10篇。

先确认项目自带的资料完整，再生成抽取结果：

```bash
python -m bio_knowledge_lab fetch --verify-only
python -m bio_knowledge_lab extract --mode replay --split initial --output runs/manual/extracted_initial.jsonl
```

**看什么结果：** 在 VS Code 左侧展开 `runs → manual`，打开 `extracted_initial.jsonl`，搜索文献编号 `28846666`。这类文件每行是一篇文献，行很长是正常的。

1. 看原文 `text`，标题中有 `Interleukin 6 (IL-6)`。
2. 看 `entities` 中的 `m1`、`m2`，是否找到了全称和缩写。`m1`、`m2` 只是这篇文章里的位置编号。
3. 看 `relations` 中的 `r2`：程序提出 IL-6 与妊娠糖尿病（GDM）“有关联”。读它的 `evidence`（依据），再回到摘要，看原文是否支持这个说法。“有关联”不等于“导致”。

原文也保存在 `data/corpus/documents.jsonl`。后面用来评分的人工参考在 `data/reference/gold.jsonl`；两者不是同一份材料。

## 3. 认清对象，再和参考答案比较

**做什么、为什么：** 名字找到了，还要判断它指的是谁。程序从标准词典中选择编号，再与数据集作者提供的人工参考比较。

```bash
python -m bio_knowledge_lab align --input runs/manual/extracted_initial.jsonl --output runs/manual/aligned_initial.jsonl --method contextual --mode replay
python -m bio_knowledge_lab evaluate --input runs/manual/aligned_initial.jsonl --output runs/manual/evaluation_initial.json
```

**看什么结果：** 打开 `aligned_initial.jsonl`，仍找 `28846666` 的 `m1`、`m2`。两者的 `links` 都选了 `NCBIGene:3569`，表示程序认为它们指向同一个标准对象。这是程序给出的候选身份，还需要核对。

再打开 `evaluation_initial.json`，先只看三项里的 `f1`：

| 文件中的名称 | 它在比较什么 |
|---|---|
| `ner_strict` | 名称的位置和类别是否匹配参考 |
| `linking_strict` | 名称和标准编号是否一起匹配参考 |
| `relation_end_to_end` | 两端对象的身份和关系是否一起匹配参考 |

F1 是综合比较分数，越高表示与这份参考越一致，不是简单的正确率，也不是你的成绩。**参考用于比较，不会自动填回预测。**

## 4. 把文献放在一起查询

**做什么、为什么：** 把结果保存到资料库，看看不同文献是否提到了同一个对象。

```bash
python -m bio_knowledge_lab fuse --input runs/manual/aligned_initial.jsonl --db runs/manual/knowledge.sqlite
python -m bio_knowledge_lab query --db runs/manual/knowledge.sqlite --output runs/manual/query_initial.json
```

**看什么结果：** 第一次导入应新增40篇。打开 `query_initial.json`，找 `cross_document_entities`，选一个对象，看它连接了哪些文献、用了哪些名称。每篇文献的说法仍分别保留。

`knowledge.sqlite` 是程序保存资料的数据库，不用直接打开；我们通过 `query` 导出的文件看它。

## 5. 回到原文，检查判断有没有依据

**做什么、为什么：** 一部分检查能发现“编号指错位置”等格式问题；另一部分帮助找出需要重新读原文的判断。两者都不能保证所有内容正确。

```bash
python -m bio_knowledge_lab check --db runs/manual/knowledge.sqlite --output runs/manual/check_initial.json
python -m bio_knowledge_lab check-evidence --mode replay --input runs/manual/aligned_initial.jsonl --output runs/manual/verification_initial.jsonl
```

**看什么结果：** 打开 `check_initial.json`，看看有哪些待查项。再打开 `verification_initial.jsonl`，选一条关系，读它的判断、引用的原文和理由。

`supported_text` 表示核查模型认为原文支持；`insufficient_text` 表示依据不足；`contradicted_text` 表示模型认为不符；`invalid_judgment` 表示这次核查输出未通过检查，例如引文无法定位。**“待查”不等于已经证实错误。**

## 6. 看一次修改怎样留下记录

**做什么、为什么：** 先用一个预设的小错误，观察修改前后和历史记录。这里演示的是“怎样修改并保留历史”；真实错误的改进在第8—11步。

先准备并应用这个教学错误：

```bash
python -m bio_knowledge_lab prepare-revision --db runs/manual/knowledge.sqlite --output-dir runs/manual/revisions
python -m bio_knowledge_lab revise --db runs/manual/knowledge.sqlite --proposal runs/manual/revisions/teaching_injection.json
python -m bio_knowledge_lab query --db runs/manual/knowledge.sqlite --output runs/manual/query_injected.json
```

再恢复它，并查看历史：

```bash
python -m bio_knowledge_lab revise --db runs/manual/knowledge.sqlite --proposal runs/manual/revisions/correction.json
python -m bio_knowledge_lab query --db runs/manual/knowledge.sqlite --output runs/manual/query_corrected.json
python -m bio_knowledge_lab history --db runs/manual/knowledge.sqlite --output runs/manual/history.json
```

**看什么结果：** 打开 `runs/manual/revisions/revision_lesson.json`，找到文献编号 `doc_id` 和关系编号 `relation_id`。按这两个编号比较 `query_initial.json`、`query_injected.json`、`query_corrected.json`，看同一条关系怎样改变又恢复。再到 `history.json` 找到两次修改。内容恢复了，修改记录仍然存在。

## 7. 加入另外10篇文献

**做什么、为什么：** 新文献也要先整理、认清对象，再加入原来的资料库。

```bash
python -m bio_knowledge_lab extract --mode replay --split incremental --output runs/manual/extracted_incremental.jsonl
python -m bio_knowledge_lab align --input runs/manual/extracted_incremental.jsonl --output runs/manual/aligned_incremental.jsonl --method contextual --mode replay
python -m bio_knowledge_lab evaluate --input runs/manual/aligned_incremental.jsonl --output runs/manual/evaluation_incremental.json
python -m bio_knowledge_lab update --input runs/manual/aligned_incremental.jsonl --db runs/manual/knowledge.sqlite
python -m bio_knowledge_lab query --db runs/manual/knowledge.sqlite --output runs/manual/query_updated.json
python -m bio_knowledge_lab check --db runs/manual/knowledge.sqlite --output runs/manual/check_updated.json
python -m bio_knowledge_lab check-evidence --mode replay --input runs/manual/aligned_incremental.jsonl --output runs/manual/verification_incremental.jsonl
```

**看什么结果：** 打开 `query_updated.json`，文献总数应从40变成50。搜索 `3569`，看看 IL-6 现在连接了哪些文献。新增部分也有自己的评价和核查结果。

再试着导入同一批资料：

```bash
python -m bio_knowledge_lab update --input runs/manual/aligned_incremental.jsonl --db runs/manual/knowledge.sqlite
python -m bio_knowledge_lab query --db runs/manual/knowledge.sqlite --output runs/manual/query_repeated.json
```

应显示 `added: 0`、`unchanged: 10`，两份更新后的查询结果相同。说明程序识别出了重复资料。

到这里，基础流程完成。回看第3步的标准编号、第4步的文献关联、第6步的修改历史，能说清它们分别有什么用即可。下面接着看真实错误如何推动程序改进。

## 8. 重新生成一份旧方法的结果

**做什么、为什么：** 用同样的50篇文献建立比较起点，才能知道新版具体改了什么。旧方法和改进方法都在当前项目里，不用下载两个版本。

```bash
python -m bio_knowledge_lab feedback-lab --step baseline --workdir runs/feedback
```

**看什么结果：** 打开 `runs/feedback/baseline.jsonl`，搜索 `18593936` 和 `survivin`，旧方法选了小鼠编号 `11799`。再看 `baseline_evaluation.json` 中的三个 F1。

这一步会自行生成旧结果，不读取前面的 `runs/manual`，也不改原来的资料库。后面都在 `runs/feedback` 中比较，避免混用不同批次的结果。

## 9. 看看问题到底出在哪里

**做什么、为什么：** 把旧结果、原文、人工参考和已经整理的核查意见放在一起，找到该改的地方。

```bash
python -m bio_knowledge_lab feedback-lab --step inspect --workdir runs/feedback
```

**看什么结果：** 打开 `inspection.md`。不必一次看完24条，先跟着三个例子看：

- **第15条，survivin：** 名称找到了，但人源细胞中的对象被连到了小鼠编号。旧候选库缺少合适的人类对象；要先补候选，再结合上下文选择。
- **第1条，PKCalpha 与 p21：** 原文说“减少 PKCalpha 后，p21 增加”。不能只看到“增加”，就把两者标成同向变化。
- **第21条，insulin：** 原参考是小鼠编号 `16333`；但细胞来自小鼠，不足以证明外加胰岛素试剂也来自小鼠。证据不足时，程序应保留待查。

人工参考和这次核查意见也可能有疑点。遇到不一致，要回原文找依据，不能为了分数把答案直接抄进结果。

## 10. 理解改动，再运行改进版

**做什么、为什么：** 针对刚才的问题，补充名称候选、按附近文字判断对象，并检查少数明确的关系句式。AI 原来的回答保持不变，这次改的是本地程序的处理方法。

```bash
python -m bio_knowledge_lab feedback-lab --step optimize --workdir runs/feedback
```

**看什么结果：** 打开 `improved.jsonl`，再找刚才的 survivin：相关三处编号应由 `11799` 变为人的 `332`；第9步看的 PKCalpha—p21 关系由同向改为反向。顺着 `improvement_review` 或 `relation_rule_review` 看修改理由。

insulin 等问题仍可能保留旧编号并标为待查。看见 `needs_review` 就表示还需核对；`rule_candidate` 表示规则给出的候选，不代表已经由专家确认。新版也没有重新训练或重新调用 AI。

## 11. 比较前后，看看有没有变好

**做什么、为什么：** 个别例子变好了，还要看整体有没有改善、有没有带来新的问题。

```bash
python -m bio_knowledge_lab feedback-lab --step compare --workdir runs/feedback
```

**看什么结果：** 打开 `comparison.md`，按这个顺序读：

1. 看“全部文献”的前后分数；名字和位置没有重新抽取，这项分数应不变。
2. 看具体哪些编号和关系变了，再看改善、未变和退步的记录。
3. 看最后仍未解决的问题，理解为什么有些结果继续待查。

这份固定资料的实测结果：5处编号、3处关系标签发生改变；链接 F1 从61.92%到62.17%，关系 F1 从17.28%到17.40%。提高幅度有限，并没有把所有问题解决。

报告还把“涉及这次反馈的10篇”和“另外40篇”分开显示。后者的分数本轮没有变化，但以前已用于项目开发，不能据此证明对所有新文献都有效。这种分组与第7步的先后导入顺序不是一回事。

改进结果保存在新文件里，**不会自动写回原来的 `knowledge.sqlite`**。

## 做到这里就完成了

不需要交表或报告。能对着自己看过的一个例子讲清楚“原来是什么、为什么有问题、改了什么、还有哪里不确定”即可。

本次可以跳过：一键 `demo`、另下模型做 SapBERT 对照、付费 API、运行程序测试。正文已包含这次完整体验需要的步骤。

遇到报错先停在当前步骤，把报错文字给老师看。若提示文件已存在，保留旧结果，换新项目文件夹完整重做，或按第1步给改进体验换一个新目录；不要把参考答案填进去凑结果。

教师和想深入了解的同学可看：[教师说明](TEACHER_GUIDE.md)、[资料来源](DATA_SOURCES.md)、[方法说明](METHODS.md)、[实际验证记录](VERIFICATION.md)。
