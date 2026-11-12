# 第三方材料与引用

本仓库的课程代码、教学数据转换、提示适配和原始研究材料分别标注来源。项目自己的许可证不改变第三方数据、论文、模型和代码的许可。

## 论文和作者实现

| 项目 | 原始来源 | 本仓库的使用方式与许可边界 |
|---|---|---|
| ACL 2026 标注指南方法 | [论文](https://aclanthology.org/2026.acl-long.1760/)；[作者仓库](https://github.com/KonWooKim/llm-guideline-moderation) | 方法和任务规范引用；公开仓库页面未核实到独立代码许可，不能据公开可见便声称其代码是 MIT 或可任意再分发 |
| NC 2025 BioNLP benchmark | [论文](https://doi.org/10.1038/s41467-025-56989-2)；[作者仓库](https://github.com/BIDS-Xu-Lab/Biomedical-NLP-Benchmarks) | 作者代码仓库标示 Apache-2.0；数据集各自的原始许可仍需分别遵守；本课程的 BioRED 文档级提示属于适配 |
| MDKG | [论文](https://doi.org/10.1038/s41467-025-62781-z)；[作者仓库](https://github.com/MonsterTea/MDKG) | 方法引用；当前仓库页面未核实到独立代码许可，不按 MIT 等许可复制分发整套源码 |
| CER | [论文](https://doi.org/10.1145/3726302.3729931)；[作者仓库](https://github.com/PRAISELab-PicusLab/CER) | 作者仓库说明 CC BY-NC 4.0。课程实现借鉴检索与证据核查流程，不能将上游许可更改成项目自己的许可 |

## 数据与模型

- **BioRED**：[官方仓库](https://github.com/ncbi/BioRED)、[官方发布目录](https://ftp.ncbi.nlm.nih.gov/pub/lu/BioRED/)。保留原文 PMID、原始标注版本、数据哈希及坐标转换说明。PubMed 可访问性不等于全部摘要文字属于公有领域；论文文本与人工标注的权利来源应分别识别。课堂使用及进一步再分发按原始发布条件处理。
- **独立实体词典**：具体 NCBI、MeSH 或其他数据库来源、下载版本与筛选方式见 [DATA_SOURCES.md](docs/DATA_SOURCES.md)。不能用选中文献的金标名称－ID 对冒充外部标准知识库。
- **可选 SapBERT**：[作者模型卡](https://huggingface.co/cambridgeltl/SapBERT-from-PubMedBERT-fulltext)标示 Apache-2.0。固定 revision 为 `090663c3ae57bf35ffe4d0d468a2a88d03051a4d`；模型和分词器的实测文件哈希见 [model_manifest.json](data/model_manifest.json)。权重单独下载，不纳入课程仓库；UMLS 训练数据的权利不因模型卡许可而变为课程自有。推理适配见 [METHODS.md](docs/METHODS.md)，不能把词典匹配输出标作模型输出。
- **DeepSeek**：使用官方 API 产生的真实结果应保留模型名、调用时间、提示及输入哈希、用量。真实响应与人工金标性质不同；费用和服务规则以调用时官方说明为准。

## 分发内容

下载缓存、个人运行目录、虚拟环境、凭据、访问令牌和大型模型权重不应进入仓库。第三方材料若没有明确再分发许可，优先提供来源链接及下载／校验程序，不把完整上游仓库复制成课程自有代码。发布清单和实测内容以仓库实际文件及 [验证记录](docs/VERIFICATION.md) 为准。
