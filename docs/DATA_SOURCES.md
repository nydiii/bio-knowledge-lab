# 数据来源、版本与复现范围

本项目使用公开真实摘要、原作者人工标注及独立标准词典。固定课程快照采集于 **2026-11-12**。这些是教学用途的历史快照，不保证反映当前最新数据库；NLM/NCBI 未背书本项目。Source: National Library of Medicine。

## 同一批文献怎样选出

原始来源是 [BioRED 官方仓库](https://github.com/ncbi/BioRED) 指向的 [BIORED.zip](https://ftp.ncbi.nlm.nih.gov/pub/lu/BioRED/BIORED.zip)，原版 **600 篇 PubMed 摘要**，对应 BioRED 2022 数据论文。不是后续 BioCreative VIII 的 1000 篇扩展，也不包含 BioREDirect 2025 的方向新增金标。

`scripts/prepare_data.py` 对全部 600 篇原始实体字符跨度做子串检查，然后按基因／疾病标准标识构造文献关联图：仅用在 2–45 篇中出现的对象作为选样连接；以加权连接分数确定起点，贪心选取与已选文献相连的资料，PMID 用作固定平局规则。实体标注仅用于**教学选样及参考评价**，不进入模型抽取输入或候选词典的筛选。

选出 **50 篇**，主题连接围绕炎症、免疫信号与疾病，涉及肾病、肿瘤、关节炎及代谢研究。不是限定单一疾病或物种的随机样本。按选样顺序每第 5 篇作为增量：**40 篇初始、10 篇增量**。共保留 **2525 个实体提及、1197 条文档级关系、139 个跨文献共享的基因／疾病标准 ID**。

选中的材料保留全部六类实体及其原始名称：

| 原始实体类别 | 50 篇中的提及数 |
|---|---:|
| GeneOrGeneProduct | 1451 |
| DiseaseOrPhenotypicFeature | 524 |
| ChemicalEntity | 235 |
| OrganismTaxon | 174 |
| CellLine | 95 |
| SequenceVariant | 46 |

八个允许关系标签为 `Association`、`Positive_Correlation`、`Negative_Correlation`、`Bind`、`Cotreatment`、`Comparison`、`Drug_Interaction`、`Conversion`。所选 50 篇实际包含前五种；未出现后三种不能据此宣称已验证相应抽取性能。`novelty` 的原值 `Novel` / `No` 分别表示本篇新发现／背景知识，不是真／假，也不是肯定／否定。

每篇原始 `Train/Dev/Test` 划分保存在 `source_split`；课程 `initial/incremental` 是另一种用途划分。这个有意选择的连通子集混合原始划分，课程分数**不能当作官方 BioRED 测试集指标**。原文只有摘要，不能将本实验称为全文或 PDF 版面抽取。

## 文件对应与坐标

| 文件 | 内容与用途 |
|---|---|
| `data/corpus/documents.jsonl` | 模型可读原文；`doc_id/title/abstract/text/source_split/split/source_url`，没有 gold 实体或关系 |
| `data/reference/gold.jsonl` | 原作者人工标注转换后的参考；模型输入不读取 |
| `data/reference/cross_document_gold.json` | 教师参考：共享标准对象及其出现的 PMID |
| `data/reference/selection_report.json` | 确定性选样、数量、类型覆盖、词典统计及文献标题 |
| `data/kb/entities.jsonl` | 独立数据库形成的候选词典，不是从 gold 反查生成的答案表 |
| `data/manifest.json` | 官方原始文件 URL、字节数、SHA-256 与每个课程派生文件 SHA-256 |

`text = title + "\n" + abstract`。跨度采用 Python Unicode 字符位置，左闭右开，必须满足 `text[start:end] == entity.text`。原 BioRED 摘要起点为标题长度加一个分隔字符，替换为换行不改变坐标。600 篇原始实体的跨度均已核对，没有为了通过检查改变原文。

gold 实体包含 `mention_id/text/start/end/type/ids`。`ids` 是 `{namespace,id}` 数组，多标识原样保留。gold 关系包含 `head_ids/tail_ids/type/novelty/raw_head/raw_tail/relation_id`。标准标识端点属于**文档级实体对**，不等同于某一个局部提及。原版没有方向标注，`direction=not_annotated`，不得把原实体先后顺序解释为因果箭头。

原标注覆盖实体、标准标识、文档级关系与新颖性，**不覆盖逐句证据、完整实验条件、模型置信度、课程修订历史**。这些新增字段必须分别保留候选／待审状态。[官方标注指南](https://ftp.ncbi.nlm.nih.gov/pub/lu/BioRED/BioRED_Annotation_Guideline.pdf)

## 独立外部词典：无 gold 名称—ID 泄漏

| 来源 | 内容 | 固定范围 |
|---|---|---|
| NCBI `gene_info` | 官方符号、同义名称、描述、Gene ID、物种 | 人 9606、小鼠 10090、大鼠 10116 的完整源文件 |
| NLM MeSH XML `desc2026.gz` | 描述词、概念名称和术语、树类别 | MeSH 2026 描述词版本 |
| NLM MeSH XML `supp2026.gz` | 补充概念及其映射描述词 | 2026-11-12 获取的 2026 文件快照 |
| NCBI Taxonomy EFetch | 正式种名、官方通用名称和同义名称 | 9606、10090、10116；与所用 Gene 字典范围对应 |

从独立基因与 MeSH 源文件生成候选时，只读取 `documents.jsonl` 的**未标注原始文本**，枚举 1–12 词的规范化 n-gram，与官方名称及别名做检索。再加入按 ID 的 SHA-256 固定抽取的约 1/127 背景对象。保留所有命中对象及原官方别名，不参考测试 gold ID 删除干扰项，最终 **7347 个候选条目**。背景候选包含大量同名跨物种、非目标基因及不相关概念，不是每个提及仅提供正确答案的 oracle 词典。

命名空间为 `NCBIGene`、`MESH`、`NCBITaxon`。原 gold 中另有 `OMIM`、`Cellosaurus`、`tmVar` / `dbSNP`；本地候选词典尚未覆盖这些对象，必须保留未解决状态，不能把它们改造成猜测的 MeSH 或基因标识。其他物种基因同样不会强行映射成人类。CellLine 与 SequenceVariant 仍参与真实抽取、关系保存和参考评价；未提供相应归一词典属于明确的覆盖限制。

`gene_info` 的名称来源不是模型生成。MeSH 描述词按树类别 C/F03 提供疾病候选、D 提供化学候选；补充概念按官方映射到描述词继承候选类别。映射描述词上的 `*` 前缀仅为源格式标记，会去掉后查找。一个标准 ID 可有不同任务类型解释，不代表新增科学实体。

## 下载、重建与离线验证

在仓库根目录执行：

```bash
python scripts/prepare_data.py --verify-bundled
```

该命令不联网，检查随仓库保存的全部派生快照，预期 `passed: true`。

研究原始数据处理流程时执行：

```bash
python scripts/prepare_data.py --fetch
```

这会下载官方资料到 `data/downloads/`，大约需要 100 MB 下载空间，并按相同算法重建。源数据和派生文件的哈希固定在 manifest 中；源文件是动态更新的，日后服务器可能已变更。遇到哈希变化程序会停止，不静默用新版覆盖课程参考。**课程免费路径使用随仓库的冻结 JSONL，不要求重新下载动态词典。**

重建采用临时目录，先比较全部源文件和派生文件哈希，所有比较通过后才替换课程文件，manifest 最后写入。JSON 键排序，选样分数累加的集合遍历也排序，避免不同 `PYTHONHASHSEED` 导致内容或字节变化。文件已被手工改动时，普通重建会拒绝覆盖。若确实要升级数据库、修改选样规模或变更生成规则，应在独立副本中审查变化，显式使用 `--refresh-lock` 更新锁文件，并重新完成验收；该选项不是学生日常步骤。发布前已执行一次序列化规范修复，将 manifest 升为 1.1，保留了原 50 篇文献的 ID、文本、划分及全部标注内容。

## 使用条款与署名

- BioRED 数据与指南由官方公开提供，引用其数据论文及官方仓库。本文献摘要仍可能涉及原出版方版权，不能因存放在 NCBI 上就把摘要声明为 MIT。仓库已公开；第三方材料的原有权利与使用条件继续适用。原始资料来源与下载器均保留供核对。
- NLM MeSH 无下载费或使用费，要求清楚署名 NLM、不得暗示背书，并标明所用版本或不是最新数据。本项目在此明确标注 MeSH 2026 和下载日期。[MeSH 官方使用条款](https://www.nlm.nih.gov/databases/download/terms_and_conditions_mesh.html)
- [MeSH 官方下载说明](https://www.nlm.nih.gov/databases/download/mesh.html)指出描述词按年更新、补充概念持续更新。冻结哈希用于教学复现，不表示它是最新知识。
- NCBI Gene 和 Taxonomy 的 source URL、原始文件哈希均写入 manifest，候选条目保留对应官方记录链接。第三方数据不归入课程代码的 MIT 授权。
- 未使用 CTD 派生词典；不需要学生为本项目完成 CTD 数据使用通知。
