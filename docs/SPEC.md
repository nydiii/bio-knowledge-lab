# 生物科学知识建模实训：已确认规格

用户已授权完整实施。面向会使用 Python 的本科生，普通电脑 CPU，无需独立显卡，不以压缩第一版功能交付。处理一批公开生物医学文献，体验信息抽取、实体对齐与跨文献融合、证据校验与修订更新；真实 DeepSeek API 与真实结果免费回放均提供。教师端本项目全部付费调用累计不超过人民币 5 元。

## 数据和科学边界

- 从官方 BioRED 获取原始摘要、人工实体及文档级关系标注。按跨文献关联程度选择有可解释联系的一批资料；保留原始标签、标准标识、novelty 和独立文献记录，不自行限制为单一物种或抹去其他实体类型。
- 模型输入只包含原文和训练规则；预测、人工 gold 和外部实体词典隔离。已有 gold 仅用于评价及显式的教师参考实验，不能偷渡为抽取/归一结果。
- 单篇关系按文档粒度保存；实体合并不合并文献证据。不把无关系、负相关、背景知识和证据不足混为一类；不从原版实体对顺序推出因果方向。
- 逐句证据、实验上下文为课程新增的有来源候选，不宣称已有人工 gold。原金标不静默覆盖。
- 抽取参考 ACL 2026 guideline refinement 与 NC 2025 BioNLP benchmark，归一借鉴 MDKG 2025，核查借鉴 CER 2025。公开模块原样复现、改写迁移和课程工程必须分别记录。
- 教学错误注入是对真实记录副本的明确扰动；真实模型错误原样保留。增量文献另有封存 gold，更新前后查询与历史可验证。

## 软件和交付

独立 Python 包与 SQLite 知识库、中文逐步手册、教师说明、来源清单、版本固定、真实响应及用量、自动验收、独立电脑回传脚本、待人工审阅表。新仓库建议 bio-knowledge-lab，沿用 nydiii 账号及先私有的发布偏好。化学仓库不修改。

## 模块契约

数据位于 data/corpus/documents.jsonl（每行 doc_id/title/abstract/text/split，text 为 title + 换行 + abstract，offset 依此），data/reference/gold.jsonl（doc_id/entities/relations），data/kb/entities.jsonl（namespace/id/name/aliases/type/tax_id/source）。manifest.json 固定来源 URL、SHA256、原始坐标转换和选样算法；metadata 可另附字段。

抽取输出每行：doc_id, entities:[{mention_id,text,start,end,type}], relations:[{relation_id,head,tail,type,novelty,evidence:[{start,end,text}],context:{}}]。head/tail 是 mention_id；不带 gold ID。未报告 context 保留空，不补推断事实。

对齐输出每个 mention 带 links:[{namespace,id,score,method}]、link_status，保留原字段。可歧义/未解决。外部 KB 不由选定文献 gold 名称-ID 对生成。

pipeline.py 提供 align_records(records,kb_path,method='lexical'), ingest_records(db_path,records), validate_database(db_path), query_database(db_path), apply_revision(db_path,revision), history(db_path), evaluate_records(records,gold_path)。函数返回可序列化 dict/list，所有持久写操作必须保留来源和版本、拒绝错误跨度/未知端点，不能覆盖历史。

主 CLI 提供 fetch/extract/align/fuse/evaluate/check/query/revise/history/update/demo/verify，额外证据核查模块保留检索证据及候选判决。
