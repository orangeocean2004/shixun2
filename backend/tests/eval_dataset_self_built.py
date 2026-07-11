# -*- coding: utf-8 -*-
"""Auto-generated self-built evaluation dataset."""

from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class EvalQuestion:
    question: str
    answer_keywords: list[str]


@dataclass
class EvalDocument:
    doc_path: str
    doc_id: str
    questions: list[EvalQuestion] = field(default_factory=list)


EVAL_DATASET: list[EvalDocument] = [
    EvalDocument(
        doc_path=r"C:\Users\yh200\Desktop\zhinengti\assets\title.md",
        doc_id="eval_title",
        questions=[
            EvalQuestion(
                question="在面向RAG的智能分段中，为什么不能使用朴素的固定长度切分？",
                answer_keywords=["固定长度切分", "语义", "噪声", "长度限制", "召回"],
            ),
            EvalQuestion(
                question="本课题中，分段智能体需要为每个片段生成哪些内容组织信息？",
                answer_keywords=["标签", "摘要", "实体标签", "原文回链"],
            ),
            EvalQuestion(
                question="本课题与开源分段方案的主要区别是什么？",
                answer_keywords=["结构/语义感知", "下游检索指标", "闭环评估", "优化目标"],
            ),
            EvalQuestion(
                question="验收标准中，对分段边界质量有哪些具体指标要求？",
                answer_keywords=["不破句率", "表格/公式/代码整体成块率", "目标长度区间命中率"],
            ),
        ],
    ),
    EvalDocument(
        doc_path=r"C:\Users\yh200\Desktop\zhinengti\data\benchmarks\docs\zh\d2l_zh_intro.md",
        doc_id="eval_d2l_intro",
        questions=[
            EvalQuestion(
                question="机器学习中的“学习”过程通常包括哪些步骤？",
                answer_keywords=["随机初始化参数", "数据样本", "调整参数", "重复步骤"],
            ),
            EvalQuestion(
                question="在机器学习中，什么是“过拟合”？",
                answer_keywords=["训练集", "表现良好", "推广", "测试集", "过拟合"],
            ),
            EvalQuestion(
                question="监督学习中，回归问题的主要特点是什么？",
                answer_keywords=["回归", "标签", "数值", "预测"],
            ),
            EvalQuestion(
                question="为什么在机器学习中，仅仅拥有海量的数据是不够的？",
                answer_keywords=["海量的数据", "正确的数据", "错误", "特征", "预测"],
            ),
        ],
    ),
    EvalDocument(
        doc_path=r"C:\Users\yh200\Desktop\zhinengti\data\benchmarks\docs\zh\vue3_guide_intro.txt",
        doc_id="eval_vue3",
        questions=[
            EvalQuestion(
                question="Vue 2 于何时停止维护？",
                answer_keywords=["Vue 2", "2023 年 12 月 31 日", "停止维护"],
            ),
            EvalQuestion(
                question="Vue 的两个核心功能是什么？",
                answer_keywords=["声明式渲染", "响应性"],
            ),
            EvalQuestion(
                question="Vue 的单文件组件将哪三部分封装在同一个文件里？",
                answer_keywords=["逻辑", "模板", "样式"],
            ),
            EvalQuestion(
                question="对于打算用 Vue 构建完整单页应用的用户，文档推荐使用哪种 API 风格？",
                answer_keywords=["组合式 API", "单文件组件"],
            ),
        ],
    ),
    EvalDocument(
        doc_path=r"C:\Users\yh200\Desktop\zhinengti\data\benchmarks\docs\zh\rust_zh_ownership.txt",
        doc_id="eval_rust",
        questions=[
            EvalQuestion(
                question="Rust 的所有权系统是如何管理内存的？",
                answer_keywords=["所有权", "编译器", "编译时", "规则", "检查"],
            ),
            EvalQuestion(
                question="栈和堆在内存结构上有什么主要区别？",
                answer_keywords=["栈", "堆", "后进先出", "指针", "分配"],
            ),
            EvalQuestion(
                question="Rust 的所有权规则中，值在离开作用域后会发生什么？",
                answer_keywords=["所有者", "作用域", "丢弃", "drop", "离开"],
            ),
            EvalQuestion(
                question="在 Rust 中，String 类型的变量赋值时为什么会导致移动而非浅拷贝？",
                answer_keywords=["移动", "浅拷贝", "无效", "二次释放", "指针"],
            ),
        ],
    ),
    EvalDocument(
        doc_path=r"C:\Users\yh200\Desktop\zhinengti\data\benchmarks\docs\zh\dbgpt_readme.md",
        doc_id="eval_dbgpt",
        questions=[
            EvalQuestion(
                question="DB-GPT 是什么类型的软件？",
                answer_keywords=["开源", "Agentic AI", "数据分析", "智能助手"],
            ),
            EvalQuestion(
                question="DB-GPT 可以在哪些环境中安全执行分析任务？",
                answer_keywords=["沙箱环境", "安全执行", "隔离环境"],
            ),
            EvalQuestion(
                question="DB-GPT 支持哪些数据源连接？",
                answer_keywords=["数据库", "CSV", "Excel", "数仓", "知识库", "文档"],
            ),
            EvalQuestion(
                question="如何通过一键安装脚本启动 DB-GPT？",
                answer_keywords=["curl", "install.sh", "bash", "profile", "API Key"],
            ),
        ],
    ),
    EvalDocument(
        doc_path=r"C:\Users\yh200\Desktop\zhinengti\data\benchmarks\docs\zh\paddleocr_readme.md",
        doc_id="eval_paddleocr",
        questions=[
            EvalQuestion(
                question="PaddleOCR的许可证是什么？",
                answer_keywords=["Apache", "2", "license"],
            ),
            EvalQuestion(
                question="PP-OCRv3中文超轻量模型的推荐场景是什么？",
                answer_keywords=["移动端", "服务器端", "PP-OCRv3"],
            ),
            EvalQuestion(
                question="2022年8月发布的PP-StructureV2新增了哪些功能？",
                answer_keywords=["版面复原", "PDF转Word", "PP-StructureV2"],
            ),
            EvalQuestion(
                question="如何加入PaddleOCR开源社区？",
                answer_keywords=["微信", "扫描二维码", "填写问卷"],
            ),
        ],
    ),
    EvalDocument(
        doc_path=r"C:\Users\yh200\Desktop\zhinengti\data\benchmarks\docs\zh\markdown_zh_guide.txt",
        doc_id="eval_markdown",
        questions=[
            EvalQuestion(
                question="GitHub Flavored Markdown 的简称是什么？",
                answer_keywords=["GitHub Flavored Markdown", "GFM"],
            ),
            EvalQuestion(
                question="在Markdown中，如何实现文字高亮？",
                answer_keywords=["文字高亮", "反引号"],
            ),
            EvalQuestion(
                question="在Markdown表格中，如何指定列的对齐方式？",
                answer_keywords=["表格", "对齐", "左对齐", "居中", "右对齐"],
            ),
            EvalQuestion(
                question="在Markdown中，如何创建复选框列表？",
                answer_keywords=["复选框列表", "- [x]", "- [ ]"],
            ),
        ],
    ),
    EvalDocument(
        doc_path=r"C:\Users\yh200\Desktop\zhinengti\data\benchmarks\docs\zh\react_zh_learn.txt",
        doc_id="eval_react",
        questions=[
            EvalQuestion(
                question="React 组件本质上是什么？",
                answer_keywords=["React 组件", "JavaScript 函数", "标签"],
            ),
            EvalQuestion(
                question="在 JSX 中，如何为 JavaScript 开辟通道以使用动态属性？",
                answer_keywords=["JSX", "花括号", "动态属性"],
            ),
            EvalQuestion(
                question="React 组件之间通过什么进行通讯？",
                answer_keywords=["React 组件", "props", "通讯"],
            ),
            EvalQuestion(
                question="在渲染列表时，为什么需要为每个元素指定 key？",
                answer_keywords=["渲染列表", "key", "跟踪", "位置"],
            ),
        ],
    ),
]
