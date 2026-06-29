# 面向 RAG 的智能分段 Demo

这是一个以“结构/语义感知分段”为核心的课程项目脚手架。

当前已经可运行的主路径是 `scripts/segment_file.py`，它会：
- 读取文档（`.md/.txt/.docx/.pdf`）
- 解析为统一的文档块（`DocumentBlock`）
- 按标题边界、语义边界与长度约束进行分段
- 输出带回链、内容组织字段、检索增强文本与统计信息的 JSON

## 当前状态

- ✅ 已实现并可运行：Python CLI 分段流程
- ✅ 已实现：文本/DOCX/PDF 读取器
- ✅ 已实现：分段策略（标题感知、embedding 语义边界、特殊块保护、超长拆分、过短合并、质量标记）
- ✅ 已实现：内容组织字段（标签、摘要、实体标签、原文回链、小节标题、检索增强文本）
- ✅ 已实现：FastAPI 上传分段、入库检索、查询 chunks 接口
- ✅ 已实现：Vue 基础演示页面
- ✅ 已实现：固定长度基线、检索评测脚本、参数搜索脚本
- 🚧 待完善：正式技术报告、Docker/部署文档、长表格细粒度拆分

## 本版本成绩

最近一次验证结果：

```text
py_compile：通过
unittest：21/21 通过
eval_rag.py：PASS

Recall@5: +10.1%  >= 10% 目标
Recall@3: +32.7%
Recall@1: +7.4%
Precision@5: +4.3%
nDCG@5: +10.2%
MRR: -0.7%
```

说明：以上指标是在当前项目评测集上，相对固定 512 字符切分基线的提升。

## 快速开始（本地演示）

### 1. 安装依赖

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
```

### 2. 运行示例文档

```bash
python3 scripts/segment_file.py assets/title.md -o data/outputs/title_chunks.json
```

你会看到类似输出：
- `Loaded blocks: ...`
- `Generated chunks: ...`
- `Output written: ...`

### 3. 运行你自己的文档

```bash
python3 scripts/segment_file.py <输入文件> -o <输出JSON>
```

支持的输入格式：
- `.txt` / `.md` / `.markdown`
- `.docx`
- `.pdf`

常用参数示例：

```bash
python3 scripts/segment_file.py assets/title.md \
  --doc-id my_doc \
  --min-chars 300 \
  --target-chars 900 \
  --max-chars 1200 \
  --overlap-sentences 1 \
  -o data/outputs/my_doc_chunks.json
```

### 4. 运行测试与评测

```bash
python -m unittest backend.tests.test_segmenting backend.tests.test_query_retrieval backend.tests.test_keyword_extraction -v
python scripts/eval_rag.py
```

## 输出结构说明

CLI 输出 JSON 包含：
- `doc_id`
- `chunks[]`
  - `chunk_id`
  - `chunk_type`
  - `title_path`
  - `section_titles`
  - `content`
  - `summary`
  - `label`
  - `entity_tags`
  - `backlink`
  - `retrieval_text`
  - `char_count`
  - `source_refs`
  - `strategy_info`
  - `quality_flags`
- `statistics`（分段统计）
- `strategy`（本次分段参数）

## 代码架构（已实现部分）

### 端到端主流程

1. `scripts/segment_file.py`
   - 解析命令行参数
   - 构建 `SegmentConfig`
   - 调用 `load_document(...)`
   - 调用 `segment_blocks(...)`
   - 写入输出 JSON

2. `backend/app/services/document_loader/loader.py`
   - 按后缀分发读取器
   - 统一返回 `DocumentBlock[]`

3. `backend/app/services/segmenting/`
   - `parser.py`：纯文本逻辑分块（标题/表格/列表/代码）
   - `heading.py`：标题识别与层级估计
   - `splitter.py`：候选分段、embedding 语义边界、超长拆分、过短合并
   - `segmenter.py`：主流程编排，生成最终 chunk、质量标记与内容组织字段
   - `statistics.py`：统计指标与序列化
   - `models.py`：核心数据结构

4. `backend/app/services/segmenter.py`
   - 对外稳定导出：`segment_blocks` / `segment_text`

5. `backend/app/services/rag_store/`
   - SQLite 保存文档与 chunk 元数据
   - Chroma 保存向量并支持查询

6. `backend/app/services/evaluation/`
   - 固定长度基线与 Recall@k、Precision@k、nDCG、MRR 评测

## 已知限制

- 长表格目前优先整体保护，后续可按行组拆分并重复表头。
- 当前评测集规模较小，主要用于课程验收和回归对比。
- embedding 模型优先使用本地 Hugging Face 缓存；不可用时会回退到稳定字符 n-gram 向量。

## 目录说明（与演示相关）

- `assets/`：示例输入文档
- `data/outputs/`：CLI 输出目录
- `scripts/segment_file.py`：当前推荐入口
- `scripts/eval_rag.py`：智能分段与固定长度基线评测
- `scripts/tune_segmenting_params.py`：分段参数搜索
