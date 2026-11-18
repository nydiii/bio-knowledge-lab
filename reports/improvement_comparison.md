# 旧版与改进版：实际运行比较

本页由实际输出计算，只需阅读，不用填写或提交。

新版是固定模型回答上的本地规则改进，本次没有新模型推理。原抽取跨度/类型不变，实体识别分数应不变。

两版使用相同的原 BioRED 金标和评价器。下面是与固定参考的一致性，不是专家审定率；原参考争议也照常计分。

## 开发案例（10 篇）

| 指标 | 旧版 precision / recall / F1 | 新版 precision / recall / F1 |
|---|---|---|
| 实体识别 | 77.70% / 72.28% / 74.89% | 77.70% / 72.28% / 74.89% |
| 严格链接 | 80.41% / 40.45% / 53.83% | 82.45% / 41.48% / 55.19% |
| 端到端关系 | 9.02% / 4.03% / 5.57% | 9.85% / 4.36% / 6.05% |
| 关系及 novelty | 8.27% / 3.69% / 5.10% | 9.09% / 4.03% / 5.58% |

## 本轮未参与调整的验证文献（40 篇）

| 指标 | 旧版 precision / recall / F1 | 新版 precision / recall / F1 |
|---|---|---|
| 实体识别 | 74.00% / 78.07% / 75.98% | 74.00% / 78.07% / 75.98% |
| 严格链接 | 82.97% / 51.72% / 63.72% | 82.97% / 51.72% / 63.72% |
| 端到端关系 | 28.35% / 16.46% / 20.83% | 28.35% / 16.46% / 20.83% |
| 关系及 novelty | 27.62% / 16.13% / 20.37% | 27.62% / 16.13% / 20.37% |

## 全部文献（50 篇）

| 指标 | 旧版 precision / recall / F1 | 新版 precision / recall / F1 |
|---|---|---|
| 实体识别 | 74.64% / 76.95% / 75.78% | 74.64% / 76.95% / 75.78% |
| 严格链接 | 82.55% / 49.54% / 61.92% | 82.88% / 49.74% / 62.17% |
| 端到端关系 | 24.43% / 13.37% / 17.28% | 24.62% / 13.45% / 17.40% |
| 关系及 novelty | 23.71% / 13.03% / 16.82% | 23.90% / 13.12% / 16.94% |

开发案例的改善只能证明这些案例被修复。本轮验证文献历史开发已可见，不是全新的独立测试集。

## 所有实体链接的变化

严格判定要求位置、类型和完整 ID 集合一致；撤回错误候选为待审不等于已经找到正确 ID。

改善：5；退步：0；未变（匹配）：1249；仍未匹配：687；无可匹配的参考提及：662。

发生 ID 集合变化的提及：5。

| 文献/提及 | 名称 | 旧 ID | 新 ID | 原参考 | 结果 |
|---|---|---|---|---|---|
| 19672862/m26 | glycogen synthase kinase-3beta | NCBIGene:56637 | NCBIGene:2932 | NCBIGene:2932 | 改善 |
| 19672862/m27 | GSK-3beta | NCBIGene:56637 | NCBIGene:2932 | NCBIGene:2932 | 改善 |
| 18593936/m13 | survivin | NCBIGene:11799 | NCBIGene:332 | NCBIGene:332 | 改善 |
| 18593936/m19 | survivin | NCBIGene:11799 | NCBIGene:332 | NCBIGene:332 | 改善 |
| 18593936/m39 | survivin | NCBIGene:11799 | NCBIGene:332 | NCBIGene:332 | 改善 |

另有 142 个提及附加待核查提示。这是规则发现的风险，不是已证实错误；旧候选 ID 可能仍保留，不能计为已经修复。

## 关系标签变化

仅列实际改动；来源句支持是规则候选，不代表所有端点身份也已正确。

- `19672862/r14`：Positive_Correlation → Negative_Correlation；固定参考：Negative_Correlation。

- `19672862/r15`：Positive_Correlation → Negative_Correlation；固定参考：Negative_Correlation。

- `21750150/r10`：Positive_Correlation → Negative_Correlation；固定参考：Negative_Correlation。

## 本轮优先核查的记录现在怎样了

下面逐条显示实际预测；原参考辅助整理或人工建议不是算法必然能输出的答案。

- 第 1 条 `19672862/r14`：Positive_Correlation → Negative_Correlation。rule_candidate。

- 第 2 条 `19672862/r15`：Positive_Correlation → Negative_Correlation。rule_candidate。

- 第 3 条 `21750150/r10`：Positive_Correlation → Negative_Correlation。rule_candidate。

- 第 4 条 `25305591/r7`：Positive_Correlation → Positive_Correlation。本轮未自动修改；继续参照诊断说明核查具体字段。

- 第 5 条 `27014915/r6`：Negative_Correlation → Negative_Correlation。本轮未自动修改；继续参照诊断说明核查具体字段。

- 第 6 条 `27084744/r16`：Positive_Correlation → Positive_Correlation。本轮未自动修改；继续参照诊断说明核查具体字段。

- 第 7 条 `27248656/r18`：Negative_Correlation → Negative_Correlation。本轮未自动修改；继续参照诊断说明核查具体字段。

- 第 8 条 `19306381/r5`：Association → Association。本轮未自动修改；继续参照诊断说明核查具体字段。

- 第 9 条 `19306381/r6`：Association → Association。本轮未自动修改；继续参照诊断说明核查具体字段。

- 第 10 条 `27248656/r11`：Negative_Correlation → Negative_Correlation。本轮未自动修改；继续参照诊断说明核查具体字段。

- 第 11 条 `27248656/r7`：Positive_Correlation → Positive_Correlation。本轮未自动修改；继续参照诊断说明核查具体字段。

- 第 12 条 `27248656/r8`：Positive_Correlation → Positive_Correlation。本轮未自动修改；继续参照诊断说明核查具体字段。

- 第 13 条 `18507837/m24`：NCBIGene:1032 → NCBIGene:1032。not_rechecked；本轮规则没有充分局部依据，保留旧版候选。

- 第 14 条 `18507837/m31`：NCBIGene:9477 → NCBIGene:9477。not_rechecked；本轮规则没有充分局部依据，保留旧版候选。

- 第 15 条 `18593936/m13`：NCBIGene:11799 → NCBIGene:332。rule_candidate；独立别名候选与本次提及的局部来源一致。

- 第 16 条 `18593936/m19`：NCBIGene:11799 → NCBIGene:332。rule_candidate；独立别名候选与本次提及的局部来源一致。

- 第 17 条 `18593936/m39`：NCBIGene:11799 → NCBIGene:332。rule_candidate；独立别名候选与本次提及的局部来源一致。

- 第 18 条 `19463742/m1`：NCBIGene:4160 → NCBIGene:4160。not_rechecked；本轮规则没有充分局部依据，保留旧版候选。

- 第 19 条 `19463742/m26`：NCBIGene:3630 → NCBIGene:3630。needs_review；同名候选或不同实验涉及多个物种，当前提及缺少唯一身份依据。 保留旧版候选并提示待核查，本轮未确认或修复该身份。

- 第 20 条 `19463742/m3`：NCBIGene:3630 → NCBIGene:3630。needs_review；同名候选或不同实验涉及多个物种，当前提及缺少唯一身份依据。 保留旧版候选并提示待核查，本轮未确认或修复该身份。

- 第 21 条 `19463742/m30`：NCBIGene:3630 → NCBIGene:3630。needs_review；同名候选或不同实验涉及多个物种，当前提及缺少唯一身份依据。 保留旧版候选并提示待核查，本轮未确认或修复该身份。

- 第 22 条 `19463742/m33`：NCBIGene:3630 → NCBIGene:3630。needs_review；同名候选或不同实验涉及多个物种，当前提及缺少唯一身份依据。 保留旧版候选并提示待核查，本轮未确认或修复该身份。

- 第 23 条 `19672862/m26`：NCBIGene:56637 → NCBIGene:2932。rule_candidate；独立别名候选与本次提及的局部来源一致。

- 第 24 条 `19672862/m27`：NCBIGene:56637 → NCBIGene:2932。rule_candidate；独立别名候选与本次提及的局部来源一致。

## 怎样理解仍然存在的问题

- insulin 的细胞物种不等于外加试剂物种；多 ID 原参考也不能用全部候选机械填满。保留待审是透明处理，未计作严格修复。
- VIP、DAPT 与 Hsp90beta 的干预方向/对象粒度仍需按原文解释，不能由一个动词自动改标签。
- p19、TRFP 的原参考疑点单独记录；不修改原 gold 追求更高分。
- invalid_judgment 是原核查引文/输出未通过，不能直接说关系错了。本轮未重新调用核查模型，也未把旧核查结果冒充新版判决。
- 原文、候选、金标和规则候选来源仍各自保留；软件通过、分数提高、科学审定和论文严格复现是不同结论。
