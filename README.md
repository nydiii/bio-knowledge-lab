# 生物科学知识建模实训

围绕 **50 篇真实生物医学摘要**，让学生把原文变成可关联、可核查、可修订的知识库。案例以炎症与免疫信号为联系，跨肾病、肿瘤、关节炎等研究文献；先导入 40 篇，再加入 10 篇。

适合会使用 Python 的本科生。**普通电脑、无需独立显卡；默认免费回放，不需要 API Key。** 也提供 DeepSeek 真实调用路径。回放保存的是实际调用响应，没有以人工参考答案替代模型结果。

## 从这里开始

- **[逐步操作手册](docs/MANUAL.md)**：安装、下载、分步操作、真实 API、预期结果和常见问题。
- **[教师说明](docs/TEACHER_GUIDE.md)** · **[人工核查表](docs/MANUAL_REVIEW.md)** · **[回传模板](docs/REVIEW_RETURN.md)**。
- **[数据来源](docs/DATA_SOURCES.md)** · **[字段与参考答案](docs/SCHEMA.md)** · **[论文方法与适配边界](docs/METHODS.md)**。
- **[实际验证记录](docs/VERIFICATION.md)**：费用、指标、测试环境、未覆盖内容。
- **[24 条优先核查记录](reports/priority_review.csv)** · [完整诊断队列](reports/review_queue.csv)。

| 环节 | 实际操作 | 主要验收 |
|---|---|---|
| 科学信息抽取 | 有指南的实体识别，再做文档级关系抽取；保存原文位置和响应 | 对照原数据集人工标注计算严格指标 |
| 知识对齐与融合 | 独立 NCBI/MeSH 候选、文内缩写、上下文候选重排；词典/SapBERT 对照 | 跨文献统一实体，保留多篇独立证据与歧义 |
| 知识校验与更新 | 结构与证据核对、文献检索、明确的教学错误、带历史修订和增量导入 | 修订前后查询变化，历史不丢失，重复导入不膨胀 |

## 安装与完整回放

推荐 **Python 3.12**。克隆或下载本仓库，进入含 `pyproject.toml` 的目录。

macOS / Linux：

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
python -m bio_knowledge_lab demo --workdir runs/my-first-lab
python -m bio_knowledge_lab verify --workdir runs/my-first-lab
```

Windows PowerShell：

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m bio_knowledge_lab demo --workdir runs/my-first-lab
.\.venv\Scripts\python.exe -m bio_knowledge_lab verify --workdir runs/my-first-lab
```

默认路径仅使用 Python 标准库；安装后运行回放不联网、不收费。重复验收使用 `verify`，重做实验换新工作目录。`passed: true` 表示流程验收通过，**不是所有科学内容均正确**。

运行完成可看到：50 篇文献、2603 个预测实体提及、690 条文献关系候选、84 个连接多篇文献的标准实体。目录中有 SQLite 库、各阶段 JSONL、评价报告、四个查询快照、修订提案和版本历史。

需要回传学生电脑的运行情况：

```bash
python scripts/verify_student_setup.py --output runs/student-check
```

回传生成的 ZIP 和填写后的 `docs/REVIEW_RETURN.md`。不需要自己排错，也不应回传密钥。

## 方法与真实效果

采用 ACL 2026 指南复用、Nature Communications 2025 生物医学关系分类实验、MDKG 2025 实体链接与 CER/SIGIR 2025 证据核查的部分思想。**这是完整教学流程的代码实现与方法迁移，不是四篇论文全部训练实验或原始指标的复现。** 原作者仓库、固定版本和具体差异见 [METHODS](docs/METHODS.md)。

额外的上下文候选重排、SQLite 历史、预算控制、课程错误注入由本项目实现。SapBERT CPU 对照已在同一批资料上运行；没有强制学生训练或部署大模型。

对选定 50 篇有联系的文献，主线真实结果为：严格实体识别 F1 **0.758**，实体识别加标准 ID 的严格链接 F1 **0.619**，含实体链接的端到端关系 F1 **0.173**。[完整指标](reports/metrics.json)

关系任务仍有明显漏检和错误，本项目适合学习、比较和修订模型结果，不能把生成库当作已审定的生物学事实库。缺少归一词典的变体、细胞系等保留未解决；模型判断与新增证据句、条件不冒充人工金标。文献是摘要，课堂选择子集混合原训练/验证/测试划分，不能将这些分数宣传为官方 BioRED 测试成绩。

## API 与免费路径

教师准备本批真实结果共调用 216 次（包括早期链接实验及修正重跑），按已核官方高峰价、忽略缓存优惠，保守估算 **3.641656 元**，低于批准的 5 元。[逐次脱敏用量](reports/api_usage.json)

学生免费路径不再产生这些费用。真实调用需要自行配置 API；抽取、上下文对齐、证据核查必须共用同一个预算账本。失败状态保留预留，不自动无限重试，不通过删除账本规避费用上限。API 模型版本和输出可能随时间变化，真实运行不要求逐字等于发布回放。

原始响应完整保存在 `data/replay/`，旧实验也保留并计入费用；当前上下文回放按提示哈希选取。原文、人工 gold、独立候选词典与回放均有 SHA-256 校验。

## 数据及许可

原始 BioRED 600 摘要中选出本课程 50 篇，保留 2525 个人工实体标注、1197 条文档级关系作为参考。独立候选库来自 NCBI Gene、NCBI Taxonomy 与 NLM MeSH 2026，不从测试 gold 构造名称到 ID 的答案表。

课程原始代码采用 [MIT](LICENSE)。论文摘要、数据、模型和第三方代码保留原有条款，详见 [THIRD_PARTY](THIRD_PARTY.md)。仓库已公开，任何人均可查看、下载和 Fork；访客不能直接修改原仓库。当前仅所有者 `nydiii` 具有写入权限。
