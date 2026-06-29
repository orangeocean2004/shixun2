# Changelog

## 2026-06-29 - master 整合优化版

本版本基于最新 `master` 整合 `yh` 分支中的 RAG 分段优化与评测闭环，同时保留主线已有的 FastAPI、Chroma/SQLite 入库检索、Vue 演示页面、标签/摘要/实体/回链等能力。

### 主要更新

- 保留主线 RAG store：
  - 继续使用 SQLite 保存文档与 chunk 元数据。
  - 继续使用 Chroma 保存向量并支持查询。

- 增强智能分段：
  - 新增 `heading_flush_min_chars`，减少短标题导致的碎片化。
  - 引入 `tiktoken` token 计数，替代纯正则 token 估算。
  - 递归使用段落、换行、句号、逗号等分隔符拆分超长 chunk。
  - embedding 语义边界优先使用本地 `paraphrase-multilingual-MiniLM-L12-v2`，不可用时回退词频相似度。

- 修正标题与检索表示：
  - 合并多个短小节时，`title_path` 优先来自 chunk 中第一个有效小节标题。
  - 新增 `section_titles`，记录 chunk 内实际包含的小节标题。
  - 新增 `retrieval_text`，与展示用 `content` 分离，并优先用于 Chroma 入库与检索重排。

- 增强指标类内容：
  - 识别包含百分比、阈值、Recall、nDCG、MRR、验收标准、评价指标等内容的 chunk。
  - 指标类 chunk 标记为 `metric`，并添加 `contains_metric` 质量标记。

- 补齐评测闭环：
  - 新增固定长度切分基线。
  - 新增 `scripts/eval_rag.py`。
  - 新增 `scripts/tune_segmenting_params.py`。
  - 新增 Recall@k、Precision@k、nDCG@k、MRR 评测。

### 验证结果

已通过：

```text
py_compile：通过
unittest：21/21 通过
eval_rag.py：PASS
```

相对固定 512 字符切分基线的整体提升：

| 指标 | 智能分段 | 固定长度基线 | 提升 |
|---|---:|---:|---:|
| Recall@1 | 0.1688 | 0.1573 | +7.4% |
| Recall@3 | 0.4419 | 0.3330 | +32.7% |
| Recall@5 | 0.5660 | 0.5139 | +10.1% |
| Precision@5 | 0.5600 | 0.5367 | +4.3% |
| nDCG@5 | 0.6917 | 0.6277 | +10.2% |
| MRR | 0.7778 | 0.7833 | -0.7% |

结论：

```text
VERDICT: PASS -- Recall@5 improvement +10.1% >= 10% target
```

### 当前仍可继续优化

- 扩大评测集规模，降低小样本波动。
- 长表格按行组拆分并重复表头。
- 摘要与实体标签可进一步接入更强模型或标准实体库。
- 补充正式技术报告、接口文档和部署文档。
