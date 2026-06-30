"""生成系统架构图 PNG"""
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
import numpy as np

fig, ax = plt.subplots(1, 1, figsize=(18, 10))
ax.set_xlim(0, 18)
ax.set_ylim(0, 10)
ax.axis('off')

# 颜色方案
C_INPUT = '#E3F2FD'    # 浅蓝 - 输入
C_PROCESS = '#E8F5E9'   # 浅绿 - 处理
C_OUTPUT = '#FFF3E0'    # 浅橙 - 输出
C_EVAL = '#F3E5F5'      # 浅紫 - 评估
C_BORDER = '#37474F'    # 深灰边框
C_ARROW = '#546E7A'     # 箭头色

def draw_box(ax, x, y, w, h, color, border_color, text='', sub_lines=None, title=None, title_color='#1565C0'):
    """画一个圆角矩形框"""
    box = FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.08",
                          facecolor=color, edgecolor=border_color, linewidth=1.5, alpha=0.95)
    ax.add_patch(box)
    if title:
        ax.text(x + w/2, y + h - 0.25, title, ha='center', va='top',
                fontsize=9, fontweight='bold', color=title_color, family='sans-serif')
    if sub_lines:
        start_y = y + h - 0.55 if title else y + h - 0.2
        for i, line in enumerate(sub_lines):
            ax.text(x + 0.2, start_y - i * 0.28, line, ha='left', va='top',
                    fontsize=6.5, color='#424242', family='sans-serif')

def draw_arrow(ax, x1, y1, x2, y2, color=C_ARROW):
    """画箭头"""
    ax.annotate('', xy=(x2, y2), xytext=(x1, y1),
                arrowprops=dict(arrowstyle='->', color=color, lw=1.5,
                               connectionstyle='arc3,rad=0'))

# === 大外框 ===
outer = FancyBboxPatch((0.3, 0.3), 17.4, 9.2, boxstyle="round,pad=0.15",
                        facecolor='#FAFAFA', edgecolor='#BDBDBD', linewidth=1.5, linestyle='--')
ax.add_patch(outer)
ax.text(9, 9.35, '课题11  智能分段与内容组织智能体', ha='center', va='center',
        fontsize=14, fontweight='bold', color='#1A237E', family='sans-serif')

# === 输入层 (左) ===
ax.text(1.6, 8.8, '输入层', ha='center', fontsize=9, fontweight='bold', color='#1565C0')
draw_box(ax, 0.6, 6.8, 2.0, 1.7, '#BBDEFB', '#1565C0', title='Document Loader',
         sub_lines=['python-docx / PyMuPDF', '.txt  .md  .docx  .pdf', '图片提取 & 表格展平'])

# === 处理层 (中) ===
ax.text(9, 8.8, '处理层', ha='center', fontsize=9, fontweight='bold', color='#2E7D32')

draw_box(ax, 3.2, 6.8, 2.8, 1.7, '#C8E6C9', '#2E7D32', title='Preprocessor',
         sub_lines=['封面/目录去除', '正文型长表格展平', '空白段落清洗'])

draw_box(ax, 6.6, 6.8, 4.8, 1.7, '#C8E6C9', '#2E7D32', title='Segment Engine',
         sub_lines=['标题边界优先  |  语义边界检测', '长度约束控制  |  特殊块保护', '过长拆分 / 过短合并 / 重平衡'])

draw_box(ax, 3.2, 4.5, 2.8, 1.7, '#C8E6C9', '#2E7D32', title='Content Organizer',
         sub_lines=['规则: jieba TF-IDF + 抽取式摘要', 'LLM: DeepSeek 生成标签/摘要', '实体识别 + 资产引用保留'])

draw_box(ax, 6.6, 4.5, 4.8, 1.7, '#C8E6C9', '#2E7D32', title='Vector Store',
         sub_lines=['MiniLM-L12-v2  384维语义嵌入', 'TF-IDF char-n-gram 1~4 关键词', '语义检索 + 关键词重排'])

# === 输出层 (右) ===
ax.text(16.4, 8.8, '输出层', ha='center', fontsize=9, fontweight='bold', color='#E65100')

draw_box(ax, 14.2, 6.8, 4.4, 1.7, '#FFE0B2', '#E65100', title='HTTP API (FastAPI)',
         sub_lines=['GET  /health  POST  /segment/upload', 'POST /rag/index/upload  /rag/query', 'GET  /images/{doc_id}/{filename}'])

draw_box(ax, 14.2, 4.5, 4.4, 1.7, '#FFE0B2', '#E65100', title='Vue 3 前端 (Vite)',
         sub_lines=['文档上传  |  分段结果展示', '图片渲染  |  检索面板', '指标面板: 统计 + 策略'])

# === CLI 工具 ===
draw_box(ax, 8.5, 1.6, 7.0, 2.2, '#ECEFF1', '#607D8B', title='CLI 工具脚本',
         sub_lines=['segment_file.py      命令行分段入口', 'run_evaluation.py    完整评估 → JSON报告',
                    'human_eval_semantic.py  人工评估工具', 'synthesize_qa_pairs.py  QA对合成'])

# === 评估层 (底) ===
ax.text(9, 1.3, '评估层', ha='center', fontsize=9, fontweight='bold', color='#7B1FA2')
draw_box(ax, 0.6, 0.5, 7.5, 0.7, '#F3E5F5', '#7B1FA2')
ax.text(4.35, 0.85, '内容组织评估: 标签准确率 / 摘要忠实度 / 实体精度 (LLM-as-judge)',
        ha='center', va='center', fontsize=6.5, color='#424242')
draw_box(ax, 8.5, 0.5, 4.5, 0.7, '#F3E5F5', '#7B1FA2')
ax.text(10.75, 0.85, '检索对比: Smart vs Baseline',
        ha='center', va='center', fontsize=6.5, color='#424242')
draw_box(ax, 13.3, 0.5, 4.5, 0.7, '#F3E5F5', '#7B1FA2')
ax.text(15.55, 0.85, '边界质量: 不破句率 / 成块率',
        ha='center', va='center', fontsize=6.5, color='#424242')

# === 箭头 ===
# 输入到预处理
draw_arrow(ax, 2.6, 7.65, 3.2, 7.65)
# 预处理到分段引擎
draw_arrow(ax, 6.0, 7.65, 6.6, 7.65)
# 分段引擎到内容组织 (偏左)
draw_arrow(ax, 7.0, 6.8, 4.6, 6.2)
# 分段引擎到向量存储 (偏右)
draw_arrow(ax, 11.0, 6.8, 9.0, 6.2)
# 内容组织到向量存储
draw_arrow(ax, 6.0, 4.5, 6.6, 4.5)
# 处理到 API
draw_arrow(ax, 11.4, 7.65, 14.2, 7.65)
# 处理到前端
draw_arrow(ax, 11.4, 6.0, 14.2, 5.35)
# API 到 评估
draw_arrow(ax, 15.0, 6.8, 15.0, 1.2)
# 向量到 CLI
draw_arrow(ax, 9.0, 4.5, 9.0, 3.8)

# === 图例 ===
legend_y = 9.5
ax.text(12.5, legend_y, '文档格式', fontsize=6, color='#1565C0', fontweight='bold')
ax.text(13.5, legend_y, '本地模型', fontsize=6, color='#2E7D32', fontweight='bold')
ax.text(14.5, legend_y, '远程 LLM', fontsize=6, color='#E65100', fontweight='bold')

plt.tight_layout(pad=0.5)
plt.savefig('data/outputs/architecture.png', dpi=200, bbox_inches='tight',
            facecolor='white', edgecolor='none')
plt.close()
print('Architecture diagram saved: data/outputs/architecture.png')
