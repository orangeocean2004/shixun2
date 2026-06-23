# 面向 RAG 的智能分段 Demo

这是一个以“结构/语义感知分段”为核心的课程项目脚手架。

当前已经可运行的主路径是 `scripts/segment_file.py`，它会：
- 读取文档（`.md/.txt/.docx/.pdf`）
- 解析为统一的文档块（`DocumentBlock`）
- 按标题边界与长度约束进行分段
- 输出带回链与统计信息的 JSON

## 当前状态

- ✅ 已实现并可运行：Python CLI 分段流程
- ✅ 已实现：文本/DOCX/PDF 读取器
- ✅ 已实现：分段策略（标题感知、特殊块保护、超长拆分、过短合并、质量标记）
- 🚧 FastAPI 与前端目录已创建，但核心文件仍是占位

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

## 输出结构说明

CLI 输出 JSON 包含：
- `doc_id`
- `chunks[]`
  - `chunk_id`
  - `chunk_type`
  - `title_path`
  - `content`
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
   - `splitter.py`：候选分段、超长拆分、过短合并
   - `segmenter.py`：主流程编排，生成最终 chunk 与质量标记
   - `statistics.py`：统计指标与序列化
   - `models.py`：核心数据结构

4. `backend/app/services/segmenter.py`
   - 对外稳定导出：`segment_blocks` / `segment_text`

## 已知限制

- `backend/app/main.py`、`backend/app/api/routes.py`、`frontend/` 目前仍是占位内容。
- `backend/tests/` 还没有测试用例。
- 当前长度控制以字符数近似 token 数，后续可替换为 tokenizer 统计。

## 目录说明（与演示相关）

- `assets/`：示例输入文档
- `data/outputs/`：CLI 输出目录
- `scripts/segment_file.py`：当前推荐入口
