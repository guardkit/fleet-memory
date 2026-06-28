"""Heading-aware prose chunker for memory episodes.

Pure function that splits markdown/text into overlapping chunks for downstream
processing. No I/O, no embedding, no storage — just text transformation.

Sizing is token-accurate (tiktoken cl100k_base, matching retrieval/assembly.py).
An earlier whitespace-word-count estimate grossly under-counted code/JSON/tables
(few spaces, many tokens), so structured sections escaped splitting and became
oversized chunks — the cause of the empty/blob retrieval documented in
docs/evals/FEAT-MEM-05-parity-eval-2026-06-27.md.
"""

from __future__ import annotations

import re

import tiktoken

from fleet_memory.relay.schema import Chunk

# Shared encoding so a chunk's measured size matches what assembly will measure.
_ENCODING = tiktoken.get_encoding("cl100k_base")


def _token_count(text: str) -> int:
    """Actual token count via tiktoken (not whitespace words)."""
    return len(_ENCODING.encode(text))


def chunk_prose(
    body: str,
    *,
    target_tokens: int,
    overlap_ratio: float,
    source_ref: str | None,
    project: str,
) -> list[Chunk]:
    """Split prose into heading-aware chunks with configurable size and overlap.

    Args:
        body: Text to chunk (markdown or plain text)
        target_tokens: Target size per chunk in tokens (tiktoken-measured)
        overlap_ratio: Fraction of chunk to overlap with next (0.0-1.0)
        source_ref: Source reference to propagate to all chunks
        project: Project identifier to propagate to all chunks

    Returns:
        List of Chunk objects with monotonic indices from 0.
        Empty list if body is empty or whitespace-only.

    Behavior:
        - Chunks are bounded by ~target_tokens using tiktoken token counts
        - Adjacent chunks overlap by ~overlap_ratio to preserve context
        - Prefers splitting at markdown heading boundaries (# lines)
        - Never separates a heading from its section content
        - Pure function: deterministic, no I/O, no side effects
    """
    # Handle empty or whitespace-only input
    if not body or not body.strip():
        return []

    # Calculate overlap size in tokens
    overlap_tokens = int(target_tokens * overlap_ratio)

    # Split text into sections at heading boundaries
    sections = _split_into_sections(body)

    chunks: list[Chunk] = []
    current_chunk_text = ""

    for section in sections:
        section_tokens = _token_count(section)

        # If section itself exceeds target, split it into sub-chunks
        if section_tokens > target_tokens:
            # Finalize any accumulated content first
            if current_chunk_text.strip():
                chunks.append(
                    Chunk(
                        index=len(chunks),
                        text=current_chunk_text.strip(),
                        source_ref=source_ref,
                        project=project,
                    )
                )
                current_chunk_text = ""

            # Split large section into multiple chunks
            section_chunks = _split_large_section(section, target_tokens, overlap_tokens)
            for section_text in section_chunks:
                chunks.append(
                    Chunk(
                        index=len(chunks),
                        text=section_text.strip(),
                        source_ref=source_ref,
                        project=project,
                    )
                )
        # If current chunk + section would exceed target, finalize current chunk
        elif current_chunk_text and _token_count(current_chunk_text + section) > target_tokens:
            # Finalize current chunk
            chunks.append(
                Chunk(
                    index=len(chunks),
                    text=current_chunk_text.strip(),
                    source_ref=source_ref,
                    project=project,
                )
            )

            # Start next chunk with overlap from previous
            if overlap_tokens > 0:
                overlap_buffer = _extract_tail_tokens(current_chunk_text, overlap_tokens)
                current_chunk_text = overlap_buffer + section
            else:
                current_chunk_text = section
        else:
            # Add section to current chunk
            current_chunk_text += section

    # Finalize last chunk if any content remains
    if current_chunk_text.strip():
        chunks.append(
            Chunk(
                index=len(chunks),
                text=current_chunk_text.strip(),
                source_ref=source_ref,
                project=project,
            )
        )

    return chunks


def _split_into_sections(text: str) -> list[str]:
    """Split text into sections at markdown heading boundaries.

    A section is either:
    - A heading line + its content until the next heading
    - Content before the first heading

    Args:
        text: Input text (markdown or plain)

    Returns:
        List of text sections, preserving headings with their content
    """
    lines = text.split("\n")
    sections: list[str] = []
    current_section: list[str] = []

    for line in lines:
        # Check if this is a markdown heading
        if re.match(r"^#{1,6}\s", line):
            # If we have accumulated content, save it as a section
            if current_section:
                sections.append("\n".join(current_section) + "\n")
                current_section = []
            # Start new section with the heading
            current_section.append(line)
        else:
            current_section.append(line)

    # Add final section
    if current_section:
        sections.append("\n".join(current_section))

    # If no headings found, treat as single section
    if not sections:
        return [text]

    return sections


def _split_large_section(section: str, target_tokens: int, overlap_tokens: int) -> list[str]:
    """Split a large section into multiple chunks with overlap, on token boundaries.

    Operates on the actual tiktoken token stream so code/JSON/tables (which have
    few whitespace words but many tokens) are split correctly rather than left as
    a single oversized chunk.

    Args:
        section: Text section to split
        target_tokens: Target chunk size in tokens
        overlap_tokens: Number of tokens to overlap between chunks

    Returns:
        List of text chunks (each ~target_tokens) with overlap
    """
    tokens = _ENCODING.encode(section)
    if len(tokens) <= target_tokens:
        return [section]

    chunks: list[str] = []
    start = 0

    while start < len(tokens):
        # Take target_tokens tokens from current position
        end = min(start + target_tokens, len(tokens))
        chunks.append(_ENCODING.decode(tokens[start:end]))

        # Move forward by (target - overlap) to create overlap
        if end >= len(tokens):
            break
        start = end - overlap_tokens if overlap_tokens > 0 else end

    return chunks


def _extract_tail_tokens(text: str, num_tokens: int) -> str:
    """Extract approximately num_tokens from the end of text (token-accurate).

    Args:
        text: Source text
        num_tokens: Number of tokens to extract from end

    Returns:
        Text containing approximately num_tokens from the end
    """
    tokens = _ENCODING.encode(text)
    if len(tokens) <= num_tokens:
        return text

    return _ENCODING.decode(tokens[-num_tokens:]) + " "
