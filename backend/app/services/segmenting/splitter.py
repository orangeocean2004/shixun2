from __future__ import annotations

import re
from collections import Counter
from typing import Any

from .heading import heading_level, normalize_heading
from .models import CandidateChunk, DocumentBlock, SegmentConfig


SENTENCE_PATTERN = re.compile(r"[^。！？!?；;.\n]+[。！？!?；;.]?")
TOKEN_PATTERN = re.compile(r"[\u4e00-\u9fff]|[A-Za-z0-9_]+|[^\s]")


def build_candidate_chunks(
    blocks: list[DocumentBlock],
    config: SegmentConfig,
) -> list[CandidateChunk]:
    """把结构化 block 序列变成候选 chunk。

    这里尽量保留标题上下文，同时在块级阶段做三件事：
    1. 语义变化明显时提前收束当前 chunk
    2. 超长普通块按句子拆分
    3. 表格、公式、代码保持整体成块
    """

    candidates: list[CandidateChunk] = []
    title_stack: list[tuple[int, str]] = []
    current_blocks: list[DocumentBlock] = []
    current_title_path: list[str] = []
    current_heading_block: DocumentBlock | None = None

    def flush_current(split_reason: str) -> None:
        nonlocal current_blocks
        if not current_blocks:
            return
        if is_heading_only(current_blocks):
            current_blocks = []
            return
        candidates.append(make_candidate(current_blocks, current_title_path, split_reason))
        current_blocks = []

    for block in blocks:
        if block.block_type == "heading":
            # 仅当已累积足够内容时才收束；短节段与后续内容合并，
            # 避免多标题文档（如报告）产生大量碎片。
            current_text = candidate_text(current_blocks) if current_blocks else ""
            if len(current_text) >= config.heading_flush_min_chars:
                flush_current("heading_boundary")
            level = heading_level(block.text)
            title = normalize_heading(block.text)
            title_stack = [(item_level, item_title) for item_level, item_title in title_stack if item_level < level]
            title_stack.append((level, title))
            current_title_path = [item_title for _, item_title in title_stack]
            current_heading_block = block
            if config.include_heading_in_content:
                if not current_blocks:
                    current_blocks = [block]
                else:
                    current_blocks.append(block)
            continue

        if is_protected_block(block):
            flush_current("before_special_block")
            special_blocks = [block]
            if config.include_heading_in_content and current_heading_block is not None:
                # 保留标题上下文，避免特殊块脱离语义背景。
                special_blocks = [current_heading_block, block]
            candidates.append(make_candidate(special_blocks, current_title_path, f"protected_{block.block_type}"))
            current_blocks = [current_heading_block] if config.include_heading_in_content and current_heading_block is not None else []
            continue

        if current_blocks and not is_heading_only(current_blocks):
            current_text = candidate_text(current_blocks)
            if should_flush_for_semantic_boundary(current_text, block.text, config):
                flush_current("semantic_boundary")
                if config.include_heading_in_content and current_heading_block is not None:
                    current_blocks = [current_heading_block]

        if is_long_block(block, config):
            flush_current("before_long_block")
            for index, piece in enumerate(split_long_text(block.text, config)):
                piece_block = clone_block(block, piece)
                piece_blocks = [piece_block]
                if config.include_heading_in_content and current_heading_block is not None:
                    piece_blocks = [current_heading_block, piece_block]
                candidates.append(make_candidate(piece_blocks, current_title_path, "long_block_sentence_split"))
            current_blocks = [current_heading_block] if config.include_heading_in_content and current_heading_block is not None else []
            continue

        if not current_blocks and config.include_heading_in_content and current_heading_block is not None:
            current_blocks = [current_heading_block]

        # 预检查：如果加入当前 block 会导致 token 溢出，先收束再添加
        if current_blocks and not is_heading_only(current_blocks):
            current_tokens = count_tokens(candidate_text(current_blocks))
            block_tokens = count_tokens(block.text)
            if current_tokens + block_tokens > config.max_tokens and current_tokens >= config.min_tokens:
                flush_current("pre_add_token_overflow")

        current_blocks.append(block)

        if should_flush_for_length_boundary(current_blocks, config):
            flush_current("target_length_reached")
            if config.include_heading_in_content and current_heading_block is not None:
                current_blocks = [current_heading_block]

    flush_current("document_end")
    return candidates


def split_oversized_chunks(
    candidates: list[CandidateChunk],
    config: SegmentConfig,
) -> list[CandidateChunk]:
    """把超长普通 chunk 再按句子边界拆开。"""

    result: list[CandidateChunk] = []
    for candidate in candidates:
        if candidate["chunk_type"] in {"table", "formula", "code"}:
            result.append(candidate)
            continue
        if candidate["char_count"] <= config.max_chars and candidate["token_count"] <= config.max_tokens:
            result.append(candidate)
            continue

        pieces = split_candidate_content(candidate["content"], candidate["source_blocks"], config)
        for index, piece in enumerate(pieces):
            split_candidate = dict(candidate)
            split_candidate["content"] = piece["content"]
            split_candidate["char_count"] = len(piece["content"])
            split_candidate["token_count"] = count_tokens(piece["content"])
            split_candidate["source_blocks"] = piece["source_blocks"]
            split_candidate["chunk_type"] = "normal"
            split_candidate["strategy_info"] = {
                **candidate["strategy_info"],
                "split_reason": "sentence_boundary_for_oversized_chunk",
                "split_index": index,
            }
            result.append(split_candidate)
    return result


def merge_short_chunks(
    candidates: list[CandidateChunk],
    config: SegmentConfig,
) -> list[CandidateChunk]:
    """自适应合并过短 chunk。

    优先合并同一标题路径下的相邻普通 chunk；如果当前 chunk 明显偏短，
    也允许吸收后续相邻普通 chunk，只要合并后仍然符合长度上限并且
    语义上不至于完全跳题。
    """

    merged: list[CandidateChunk] = []
    index = 0

    while index < len(candidates):
        current = candidates[index]
        if current["chunk_type"] in {"table", "formula", "code"}:
            merged.append(current)
            index += 1
            continue

        pending = current
        look_ahead = index + 1

        while look_ahead < len(candidates):
            next_candidate = candidates[look_ahead]
            if next_candidate["chunk_type"] in {"table", "formula", "code"}:
                break
            if not can_merge_chunks(pending, next_candidate, config):
                break

            pending = merge_candidates(pending, next_candidate)
            look_ahead += 1
            if len(pending["content"]) >= config.min_chars and pending["token_count"] >= config.min_tokens:
                break

        merged.append(pending)
        index = look_ahead

    merged = rebalance_short_chunks(merged, config)
    merged = absorb_trailing_short_chunks(merged, config)
    return merged


def is_protected_block(block: DocumentBlock) -> bool:
    """特殊结构块需要尽量整体保留。"""

    return block.block_type in {"table", "formula", "code"}


def is_heading_only(blocks: list[DocumentBlock]) -> bool:
    """判断当前块列表是否只是标题上下文。"""

    return bool(blocks) and all(block.block_type == "heading" for block in blocks)


def make_candidate(
    blocks: list[DocumentBlock],
    title_path: list[str],
    split_reason: str,
) -> CandidateChunk:
    """把若干 DocumentBlock 打包成一个候选 chunk。"""

    content = candidate_text(blocks)
    chunk_type = "normal"
    if len(blocks) == 1 and is_protected_block(blocks[0]):
        chunk_type = blocks[0].block_type

    return {
        "content": content,
        "title_path": list(title_path),
        "chunk_type": chunk_type,
        "source_blocks": list(blocks),
        "strategy_info": {"split_reason": split_reason},
        "char_count": len(content),
        "token_count": count_tokens(content),
    }


def candidate_text(blocks: list[DocumentBlock]) -> str:
    """把 block 序列拼成 chunk 文本。"""

    return "\n\n".join(block.text.strip() for block in blocks if block.text.strip()).strip()


def split_candidate_content(
    content: str,
    source_blocks: list[DocumentBlock],
    config: SegmentConfig,
) -> list[dict[str, Any]]:
    """把超长 chunk 拆成更小的候选文本片段。"""

    heading_prefix = ""
    body = content.strip()

    if source_blocks and source_blocks[0].block_type == "heading":
        heading_prefix = source_blocks[0].text.strip()
        body = strip_leading_heading(body, heading_prefix)

    max_body_chars = available_body_chars(heading_prefix, config)
    # token 感知：取 chars 和 tokens 两者中更严格的约束
    # 用当前 chunk 的实际 t/c 比率估算对应的 char 上限
    effective_max_chars = _token_aware_char_limit(body, config)
    effective_max_chars = min(max_body_chars, effective_max_chars)
    pieces = split_text_recursively(body, effective_max_chars, config)
    if not pieces:
        pieces = [body]

    result: list[dict[str, Any]] = []
    for piece in pieces:
        result.append(build_piece(heading_prefix, [piece], source_blocks))

    if not result:
        result.append(
            {
                "content": content.strip(),
                "source_blocks": list(source_blocks),
            }
        )

    return [piece for piece in result if piece["content"].strip()]


def build_piece(
    heading_prefix: str,
    sentences: list[str],
    source_blocks: list[DocumentBlock],
) -> dict[str, Any]:
    """构造一个拆分后的片段。"""

    body = "".join(sentences).strip()
    if heading_prefix:
        content = f"{heading_prefix}\n\n{body}".strip()
    else:
        content = body
    return {
        "content": content,
        "source_blocks": list(source_blocks),
    }


def strip_leading_heading(content: str, heading: str) -> str:
    """去掉 chunk 头部的标题行，方便按正文拆分。"""

    lines = content.splitlines()
    if not lines:
        return content
    if lines[0].strip() != heading:
        return content
    return "\n".join(lines[1:]).lstrip("\n")


def split_long_text(text: str, config: SegmentConfig) -> list[str]:
    """递归切分超长文本，并给后续 chunk 添加少量 overlap。"""

    return split_text_recursively(text, config.max_chars, config)


def split_text_recursively(text: str, max_chars: int, config: SegmentConfig) -> list[str]:
    """按 LangChain RecursiveCharacterTextSplitter 的思路切分文本。

    优先保留段落、换行和句子边界；只有当某个单元仍超过长度上限时，
    才继续使用更细粒度的分隔符，最后用硬切作为兜底。
    """

    limit = max(1, max_chars)
    normalized = text.strip()
    if not normalized:
        return []
    if len(normalized) <= limit:
        return [normalized]

    units = recursive_split_units(normalized, limit, config.recursive_separators)
    return merge_recursive_units(units, limit, config.overlap_sentences)


def recursive_split_units(text: str, max_chars: int, separators: tuple[str, ...]) -> list[str]:
    """递归拆出不超过长度上限的基础文本单元。"""

    stripped = text.strip()
    if not stripped:
        return []
    if len(stripped) <= max_chars:
        return [stripped]

    if not separators:
        return split_unit_by_length(stripped, max_chars)

    separator = choose_separator(stripped, separators)
    remaining_separators = separators[separators.index(separator) + 1 :]

    if separator == "":
        return split_unit_by_length(stripped, max_chars)

    raw_parts = stripped.split(separator)
    units: list[str] = []
    for index, raw_part in enumerate(raw_parts):
        if not raw_part.strip():
            continue
        part = raw_part
        if index < len(raw_parts) - 1:
            part = f"{part}{separator}"
        if len(part) > max_chars:
            units.extend(recursive_split_units(part, max_chars, remaining_separators))
        else:
            units.append(part)
    return units


def choose_separator(text: str, separators: tuple[str, ...]) -> str:
    """选择当前文本中可用的最粗粒度分隔符。"""

    for separator in separators:
        if separator == "" or separator in text:
            return separator
    return ""


def merge_recursive_units(units: list[str], max_chars: int, overlap_count: int) -> list[str]:
    """把递归拆出的基础单元组合成接近长度上限的 chunk。"""

    pieces: list[str] = []
    current: list[str] = []

    for unit in units:
        unit = unit.strip(" \t")
        if not unit.strip():
            continue
        if current and len("".join(current)) + len(unit) > max_chars:
            pieces.append("".join(current).strip())
            current = bounded_overlap(current, overlap_count, max_chars)
            while current and len("".join(current)) + len(unit) > max_chars:
                current.pop(0)
        current.append(unit)

    if current:
        pieces.append("".join(current).strip())

    return [piece for piece in pieces if piece]


def split_sentences(text: str) -> list[str]:
    """中英文常见句末标点切句。"""

    sentences = [match.group(0).strip() for match in SENTENCE_PATTERN.finditer(text) if match.group(0).strip()]
    return sentences or [text.strip()]


def split_sentences_by_length(text: str, max_chars: int) -> list[str]:
    """先按句子切分，再对超长句做长度兜底拆分。"""

    units: list[str] = []
    for sentence in split_sentences(text):
        units.extend(split_unit_by_length(sentence, max_chars))
    return [unit for unit in units if unit]


def split_unit_by_length(text: str, max_chars: int) -> list[str]:
    """把单个超长文本单元拆到长度上限内。"""

    limit = max(1, max_chars)
    remaining = text.strip()
    if len(remaining) <= limit:
        return [remaining] if remaining else []

    parts: list[str] = []
    while len(remaining) > limit:
        split_at = best_split_position(remaining, limit)
        parts.append(remaining[:split_at].strip())
        remaining = remaining[split_at:].strip()
    if remaining:
        parts.append(remaining)
    return parts


def best_split_position(text: str, limit: int) -> int:
    """优先在空白或轻标点处拆分，找不到时才硬切。"""

    candidates = [text.rfind(separator, 0, limit + 1) for separator in (" ", "\n", "\t", ",", "，", "、", ":")]
    split_at = max(candidates)
    if split_at >= max(1, limit // 2):
        return split_at + 1
    return limit


def _token_aware_char_limit(text: str, config: SegmentConfig) -> int:
    """根据文本实际 t/c 比率，估算不超过 max_tokens 的最大字符数。

    中文 ~1.09 t/c → max_chars 更严格；英文 ~0.25 t/c → max_tokens 形同虚设。
    这个函数让拆分器在中英文混合场景下都能避免 token 溢出。
    """

    char_count = len(text)
    if char_count == 0:
        return config.max_chars
    token_count = count_tokens(text)
    if token_count <= config.max_tokens:
        return config.max_chars
    # 比率 < 1 意味着 chars > tokens（英文），不需要收紧
    ratio = token_count / char_count
    if ratio <= 1.0:
        return config.max_chars
    # 收紧：按比例降低 char 上限，留 5% 余量
    return max(1, int(config.max_tokens / ratio * 0.95))


def available_body_chars(heading_prefix: str, config: SegmentConfig) -> int:
    """计算带标题前缀时正文可使用的字符预算。"""

    if not heading_prefix:
        return config.max_chars
    return max(1, config.max_chars - len(heading_prefix) - 2)


def bounded_overlap(sentences: list[str], overlap_count: int, max_chars: int) -> list[str]:
    """返回不会单独超过长度预算的重叠句。"""

    if overlap_count <= 0:
        return []

    overlap: list[str] = []
    for sentence in sentences[-overlap_count:]:
        if len("".join(overlap)) + len(sentence) <= max_chars:
            overlap.append(sentence)
    return overlap


def is_long_block(block: DocumentBlock, config: SegmentConfig) -> bool:
    """判断单个 block 是否需要优先拆分。"""

    return len(block.text) > config.max_chars or count_tokens(block.text) > config.max_tokens


def should_flush_for_length_boundary(blocks: list[DocumentBlock], config: SegmentConfig) -> bool:
    """判断当前累计块是否已经达到收束条件。

    双目标取较小者：当字符数或 token 数任一达到目标区间时即收束。
    tiktoken 下中文约 1.09 t/c，英文约 0.25 t/c，双目标可保证
    两种语言都在安全范围内。
    """

    if not blocks:
        return False
    content = candidate_text(blocks)
    token_count = count_tokens(content)

    chars_reached = len(content) >= config.target_chars
    tokens_reached = token_count >= config.target_tokens

    # 两个指标都未达目标 → 继续累积
    if not chars_reached and not tokens_reached:
        return False

    # token 已达硬上限 → 必须收束（安全网）
    if token_count >= config.max_tokens:
        return True

    if is_heading_only(blocks):
        return False
    return True


def should_flush_for_semantic_boundary(current_text: str, next_text: str, config: SegmentConfig) -> bool:
    """用轻量词向量相似度判断是否应提前收束。"""

    if not config.enable_semantic_boundary:
        return False
    if len(current_text) < config.min_chars:
        return False
    similarity = cosine_similarity(current_text, next_text)
    return similarity < config.semantic_boundary_threshold


def can_merge_chunks(left: CandidateChunk, right: CandidateChunk, config: SegmentConfig) -> bool:
    """判断两个候选 chunk 是否适合合并。"""

    if right["chunk_type"] != "normal":
        return False

    separator_chars = 2 if left["content"].strip() and right["content"].strip() else 0
    combined_chars = left["char_count"] + right["char_count"] + separator_chars
    combined_tokens = left["token_count"] + right["token_count"]
    if combined_chars > config.max_chars or combined_tokens > config.max_tokens:
        return False

    if left["title_path"] == right["title_path"]:
        return True

    shared = common_title_path(left["title_path"], right["title_path"])
    if shared and len(shared) >= 1:
        return left["char_count"] < config.min_chars or right["char_count"] < config.min_chars

    if left["char_count"] < max(120, (config.min_chars * 2) // 3):
        return combined_chars <= config.target_chars

    very_short_left = left["char_count"] < max(80, config.min_chars // 2)
    very_short_right = right["char_count"] < max(80, config.min_chars // 2)

    if very_short_left or very_short_right:
        similarity = cosine_similarity(left["content"], right["content"])
        if not left["title_path"] or not right["title_path"]:
            return True
        return similarity >= (config.semantic_boundary_threshold * 0.35) or combined_chars <= config.target_chars

    return False


def merge_candidates(left: CandidateChunk, right: CandidateChunk) -> CandidateChunk:
    """合并两个候选 chunk，并记录合并原因。"""

    merged_title_path = common_title_path(left["title_path"], right["title_path"])
    if not merged_title_path:
        merged_title_path = list(left["title_path"] or right["title_path"])

    content = f'{left["content"]}\n\n{right["content"]}'.strip()
    return {
        "content": content,
        "title_path": merged_title_path,
        "chunk_type": "normal",
        "source_blocks": left["source_blocks"] + right["source_blocks"],
        "strategy_info": {
            "split_reason": right["strategy_info"].get("split_reason", "merged"),
            "merge_reason": "adaptive_short_chunk_merge",
            "merged_title_paths": [left["title_path"], right["title_path"]],
        },
        "char_count": len(content),
        "token_count": count_tokens(content),
    }


def rebalance_short_chunks(
    chunks: list[CandidateChunk],
    config: SegmentConfig,
) -> list[CandidateChunk]:
    """在无法整体合并时，从前一个 chunk 匀一些句子给过短的 chunk。

    场景：章节末段因标题边界 flush 变成孤儿 chunk（< min_chars），
    但与前块合并又超出 max_chars。此时从前块尾部拆出若干句子补入孤儿，
    使双方都在 min~max 区间内。

    只对共享标题前缀的相邻普通 chunk 生效；不触及表格/代码/公式。
    """

    if len(chunks) < 2:
        return chunks

    result = list(chunks)
    index = 1  # 从第二个 chunk 开始检查

    while index < len(result):
        prev = result[index - 1]
        curr = result[index]

        # 只处理普通块
        if prev["chunk_type"] != "normal" or curr["chunk_type"] != "normal":
            index += 1
            continue

        # 不需要重平衡
        if curr["char_count"] >= config.min_chars:
            index += 1
            continue
        if prev["char_count"] <= config.min_chars:
            index += 1
            continue

        # 只在共享标题上下文时重平衡，避免跨主题混合。
        # 两个 chunk 都没有标题（无标题文档）时也允许重平衡。
        shared = common_title_path(prev["title_path"], curr["title_path"])
        both_empty = not prev["title_path"] and not curr["title_path"]
        if len(shared) < 1 and not both_empty:
            index += 1
            continue

        # 计算需要从前块移多少字符到后块
        deficit = config.min_chars - curr["char_count"]
        # 额外多移一些作为缓冲，避免刚好卡在边界
        move_target = min(deficit + 80, prev["char_count"] - config.min_chars)
        if move_target <= 0:
            index += 1
            continue

        prev_text = prev["content"]
        prev_sentences = split_sentences(prev_text)
        if len(prev_sentences) <= 1:
            index += 1
            continue

        # 从后往前取句子，直到累计长度达到 move_target
        moved_chars = 0
        moved_parts: list[str] = []
        remaining_prev = list(prev_sentences)

        while moved_chars < move_target and len(remaining_prev) > 1:
            sentence = remaining_prev.pop().strip()
            if not sentence:
                continue
            moved_parts.insert(0, sentence)
            moved_chars += len(sentence)

        if not moved_parts:
            index += 1
            continue

        # 重建两个 chunk
        new_prev_content = "".join(remaining_prev).strip()
        moved_content = "".join(moved_parts).strip()
        new_curr_content = f"{moved_content}\n\n{curr['content']}".strip()

        # 更新 prev
        result[index - 1] = {
            **prev,
            "content": new_prev_content,
            "char_count": len(new_prev_content),
            "token_count": count_tokens(new_prev_content),
            "strategy_info": {
                **prev["strategy_info"],
                "rebalanced": True,
                "rebalance_role": "donor",
                "chars_donated": moved_chars,
            },
        }

        # 更新 curr
        result[index] = {
            **curr,
            "content": new_curr_content,
            "char_count": len(new_curr_content),
            "token_count": count_tokens(new_curr_content),
            "strategy_info": {
                **curr["strategy_info"],
                "rebalanced": True,
                "rebalance_role": "recipient",
                "chars_received": moved_chars,
            },
        }

        index += 1

    return result


def absorb_trailing_short_chunks(chunks: list[CandidateChunk], config: SegmentConfig) -> list[CandidateChunk]:
    """把尾部仍然偏短、且能自然并入前一块的 chunk 吃掉。"""

    merged = list(chunks)
    while len(merged) >= 2:
        last = merged[-1]
        prev = merged[-2]
        if last["chunk_type"] in {"table", "formula", "code"}:
            break
        if last["char_count"] >= config.min_chars and last["token_count"] >= config.min_tokens:
            break
        if not can_merge_chunks(prev, last, config):
            break
        merged[-2] = merge_candidates(prev, last)
        merged.pop()
    return merged


def common_title_path(left: list[str], right: list[str]) -> list[str]:
    """返回两个标题路径的公共前缀。"""

    shared: list[str] = []
    for left_title, right_title in zip(left, right):
        if left_title != right_title:
            break
        shared.append(left_title)
    return shared


def clone_block(block: DocumentBlock, text: str) -> DocumentBlock:
    """复制一个 block，但替换文本内容。"""

    return DocumentBlock(
        block_id=block.block_id,
        text=text,
        block_type=block.block_type,
        page=block.page,
        metadata=dict(block.metadata),
    )


_tiktoken_encoder: Any = None


def _get_tiktoken_encoder() -> Any:
    """延迟加载 tiktoken 编码器，避免导入时的网络开销。"""
    global _tiktoken_encoder
    if _tiktoken_encoder is not None:
        return _tiktoken_encoder
    try:
        import tiktoken

        _tiktoken_encoder = tiktoken.get_encoding("cl100k_base")
    except Exception:
        _tiktoken_encoder = False
    return _tiktoken_encoder


def count_tokens(text: str) -> int:
    """估算文本的 BPE token 数。

    优先使用 tiktoken（cl100k_base，GPT-4 / GPT-3.5 通用编码），
    无法加载时回退到轻量正则近似。
    """

    encoder = _get_tiktoken_encoder()
    if encoder and encoder is not False:
        try:
            return len(encoder.encode(text or ""))
        except Exception:
            pass
    return len(TOKEN_PATTERN.findall(text or ""))


def cosine_similarity(left: str, right: str) -> float:
    """基于 token 计数的余弦相似度。"""

    left_counts = Counter(token.lower() for token in TOKEN_PATTERN.findall(left or "") if token.strip())
    right_counts = Counter(token.lower() for token in TOKEN_PATTERN.findall(right or "") if token.strip())
    if not left_counts or not right_counts:
        return 0.0

    shared = set(left_counts) & set(right_counts)
    dot = sum(left_counts[token] * right_counts[token] for token in shared)
    left_norm = sum(count * count for count in left_counts.values()) ** 0.5
    right_norm = sum(count * count for count in right_counts.values()) ** 0.5
    if not left_norm or not right_norm:
        return 0.0
    return round(dot / (left_norm * right_norm), 6)
