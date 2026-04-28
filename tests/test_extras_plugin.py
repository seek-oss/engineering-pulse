"""Tests for the drop-in extras plugin."""
from __future__ import annotations

from pathlib import Path

import pytest

from scripts.extras_plugin import (
    Extra,
    discover_extras,
    markdown_to_html,
    parse_extra,
    render_extras_section,
)


# ── discover_extras ────────────────────────────────────────────────────────


class TestDiscoverExtras:
    def test_missing_dir_returns_empty(self, tmp_path: Path) -> None:
        assert discover_extras(tmp_path / "does-not-exist") == []

    def test_empty_dir_returns_empty(self, tmp_path: Path) -> None:
        assert discover_extras(tmp_path) == []

    def test_discovers_md_files(self, tmp_path: Path) -> None:
        (tmp_path / "a.md").write_text("# A\n", encoding="utf-8")
        (tmp_path / "b.md").write_text("# B\n", encoding="utf-8")
        names = [p.name for p in discover_extras(tmp_path)]
        assert names == ["a.md", "b.md"]

    def test_skips_underscore_templates(self, tmp_path: Path) -> None:
        (tmp_path / "real.md").write_text("# real\n", encoding="utf-8")
        (tmp_path / "_example.md").write_text("# example\n", encoding="utf-8")
        (tmp_path / "_template.md").write_text("# template\n", encoding="utf-8")
        names = [p.name for p in discover_extras(tmp_path)]
        assert names == ["real.md"]

    def test_ignores_non_md_files(self, tmp_path: Path) -> None:
        (tmp_path / "a.md").write_text("# A\n", encoding="utf-8")
        (tmp_path / "b.txt").write_text("ignored", encoding="utf-8")
        (tmp_path / "c.markdown").write_text("ignored", encoding="utf-8")
        names = [p.name for p in discover_extras(tmp_path)]
        assert names == ["a.md"]

    def test_returns_sorted(self, tmp_path: Path) -> None:
        (tmp_path / "zebra.md").write_text("# z\n", encoding="utf-8")
        (tmp_path / "alpha.md").write_text("# a\n", encoding="utf-8")
        (tmp_path / "mango.md").write_text("# m\n", encoding="utf-8")
        names = [p.name for p in discover_extras(tmp_path)]
        assert names == ["alpha.md", "mango.md", "zebra.md"]


# ── parse_extra ────────────────────────────────────────────────────────────


class TestParseExtra:
    def test_extracts_first_h1_as_title(self, tmp_path: Path) -> None:
        f = tmp_path / "task.md"
        f.write_text("# Release checklist\n\nSome body.\n", encoding="utf-8")
        extra = parse_extra(f)
        assert extra.title == "Release checklist"
        assert "Some body" in extra.body_html
        assert extra.source == f

    def test_no_h1_uses_filename_stem(self, tmp_path: Path) -> None:
        f = tmp_path / "oncall-notes.md"
        f.write_text("Just some content with no heading.\n", encoding="utf-8")
        extra = parse_extra(f)
        assert extra.title == "oncall-notes"
        assert "Just some content" in extra.body_html

    def test_h2_only_does_not_become_title(self, tmp_path: Path) -> None:
        f = tmp_path / "x.md"
        f.write_text("## subheading\n\nbody\n", encoding="utf-8")
        extra = parse_extra(f)
        assert extra.title == "x"
        # ## should still render in the body (as h3 in our subset)
        assert "<h3>subheading</h3>" in extra.body_html

    def test_h1_with_inline_formatting(self, tmp_path: Path) -> None:
        f = tmp_path / "x.md"
        f.write_text("# Title with **bold** word\n\nbody\n", encoding="utf-8")
        extra = parse_extra(f)
        # The title is treated as plain text (escaped on render)
        assert extra.title == "Title with **bold** word"


# ── markdown_to_html ───────────────────────────────────────────────────────


class TestMarkdownToHtml:
    def test_empty_returns_empty(self) -> None:
        assert markdown_to_html("") == ""
        assert markdown_to_html("   \n  \n") == ""

    def test_paragraph(self) -> None:
        assert "<p>hello world</p>" in markdown_to_html("hello world")

    def test_headings(self) -> None:
        out = markdown_to_html("# H1\n\n## H2\n\n### H3")
        assert "<h2>H1</h2>" in out
        assert "<h3>H2</h3>" in out
        assert "<h4>H3</h4>" in out

    def test_bullet_list(self) -> None:
        out = markdown_to_html("- one\n- two\n- three")
        assert out.count("<li>") == 3
        assert "<ul>" in out and "</ul>" in out

    def test_numbered_list(self) -> None:
        out = markdown_to_html("1. one\n2. two")
        assert "<ol>" in out and "</ol>" in out
        assert out.count("<li>") == 2

    def test_bold_italic_code(self) -> None:
        out = markdown_to_html("text with **bold**, *italic*, and `code`.")
        assert "<strong>bold</strong>" in out
        assert "<em>italic</em>" in out
        assert "<code>code</code>" in out

    def test_link(self) -> None:
        out = markdown_to_html("[click](https://example.com)")
        assert '<a href="https://example.com">click</a>' in out

    def test_autolink_bare_url(self) -> None:
        out = markdown_to_html("see https://example.com for more")
        assert '<a href="https://example.com">https://example.com</a>' in out

    def test_fenced_code_block(self) -> None:
        src = "```\necho hi\n```"
        out = markdown_to_html(src)
        assert "<pre><code>echo hi</code></pre>" in out

    def test_fenced_code_block_escapes_html(self) -> None:
        src = "```\n<script>x</script>\n```"
        out = markdown_to_html(src)
        assert "&lt;script&gt;" in out
        assert "<script>" not in out

    def test_inline_html_is_escaped(self) -> None:
        out = markdown_to_html("hello <script>alert(1)</script> world")
        assert "<script>" not in out
        assert "&lt;script&gt;" in out

    def test_consecutive_paragraphs(self) -> None:
        out = markdown_to_html("first paragraph.\n\nsecond paragraph.")
        assert out.count("<p>") == 2

    def test_paragraph_lines_joined(self) -> None:
        # Multi-line paragraph (no blank line) should be one <p>
        out = markdown_to_html("line one\nline two")
        assert out.count("<p>") == 1
        assert "line one line two" in out

    def test_list_then_paragraph(self) -> None:
        out = markdown_to_html("- item\n\nafter")
        assert "<ul>" in out
        assert "</ul>" in out
        assert "<p>after</p>" in out


# ── render_extras_section ─────────────────────────────────────────────────


class TestRenderExtrasSection:
    def test_missing_dir_returns_none(self, tmp_path: Path) -> None:
        assert render_extras_section(tmp_path / "missing") is None

    def test_empty_dir_returns_none(self, tmp_path: Path) -> None:
        assert render_extras_section(tmp_path) is None

    def test_only_underscore_files_returns_none(self, tmp_path: Path) -> None:
        (tmp_path / "_example.md").write_text("# example\n", encoding="utf-8")
        assert render_extras_section(tmp_path) is None

    def test_renders_one_card_per_file(self, tmp_path: Path) -> None:
        (tmp_path / "a.md").write_text("# Alpha\n\nBody A\n", encoding="utf-8")
        (tmp_path / "b.md").write_text("# Beta\n\nBody B\n", encoding="utf-8")
        out = render_extras_section(tmp_path)
        assert out is not None
        assert out.count("extra-card") == 2
        assert "Alpha" in out and "Beta" in out
        assert "Body A" in out and "Body B" in out

    def test_uses_default_label(self, tmp_path: Path) -> None:
        (tmp_path / "x.md").write_text("# X\n", encoding="utf-8")
        out = render_extras_section(tmp_path)
        assert out is not None
        assert "Part E — Extras" in out

    def test_custom_label(self, tmp_path: Path) -> None:
        (tmp_path / "x.md").write_text("# X\n", encoding="utf-8")
        out = render_extras_section(tmp_path, label="Custom")
        assert out is not None
        assert "Custom" in out

    def test_title_is_escaped(self, tmp_path: Path) -> None:
        (tmp_path / "x.md").write_text("# <evil>\n\nbody\n", encoding="utf-8")
        out = render_extras_section(tmp_path)
        assert out is not None
        assert "<evil>" not in out
        assert "&lt;evil&gt;" in out
