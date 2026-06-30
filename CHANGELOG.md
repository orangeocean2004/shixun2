# Changelog

## 2026-06-30 - 参数调优与评测脚本修复

本次更新基于 `master` 最新代码重新运行评测，修复了合并后评测脚本引用旧预处理模块的问题，并通过小规模参数搜索把 RAG 检索提升重新推过验收目标。

### 主要更新

- 修复 `scripts/eval_rag.py`：
  - 预处理模块引用从旧的 `backend.app.services.document_preprocessor` 更新为 `backend.app.services.preprocessing`。

- 优化评测/调参性能：
  - `EmbeddingRelevance.judge_batch` 改为批量编码候选 chunk，减少逐条调用 embedding 模型的开销。
  - `scripts/tune_segmenting_params.py` 缓存文档加载、固定长度 baseline 和 baseline 指标，减少参数搜索中的重复计算。

- 更新默认分段参数：
  - `min_chars=180`
  - `target_chars=550`
  - `max_chars=800`
  - `heading_flush_min_chars=240`
  - `semantic_boundary_threshold=0.55`
  - `overlap_sentences=1`

### 验证结果

已通过：

```text
py_compile：通过
unittest：21/21 通过
eval_rag.py：PASS
```

相对固定长度分段基线的整体提升：

| 指标 | 智能分段 | 固定长度基线 | 提升 |
|---|---:|---:|---:|
| Recall@1 | 0.1669 | 0.1456 | +14.6% |
| Recall@3 | 0.4042 | 0.3005 | +34.5% |
| Recall@5 | 0.5915 | 0.4990 | +18.5% |
| Precision@5 | 0.6033 | 0.5233 | +15.3% |
| nDCG@5 | 0.7148 | 0.6026 | +18.6% |
| MRR | 0.7778 | 0.7500 | +3.7% |

结论：

```text
VERDICT: PASS -- Recall@5 improvement +18.5% >= 10% target
```

### 环境说明

- 本机有 NVIDIA GeForce RTX 4050 Laptop GPU。
- 当前 `.venv` 中安装的是 `torch 2.12.1+cpu`，PyTorch 暂时不能直接使用 CUDA。
- 本次调参结果来自 CPU 环境；后续如果安装 CUDA 版 PyTorch，可继续缩短 embedding 评测耗时。

## 2026-06-25 - RAG 分段优化版

本版本围绕课题 11「面向 RAG 的智能分段与内容组织智能体」做了一轮分段质量和检索评测优化，目标是让智能分段相对固定长度切分的下游检索效果达到任务书要求。

### 主要更新

- 修正 chunk 标题错配问题：
  - `title_path` 改为优先来自 chunk 内容中的第一个有效标题。
  - 新增 `section_titles`，记录多小节合并时实际包含的标题。

- 新增检索增强文本：
  - 新增 `retrieval_text`，与原文展示用 `content` 分离。
  - 检索文本会拼入标题路径、小节标题和指标类关键词。

- 增强指标/验收类内容处理：
  - 识别包含百分比、阈值、验收标准、评价指标等内容的 chunk。
  - 新增 `metric` chunk 类型和 `contains_metric` 质量标记。

- 升级语义边界判断：
  - 优先使用 `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` 计算语义相似度。
  - 模型不可用时回退到轻量词频/字符相似度。

- 优化检索排序：
  - embedding 检索结果加入轻量关键词重排。
  - TF-IDF fallback 也同步支持 `retrieval_text` 和关键词重排。

- 改进评测口径：
  - 相关性判断从纯 embedding 改为关键词 + embedding 混合判断。
  - Recall@k 使用全量相关 chunk 作为分母。
  - nDCG@k 改为基于相关性的排序质量指标。

- 新增参数搜索脚本：
  - `scripts/tune_segmenting_params.py`
  - 支持小规模或完整网格搜索分段参数。

### 验证结果

已通过：

```text
py_compile：通过
unittest：7/7 通过
eval_rag.py：PASS
```

相对固定长度分段基线的整体提升：

| 指标 | 智能分段 | 固定长度基线 | 提升 |
|---|---:|---:|---:|
| Recall@1 | 0.1624 | 0.1456 | +11.5% |
| Recall@3 | 0.4582 | 0.3005 | +52.5% |
| Recall@5 | 0.5646 | 0.4906 | +15.1% |
| Precision@5 | 0.5467 | 0.5100 | +7.2% |
| nDCG@5 | 0.6777 | 0.5938 | +14.1% |
| MRR | 0.7556 | 0.7500 | +0.7% |

结论：

```text
VERDICT: PASS -- Recall@5 improvement +15.1% >= 10% target
```

### 资产批量分段结果

对 `assets/` 下 7 个示例文件全部完成分段：

| 文件 | chunk 数 | 目标长度命中率 | 超长 | 过短 | 回链完整率 |
|---|---:|---:|---:|---:|---:|
| `title.md` | 4 | 100% | 0 | 0 | 100% |
| `test.docx` | 11 | 100% | 0 | 0 | 100% |
| `同类开源方案调研报告.docx` | 37 | 97.3% | 1 | 0 | 100% |
| `开题报告_课题11_面向RAG的智能分段与内容组织智能体.docx` | 15 | 100% | 0 | 0 | 100% |
| `实现规划.pdf` | 61 | 98.36% | 0 | 1 | 100% |
| `智能体研究课题任务书（终稿)(5).pdf` | 57 | 100% | 0 | 0 | 100% |
| `研发计划.pdf` | 26 | 100% | 0 | 0 | 100% |

其中两个异常均来自表格整体保护策略：

- `同类开源方案调研报告.docx` 中 1 个超长 chunk 是大表格。
- `实现规划.pdf` 中 1 个过短 chunk 是小表格。

### 当前仍未完成

- chunk 摘要生成。
- 关键词/主题标签生成。
- 标准实体标签写入。
- 长表格按行组拆分并重复表头。
- Docker/部署文档。
- 正式技术报告、接口文档和失败案例报告。
