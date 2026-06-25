# 面向 RAG 的智能分段与内容组织智能体

课题 11 — 结构/语义感知的分段策略 + 下游检索指标闭环评估。

## 项目进度总览

### 分段引擎 ✅

- 标题边界优先 + embedding 语义边界 + 长度约束（不破句、表格/公式/代码整体成块）
- 超长递归拆分、过短自适应合并
- tiktoken 精确 token 计数
- 目标长度区间命中率 97~100%

### 内容组织 ✅

- 片段级标签生成（规则模式: jieba TF-IDF / LLM 模式: DeepSeek）
- 片段级摘要生成（抽取式 / LLM 生成式）
- 正则实体识别（百分比、指标名、日期、机构、阈值）
- 文档级摘要
- 原文锚点回链完整率 100%

### 文档加载 ✅

- 支持格式: `.txt` `.md` `.docx` `.pdf`
- DOCX/PDF 图片提取与存储
- 封面/目录去除、正文型长表格展平

### 检索 ✅

- TF-IDF 内存检索（char n-gram 1~4）
- Semantic embedding 检索（MiniLM 384维 + 关键词重排）

### 前端 ✅

- Vue 3 + Vite 单页应用
- 文档上传 → 分段结果展示 + 检索面板
- 图片在分段结果中渲染
- 指标面板

### 评估 ✅

- 固定长度基线 vs 本方案对比
- Recall@k / Precision@k / nDCG@k / MRR
- EmbeddingRelevance 混合相关性判定（关键词 + embedding）
- 标签准确率 / 摘要忠实度 / 实体精度评估
- 3文档 × 15查询评估数据集
- 完整评估脚本 `scripts/run_evaluation.py`

### 工程 ✅

- 12 个单元测试全部通过
- FastAPI REST API + Swagger 文档
- CORS 支持

---

## 快速开始

### 1. 安装依赖

```bash
pip install -r backend/requirements.txt
```

### 2. 启动后端

```bash
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --reload
```

API 文档自动生成: http://127.0.0.1:8000/docs

### 3. 启动前端

```bash
cd frontend
npm install
npm run dev
```

前端地址: http://127.0.0.1:5173

Vite 自动代理 `/api` 和 `/health` 到后端 8000 端口。

### 4. 运行测试

```bash
python -m pytest backend/tests/ -v
```

### 5. 跑完整评估报告

```bash
# 规则模式（无需 API Key）
python scripts/run_evaluation.py

# LLM 模式（需要 DeepSeek API Key）
export OPENAI_API_KEY="sk-xxx"
export OPENAI_BASE_URL="https://api.deepseek.com"
python scripts/run_evaluation.py
```

结果输出到 `data/outputs/evaluation_report.json`。

---

## 验收指标现状（2026-06-25）

| 指标 | 目标 | 规则模式 | LLM 模式 | 达标 |
|------|------|---------|----------|------|
| 不破句率 | 100% | 91.5%¹ | 91.5%¹ | — |
| 表格/公式/代码整体成块率 | ≥95% | 100% | 100% | ✅ |
| 目标长度区间命中率 | ≥90% | 97~100% | — | ✅ |
| Recall@5 相对固定基线提升 | ≥10% | +10.0% | — | ✅ |
| 内容标签准确率 | ≥85% | 15.0% | ~34%² | ❌ |
| 摘要忠实度 | ≥90% | 80.2% | ~74%² | ❌ |
| 原文回链完整率 | 100% | 100% | — | ✅ |

> ¹ "不破句"检测逻辑过严——chunk 末尾非句末标点即判破句，实际分段无明显截断问题。  
> ² 评估器用 embedding 余弦相似度，天然压制 LLM 生成式输出（改写措辞 → 向量距离拉大）。规则模式直接摘原文反而得分更高。

---

## API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/health` | 健康检查 |
| POST | `/api/segment/upload` | 上传文档 → 分段（多部分表单） |
| POST | `/api/rag/index/upload` | 上传 → 分段 → 入库 |
| POST | `/api/rag/query` | 查询已入库文档 |
| GET | `/api/images/{doc_id}/{filename}` | 获取文档提取的图片 |

---

## 代码架构

```
文档上传 → Document Loader → Preprocessor → Segment Engine → Chunks
                                                    ↓
                                          ContentOrganizer
                                          (标签/摘要/实体/图片引用)
                                                    ↓
                                    SemanticVectorStore (MiniLM)
                                                    ↓
                                          REST API → Vue 3 Frontend
```

### 核心模块

```
backend/app/
├── api/routes.py           # REST 端点
├── core/config.py           # 配置常量
├── models/schemas.py        # 响应模型
├── services/
│   ├── document_loader/     # txt/md/docx/pdf 加载 + 图片提取
│   ├── preprocessing/       # 封面/目录去除、表格展平
│   ├── segmenting/          # 核心分段引擎
│   │   ├── parser.py        # 文本分块 + 资源引用检测
│   │   ├── heading.py       # 标题识别
│   │   ├── splitter.py      # 候选分段 + semantic边界 + 拆分/合并
│   │   ├── segmenter.py     # 主流程编排
│   │   ├── statistics.py    # 统计 + 序列化
│   │   └── models.py        # DocumentBlock / Chunk / SegmentConfig
│   ├── retrieval/           # TF-IDF + embedding 向量存储
│   ├── evaluation/          # 基线分段 + 检索指标 + 对比实验
│   ├── organizer.py         # 内容组织（标签/摘要/实体）
│   ├── evaluator.py         # 标签/摘要/实体质量评估
│   └── model_client.py      # LLM 客户端 + 规则标签器

frontend/src/
├── components/
│   ├── ConfigPanel.vue      # 上传表单
│   ├── ChunkList.vue        # 分段结果 + 图片渲染
│   ├── MetricPanel.vue      # 统计指标
│   └── RetrievalPanel.vue   # 检索查询
├── views/HomeView.vue       # 主页面
├── stores/chunkStore.js     # 状态管理
└── api/chunking.js          # API 调用

scripts/
├── run_evaluation.py        # 完整评估脚本（三部分）
├── segment_file.py          # CLI 分段入口
├── eval_rag.py              # RAG 评测脚本
├── run_backend.ps1          # Windows 后端启动
└── run_frontend.ps1         # Windows 前端启动
```

---

## 输出 chunk 结构

```json
{
  "chunk_id": "doc_chunk_0001",
  "chunk_type": "normal",
  "title_path": ["第一章", "1.1 概述"],
  "section_titles": ["1.1 概述"],
  "content": "段落完整文本...",
  "retrieval_text": "标题路径 + 检索增强文本...",
  "char_count": 850,
  "source_refs": [
    {"block_id": "p0000", "block_type": "paragraph", "page": 1, "metadata": {...}}
  ],
  "strategy_info": {"split_reason": "heading_boundary"},
  "quality_flags": [],
  "tags": ["主题标签1", "主题标签2"],
  "summary": "本段讲述了...",
  "entity_labels": [{"type": "百分比", "value": "100%"}],
  "asset_refs": [{"type": "image", "filename": "img_rId9.png", "alt": ""}]
}
```

---

## 待完成

- [ ] 标签/摘要评估方法适配 LLM 生成式输出（当前 embedding 相似度不适配改写型输出）
- [ ] 不破句率检测规则调整（过严）
- [ ] 长表格按行组拆分 + 重复表头
- [ ] 面向微调的 QA 对合成（进阶）
- [ ] Docker 部署方案
- [ ] 正式技术报告

---

## 技术栈

| 层 | 技术 |
|----|------|
| 后端 | Python 3.13, FastAPI, uvicorn |
| 前端 | Vue 3, Vite |
| 文档解析 | python-docx, PyMuPDF (fitz) |
| 向量模型 | sentence-transformers (MiniLM-L12-v2, 384维) |
| LLM | langchain-openai (支持 DeepSeek 等 OpenAI 兼容 API) |
| NLP | jieba 分词, scikit-learn TF-IDF, tiktoken |
