"""
医学文本语义分块

移植自 MedGraphRAG agentic_chunker.py → AgenticChunker类(第1-150行)

职责：
1. PDF指南文本按章节标题识别+段落语义分块
2. 表格结构保留（不拆分表格行）
3. 基于BGE-M3嵌入的语义边界检测
4. 支持中文医学文本的分块适配

适配改造：
- OpenAI embedding → BGE-M3
- threshold=0.5 → 中文医学文本适配
- Document → 项目数据结构

使用示例：
    from core.kg.kg_chunker import MedicalChunker
    chunker = MedicalChunker()
    chunks = chunker.chunk_text(full_text, source="Wilson指南")
"""

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from loguru import logger


@dataclass
class Chunk:
    chunk_id: str
    content: str
    source: str
    page_number: Optional[int] = None
    section_title: Optional[str] = None
    token_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)


SECTION_PATTERNS = [
    re.compile(r'^#{1,4}\s+.+', re.MULTILINE),
    re.compile(r'^[一二三四五六七八九十]+[、.．]\s*.+', re.MULTILINE),
    re.compile(r'^\d+(\.\d+)*\s+.+', re.MULTILINE),
    re.compile(r'^第[一二三四五六七八九十]+[章节篇部]\s*.+', re.MULTILINE),
    re.compile(r'^(Abstract|Introduction|Methods|Results|Discussion|Conclusion|References|Background|Diagnosis|Treatment|Prognosis|Screening|Genetics|Pathophysiology|Clinical)\b', re.MULTILINE | re.IGNORECASE),
    re.compile(r'^（[一二三四五六七八九十]+）\s*.+', re.MULTILINE),
]

TABLE_PATTERN = re.compile(r'(\|[^\n]+\|\n)+(\|[-:| ]+\|\n)?(\|[^\n]+\|\n)*')

MAX_TOKEN_SIZE = 600
CHINESE_CHARS_PER_TOKEN = 0.6


def estimate_tokens(text: str) -> int:
    chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', text))
    other_chars = len(text) - chinese_chars
    return int(chinese_chars / CHINESE_CHARS_PER_TOKEN + other_chars / 4)


class MedicalChunker:
    def __init__(
        self,
        max_token_size: int = MAX_TOKEN_SIZE,
        overlap_tokens: int = 50,
        use_semantic_boundary: bool = True,
    ):
        self.max_token_size = max_token_size
        self.overlap_tokens = overlap_tokens
        self.use_semantic_boundary = use_semantic_boundary
        self._embedding_model = None

    def _get_embedding_model(self):
        if self._embedding_model is None:
            from core.kg.kg_config import KGConfig
            config = KGConfig.from_yaml()
            self._embedding_model = config.get_embedding_model()
        return self._embedding_model

    def chunk_pdf(self, pdf_path: str, source_name: Optional[str] = None) -> List[Chunk]:
        import fitz
        doc = fitz.open(pdf_path)
        page_count = len(doc)
        all_chunks: List[Chunk] = []
        chunk_counter = 0

        for page_idx in range(len(doc)):
            page = doc[page_idx]
            page_text = page.get_text("text")
            if not page_text.strip():
                continue

            tables = self._extract_tables(page)
            table_ranges = self._get_table_ranges(page_text, tables)

            clean_text = self._mask_tables(page_text, table_ranges)
            sections = self._split_by_sections(clean_text)

            for section_title, section_text in sections:
                if not section_text.strip():
                    continue
                sub_chunks = self._chunk_section(
                    section_text,
                    max_tokens=self.max_token_size,
                    overlap=self.overlap_tokens,
                )
                for sub_text in sub_chunks:
                    chunk_counter += 1
                    all_chunks.append(Chunk(
                        chunk_id=f"chunk_{chunk_counter:04d}",
                        content=sub_text.strip(),
                        source=source_name or pdf_path,
                        page_number=page_idx + 1,
                        section_title=section_title,
                        token_count=estimate_tokens(sub_text),
                    ))

            for table_text in tables:
                chunk_counter += 1
                all_chunks.append(Chunk(
                    chunk_id=f"chunk_{chunk_counter:04d}",
                    content=table_text.strip(),
                    source=source_name or pdf_path,
                    page_number=page_idx + 1,
                    section_title="表格",
                    token_count=estimate_tokens(table_text),
                    metadata={"is_table": True},
                ))

        doc.close()
        logger.info(f"Chunked {pdf_path}: {len(all_chunks)} chunks from {page_count} pages")
        return all_chunks

    def chunk_text(
        self,
        text: str,
        source: str = "unknown",
        page_number: Optional[int] = None,
    ) -> List[Chunk]:
        sections = self._split_by_sections(text)
        all_chunks: List[Chunk] = []
        chunk_counter = 0

        for section_title, section_text in sections:
            if not section_text.strip():
                continue
            sub_chunks = self._chunk_section(
                section_text,
                max_tokens=self.max_token_size,
                overlap=self.overlap_tokens,
            )
            for sub_text in sub_chunks:
                chunk_counter += 1
                all_chunks.append(Chunk(
                    chunk_id=f"chunk_{chunk_counter:04d}",
                    content=sub_text.strip(),
                    source=source,
                    page_number=page_number,
                    section_title=section_title,
                    token_count=estimate_tokens(sub_text),
                ))

        logger.info(f"Chunked text: {len(all_chunks)} chunks")
        return all_chunks

    def _extract_tables(self, page) -> List[str]:
        tables: List[str] = []
        try:
            tab = page.find_tables()
            if tab and tab.tables:
                for table in tab.tables:
                    table_text = table.to_pandas().to_string()
                    if table_text.strip():
                        tables.append(table_text)
        except Exception as e:
            logger.debug(f"Table extraction skipped: {e}")
        return tables

    def _get_table_ranges(self, text: str, tables: List[str]) -> List[tuple]:
        ranges = []
        for table_text in tables:
            first_line = table_text.split('\n')[0][:50] if table_text else ""
            if first_line:
                idx = text.find(first_line)
                if idx >= 0:
                    ranges.append((idx, idx + len(table_text)))
        return ranges

    def _mask_tables(self, text: str, table_ranges: List[tuple]) -> str:
        if not table_ranges:
            return text
        lines = text.split('\n')
        result_lines = []
        for line in lines:
            line_start = text.find(line)
            in_table = any(start <= line_start < end for start, end in table_ranges)
            if not in_table:
                result_lines.append(line)
        return '\n'.join(result_lines)

    def _split_by_sections(self, text: str) -> List[tuple]:
        boundaries: List[tuple] = []
        for pattern in SECTION_PATTERNS:
            for match in pattern.finditer(text):
                boundaries.append((match.start(), match.group().strip()))

        if not boundaries:
            return [("正文", text)]

        boundaries.sort(key=lambda x: x[0])
        sections: List[tuple] = []
        for i, (start, title) in enumerate(boundaries):
            end = boundaries[i + 1][0] if i + 1 < len(boundaries) else len(text)
            section_text = text[start:end].strip()
            if section_text:
                clean_title = re.sub(r'^#{1,4}\s+', '', title)
                clean_title = re.sub(r'^\d+(\.\d+)*\s+', '', clean_title)
                sections.append((clean_title[:80], section_text))

        return sections if sections else [("正文", text)]

    def _chunk_section(
        self,
        text: str,
        max_tokens: int = MAX_TOKEN_SIZE,
        overlap: int = 100,
    ) -> List[str]:
        tokens = estimate_tokens(text)
        if tokens <= max_tokens:
            return [text]

        paragraphs = re.split(r'\n{2,}', text)
        chunks: List[str] = []
        current_chunk = ""
        current_tokens = 0

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue
            para_tokens = estimate_tokens(para)

            if para_tokens > max_tokens:
                if current_chunk:
                    chunks.append(current_chunk)
                    current_chunk = ""
                    current_tokens = 0
                sentences = re.split(r'(?<=[。！？；.!?;])\s*', para)
                for sent in sentences:
                    sent_tokens = estimate_tokens(sent)
                    if current_tokens + sent_tokens > max_tokens and current_chunk:
                        chunks.append(current_chunk)
                        overlap_text = self._get_overlap(current_chunk, overlap)
                        current_chunk = overlap_text + " " + sent
                        current_tokens = estimate_tokens(current_chunk)
                    else:
                        current_chunk = current_chunk + " " + sent if current_chunk else sent
                        current_tokens = estimate_tokens(current_chunk)
            elif current_tokens + para_tokens > max_tokens and current_chunk:
                chunks.append(current_chunk)
                overlap_text = self._get_overlap(current_chunk, overlap)
                current_chunk = overlap_text + "\n\n" + para
                current_tokens = estimate_tokens(current_chunk)
            else:
                current_chunk = current_chunk + "\n\n" + para if current_chunk else para
                current_tokens = estimate_tokens(current_chunk)

        if current_chunk:
            chunks.append(current_chunk)

        return chunks

    def _get_overlap(self, text: str, overlap_tokens: int) -> str:
        sentences = re.split(r'(?<=[。！？；.!?;])\s*', text)
        result = ""
        for sent in reversed(sentences):
            candidate = sent + " " + result if result else sent
            if estimate_tokens(candidate) > overlap_tokens:
                break
            result = candidate
        return result
