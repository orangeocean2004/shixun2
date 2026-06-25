"""Evaluation dataset for RAG segmentation quality.

Each entry has a question whose answer is verifiably contained
in one or more specific chunks of the segmented document.
Ground truth is expressed as the expected answer text that
should appear in retrieved chunks.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class EvalQuestion:
    question: str
    """Natural-language query to send to the retrieval system."""

    answer_keywords: list[str]
    """Keywords that MUST appear in retrieved chunks for this to be correct.

    At least one keyword must match for the chunk to be considered relevant.
    """


@dataclass
class EvalDocument:
    doc_path: str
    """Path to the document file relative to project root."""

    doc_id: str
    """Stable identifier for this evaluation document."""

    questions: list[EvalQuestion] = field(default_factory=list)


# ── Dataset ──────────────────────────────────────────────

EVAL_DATASET: list[EvalDocument] = [
    EvalDocument(
        doc_path="assets/title.md",
        doc_id="eval_title",
        questions=[
            EvalQuestion(
                question="这个课题的名称是什么？",
                answer_keywords=["课题11", "面向RAG", "智能分段", "内容组织", "智能体"],
            ),
            EvalQuestion(
                question="分段策略中需要保护哪些特殊内容块？",
                answer_keywords=["表格", "公式", "代码", "整体成块", "不截断"],
            ),
            EvalQuestion(
                question="验收标准中不破句率和目标长度命中率的要求是多少？",
                answer_keywords=["不破句率", "100%", "目标长度区间命中率", "90%"],
            ),
            EvalQuestion(
                question="这个课题与朴素固定长度切分的区别是什么？",
                answer_keywords=["结构", "语义感知", "闭环评估", "下游检索"],
            ),
            EvalQuestion(
                question="课题要求交付哪些东西？",
                answer_keywords=["可运行", "分段智能体", "标准接口", "chunk序列", "对比实验"],
            ),
        ],
    ),
    EvalDocument(
        doc_path="assets/同类开源方案调研报告.docx",
        doc_id="eval_survey",
        questions=[
            EvalQuestion(
                question="调研报告分析了哪些开源分段工具？",
                answer_keywords=["LangChain", "LlamaIndex", "Unstructured", "Docling"],
            ),
            EvalQuestion(
                question="开源方案在语义分段方面有什么不足？",
                answer_keywords=["固定长度", "分隔符", "语义感知弱", "标题层级"],
            ),
            EvalQuestion(
                question="调研中提到了哪些检索评估指标？",
                answer_keywords=["Recall", "nDCG", "MRR", "命中率"],
            ),
            EvalQuestion(
                question="哪些项目支持多模态文档解析？",
                answer_keywords=["Docling", "Unstructured", "PDF", "图像"],
            ),
            EvalQuestion(
                question="报告中对RAGFlow的评价是什么？",
                answer_keywords=["RAGFlow", "元数据", "溯源", "chunk"],
            ),
        ],
    ),
    EvalDocument(
        doc_path="assets/开题报告_课题11_面向RAG的智能分段与内容组织智能体.docx",
        doc_id="eval_open_report",
        questions=[
            EvalQuestion(
                question="开题报告中描述的系统总体目标是什么？",
                answer_keywords=["设计并实现", "面向RAG", "智能分段", "内容组织", "智能体"],
            ),
            EvalQuestion(
                question="报告中提到了哪些技术难点？",
                answer_keywords=["语义完整", "边界不破坏", "长度可控", "检索指标", "闭环验证"],
            ),
            EvalQuestion(
                question="系统的验收标准是什么？",
                answer_keywords=["不破句率", "整体成块率", "命中率", "完整率"],
            ),
            EvalQuestion(
                question="技术方案中采用了什么架构？",
                answer_keywords=["FastAPI", "Vue", "Python", "前端", "后端"],
            ),
            EvalQuestion(
                question="报告中提到了哪些创新点或差异化优势？",
                answer_keywords=["结构感知", "语义感知", "闭环评估", "下游检索", "优化目标"],
            ),
        ],
    ),
]
