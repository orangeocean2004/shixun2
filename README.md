# 课题11 — 面向 RAG 的智能分段与内容组织智能体

> **任务书定位**：专项能力智能体  
> **核心目标**：把结构化全文按结构/语义感知策略分段，生成标签、摘要、实体标注，以下游检索指标闭环评测分段效果。

## 快速开始

### 1. 安装依赖

```bash
# Python 后端
pip install -r backend/requirements.txt

# 前端（可选）
cd frontend && npm install
```

### 2. 启动后端

```bash
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --reload
```

访问 `http://127.0.0.1:8000/docs` 查看 Swagger 文档。

### 3. 启动前端（可选）

```bash
cd frontend && npm run dev
```

前端运行在 `http://127.0.0.1:5173`。

### 4. CLI 分段（无需启动服务）

```bash
python scripts/segment_file.py assets/title.md -o data/outputs/title_chunks.json
```

### 5. 运行评测

```bash
# 三策略对比
python scripts/eval_rag.py

# 生成评测报告 + badcase 分析
python scripts/eval_report.py
```

---

## API 端点（11 个）

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/health` | 健康检查 |
| `GET` | `/api/strategies` | 列出可用分段策略、关键词策略和默认配置 |
| `POST` | `/api/segment/upload` | 上传文档 → 智能分段 → 入库 |
| `POST` | `/api/organize` | 对已有 chunks 独立执行内容组织（标签/摘要/实体） |
| `POST` | `/api/evaluate` | 三策略对比评测，返回 Recall@k/nDCG/MRR |
| `POST` | `/api/query` | 检索查询 + LLM 问答 |
| `GET` | `/api/chunks/all` | 获取指定文档的所有 chunk |
| `POST` | `/api/synthesize-qa` | 基于 chunk 生成 QA 对 |
| `GET` | `/api/settings/model` | 获取 LLM 配置 |
| `PUT` | `/api/settings/model` | 更新 LLM 配置 |
| `GET` | `/api/images/{doc_id}/{filename}` | 获取文档中提取的图片 |

---

## 评测结果

### 三策略对比（Smart vs Heading vs Fixed）

| 指标 | Smart | Heading | Fixed | S vs H | S vs F |
|------|-------|---------|-------|--------|--------|
| Recall@1 | 0.1669 | 0.1546 | 0.1456 | +8.0% | +14.6% |
| Recall@3 | 0.4042 | 0.4181 | 0.3005 | -3.3% | +34.5% |
| Recall@5 | 0.5915 | 0.5706 | 0.4990 | +3.7% | **+18.5%** |
| Precision@5 | 0.6033 | 0.5200 | 0.5233 | +16.0% | +15.3% |
| nDCG@5 | 0.7148 | 0.6297 | 0.6026 | +13.5% | +18.6% |
| MRR | 0.7778 | 0.6833 | 0.7500 | +13.8% | +3.7% |

- **结构信息贡献** (Heading vs Fixed): +14.4%
- **语义边界增量** (Smart vs Heading): +3.7%  
- **总提升** (Smart vs Fixed): **+18.5%** ✅ 超过 +10% 目标

详细报告：`data/outputs/evaluation_report.md`

---

## 架构

```
文档上传 → Document Loader → Preprocessor → Segment Engine ──→ Chunks
  (.txt/.md/           (.docx/pdf         (heading/semantic/     (title_path,
   .docx/.pdf)          清洗/展平)          special-block/         source_refs,
                                           overlap)               quality_flags)
                                         │
                                    ContentOrganizer
                                    (标签/摘要/实体)
                                         │
                                    RAG Store
                                    (Chroma + SQLite)
                                         │
                                    REST API ←→ Vue 3 前端
```

---

## 目录结构

```
├── backend/
│   ├── app/
│   │   ├── api/routes.py              ← 11 个 HTTP 端点
│   │   ├── core/
│   │   │   ├── config.py              ← 全局配置常量
│   │   │   └── model_settings.py      ← LLM 配置持久化
│   │   ├── main.py                    ← FastAPI 入口
│   │   ├── models/schemas.py          ← Pydantic 数据模型
│   │   └── services/
│   │       ├── document_loader/       ← 多格式文档解析 (txt/md/docx/pdf)
│   │       ├── segmenting/            ← 核心分段引擎
│   │       │   ├── models.py          ← 数据结构 (DocumentBlock, Chunk, SegmentConfig)
│   │       │   ├── parser.py          ← 纯文本逻辑分块（代码块/表格/图片检测）
│   │       │   ├── heading.py         ← 标题识别与层级树
│   │       │   ├── splitter.py        ← 候选分段 / 超长拆分 / 过短合并
│   │       │   ├── segmenter.py       ← 主流程编排
│   │       │   ├── enrichment.py      ← 标签/摘要/实体富化
│   │       │   ├── keyword_extraction.py ← 关键词提取 (jieba TF-IDF / 频率)
│   │       │   └── statistics.py      ← 分段质量统计
│   │       ├── organizer/             ← 内容组织 (打标/摘要/实体)
│   │       ├── evaluation/            ← 评测框架
│   │       │   ├── baseline.py        ← fixed_length / heading_based 基线
│   │       │   └── metrics.py         ← Recall@k / nDCG / MRR / 语义相关性判定
│   │       ├── retrieval/             ← 检索后端
│   │       │   ├── embedding.py       ← 嵌入编码器 (MiniLM / TF-IDF fallback)
│   │       │   ├── embedding_store.py ← 向量检索 (numpy + cosine)
│   │       │   ├── semantic_store.py  ← 语义检索接口
│   │       │   └── tfidf_store.py     ← TF-IDF 检索
│   │       ├── rag_store/             ← RAG 持久化存储 (Chroma + SQLite)
│   │       ├── preprocessing/         ← 文档预处理 (封面/目录/表格清洗)
│   │       └── qa_quality/            ← QA 质量校验 (可答性 + 忠实度)
│   └── tests/
│       ├── eval_dataset.py            ← 评测数据集 (3篇文档 × 15个问题)
│       ├── test_segmenting.py         ← 分段引擎测试 (10 tests)
│       └── ...
├── frontend/src/                      ← Vue 3 前端
│   ├── views/HomeView.vue             ← 主页 (上传/分段/检索)
│   └── components/                    ← ChunkList / ConfigPanel / MetricPanel / RetrievalPanel
├── scripts/
│   ├── segment_file.py                ← CLI 单文件分段
│   ├── eval_rag.py                    ← 三策略对比评测
│   ├── eval_report.py                 ← 评测报告 + badcase 分析生成
│   ├── tune_segmenting_params.py      ← 参数网格搜索
│   └── synthesize_qa_pairs.py         ← QA 对合成
├── assets/                            ← 样例文档 (2篇 docx + 1篇 md)
├── data/
│   ├── outputs/                       ← 输出目录 (评测报告/chunks/QA对)
│   └── benchmarks/docs/               ← 评测文档集 (10篇中英文)
│       ├── en/                        ← arXiv论文 + SEC年报
│       └── zh/                        ← 中文教材 + 技术文档
└── requirements.txt
```

---

## M4 里程碑状态（7月3日截止）

| 交付物 | 状态 |
|--------|------|
| fixed_length baseline | ✅ |
| heading_based baseline | ✅ |
| 三策略对比评测 | ✅ `scripts/eval_rag.py` |
| Recall@k / nDCG / MRR | ✅ Recall@5 +18.5% |
| /segment /organize /evaluate /strategies | ✅ 4 个 API 全部到齐 |
| 对比报告 | ✅ `data/outputs/evaluation_report.md` |
| Badcase 分析 | ✅ 16 个 badcase 逐项分析 |
| 评测文档集 | ✅ 10 篇中英文文档 |

---

## 配置 LLM（可选）

在前端设置页或通过 API 配置：

```json
{
  "OPENAI_API_KEY": "sk-xxx",
  "OPENAI_BASE_URL": "https://api.deepseek.com",
  "LLM_MODEL": "deepseek-chat"
}
```

配置后内容组织自动升级为 LLM 模式，QA 合成和 RAG 问答也可使用。

## 已知限制

- 评测数据集规模偏小（3 篇文档），后续应扩充
- LLM 生成式标签/摘要的评估对改写措辞天然低估
- 无 Docker 部署方案
- 进阶 QA 合成依赖 LLM API
