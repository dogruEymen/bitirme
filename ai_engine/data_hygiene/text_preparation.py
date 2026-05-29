from __future__ import annotations

from dataclasses import dataclass
import html
import re
from typing import Any, Iterable


TITLE_MIN_CHARS = 10
ABSTRACT_MIN_CHARS = 100
ABSTRACT_MAX_WORDS = 250

ID_COLUMNS = ["arxiv_id", "doi", "paper_id"]
SURVEY_TERMS = [
    "survey",
    "review",
    "overview",
    "taxonomy",
    "systematic literature review",
    "comprehensive review",
]
BOILERPLATE_PATTERNS = [
    r"\bin this paper\b",
    r"\bin this work\b",
    r"\bwe propose\b",
    r"\bwe present\b",
    r"\bwe introduce\b",
    r"\bwe investigate\b",
    r"\bwe study\b",
    r"\bwe show\b",
    r"\bwe demonstrate\b",
    r"\bour results show\b",
    r"\bexperimental results\b",
    r"\bextensive experiments\b",
    r"\bstate of the art\b",
    r"\bstate-of-the-art\b",
    r"\bto the best of our knowledge\b",
    r"\bthis paper proposes\b",
    r"\bthis work presents\b",
]


@dataclass
class DataHygieneResult:
    clean_records: list[dict[str, Any]]
    removed_records: list[dict[str, Any]]
    duplicate_records: list[dict[str, Any]]
    metrics: dict[str, Any]
    language_filter_applied: bool


def normalize_title_for_dedup(title: Any) -> str:
    title = "" if title is None else str(title)
    title = html.unescape(title).lower()
    title = re.sub(r"\s+", " ", title)
    title = re.sub(r"[^\w\s]", "", title)
    title = re.sub(r"\s+", " ", title)
    return title.strip()


def light_clean_text(text: Any) -> str:
    text = "" if text is None else str(text)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"\$+", " ", text)
    text = re.sub(r"\\[a-zA-Z]+", " ", text)
    text = re.sub(r"[{}]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def remove_academic_boilerplate(text: Any) -> str:
    text = "" if text is None else str(text)
    text = text.lower()
    for pattern in BOILERPLATE_PATTERNS:
        text = re.sub(pattern, " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def count_words(text: Any) -> int:
    return len(str(text or "").split())


def truncate_words(text: Any, max_words: int = ABSTRACT_MAX_WORDS) -> str:
    return " ".join(str(text or "").split()[:max_words])


def get_category_family(category: Any) -> str:
    category = "" if category is None else str(category).strip()
    if category.startswith("cs."):
        return "cs"
    if category.startswith("math."):
        return "math"
    if category.startswith("stat."):
        return "stat"
    if category.startswith("q-bio."):
        return "q-bio"
    if category.startswith("q-fin."):
        return "q-fin"
    if category.startswith("econ."):
        return "econ"
    if category.startswith("eess."):
        return "eess"
    if category.startswith(("astro-ph", "cond-mat", "gr-qc", "hep-", "math-ph", "nlin", "nucl-", "physics", "quant-ph")):
        return "physics"
    return "other"


def is_survey_title(title_clean: Any) -> bool:
    title = str(title_clean or "").lower()
    return any(term in title for term in SURVEY_TERMS)


def valid_title_and_abstract(title: Any, abstract: Any) -> bool:
    title_clean = light_clean_text(title)
    abstract_clean = light_clean_text(abstract)
    return len(title_clean) > TITLE_MIN_CHARS and len(abstract_clean) > ABSTRACT_MIN_CHARS


def prepare_article_texts(title: Any, abstract: Any, max_abstract_words: int = ABSTRACT_MAX_WORDS) -> dict[str, Any]:
    title_clean = light_clean_text(title)
    abstract_clean = light_clean_text(abstract)
    abstract_truncated = truncate_words(abstract_clean, max_abstract_words)
    abstract_representation = remove_academic_boilerplate(abstract_truncated)
    embedding_text = build_embedding_text(title_clean, abstract_truncated)
    representation_text = build_representation_text(title_clean, abstract_representation)
    return {
        "title_clean": title_clean,
        "abstract_clean": abstract_clean,
        "abstract_word_count": count_words(abstract_clean),
        "abstract_truncated": abstract_truncated,
        "abstract_representation": abstract_representation,
        "embedding_text": embedding_text,
        "representation_text": representation_text,
        "embedding_text_len": len(embedding_text),
        "representation_text_len": len(representation_text),
        "is_survey": is_survey_title(title_clean),
    }


def build_embedding_text(title: Any, abstract: Any, max_abstract_words: int = ABSTRACT_MAX_WORDS) -> str:
    title_clean = light_clean_text(title)
    abstract_truncated = truncate_words(light_clean_text(abstract), max_abstract_words)
    return f"{title_clean}. {title_clean}. {abstract_truncated}".strip()


def build_representation_text(title: Any, abstract: Any, max_abstract_words: int = ABSTRACT_MAX_WORDS) -> str:
    title_clean = light_clean_text(title)
    abstract_truncated = truncate_words(light_clean_text(abstract), max_abstract_words)
    abstract_representation = remove_academic_boilerplate(abstract_truncated)
    return f"{title_clean}. {title_clean}. {abstract_representation}".strip()


def clean_paper_records(
    records: Iterable[dict[str, Any]],
    apply_language_filter: bool = True,
    detect_language: bool = False,
    max_abstract_words: int = ABSTRACT_MAX_WORDS,
) -> DataHygieneResult:
    rows = [_normalize_input_record(record) for record in records]
    removed_records: list[dict[str, Any]] = []
    duplicate_records: list[dict[str, Any]] = []

    initial_metrics = _initial_metrics(rows)

    rows = _remove_by_predicate(
        rows,
        removed_records,
        lambda row: len(row["title"]) <= TITLE_MIN_CHARS,
        "title_too_short_or_empty",
    )
    rows = _remove_by_predicate(
        rows,
        removed_records,
        lambda row: len(row["abstract"]) <= ABSTRACT_MIN_CHARS,
        "abstract_too_short_or_empty",
    )

    rows = _dedupe_by_ids(rows, duplicate_records)
    rows = _dedupe_by_normalized_title(rows, duplicate_records)

    for row in rows:
        row.update(prepare_article_texts(row["title"], row["abstract"], max_abstract_words=max_abstract_words))

    rows = _remove_by_predicate(
        rows,
        removed_records,
        lambda row: len(row["title_clean"]) <= TITLE_MIN_CHARS,
        "title_too_short_after_cleaning",
    )
    rows = _remove_by_predicate(
        rows,
        removed_records,
        lambda row: len(row["abstract_clean"]) <= ABSTRACT_MIN_CHARS,
        "abstract_too_short_after_cleaning",
    )

    language_filter_applied = False
    if apply_language_filter:
        rows, removed_for_language, language_filter_applied = _apply_language_filter(rows, detect_language=detect_language)
        removed_records.extend(removed_for_language)

    for row in rows:
        row["category_family"] = get_category_family(row.get("primary_category"))

    metrics = {**initial_metrics, **_final_metrics(rows, initial_metrics)}
    metrics["duplicate_total"] = len(duplicate_records)
    metrics["language_filter_applied"] = language_filter_applied
    return DataHygieneResult(
        clean_records=rows,
        removed_records=removed_records,
        duplicate_records=duplicate_records,
        metrics=metrics,
        language_filter_applied=language_filter_applied,
    )


def _normalize_input_record(record: dict[str, Any]) -> dict[str, Any]:
    row = dict(record)
    row["title"] = light_clean_text(row.get("title"))
    row["abstract"] = light_clean_text(row.get("abstract", row.get("abstract_text")))
    if "abstract_text" not in row:
        row["abstract_text"] = row["abstract"]
    if "paper_id" not in row and row.get("external_id"):
        row["paper_id"] = row["external_id"]
    if "arxiv_id" not in row and row.get("source") == "arxiv":
        row["arxiv_id"] = row.get("external_id")
    return row


def _initial_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "initial_rows": len(rows),
        "empty_title_count": sum(1 for row in rows if len(row["title"]) == 0),
        "empty_abstract_count": sum(1 for row in rows if len(row["abstract"]) == 0),
        "short_title_count_len_le_10": sum(1 for row in rows if len(row["title"]) <= TITLE_MIN_CHARS),
        "short_abstract_count_len_le_100": sum(1 for row in rows if len(row["abstract"]) <= ABSTRACT_MIN_CHARS),
    }


def _final_metrics(rows: list[dict[str, Any]], initial_metrics: dict[str, Any]) -> dict[str, Any]:
    return {
        "final_rows": len(rows),
        "removed_total": initial_metrics["initial_rows"] - len(rows),
        "final_empty_title_count": sum(1 for row in rows if len(row.get("title_clean", "")) == 0),
        "final_empty_abstract_count": sum(1 for row in rows if len(row.get("abstract_clean", "")) == 0),
        "avg_title_length": _mean([len(row.get("title_clean", "")) for row in rows]),
        "avg_abstract_length": _mean([len(row.get("abstract_clean", "")) for row in rows]),
        "avg_abstract_word_count": _mean([row.get("abstract_word_count", 0) for row in rows]),
        "survey_count": sum(1 for row in rows if row.get("is_survey")),
    }


def _mean(values: list[int | float]) -> float:
    return float(sum(values) / len(values)) if values else 0.0


def _remove_by_predicate(
    rows: list[dict[str, Any]],
    removed_records: list[dict[str, Any]],
    predicate,
    reason: str,
) -> list[dict[str, Any]]:
    kept = []
    for row in rows:
        if predicate(row):
            removed = dict(row)
            removed["removal_reason"] = reason
            removed_records.append(removed)
        else:
            kept.append(row)
    return kept


def _dedupe_by_ids(rows: list[dict[str, Any]], duplicate_records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped = rows
    for id_column in ID_COLUMNS:
        seen = set()
        next_rows = []
        for row in deduped:
            value = str(row.get(id_column) or "").strip()
            if value and value in seen:
                duplicate = dict(row)
                duplicate["duplicate_reason"] = f"duplicate_{id_column}"
                duplicate_records.append(duplicate)
                continue
            if value:
                seen.add(value)
            next_rows.append(row)
        deduped = next_rows
    return deduped


def _dedupe_by_normalized_title(
    rows: list[dict[str, Any]],
    duplicate_records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    seen = set()
    kept = []
    for row in rows:
        row["title_norm"] = normalize_title_for_dedup(row.get("title"))
        title_norm = row["title_norm"]
        if title_norm and title_norm in seen:
            duplicate = dict(row)
            duplicate["duplicate_reason"] = "duplicate_normalized_title"
            duplicate_records.append(duplicate)
            continue
        if title_norm:
            seen.add(title_norm)
        kept.append(row)
    return kept


def _apply_language_filter(
    rows: list[dict[str, Any]],
    detect_language: bool,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], bool]:
    if detect_language:
        detector = _language_detector()
        if detector is not None:
            for row in rows:
                row["lang"] = detector(row.get("abstract_clean") or row.get("abstract") or "")

    if not any(str(row.get("lang") or row.get("language") or "").strip() for row in rows):
        return rows, [], False

    kept = []
    removed = []
    for row in rows:
        lang = str(row.get("lang") or row.get("language") or "en").strip().lower()
        row["lang"] = lang or "unknown"
        if row["lang"] != "en":
            rejected = dict(row)
            rejected["removal_reason"] = "non_english_or_unknown_language"
            removed.append(rejected)
        else:
            kept.append(row)
    return kept, removed, True


def _language_detector():
    try:
        from langdetect import DetectorFactory, detect
    except ImportError:
        return None

    DetectorFactory.seed = 42

    def safe_detect_lang(text: str) -> str:
        try:
            return detect(text)
        except Exception:
            return "unknown"

    return safe_detect_lang
