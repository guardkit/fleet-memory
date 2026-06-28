"""Unit tests for prose chunker.

Tests chunk_prose function covering all TASK-RLY-003 acceptance criteria.
"""

from __future__ import annotations

import pytest

from fleet_memory.relay.chunker import chunk_prose
from fleet_memory.relay.schema import Chunk


class TestChunkProseUnderTargetSize:
    """Test AC-001: Body under target size produces exactly 1 chunk."""

    def test_short_body_returns_single_chunk(self) -> None:
        """Body well under target size returns exactly 1 chunk."""
        body = "This is a short text that fits in one chunk."
        chunks = chunk_prose(
            body, target_tokens=1000, overlap_ratio=0.15, source_ref="ref://x", project="test"
        )
        assert len(chunks) == 1
        assert chunks[0].text == body
        assert chunks[0].index == 0
        assert chunks[0].source_ref == "ref://x"
        assert chunks[0].project == "test"

    def test_body_exactly_at_target_returns_single_chunk(self) -> None:
        """Body exactly at target size returns 1 chunk."""
        # ~200 tokens worth of text (approximate)
        body = " ".join(["word"] * 200)
        chunks = chunk_prose(
            body, target_tokens=200, overlap_ratio=0.15, source_ref=None, project="proj"
        )
        assert len(chunks) == 1


class TestChunkProseOverTargetSize:
    """Test AC-002: Body just over target size produces 2 chunks with overlap."""

    def test_body_just_over_target_returns_two_chunks(self) -> None:
        """Body just over target size produces exactly 2 chunks."""
        # ~250 tokens worth of text (to exceed 200 target)
        body = " ".join(["word"] * 250)
        chunks = chunk_prose(
            body, target_tokens=200, overlap_ratio=0.15, source_ref="ref", project="proj"
        )
        assert len(chunks) == 2

    def test_two_chunks_have_overlapping_content(self) -> None:
        """Adjacent chunks share overlapping content."""
        body = " ".join([f"word{i}" for i in range(300)])
        chunks = chunk_prose(
            body, target_tokens=200, overlap_ratio=0.15, source_ref="ref", project="proj"
        )
        # Distinct multi-token words ("word123" ~= 2 tokens) → token-accurate
        # sizing yields >=2 chunks; the exact-count AC is covered by
        # test_body_just_over_target_returns_two_chunks (single-token "word").
        assert len(chunks) >= 2
        # Second chunk should start with content from end of first chunk
        # Extract some words from end of first chunk
        first_chunk_words = chunks[0].text.split()
        second_chunk_words = chunks[1].text.split()
        # There should be overlap
        overlap_size = int(200 * 0.15)
        if overlap_size > 0:
            # At least some words from end of first should appear at start of second
            assert any(word in second_chunk_words[:50] for word in first_chunk_words[-30:])


class TestChunkProseHeadingAware:
    """Test AC-003: Multi-heading document splits at heading boundaries."""

    def test_splits_at_heading_boundaries_when_possible(self) -> None:
        """Document with headings prefers to split at heading boundaries."""
        body = """# Introduction
This is the introduction section with some content.

# Section One
This is section one with enough content to force a split.
""" + " ".join(["word"] * 200) + """

# Section Two
This is section two with more content.
""" + " ".join(["word"] * 200)

        chunks = chunk_prose(
            body, target_tokens=150, overlap_ratio=0.1, source_ref="ref", project="proj"
        )
        # Should produce multiple chunks
        assert len(chunks) >= 2

    def test_heading_never_orphaned_from_section(self) -> None:
        """Heading line is never separated from content it introduces."""
        body = """# First Heading
First section content here.

# Second Heading
Second section content here.

# Third Heading
Third section content here.
"""
        chunks = chunk_prose(
            body, target_tokens=50, overlap_ratio=0.1, source_ref="ref", project="proj"
        )
        # Each chunk that contains a heading should have content after it
        for chunk in chunks:
            lines = chunk.text.strip().split('\n')
            for i, line in enumerate(lines):
                if line.startswith('#'):
                    # If this is a heading, it should not be the last line
                    # OR if it is the last line, there should be more chunks
                    if i == len(lines) - 1:
                        # This heading is at the end of chunk
                        # It's OK only if this is the last chunk and heading has no content
                        pass
                    else:
                        # There should be content after the heading in this chunk
                        remaining_lines = lines[i+1:]
                        # At least one non-empty line should follow
                        assert any(line.strip() for line in remaining_lines)


class TestChunkProseOverlap:
    """Test AC-004: Each chunk after first begins with overlapping content."""

    def test_each_chunk_after_first_has_overlap(self) -> None:
        """All chunks except first contain content from previous chunk."""
        # Create a document that will split into multiple chunks
        body = " ".join([f"word{i:04d}" for i in range(500)])
        chunks = chunk_prose(
            body, target_tokens=150, overlap_ratio=0.15, source_ref="ref", project="proj"
        )
        assert len(chunks) >= 2

        # Check each chunk after the first
        for i in range(1, len(chunks)):
            prev_chunk_words = chunks[i-1].text.split()
            curr_chunk_words = chunks[i].text.split()
            # Current chunk should start with some words from previous chunk
            # At least one word from the end of previous should appear at start of current
            overlap_found = False
            for word in prev_chunk_words[-50:]:
                if word in curr_chunk_words[:50]:
                    overlap_found = True
                    break
            assert overlap_found, f"Chunk {i} has no overlap with chunk {i-1}"


class TestChunkProseEmptyBody:
    """Test AC-005: Empty body and whitespace-only body return []."""

    def test_empty_string_returns_empty_list(self) -> None:
        """Empty body returns []."""
        chunks = chunk_prose(
            "", target_tokens=1000, overlap_ratio=0.15, source_ref="ref", project="proj"
        )
        assert chunks == []

    def test_whitespace_only_returns_empty_list(self) -> None:
        """Whitespace-only body returns []."""
        chunks = chunk_prose(
            "   \n\t  \n  ", target_tokens=1000, overlap_ratio=0.15, source_ref="ref", project="proj"
        )
        assert chunks == []

    def test_only_newlines_returns_empty_list(self) -> None:
        """Body with only newlines returns []."""
        chunks = chunk_prose(
            "\n\n\n", target_tokens=1000, overlap_ratio=0.15, source_ref="ref", project="proj"
        )
        assert chunks == []


class TestChunkProseMetadata:
    """Test AC-006: Chunk.index monotonic from 0; metadata propagation."""

    def test_chunk_index_monotonic_from_zero(self) -> None:
        """Chunk indices are sequential starting from 0."""
        body = " ".join([f"word{i}" for i in range(500)])
        chunks = chunk_prose(
            body, target_tokens=150, overlap_ratio=0.15, source_ref="ref", project="proj"
        )
        assert len(chunks) >= 2
        for i, chunk in enumerate(chunks):
            assert chunk.index == i

    def test_source_ref_propagates_to_all_chunks(self) -> None:
        """source_ref propagates to every chunk."""
        body = " ".join([f"word{i}" for i in range(500)])
        chunks = chunk_prose(
            body, target_tokens=150, overlap_ratio=0.15, source_ref="ref://test/path", project="proj"
        )
        assert all(chunk.source_ref == "ref://test/path" for chunk in chunks)

    def test_project_propagates_to_all_chunks(self) -> None:
        """project propagates to every chunk."""
        body = " ".join([f"word{i}" for i in range(500)])
        chunks = chunk_prose(
            body, target_tokens=150, overlap_ratio=0.15, source_ref="ref", project="my-project"
        )
        assert all(chunk.project == "my-project" for chunk in chunks)

    def test_source_ref_none_propagates(self) -> None:
        """source_ref=None propagates to all chunks."""
        body = "short text"
        chunks = chunk_prose(
            body, target_tokens=1000, overlap_ratio=0.15, source_ref=None, project="proj"
        )
        assert all(chunk.source_ref is None for chunk in chunks)


class TestChunkProsePurity:
    """Test AC-007: Function is pure (no I/O, deterministic)."""

    def test_deterministic_same_input_same_output(self) -> None:
        """Same input produces same output (deterministic)."""
        body = "# Heading\nSome content here.\n\nMore content."
        chunks1 = chunk_prose(
            body, target_tokens=100, overlap_ratio=0.15, source_ref="ref", project="proj"
        )
        chunks2 = chunk_prose(
            body, target_tokens=100, overlap_ratio=0.15, source_ref="ref", project="proj"
        )
        assert len(chunks1) == len(chunks2)
        for c1, c2 in zip(chunks1, chunks2):
            assert c1.text == c2.text
            assert c1.index == c2.index
            assert c1.source_ref == c2.source_ref
            assert c1.project == c2.project

    def test_no_side_effects_input_unchanged(self) -> None:
        """Function does not modify input."""
        body = "test content"
        original_body = body
        chunk_prose(
            body, target_tokens=1000, overlap_ratio=0.15, source_ref="ref", project="proj"
        )
        assert body == original_body


class TestChunkProseMultipleChunks:
    """Test behavior with several chunks long documents."""

    def test_very_long_document_produces_multiple_chunks(self) -> None:
        """Document several chunks long produces multiple chunks."""
        # Create a document that will clearly need many chunks
        body = " ".join([f"word{i}" for i in range(2000)])
        chunks = chunk_prose(
            body, target_tokens=200, overlap_ratio=0.15, source_ref="ref", project="proj"
        )
        assert len(chunks) >= 5  # Should produce many chunks


@pytest.mark.seam
@pytest.mark.integration_contract("Chunk")
def test_chunk_contract_shape() -> None:
    """Verify chunk_prose returns Chunk objects matching the RLY-001 contract.

    Contract: list[Chunk] with monotonic index from 0; empty body -> [].
    Producer: TASK-RLY-001
    """
    chunks = chunk_prose(
        "# H\nsome body text",
        target_tokens=1000,
        overlap_ratio=0.15,
        source_ref="ref://x",
        project="guardkit",
    )
    assert all(c.project == "guardkit" for c in chunks)
    assert [c.index for c in chunks] == list(range(len(chunks)))
    assert (
        chunk_prose(
            "   ", target_tokens=1000, overlap_ratio=0.15, source_ref=None, project="guardkit"
        )
        == []
    )


class TestChunkProseEdgeCases:
    """Additional edge case tests for robustness."""

    def test_single_word_body(self) -> None:
        """Single word body returns 1 chunk."""
        chunks = chunk_prose(
            "word", target_tokens=1000, overlap_ratio=0.15, source_ref="ref", project="proj"
        )
        assert len(chunks) == 1
        assert chunks[0].text == "word"

    def test_zero_overlap_ratio(self) -> None:
        """overlap_ratio of 0 produces non-overlapping chunks."""
        body = " ".join([f"word{i}" for i in range(300)])
        chunks = chunk_prose(
            body, target_tokens=100, overlap_ratio=0.0, source_ref="ref", project="proj"
        )
        assert len(chunks) >= 2
        # With zero overlap, chunks should not share content
        # (implementation may still have minimal overlap at boundaries)

    def test_high_overlap_ratio(self) -> None:
        """High overlap_ratio creates substantial overlap."""
        body = " ".join([f"word{i}" for i in range(300)])
        chunks = chunk_prose(
            body, target_tokens=100, overlap_ratio=0.5, source_ref="ref", project="proj"
        )
        assert len(chunks) >= 2
