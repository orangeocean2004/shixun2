# 面向 RAG 的智能分段 Demo

这是一个以“结构/语义感知分段”为核心的课程项目脚手架，对应课题 11「面向 RAG 的智能分段与内容组织智能体」。

当前已经可运行的主路径是 `scripts/segment_file.py`，它会：
- 读取文档（`.md/.txt/.docx/.pdf`）
- 解析为统一的文档块（`DocumentBlock`）
- 可选清理封面、目录等噪声
- 按标题边界、语义边界与长度约束进行分段
- 输出带回链、检索增强文本与统计信息的 JSON

## 当前状态

- ✅ 已实现并可运行：Python CLI 分段流程
- ✅ 已实现：文本/DOCX/PDF 读取器
- ✅ 已实现：文档预处理（封面、目录、正文型长表格清理）
- ✅ 已实现：分段策略（标题感知、语义边界、特殊块保护、超长拆分、过短合并、质量标记）
- ✅ 已实现：标题路径修正、检索增强文本、指标类内容增强
- ✅ 已实现：FastAPI 接口、Vue 基础演示页面、检索评测脚本
- 🚧 待完善：摘要、关键词、主题标签、实体标签、Docker/部署文档

## 本版本成绩

最近一次验证结果：

```text
py_compile：通过
eval_rag.py：PASS

Recall@5: +15.1%  >= 10% 目标
Recall@3: +52.5%
Recall@1: +11.5%
Precision@5: +7.2%
nDCG@5: +14.1%
MRR: +0.7%
```

说明：以上指标是在当前项目评测集上，相对固定长度分段基线的提升。详细更新记录见 `CHANGELOG.md`。

## 快速开始（本地演示）

### 1. 安装依赖

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
```

Windows 可把上面的 `python3` 换成 `python`，虚拟环境激活命令换成 `.\.venv\Scripts\activate`。

### 2. 运行示例文档

```bash
python scripts/segment_file.py assets/title.md -o data/outputs/title_chunks.json
```

你会看到类似输出：
- `Loaded blocks: ...`
- `Generated chunks: ...`
- `Output written: ...`

### 3. 运行你自己的文档

```bash
python scripts/segment_file.py <输入文件> -o <输出JSON>
```

支持的输入格式：
- `.txt` / `.md` / `.markdown`
- `.docx`
- `.pdf`

DOCX/PDF 可使用 `--clean-document` 清理封面、目录等噪声：

```bash
python scripts/segment_file.py assets/开题报告_课题11_面向RAG的智能分段与内容组织智能体.docx \
  --clean-document \
  -o data/outputs/open_report_chunks.json
```

常用参数示例：

```bash
python scripts/segment_file.py assets/title.md \
  --doc-id my_doc \
  --min-chars 300 \
  --target-chars 900 \
  --max-chars 1200 \
  --overlap-sentences 1 \
  -o data/outputs/my_doc_chunks.json
```

### 4. 运行测试与评测

```bash
python -m unittest backend.tests.test_segmenting -v
python scripts/eval_rag.py
```

## 输出结构说明

CLI 输出 JSON 包含：
- `doc_id`
- `source_file`
- `block_count`
- `preprocessing`（如果启用 `--clean-document`）
- `chunks[]`
  - `chunk_id`
  - `chunk_type`
  - `title_path`
  - `section_titles`
  - `content`
  - `retrieval_text`
  - `char_count`
  - `source_refs`
  - `strategy_info`
  - `quality_flags`
- `statistics`（分段统计）
- `strategy`（本次分段参数）

字段说明：
- `content`：原文展示内容
- `retrieval_text`：检索增强文本，会拼入标题、小节名和指标类关键词
- `source_refs`：原文块、页码和元数据回链
- `section_titles`：chunk 内实际包含的小节标题，避免多小节合并时标题挂错

## 代码架构（已实现部分）

### 端到端主流程

1. `scripts/segment_file.py`
   - 解析命令行参数
   - 构建 `SegmentConfig`
   - 调用 `load_document(...)`
   - 可选调用 `preprocess_document_blocks(...)`
   - 调用 `segment_blocks(...)`
   - 写入输出 JSON

2. `backend/app/services/document_loader/loader.py`
   - 按后缀分发读取器
   - 统一返回 `DocumentBlock[]`

3. `backend/app/services/preprocessing/`
   - `cleaner.py`：封面、目录、正文型长表格清理

4. `backend/app/services/segmenting/`
   - `parser.py`：纯文本逻辑分块（标题/表格/列表/代码）
   - `heading.py`：标题识别与层级估计
   - `splitter.py`：候选分段、embedding 语义边界、超长拆分、过短合并
   - `segmenter.py`：主流程编排，生成最终 chunk、来源回链与检索增强文本
   - `statistics.py`：统计指标与序列化
   - `models.py`：核心数据结构

5. `backend/app/services/retrieval/`
   - `embedding_store.py`：sentence-transformers embedding 检索与轻量关键词重排
   - `tfidf_store.py`：TF-IDF fallback 检索

6. `backend/app/services/evaluation/`
   - `baseline.py`：固定长度切分基线
   - `metrics.py`：Recall@k、Precision@k、nDCG、MRR 与混合相关性判断

7. `backend/app/services/segmenter.py`
   - 对外稳定导出：`segment_blocks` / `segment_text`

## 已知限制

- 内容组织还不完整：摘要、关键词、主题标签、实体标签仍需补齐。
- 长表格目前优先整体保护，可能产生少量 oversized table chunk；后续可按行组拆分并重复表头。
- 当前评测集规模较小，主要用于课程验收和回归对比。
- embedding 模型首次运行会访问 Hugging Face Hub 下载缓存；模型不可用时会回退到轻量字符/词频方式。

## 目录说明（与演示相关）

- `assets/`：示例输入文档
- `data/outputs/`：CLI 输出目录
- `scripts/segment_file.py`：当前推荐入口
- `scripts/eval_rag.py`：智能分段与固定长度基线评测
- `scripts/tune_segmenting_params.py`：分段参数搜索
