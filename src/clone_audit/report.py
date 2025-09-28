"""Report generation for clone audit analysis."""
from __future__ import annotations

import base64
import io
import json
from datetime import datetime
from difflib import SequenceMatcher
from typing import TYPE_CHECKING, Any, Dict, List, Optional

import requests

from .config import ReportConfig
from .models import (
    HostingRecord,
    ImageArtifact,
    ImageMatch,
    StructureMatch,
    TextMatch,
    WhoisRecord,
)
from .screenshots import ScreenshotError, capture_homepage
from .utils import canonical_path

if TYPE_CHECKING:  # pragma: no cover - type hints only
    from .analyzer import AnalysisResult


class ReportBuilder:
    def __init__(self, config: ReportConfig) -> None:
        self.config = config
        self._image_sequence = 0

    def build_markdown(self, analysis: "AnalysisResult") -> str:
        lines: List[str] = []
        comparison = analysis.comparison
        base_crawl = analysis.base.crawl
        clone_crawl = analysis.clone.crawl
        lines.append("# Clone Similarity Report")
        lines.append("")
        lines.append(f"**Base URL:** {analysis.base.crawl.root_url}")
        lines.append(f"**Clone URL:** {analysis.clone.crawl.root_url}")
        lines.append("")
        lines.append("## Similarity Overview")
        lines.append(
            f"- Overall similarity: {comparison.breakdown.overall_score:.2%}"
        )
        lines.append(f"- Text similarity: {comparison.breakdown.text_score:.2%}")
        lines.append(f"- Image similarity: {comparison.breakdown.image_score:.2%}")
        lines.append(
            f"- Structural similarity: {comparison.breakdown.structure_score:.2%}"
        )
        lines.append("")
        lines.append("## Crawl Statistics")
        lines.append(
            f"- Base pages crawled: {len(base_crawl.snapshots)} (errors: {len(base_crawl.errors)})"
        )
        lines.append(
            f"- Clone pages crawled: {len(clone_crawl.snapshots)} (errors: {len(clone_crawl.errors)})"
        )
        lines.append("")
        lines.extend(self._render_text_matches(comparison.text_matches))
        lines.extend(self._render_image_matches(comparison.image_matches))
        lines.extend(self._render_structure_matches(comparison.structure_matches))
        lines.extend(self._render_whois_section(analysis.base_whois, analysis.clone_whois))
        lines.extend(
            self._render_hosting_section(
                getattr(analysis, "base_hosting", None),
                getattr(analysis, "clone_hosting", None),
            )
        )
        if self.config.include_errors:
            lines.extend(self._render_errors(base_crawl.errors, clone_crawl.errors))
        return "\n".join(lines).strip() + "\n"

    def build_json(self, analysis: "AnalysisResult") -> Dict[str, Any]:
        comparison = analysis.comparison
        return {
            "summary": {
                "base_url": analysis.base.crawl.root_url,
                "clone_url": analysis.clone.crawl.root_url,
                "scores": {
                    "overall": comparison.breakdown.overall_score,
                    "text": comparison.breakdown.text_score,
                    "images": comparison.breakdown.image_score,
                    "structure": comparison.breakdown.structure_score,
                },
            },
            "text_matches": [self._serialise_text_match(match) for match in comparison.text_matches],
            "image_matches": [self._serialise_image_match(match) for match in comparison.image_matches],
            "structure_matches": [self._serialise_structure_match(match) for match in comparison.structure_matches],
            "whois": {
                "base": self._serialise_whois(analysis.base_whois),
                "clone": self._serialise_whois(analysis.clone_whois),
            },
            "hosting": {
                "base": self._serialise_hosting(getattr(analysis, "base_hosting", None)),
                "clone": self._serialise_hosting(getattr(analysis, "clone_hosting", None)),
            },
            "errors": {
                "base": list(analysis.base.crawl.errors),
                "clone": list(analysis.clone.crawl.errors),
            },
        }

    def build_pdf(self, analysis: "AnalysisResult", output_path: str) -> None:
        try:  # defer import so PDF support stays optional
            from fpdf import FPDF
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise RuntimeError(
                "PDF output requested but the optional dependency 'fpdf2' is not installed."
            ) from exc

        pdf = FPDF()
        pdf.set_auto_page_break(auto=True, margin=15)
        pdf.add_page()
        pdf.set_title("Clone Similarity Report")
        self._image_sequence = 0

        comparison = analysis.comparison
        self._pdf_add_header(pdf, analysis)
        pdf.ln(2)
        self._pdf_add_quick_stats(pdf, analysis)
        pdf.ln(4)
        self._pdf_add_key_highlights(pdf, analysis)
        pdf.ln(3)

        self._add_homepage_section(pdf, analysis)

        self._pdf_add_text_matches(pdf, comparison.text_matches)
        self._pdf_add_image_matches(pdf, comparison.image_matches)
        self._pdf_add_structure_summary(pdf, comparison.structure_matches)
        self._pdf_add_whois_summary(pdf, analysis)
        self._pdf_add_hosting_summary(pdf, analysis)

        pdf.output(output_path)

    def _pdf_add_header(self, pdf, analysis: "AnalysisResult") -> None:
        pdf.set_font("Helvetica", "B", 17)
        pdf.cell(0, 10, "Clone Similarity Report", ln=1)

        pdf.set_font("Helvetica", size=11)
        self._pdf_text(pdf, f"Base URL: {analysis.base.crawl.root_url}", line_height=6)
        self._pdf_text(pdf, f"Clone URL: {analysis.clone.crawl.root_url}", line_height=6)

        generated = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
        self._pdf_text(pdf, f"Generated: {generated}", line_height=6)

    def _pdf_add_quick_stats(self, pdf, analysis: "AnalysisResult") -> None:
        pdf.set_font("Helvetica", "B", 14)
        pdf.cell(0, 8, "Quick Stats", ln=1)

        stats = self._build_quick_stats(analysis)
        if not stats:
            return
        current_y = pdf.get_y()
        used_height = self._pdf_stat_cards(pdf, stats, start_y=current_y)
        next_y = current_y + used_height + 4
        pdf.set_xy(pdf.l_margin, next_y)

    def _build_quick_stats(self, analysis: "AnalysisResult") -> List[Dict[str, str]]:
        comparison = analysis.comparison
        base_crawl = analysis.base.crawl
        clone_crawl = analysis.clone.crawl
        stats: List[Dict[str, str]] = []

        stats.append(
            {
                "title": "Overall Similarity",
                "value": f"{comparison.breakdown.overall_score:.0%}",
                "detail": (
                    f"Text {comparison.breakdown.text_score:.0%} | "
                    f"Visual {comparison.breakdown.image_score:.0%} | "
                    f"Structure {comparison.breakdown.structure_score:.0%}"
                ),
            }
        )
        stats.append(
            {
                "title": "Text Alignment",
                "value": f"{comparison.breakdown.text_score:.0%}",
                "detail": f"{len(comparison.text_matches)} strong overlaps",
            }
        )
        stats.append(
            {
                "title": "Visual Overlap",
                "value": f"{comparison.breakdown.image_score:.0%}",
                "detail": f"{len(comparison.image_matches)} hash collisions",
            }
        )
        stats.append(
            {
                "title": "Structural Borrowing",
                "value": f"{comparison.breakdown.structure_score:.0%}",
                "detail": f"{len(comparison.structure_matches)} layout echoes",
            }
        )
        stats.append(
            {
                "title": "Base Coverage",
                "value": f"{len(base_crawl.snapshots)} pages",
                "detail": f"{len(base_crawl.errors)} crawl errors",
            }
        )
        stats.append(
            {
                "title": "Clone Coverage",
                "value": f"{len(clone_crawl.snapshots)} pages",
                "detail": f"{len(clone_crawl.errors)} crawl errors",
            }
        )
        hosting_stat = self._build_hosting_stat(analysis)
        if hosting_stat:
            stats.append(hosting_stat)
        return stats

    def _build_hosting_stat(self, analysis: "AnalysisResult") -> Optional[Dict[str, str]]:
        base_host = getattr(analysis, "base_hosting", None)
        clone_host = getattr(analysis, "clone_hosting", None)
        if base_host is None and clone_host is None:
            return None

        base_name = self._preferred_host_name(base_host)
        clone_name = self._preferred_host_name(clone_host)

        if base_host and base_host.error and clone_host and clone_host.error:
            return {
                "title": "Hosting Lookup",
                "value": "Unavailable",
                "detail": "Both RDAP lookups failed",
            }

        if base_name and clone_name:
            same_provider = self._normalize_host_label(base_name) == self._normalize_host_label(clone_name)
            value = "Match" if same_provider else "Different"
            detail = base_name if same_provider else f"{base_name} vs {clone_name}"
            return {
                "title": "Hosting Lookup",
                "value": value,
                "detail": detail,
            }

        if base_name or clone_name:
            known = base_name or clone_name
            context = "base" if base_name else "clone"
            return {
                "title": "Hosting Lookup",
                "value": "Partial",
                "detail": f"Only {context} resolved to {known}",
            }

        # Fallback to IP comparison if names unavailable
        base_ip = base_host.ip if base_host else None
        clone_ip = clone_host.ip if clone_host else None
        if base_ip and clone_ip:
            same_ip = base_ip == clone_ip
            value = "Shared IP" if same_ip else "Separate IPs"
            detail = f"{base_ip} vs {clone_ip}" if not same_ip else base_ip
            return {
                "title": "Hosting Lookup",
                "value": value,
                "detail": detail,
            }
        if base_ip or clone_ip:
            context = "base" if base_ip else "clone"
            ip_value = base_ip or clone_ip
            return {
                "title": "Hosting Lookup",
                "value": "IP only",
                "detail": f"Only {context} resolved ({ip_value})",
            }
        return None

    @staticmethod
    def _preferred_host_name(record: Optional[HostingRecord]) -> Optional[str]:
        if record is None or record.error:
            return None
        if record.organization:
            return record.organization
        return record.network_name

    @staticmethod
    def _normalize_host_label(value: str) -> str:
        return value.strip().lower()

    def _pdf_stat_cards(
        self,
        pdf,
        stats: List[Dict[str, str]],
        start_y: float,
        columns: int = 3,
        gap: float = 4.0,
    ) -> float:
        if not stats:
            return 0.0

        card_height = 26.0
        available_width = pdf.w - pdf.l_margin - pdf.r_margin
        card_width = (available_width - gap * (columns - 1)) / columns
        bottom_y = start_y

        for index, stat in enumerate(stats):
            column = index % columns
            row = index // columns
            x = pdf.l_margin + column * (card_width + gap)
            y = start_y + row * (card_height + gap)

            pdf.set_fill_color(247, 249, 255)
            pdf.set_draw_color(214, 221, 236)
            pdf.rect(x, y, card_width, card_height, style="DF")

            pdf.set_xy(x + 2, y + 4)
            pdf.set_font("Helvetica", "B", 8)
            pdf.set_text_color(90, 98, 125)
            pdf.cell(card_width - 4, 4, stat.get("title", "").upper())

            pdf.set_xy(x + 2, y + 10)
            pdf.set_font("Helvetica", "B", 14)
            pdf.set_text_color(32, 38, 55)
            pdf.cell(card_width - 4, 6, stat.get("value", ""))

            pdf.set_xy(x + 2, y + 17)
            pdf.set_font("Helvetica", size=8.5)
            pdf.set_text_color(82, 90, 115)
            detail = stat.get("detail", "")
            self._pdf_wrapped_text(pdf, detail, card_width - 4, line_height=3.8)

            bottom_y = max(bottom_y, y + card_height)

        pdf.set_text_color(0, 0, 0)
        return bottom_y - start_y

    def _pdf_wrapped_text(self, pdf, text: str, width: float, line_height: float = 4.0) -> float:
        if not text:
            return 0.0
        start_x = pdf.get_x()
        start_y = pdf.get_y()
        pdf.multi_cell(width, line_height, text)
        height = pdf.get_y() - start_y
        pdf.set_xy(start_x, start_y + height)
        return height

    def _pdf_add_key_highlights(self, pdf, analysis: "AnalysisResult") -> None:
        pdf.set_font("Helvetica", "B", 14)
        pdf.cell(0, 8, "Key Highlights", ln=1)
        pdf.set_font("Helvetica", size=11)

        lines: List[str] = []
        top_text = self._top_text_match(analysis.comparison.text_matches)
        if top_text:
            lines.append(
                f"Text overlap peaks at {top_text.similarity:.0%} on {self._truncate(top_text.base.page_url)}"
            )

        top_image = self._top_image_match(analysis.comparison.image_matches)
        if top_image:
            lines.append(
                f"Closest image pair scores {top_image.similarity:.0%} (distance {top_image.hamming_distance})"
            )

        if analysis.comparison.structure_matches:
            structure_peak = max(analysis.comparison.structure_matches, key=lambda m: m.similarity)
            lines.append(
                f"Structural reuse up to {structure_peak.similarity:.0%} on {self._truncate(structure_peak.clone.page_url)}"
            )

        hosting_summary = self._hosting_alignment_summary(analysis)
        if hosting_summary:
            lines.append(hosting_summary)

        timings = analysis.timings
        total_time = timings.total
        if total_time:
            crawl_time = sum(timings.crawl.values())
            extract_time = sum(timings.extract.values())
            whois_time = sum(timings.whois.values())
            lines.append(
                "Run time {:.1f}s (crawl {:.1f}s | extract {:.1f}s | compare {:.1f}s | whois {:.1f}s)".format(
                    total_time,
                    crawl_time,
                    extract_time,
                    timings.compare,
                    whois_time,
                )
            )

        if not lines:
            lines.append("No high-similarity indicators surfaced in this run.")

        for line in lines:
            self._pdf_text(pdf, f"- {line}", line_height=6)

    @staticmethod
    def _truncate(text: str, limit: int = 72) -> str:
        if len(text) <= limit:
            return text
        return text[: limit - 3] + "..."

    @staticmethod
    def _top_text_match(matches: List[TextMatch]) -> Optional[TextMatch]:
        if not matches:
            return None
        return max(matches, key=lambda match: match.similarity)

    @staticmethod
    def _top_image_match(matches: List[ImageMatch]) -> Optional[ImageMatch]:
        if not matches:
            return None
        return max(matches, key=lambda match: match.similarity)

    def _hosting_alignment_summary(self, analysis: "AnalysisResult") -> Optional[str]:
        base_host = getattr(analysis, "base_hosting", None)
        clone_host = getattr(analysis, "clone_hosting", None)
        if base_host is None and clone_host is None:
            return None

        base_name = self._preferred_host_name(base_host)
        clone_name = self._preferred_host_name(clone_host)

        if base_host and base_host.error and clone_host and clone_host.error:
            return "Hosting lookups failed for both sites"

        if base_name and clone_name:
            if self._normalize_host_label(base_name) == self._normalize_host_label(clone_name):
                return f"Both sites appear hosted by {base_name}"
            return f"Hosting differs: {base_name} vs {clone_name}"

        if base_name or clone_name:
            name = base_name or clone_name
            context = "base" if base_name else "clone"
            return f"Only the {context} host resolved ({name})"

        base_ip = base_host.ip if base_host else None
        clone_ip = clone_host.ip if clone_host else None
        if base_ip and clone_ip:
            if base_ip == clone_ip:
                return f"Both sites share IP {base_ip}"
            return f"Hosting IPs differ: {base_ip} vs {clone_ip}"
        if base_ip or clone_ip:
            context = "base" if base_ip else "clone"
            ip_value = base_ip or clone_ip
            return f"Only the {context} IP resolved ({ip_value})"
        return None

    def _pdf_add_text_matches(self, pdf, matches: List[TextMatch]) -> None:
        pdf.set_font("Helvetica", "B", 14)
        pdf.cell(0, 8, "Key Text Overlaps", ln=1)

        if not matches:
            pdf.set_font("Helvetica", size=10)
            self._pdf_text(pdf, "No high-similarity text matches detected", line_height=6)
            pdf.ln(3)
            return

        for index, match in enumerate(matches, start=1):
            self._pdf_text_match_card(pdf, index, match)

    def _pdf_text_match_card(self, pdf, index: int, match: TextMatch) -> None:
        label = f"Match {index}: {match.similarity:.0%} similarity"
        if match.high_confidence:
            label += " (high confidence)"

        pdf.set_font("Helvetica", "B", 11)
        self._pdf_text(pdf, label, line_height=6)

        pdf.set_font("Helvetica", size=9)
        self._pdf_text(pdf, f"Base page: {match.base.page_url}", line_height=5.5)
        self._pdf_text(pdf, f"Clone page: {match.clone.page_url}", line_height=5.5)

        shared_phrase = self._extract_shared_phrase(match)
        if shared_phrase:
            pdf.ln(1)
            pdf.set_text_color(36, 80, 170)
            pdf.set_font("Helvetica", "B", 10)
            self._pdf_text(pdf, f"Shared phrase: \"{shared_phrase}\"", line_height=5.5)
            pdf.set_text_color(0, 0, 0)

        pdf.ln(1)
        self._pdf_labeled_paragraph(pdf, "Base excerpt", match.base.snippet(240))
        pdf.ln(1)
        self._pdf_labeled_paragraph(pdf, "Clone excerpt", match.clone.snippet(240))
        pdf.ln(4)

    def _extract_shared_phrase(self, match: TextMatch, min_chars: int = 18) -> Optional[str]:
        base_text = match.base.text
        clone_text = match.clone.text
        if not base_text or not clone_text:
            return None

        matcher = SequenceMatcher(None, base_text, clone_text)
        block = matcher.find_longest_match(0, len(base_text), 0, len(clone_text))
        if block.size < min_chars:
            return None
        phrase = base_text[block.a : block.a + block.size].strip()
        if len(phrase) > 140:
            phrase = phrase[:137].rstrip() + "..."
        return " ".join(phrase.split())

    def _pdf_labeled_paragraph(self, pdf, label: str, text: str) -> None:
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_fill_color(236, 240, 248)
        pdf.set_text_color(82, 90, 115)
        pdf.cell(0, 5, label.upper(), ln=1, fill=True)

        pdf.set_text_color(0, 0, 0)
        pdf.set_font("Helvetica", size=10)
        self._pdf_text(pdf, text, line_height=5.2)

    def _pdf_add_image_matches(self, pdf, matches: List[ImageMatch]) -> None:
        pdf.set_font("Helvetica", "B", 14)
        pdf.cell(0, 8, "Visual Similarities", ln=1)

        if not matches:
            pdf.set_font("Helvetica", size=10)
            self._pdf_text(pdf, "No matching image hashes detected", line_height=6)
            pdf.ln(3)
            return

        for index, match in enumerate(matches, start=1):
            self._pdf_image_match_card(pdf, index, match)

    def _pdf_image_match_card(self, pdf, index: int, match: ImageMatch) -> None:
        pdf.set_font("Helvetica", "B", 11)
        self._pdf_text(
            pdf,
            f"Match {index}: {match.similarity:.0%} similarity (distance {match.hamming_distance})",
            line_height=6,
        )

        pdf.set_font("Helvetica", size=9)
        self._pdf_text(pdf, f"Base asset: {match.base.url}", line_height=5.2)
        self._pdf_text(pdf, f"Clone asset: {match.clone.url}", line_height=5.2)

        pdf.ln(1)
        self._pdf_dual_artifact_preview(pdf, match.base, match.clone)
        pdf.ln(4)

    def _pdf_dual_artifact_preview(self, pdf, base: ImageArtifact, clone: ImageArtifact) -> None:
        available_width = pdf.w - pdf.l_margin - pdf.r_margin
        gap = 8
        column_width = (available_width - gap) / 2
        start_y = pdf.get_y()
        left_x = pdf.l_margin
        right_x = left_x + column_width + gap

        pdf.set_font("Helvetica", "B", 9)
        pdf.set_xy(left_x, start_y)
        pdf.cell(column_width, 5, "Base preview")
        pdf.set_xy(right_x, start_y)
        pdf.cell(column_width, 5, "Clone preview")

        image_top = start_y + 5
        base_height = self._pdf_embed_artifact_image(pdf, base, left_x, image_top, column_width)
        clone_height = self._pdf_embed_artifact_image(pdf, clone, right_x, image_top, column_width)

        row_height = max(base_height, clone_height)
        pdf.set_y(image_top + row_height)

    def _pdf_homepage_preview(
        self,
        pdf,
        base_bytes: Optional[bytes],
        clone_bytes: Optional[bytes],
    ) -> None:
        available_width = pdf.w - pdf.l_margin - pdf.r_margin
        gap = 8
        column_width = (available_width - gap) / 2
        start_y = pdf.get_y()
        left_x = pdf.l_margin
        right_x = left_x + column_width + gap

        pdf.set_font("Helvetica", "B", 9)
        pdf.set_xy(left_x, start_y)
        pdf.cell(column_width, 5, "Base homepage")
        pdf.set_xy(right_x, start_y)
        pdf.cell(column_width, 5, "Clone homepage")

        image_top = start_y + 5
        base_height = self._pdf_embed_image_bytes(pdf, base_bytes, left_x, image_top, column_width)
        clone_height = self._pdf_embed_image_bytes(pdf, clone_bytes, right_x, image_top, column_width)

        pdf.set_y(image_top + max(base_height, clone_height))

    def _pdf_embed_artifact_image(
        self,
        pdf,
        artifact: ImageArtifact,
        x: float,
        y: float,
        width: float,
    ) -> float:
        image_bytes = self._resolve_image_bytes(artifact)
        if not image_bytes:
            pdf.set_xy(x, y + 4)
            pdf.set_font("Helvetica", size=9)
            pdf.set_text_color(120, 120, 120)
            self._pdf_wrapped_text(pdf, "Preview unavailable", width, line_height=4.2)
            pdf.set_text_color(0, 0, 0)
            return 16.0

        stream = io.BytesIO(image_bytes)
        stream.name = self._next_image_name("artifact")
        pdf.set_draw_color(214, 221, 236)
        info = pdf.image(stream, x=x, y=y, w=width)
        pdf.rect(x, y, info.rendered_width, info.rendered_height)
        pdf.set_draw_color(0, 0, 0)
        return info.rendered_height

    def _pdf_embed_image_bytes(
        self,
        pdf,
        image_bytes: Optional[bytes],
        x: float,
        y: float,
        width: float,
    ) -> float:
        if not image_bytes:
            pdf.set_xy(x, y + 4)
            pdf.set_font("Helvetica", size=9)
            pdf.set_text_color(120, 120, 120)
            self._pdf_wrapped_text(pdf, "Snapshot unavailable", width, line_height=4.2)
            pdf.set_text_color(0, 0, 0)
            return 16.0

        stream = io.BytesIO(image_bytes)
        stream.name = self._next_image_name("homepage")
        pdf.set_draw_color(214, 221, 236)
        try:
            info = pdf.image(stream, x=x, y=y, w=width)
        except RuntimeError:
            pdf.set_draw_color(0, 0, 0)
            pdf.set_xy(x, y + 4)
            pdf.set_font("Helvetica", size=9)
            pdf.set_text_color(120, 120, 120)
            self._pdf_wrapped_text(pdf, "Unable to embed snapshot", width, line_height=4.2)
            pdf.set_text_color(0, 0, 0)
            return 16.0
        pdf.rect(x, y, info.rendered_width, info.rendered_height)
        pdf.set_draw_color(0, 0, 0)
        return info.rendered_height

    def _next_image_name(self, prefix: str) -> str:
        self._image_sequence += 1
        return f"{prefix}_{self._image_sequence}.png"

    def _pdf_add_structure_summary(self, pdf, matches: List[StructureMatch]) -> None:
        pdf.set_font("Helvetica", "B", 14)
        pdf.cell(0, 8, "Structural Echoes", ln=1)

        if not matches:
            pdf.set_font("Helvetica", size=10)
            self._pdf_text(pdf, "No structural overlaps above threshold", line_height=6)
            pdf.ln(3)
            return

        pdf.set_font("Helvetica", size=10)
        for match in matches:
            self._pdf_text(
                pdf,
                f"{match.similarity:.0%} similarity | base: {match.base.page_url} | clone: {match.clone.page_url}",
                line_height=5.5,
            )
        pdf.ln(4)

    def _pdf_add_whois_summary(self, pdf, analysis: "AnalysisResult") -> None:
        pdf.set_font("Helvetica", "B", 14)
        pdf.cell(0, 8, "WHOIS Summary", ln=1)
        self._pdf_whois_block(pdf, "Base domain", analysis.base_whois)
        self._pdf_whois_block(pdf, "Clone domain", analysis.clone_whois)

    def _pdf_add_hosting_summary(self, pdf, analysis: "AnalysisResult") -> None:
        base_host = getattr(analysis, "base_hosting", None)
        clone_host = getattr(analysis, "clone_hosting", None)
        if base_host is None and clone_host is None:
            return

        pdf.set_font("Helvetica", "B", 14)
        pdf.cell(0, 8, "Hosting Providers", ln=1)
        self._pdf_hosting_block(pdf, "Base site", base_host)
        self._pdf_hosting_block(pdf, "Clone site", clone_host)
        pdf.ln(2)

    def _pdf_hosting_block(self, pdf, heading: str, record: Optional[HostingRecord]) -> None:
        pdf.set_font("Helvetica", "B", 12)
        pdf.cell(0, 6, heading, ln=1)
        pdf.set_font("Helvetica", size=10)
        if record is None:
            self._pdf_text(pdf, "No hosting data captured")
            pdf.ln(1)
            return
        if record.error:
            self._pdf_text(pdf, f"Error: {record.error}")
            pdf.ln(1)
            return
        if record.ip:
            self._pdf_text(pdf, f"IP: {record.ip}")
        name = self._preferred_host_name(record)
        if name:
            self._pdf_text(pdf, f"Provider: {name}")
        elif record.network_name:
            self._pdf_text(pdf, f"Network: {record.network_name}")
        if record.country:
            self._pdf_text(pdf, f"Country: {record.country}")
        if record.source:
            self._pdf_text(pdf, f"RDAP source: {record.source}")
        pdf.ln(1)

    def _render_text_matches(self, matches: List[TextMatch]) -> List[str]:
        if not matches:
            return ["## Text Matches", "- No high-similarity text matches detected", ""]
        lines = ["## Text Matches"]
        for match in matches:
            confidence_flag = " (high confidence)" if match.high_confidence else ""
            lines.append(
                f"- {match.similarity:.2%}{confidence_flag} | base: {match.base.page_url} | clone: {match.clone.page_url}"
            )
            lines.append(
                f"  - base snippet: `{match.base.snippet(120)}`"
            )
            lines.append(
                f"  - clone snippet: `{match.clone.snippet(120)}`"
            )
        lines.append("")
        return lines

    def _render_image_matches(self, matches: List[ImageMatch]) -> List[str]:
        if not matches:
            return ["## Image Matches", "- No matching image hashes detected", ""]
        lines = ["## Image Matches"]
        for match in matches:
            lines.append(
                "- {score:.2%} similarity | base: {base} | clone: {clone} | distance: {distance}".format(
                    score=match.similarity,
                    base=match.base.url,
                    clone=match.clone.url,
                    distance=match.hamming_distance,
                )
            )
        lines.append("")
        return lines

    def _render_structure_matches(self, matches: List[StructureMatch]) -> List[str]:
        if not matches:
            return ["## Structural Matches", "- No structural overlaps above threshold", ""]
        lines = ["## Structural Matches"]
        for match in matches:
            lines.append(
                "- {score:.2%} similarity | base: {base} | clone: {clone}".format(
                    score=match.similarity,
                    base=match.base.page_url,
                    clone=match.clone.page_url,
                )
            )
        lines.append("")
        return lines

    def _render_whois_section(self, base: WhoisRecord, clone: WhoisRecord) -> List[str]:
        lines = ["## WHOIS Summary"]
        lines.append("### Base Domain")
        lines.extend(self._format_whois(base))
        lines.append("")
        lines.append("### Clone Domain")
        lines.extend(self._format_whois(clone))
        lines.append("")
        return lines

    def _render_hosting_section(
        self,
        base: Optional[HostingRecord],
        clone: Optional[HostingRecord],
    ) -> List[str]:
        lines = ["## Hosting Providers"]
        lines.append("### Base Site")
        lines.extend(self._format_hosting(base))
        lines.append("")
        lines.append("### Clone Site")
        lines.extend(self._format_hosting(clone))
        lines.append("")
        return lines

    def _format_hosting(self, record: Optional[HostingRecord]) -> List[str]:
        if record is None:
            return ["- No hosting data captured"]
        if record.error:
            return [f"- Error: {record.error}"]

        lines = []
        if record.ip:
            lines.append(f"- IP address: {record.ip}")
        if record.organization:
            lines.append(f"- Provider: {record.organization}")
        if record.network_name and self._normalize_host_label(record.network_name) != self._normalize_host_label(record.organization or ""):
            lines.append(f"- Network: {record.network_name}")
        if record.country:
            lines.append(f"- Country: {record.country}")
        if record.source:
            lines.append(f"- RDAP: {record.source}")
        if not lines:
            lines.append("- Hosting details unavailable")
        if self.config.include_raw_data and record.raw is not None:
            raw_json = json.dumps(record.raw, indent=2, sort_keys=True)
            lines.append("- Raw RDAP:")
            lines.append("  ```json")
            for raw_line in raw_json.splitlines():
                lines.append(f"  {raw_line}")
            lines.append("  ```")
        return lines

    def _render_errors(self, base_errors: List[str], clone_errors: List[str]) -> List[str]:
        if not base_errors and not clone_errors:
            return []
        lines = ["## Crawl Errors"]
        if base_errors:
            lines.append("### Base Site")
            lines.extend(f"- {err}" for err in base_errors)
        if clone_errors:
            lines.append("### Clone Site")
            lines.extend(f"- {err}" for err in clone_errors)
        lines.append("")
        return lines

    def _format_whois(self, record: WhoisRecord) -> List[str]:
        if record.error:
            return [f"- Error: {record.error}"]
        lines = []
        lines.append(f"- Registrar: {record.registrar or 'Unknown'}")
        lines.append(f"- Created: {self._format_date(record.creation_date)}")
        lines.append(f"- Updated: {self._format_date(record.updated_date)}")
        lines.append(f"- Expires: {self._format_date(record.expiration_date)}")
        if record.name_servers:
            lines.append(
                "- Name servers: " + ", ".join(record.name_servers)
            )
        if self.config.include_raw_data and record.raw_text:
            lines.append("- Raw WHOIS:")
            lines.append("  ```")
            lines.extend(f"  {line}" for line in record.raw_text.splitlines())
            lines.append("  ```")
        return lines

    def _serialise_text_match(self, match: TextMatch) -> Dict[str, Any]:
        return {
            "similarity": match.similarity,
            "high_confidence": match.high_confidence,
            "base": {
                "url": match.base.page_url,
                "locator": match.base.locator,
                "text": match.base.text if self.config.include_raw_data else match.base.snippet(),
            },
            "clone": {
                "url": match.clone.page_url,
                "locator": match.clone.locator,
                "text": match.clone.text if self.config.include_raw_data else match.clone.snippet(),
            },
        }

    def _serialise_image_match(self, match: ImageMatch) -> Dict[str, Any]:
        return {
            "similarity": match.similarity,
            "hamming_distance": match.hamming_distance,
            "base": self._serialise_image_artifact(match.base),
            "clone": self._serialise_image_artifact(match.clone),
        }

    def _serialise_structure_match(self, match: StructureMatch) -> Dict[str, Any]:
        return {
            "similarity": match.similarity,
            "base": {
                "url": match.base.page_url,
                "depth": match.base.depth,
            },
            "clone": {
                "url": match.clone.page_url,
                "depth": match.clone.depth,
            },
        }

    @staticmethod
    def _serialise_whois(record: WhoisRecord) -> Dict[str, Any]:
        return {
            "domain": record.domain,
            "registrar": record.registrar,
            "creation_date": record.creation_date.isoformat() if record.creation_date else None,
            "updated_date": record.updated_date.isoformat() if record.updated_date else None,
            "expiration_date": record.expiration_date.isoformat() if record.expiration_date else None,
            "name_servers": list(record.name_servers),
            "error": record.error,
        }

    def _serialise_hosting(self, record: Optional[HostingRecord]) -> Dict[str, Any]:
        if record is None:
            return {}
        data: Dict[str, Any] = {
            "domain": record.domain,
            "ip": record.ip,
            "network_name": record.network_name,
            "organization": record.organization,
            "country": record.country,
            "source": record.source,
            "error": record.error,
        }
        if self.config.include_raw_data and record.raw is not None:
            data["raw"] = record.raw
        return data

    @staticmethod
    def _format_date(value: datetime | None) -> str:
        if not value:
            return "Unknown"
        return value.strftime("%Y-%m-%d")

    def _serialise_image_artifact(self, artifact: ImageArtifact) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "page_url": artifact.page_url,
            "url": artifact.url,
            "hash_bits": artifact.hash_bits,
            "bytes_size": artifact.bytes_size,
            "content_type": artifact.content_type,
        }
        if self.config.include_raw_data and artifact.preview_bytes:
            data["preview_base64"] = base64.b64encode(artifact.preview_bytes).decode("ascii")
        return data

    def _pdf_text(self, pdf, text: str, line_height: float = 5.0) -> None:
        if not text:
            return
        max_width = pdf.w - pdf.l_margin - pdf.r_margin
        for raw_line in text.splitlines() or [""]:
            self._pdf_line(pdf, raw_line, max_width, line_height)

    def _pdf_line(self, pdf, text: str, max_width: float, line_height: float) -> None:
        if text == "":
            pdf.cell(0, line_height, "", ln=1)
            return
        buffer = ""
        for char in text:
            candidate = buffer + char
            if pdf.get_string_width(candidate) <= max_width:
                buffer = candidate
                continue
            if buffer:
                pdf.cell(0, line_height, buffer, ln=1)
                buffer = char
            else:
                # Single character exceeds width; emit as-is to avoid infinite loop
                pdf.cell(0, line_height, char, ln=1)
                buffer = ""
        if buffer:
            pdf.cell(0, line_height, buffer, ln=1)

    def _add_homepage_section(self, pdf, analysis: "AnalysisResult") -> None:
        if not self.config.include_homepage or not self._should_capture_homepage(analysis):
            return

        pdf.set_font("Helvetica", "B", 14)
        pdf.cell(0, 8, "Homepage Comparison", ln=1)
        pdf.set_font("Helvetica", size=10)

        screenshots = self._collect_homepage_screenshots(analysis)
        base_bytes, clone_bytes, errors = screenshots

        if not base_bytes and not clone_bytes:
            self._pdf_text(pdf, "Homepage snapshots unavailable", line_height=6)
        else:
            self._pdf_homepage_preview(pdf, base_bytes, clone_bytes)

        for err in errors:
            pdf.set_font("Helvetica", "I", 9)
            self._pdf_text(pdf, f"Note: {err}")
            pdf.set_font("Helvetica", size=10)

        pdf.ln(2)

    def _should_capture_homepage(self, analysis: "AnalysisResult") -> bool:
        similarity = analysis.comparison.breakdown.overall_score
        if similarity >= self.config.homepage_similarity_threshold:
            return True
        root_path = canonical_path(analysis.base.crawl.root_url)
        for match in analysis.comparison.structure_matches:
            if canonical_path(match.base.page_url) == root_path and match.similarity >= self.config.homepage_similarity_threshold:
                return True
        return False

    def _collect_homepage_screenshots(
        self, analysis: "AnalysisResult"
    ) -> tuple[Optional[bytes], Optional[bytes], list[str]]:
        errors: list[str] = []
        base_bytes: Optional[bytes] = None
        clone_bytes: Optional[bytes] = None

        try:
            base_bytes = capture_homepage(
                analysis.base.crawl.root_url,
                timeout=self.config.homepage_capture_timeout,
                delay=self.config.homepage_render_delay,
                width=self.config.homepage_width,
                height=self.config.homepage_height,
                method=self.config.homepage_capture_tool,
                user_agent=self.config.homepage_user_agent,
            )
        except ScreenshotError as exc:
            errors.append(f"Base screenshot failed: {exc}")

        try:
            clone_bytes = capture_homepage(
                analysis.clone.crawl.root_url,
                timeout=self.config.homepage_capture_timeout,
                delay=self.config.homepage_render_delay,
                width=self.config.homepage_width,
                height=self.config.homepage_height,
                method=self.config.homepage_capture_tool,
                user_agent=self.config.homepage_user_agent,
            )
        except ScreenshotError as exc:
            errors.append(f"Clone screenshot failed: {exc}")

        return base_bytes, clone_bytes, errors

    def _resolve_image_bytes(self, artifact: ImageArtifact) -> Optional[bytes]:
        if artifact.preview_bytes:
            return artifact.preview_bytes
        try:
            response = requests.get(artifact.url, timeout=10)
            response.raise_for_status()
            return response.content
        except requests.RequestException:
            return None

    def _pdf_whois_block(self, pdf, heading: str, record: WhoisRecord) -> None:
        pdf.set_font("Helvetica", "B", 12)
        pdf.cell(0, 6, heading, ln=1)
        pdf.set_font("Helvetica", size=10)
        if record.error:
            self._pdf_text(pdf, f"Error: {record.error}")
            pdf.ln(1)
            return
        self._pdf_text(pdf, f"Registrar: {record.registrar or 'Unknown'}")
        self._pdf_text(pdf, f"Created: {self._format_date(record.creation_date)}")
        self._pdf_text(pdf, f"Updated: {self._format_date(record.updated_date)}")
        self._pdf_text(pdf, f"Expires: {self._format_date(record.expiration_date)}")
        if record.name_servers:
            self._pdf_text(pdf, "Name servers: " + ", ".join(record.name_servers))
        pdf.ln(2)


__all__ = ["ReportBuilder"]
