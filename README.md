# 课题11 — 面向 RAG 的智能分段与内容组织智能体

> **任务书定位**：专项能力智能体（被课题5"数据格式标准化转换智能体"调用）
> **难度**：中-高
> **核心目标**：把治理后口径统一的结构化全文，按结构/语义感知策略分段，为每个片段生成标签、摘要、实体标注与原文回链，并以下游检索指标闭环评估分段效果。

## 架构概览

```
文档上传 → Document Loader → Preprocessor → Segment Engine → Chunks
                                                    ↓
                                          ContentOrganizer
                                         (标签/摘要/实体/资产引用)
                                                    ↓
                                          RAG Store (Chroma + SQLite)
                                                    ↓
                                          REST API → Vue 3 Frontend
```

## 当前状态

### 已实现

**分段引擎** (`backend/app/services/segmenting/`)
- 结构/语义感知分段：标题边界优先 + embedding 语义边界 + 特殊块保护
- 长度控制：min/target/max 三级约束，递归拆分 + 自适应合并
- tiktoken 精确 token 计数 (cl100k_base)
- 语义边界判断：sentence-transformers MiniLM 优先，词频/字符相似度回退
- 来源锚点回链 (source_refs：block_id, page, metadata)
- 外置资产引用保留（图片/附件路径不丢失）
- 标题层级栈管理 + 跨标题合并抑制碎片化
- Metric chunk 识别（chunk_type="metric" + 检索增强文本）
- retrieval_text 与 content 分离（标题路径 + 关键词 + 正文拼接，增强检索召回）
- 图片提取与前端渲染（DOCX/PDF 内嵌图片 → [IMAGE: ...] 占位符 → 网页展示）
- 英文学术标题识别（Abstract/Keywords/Introduction/Conclusion 等）
- 分段质量统计（不破句率、表格成块率、长度命中率、回链完整率）

**内容组织** (`backend/app/services/organizer/`)
- 片段级关键词/主题标签：规则模式 (jieba TF-IDF) / LLM 模式 (DeepSeek)
- 片段级抽取式摘要：Lead-1 + TF-IDF 句子打分 / LLM 生成式摘要
- 正则实体识别：百分比/指标名/日期/机构/阈值/版本
- LLM 增强模式：配置 API Key 后自动升级，失败静默降级规则模式
- 文档级摘要生成

**LLM 集成** (`backend/app/core/config.py`)
- 配置 OPENAI_API_KEY + OPENAI_BASE_URL 即可启用
- RAG 问答：检索 chunk + LLM 生成回答 → `/api/query`
- QA 合成：基于 chunk 用 LLM 生成问答对 → `/api/synthesize-qa`
- 可答性校验（词级重叠）+ 忠实度校验（bigram N-gram）
- 前端 QA 合成标签页：一键生成 + 下载 JSONL

**文档加载** (`backend/app/services/document_loader/`)
- 多格式支持：.txt / .md / .docx / .pdf
- DOCX/PDF 图片提取与存储
- 统一结构化中间表示 (DocumentBlock)

**预处理** (`backend/app/services/preprocessing/` + `document_preprocessor.py`)
- 封面/目录去除
- 表格展平（单单元格正文表转段落）

**RAG 存储** (`backend/app/services/rag_store/`)
- Chroma 向量存储 (embedding-based)
- SQLite 元数据存储 (chunk 索引)
- 混合检索（语义 + 关键词重排）
- `POST /api/segment/upload` — 上传文档 → 分段 → 入库
- `POST /api/query` — 检索查询
- `GET /api/chunks/all` — 列出所有 chunk
- `GET /health` — 健康检查

**检索服务** (`backend/app/services/retrieval/`)
- TF-IDF 内存检索 (char n-gram 1~4)
- Embedding 语义检索 (MiniLM 384维 + 关键词重排)
- SemanticVectorStore 接口兼容层

**评估框架** (`backend/app/services/evaluation/`)
- 固定长度基线分段器 (512字符等长切分)
- IR 指标：Recall@k, Precision@k, nDCG@k, MRR
- EmbeddingRelevance 混合相关性判定（关键词 + embedding）
- Smart vs Baseline 头对头对比
- 标签准确率/摘要忠实度/实体精度评估 (`evaluator.py`)

**前端** (Vue 3 + Vite)
- 文档上传 + 分段配置面板 (ConfigPanel)
- 分段结果展示 (ChunkList)
- 统计指标面板 (MetricPanel)
- 检索查询面板 (RetrievalPanel)
- 实时 API 代理 (开发模式)

**脚本工具**
- `scripts/segment_file.py` — CLI 单文件分段
- `scripts/eval_rag.py` — RAG 分段评估（Smart vs Baseline）
- `scripts/human_eval_semantic.py` — 语义完整性人工评估工具
- `scripts/synthesize_qa_pairs.py` — 面向微调的 QA 对合成（进阶）
- `scripts/tune_segmenting_params.py` — 网格搜索参数调优
- `scripts/draw_architecture.py` — 系统架构图生成

### 评估数据集

3 个文档 × 15 个查询的标注评估数据集（`backend/tests/eval_dataset.py`）：
- `assets/title.md`
- `assets/同类开源方案调研报告.docx`
- `assets/开题报告_课题11_面向RAG的智能分段与内容组织智能体.docx`

### 验证结果

**分段质量**（已实现统计，待批量验证）：

| 指标 | 目标 | 当前代码状态 |
|------|------|-------------|
| 不破句率 | 100% | 已实现检测（statistics.py），title.md 实测 100% |
| 表格/公式/代码整体成块率 | ≥95% | 已实现检测（statistics.py），实测 100% |
| 目标长度区间命中率 | ≥90% | 已实现检测，title.md 实测 100% |
| 原文回链完整率 | 100% | 已实现检测，实测 100% |

**RAG 检索提升**（Smart vs 固定长度 Baseline，实测数据）：

| 指标 | 智能分段 | 固定基线 | 差值 |
|------|---------|---------|------|
| Recall@1 | 0.1669 | 0.1456 | +14.6% |
| Recall@3 | 0.4042 | 0.3005 | +34.5% |
| Recall@5 | 0.5915 | 0.4990 | +18.5% |
| Precision@5 | 0.6033 | 0.5233 | +15.3% |
| nDCG@5 | 0.7148 | 0.6026 | +18.6% |
| MRR | 0.7778 | 0.7500 | +3.7% |

> 当前参数搜索后默认配置为 `min_chars=180, target_chars=550, max_chars=800, heading_flush_min_chars=240, semantic_boundary_threshold=0.55, overlap_sentences=1`。`eval_rag.py` 实测 Recall@5 相对固定长度基线提升 +18.5%，达到任务书中 ≥10% 的目标。

**测试**：后端 27 个单元测试全部通过。

### 当前状态与待完成

| 项目 | 说明 |
|------|------|
| 检索提升达标 | 已完成：当前 Recall@5 +18.5%（目标 +10%），已通过 `eval_rag.py` 验证 |
| 前端依赖源 | 已修正：`package-lock.json` 使用公开 npm registry，避免依赖内网源 |
| 语义完整性人工评估 | `scripts/human_eval_semantic.py` 已就绪，待执行 |
| 标签准确率/摘要忠实度评测 | `evaluator.py` 已就绪，待实际运行评测 |
| QA 合成评测 | `synthesize_qa_pairs.py` 已就绪（需 API Key） |
| Docker/部署文档 | 未开始 |
| 正式技术报告 | 未开始 |

---

## 快速开始

### 环境要求

- Python ≥ 3.12
- Node.js ≥ 18（前端）
- Windows / macOS / Linux

### 1. 安装 Python 依赖

```bash
# 创建虚拟环境
python -m venv .venv

# 激活虚拟环境
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

# 安装依赖
pip install -r backend/requirements.txt
```

核心依赖：
- `fastapi` + `uvicorn` — Web 框架
- `pymupdf` — PDF 解析
- `python-docx` — DOCX 解析
- `chromadb` — 向量存储
- `jieba` — 中文分词
- `langchain` + `langchain-openai` — LLM 集成（可选）

### 2. 启动后端

```bash
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --reload
```

后端运行在 `http://127.0.0.1:8000`，自动生成 Swagger 文档：`http://127.0.0.1:8000/docs`

### 3. 启动前端

```bash
cd frontend
npm install
npm run dev
```

默认情况下，`npm install` 会使用本机配置的 npm registry。本项目的 `package-lock.json`
已使用公开 npm registry 生成；如果本机配置的镜像源或企业内网源解析失败，可临时使用
`npm install --registry=https://registry.npmjs.org/` 安装。

前端运行在 `http://127.0.0.1:5173`，通过 Vite proxy 转发 API 请求到后端。

### 4. CLI 分段（无需启动服务）

```bash
# 基本用法
python scripts/segment_file.py assets/title.md -o data/outputs/title_chunks.json

# 自定义参数
python scripts/segment_file.py assets/title.md \
  --doc-id my_doc \
  --min-chars 300 \
  --target-chars 900 \
  --max-chars 1200 \
  --overlap-sentences 1 \
  --clean-document \
  -o data/outputs/my_chunks.json
```

支持的输入格式：`.txt` / `.md` / `.docx` / `.pdf`

---

## API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/health` | 健康检查 |
| `POST` | `/api/segment/upload` | 上传文档 → 分段 → 入库。参数：`file` (UploadFile), `min_chars`, `target_chars`, `max_chars`, `overlap_sentences` |
| `POST` | `/api/query` | 检索查询。Body：`{"doc_id": "...", "query": "...", "top_k": 5}` |
| `GET` | `/api/chunks/all` | 列出所有已入库 chunk。参数：`?doc_id=...`（可选） |

### 配置 LLM 模式（可选）

设置环境变量后，内容组织自动升级为 LLM 模式：

```bash
export OPENAI_API_KEY="sk-xxx"
export OPENAI_BASE_URL="https://api.deepseek.com"  # DeepSeek 或其他兼容 API
```

---

## 输出结构

CLI 和 API 输出的 JSON 结构：

```json
{
  "doc_id": "title",
  "source_file": "assets/title.md",
  "block_count": 28,
  "chunks": [
    {
      "chunk_id": "title_chunk_0001",
      "chunk_type": "mixed",
      "title_path": ["1. 项目背景"],
      "content": "...",
      "char_count": 856,
      "source_refs": [{"block_id": 0, "page": 1}],
      "strategy_info": "heading_boundary",
      "quality_flags": ["contains_metric"],
      "labels": ["项目背景", "研究目标"],
      "summary": "...",
      "entities": [{"type": "percentage", "value": "85%"}]
    }
  ],
  "statistics": {
    "chunk_count": 4,
    "total_chars": "...",
    "avg_chars": "...",
    "target_range_hit_rate": 1.0,
    "table_code_formula_intact_rate": 1.0,
    "source_ref_completeness": 1.0
  },
  "strategy": {
    "min_chars": 300,
    "target_chars": 900,
    "max_chars": 1200,
    "overlap_sentences": 1
  }
}
```

---

## 目录结构

```
zhinengti/
├── backend/
│   ├── app/
│   │   ├── api/routes.py              # REST API 端点
│   │   ├── core/config.py             # 全局配置
│   │   ├── main.py                    # FastAPI 入口
│   │   ├── models/schemas.py          # Pydantic 数据模型
│   │   └── services/
│   │       ├── document_loader/       # 多格式文档加载 (txt/md/docx/pdf)
│   │       ├── document_preprocessor.py # 封面/目录去除
│   │       ├── segmenting/            # 核心分段引擎
│   │       │   ├── models.py          # 数据结构 (DocumentBlock, Chunk, SegmentConfig)
│   │       │   ├── parser.py          # 纯文本逻辑分块
│   │       │   ├── heading.py         # 标题识别与层级估计
│   │       │   ├── splitter.py        # 候选分段/超长拆分/过短合并
│   │       │   ├── segmenter.py       # 主流程编排
│   │       │   ├── enrichment.py      # 分段富化
│   │       │   ├── keyword_extraction.py # 关键词提取
│   │       │   └── statistics.py      # 统计指标
│   │       ├── segmenter.py           # 对外统一导出
│   │       ├── organizer.py           # 内容组织（打标/摘要/实体）
│   │       ├── model_client.py        # LLM 客户端（规则 + API 双模式）
│   │       ├── evaluator.py           # 标签/摘要/实体质量评估
│   │       ├── evaluation/            # RAG 评估框架
│   │       │   ├── baseline.py        # 固定长度基线分段器
│   │       │   └── metrics.py         # IR 指标 + 语义相关性判定
│   │       ├── retrieval/             # 检索后端
│   │       │   ├── tfidf_store.py     # TF-IDF 内存检索
│   │       │   ├── embedding_store.py # Embedding 语义检索
│   │       │   └── semantic_store.py  # 接口兼容层
│   │       ├── rag_store/             # RAG 持久化存储
│   │       │   ├── service.py         # 存储服务编排
│   │       │   ├── chroma_store.py    # Chroma 向量存储
│   │       │   └── sqlite_store.py    # SQLite 元数据
│   │       └── preprocessing/         # 文档预处理
│   │           └── cleaner.py         # 封面/目录/表格清洗
│   ├── tests/
│   │   ├── test_segmenting.py         # 分段引擎测试 (8 tests)
│   │   ├── test_keyword_extraction.py # 关键词提取测试
│   │   ├── test_query_retrieval.py    # 检索测试
│   │   └── eval_dataset.py            # 评估数据集 (3 docs × 15 queries)
│   └── requirements.txt
├── frontend/
│   └── src/
│       ├── App.vue                    # 根组件
│       ├── views/HomeView.vue         # 主页（含分步流程）
│       ├── components/
│       │   ├── ConfigPanel.vue        # 分段参数配置
│       │   ├── ChunkList.vue          # 分段结果列表
│       │   ├── MetricPanel.vue        # 统计指标展示
│       │   └── RetrievalPanel.vue     # 检索查询面板
│       ├── api/chunking.js            # API 封装
│       ├── stores/chunkStore.js       # Pinia 状态管理
│       └── router/index.js            # Vue Router
├── scripts/
│   ├── segment_file.py                # CLI 分段工具（主要入口）
│   ├── eval_rag.py                    # RAG 评估脚本
│   ├── human_eval_semantic.py         # 语义完整性人工评估
│   ├── synthesize_qa_pairs.py         # QA 对合成
│   ├── tune_segmenting_params.py      # 参数网格搜索
│   ├── draw_architecture.py           # 架构图生成
│   └── ai_chunking_agent_demo.py      # 早期实验脚本
├── assets/                            # 示例/测试文档
├── data/
│   ├── outputs/                       # CLI 输出目录
│   └── rag/                           # RAG 存储数据
├── pyproject.toml
└── CHANGELOG.md
```

---

## 任务书验收指标对照

| 指标 | 目标 | 当前 | 状态 | 说明 |
|------|------|------|------|------|
| 表格/公式/代码整体成块率 | ≥95% | 100% | 已实现 | statistics.py 已含检测 |
| 目标长度区间命中率 | ≥90% | 100% | 已实现 | statistics.py 已含检测 |
| 原文回链完整率 | 100% | 100% | 已实现 | statistics.py 已含检测 |
| 不破句率 | 100% | 已实现 | 已实现 | statistics.py 已含检测 |
| Recall@k/nDCG 提升 | ≥10% | **Recall@5 +18.5%，nDCG@5 +18.6%** | 已达标 | `eval_rag.py` 已通过 |
| 语义完整性（人工评估） | ≥85% | **未执行** | 待评测 | human_eval_semantic.py 已就绪 |
| 标签准确率 | ≥85% | **未评测** | 待评测 | evaluator.py 已就绪 |
| 摘要忠实度 | ≥90% | **未评测** | 待评测 | evaluator.py 已就绪 |
| QA 合成可答性 | ≥90% | **未评测** | 待评测 | synthesize_qa_pairs.py 已就绪 |
| QA 合成忠实度 | ≥90% | **未评测** | 待评测 | synthesize_qa_pairs.py 已就绪 |

**统计指标 5/5 已实现，检索提升已达标（Recall@5 +18.5% vs 目标 +10%），4 项生成质量指标仍待人工/LLM 辅助评测。**

---

## 已知限制

- 当前检索提升已达标，但评测集规模仍偏小，后续应扩充更多真实文档和问题以验证泛化稳定性
- LLM 生成式标签/摘要的评估方法（embedding 余弦相似度）对改写措辞天然低估
- `backend/app/services/rag_store/` 与 `backend/app/services/retrieval/` 存在功能重叠（均为检索），后续可整合
- 前端 RetrievalPanel 已添加到组件目录，但未集成到 HomeView
- 进阶 QA 合成依赖 LLM API，需配置 API Key
- 无 Docker 部署方案
