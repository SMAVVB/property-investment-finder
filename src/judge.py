"""
Property Investment Finder — Judge (Phase 4-interim)

Verwendet Laya (lokales Open-Source-Entscheidungsmodell) als primären Judge
zur Beantwortung der 15 Build-Plan-Fragen pro Exposé-Text.

Fragen-Typen:
  - noul (9): f_sonderumlage, f_milieuschutz, f_erbpacht, f_staffelmiete,
              f_renovation, f_heating_fossil, f_small_weg, f_tenant_issue, f_wg_layout
  - choice (2): c_tenant_type (student/single/couple/family),
                c_letting_status (let/vacant/owner-occupied/unclear)
  - score (4): s_condition, s_building, s_micro_location, s_description_trust

Laya-API: from laya import Router; router = Router(); result = router.predict(text, questions)
- questions: Dict[str, dict] mit type, instructions, criteria
- Antwort: Dict mit 'answers' -> {question_id: {type, noul/choice/score, confidence, probabilities}}

HINWEIS: Score-Fragen (s_condition, s_building, s_micro_location, s_description_trust)
sind im Zero-Shot-Modus noch ungenau (Benchmark: 0.362 Zero-Shot vs 0.766 finegetuned).
Das ist der Hauptgrund für das spätere Finetuning (Phase 4, sobald 300+ gelabelte
Listings existieren).

classifier.dev bleibt als optionaler Fallback nicht implementiert — Laya ist lokal,
kostenlos, ohne Rate-Limit, also die bessere Wahl für produktiven Dauerbetrieb.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import time
from dataclasses import dataclass, field, asdict
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Frage-Definitionen (15 Fragen nach Build-Plan)
# ---------------------------------------------------------------------------

QUESTION_DEFS: dict[str, dict[str, Any]] = {
    # --- noul-Fragen (boolean/unclear) ---
    "f_sonderumlage": {
        "type": "noul",
        "instructions": "Wird eine Sonderumlage für die Wohnung erhoben oder erwähnt?",
        "criteria": {"true": "Ja, Sonderumlage wird erhoben", "false": "Nein, keine Sonderumlage"},
    },
    "f_milieuschutz": {
        "type": "noul",
        "instructions": "Gilt Milieuschutz in der Straße/Bezirk der Wohnung?",
        "criteria": {"true": "Ja, Milieuschutz gilt", "false": "Nein, kein Milieuschutz erwähnt"},
    },
    "f_erbpacht": {
        "type": "noul",
        "instructions": "Besteht Erbbaurecht (Erbpacht) für das Grundstück?",
        "criteria": {"true": "Ja, Erbbaurecht besteht", "false": "Nein, kein Erbbaurecht"},
    },
    "f_staffelmiete": {
        "type": "noul",
        "instructions": "Ist die Miete gestaffelt (Staffelmiete) vereinbart?",
        "criteria": {"true": "Ja, Staffelmiete vereinbart", "false": "Nein, keine Staffelmiete"},
    },
    "f_renovation": {
        "type": "noul",
        "instructions": "Stehen bevorstehende Renovierungs-/Sanierungsmaßnahmen an?",
        "criteria": {"true": "Ja, Renovierung/Sanierung geplant", "false": "Nein, keine Maßnahmen geplant"},
    },
    "f_heating_fossil": {
        "type": "noul",
        "instructions": "Ist die Heizung fossil-basiert (Gas, Öl, Kohle)?",
        "criteria": {"true": "Ja, fossil-basiert (Gas/Öl/Kohle)", "false": "Nein, nicht fossil (Wärme/Pelleter/Hybrid)"},
    },
    "f_small_weg": {
        "type": "noul",
        "instructions": "Wird die Kleinwagen-Parität (Small-Weg) für Parkplätze erwähnt?",
        "criteria": {"true": "Ja, Small-Weg / Kleinwagen-Parität erwähnt", "false": "Nein, nicht erwähnt"},
    },
    "f_tenant_issue": {
        "type": "noul",
        "instructions": "Gibt es bekannte Mieterprobleme (Streit, Kündigung, Schulden)?",
        "criteria": {"true": "Ja, Mieterprobleme bekannt", "false": "Nein, keine Mieterprobleme"},
    },
    "f_wg_layout": {
        "type": "noul",
        "instructions": "Ist die Wohnung für eine WG geeignet (mehrere abgeschlossene Zimmer)?",
        "criteria": {"true": "Ja, WG-tauglich (mehrere Zimmer)", "false": "Nein, nicht WG-tauglich"},
    },
    # --- choice-Fragen ---
    "c_tenant_type": {
        "type": "choice",
        "instructions": "Welcher Mietertyp passt am besten zur Wohnung?",
        "criteria": ["student", "single", "couple", "family"],
    },
    "c_letting_status": {
        "type": "choice",
        "instructions": "Was ist der aktuelle Vermietungsstatus?",
        "criteria": ["let", "vacant", "owner-occupied", "unclear"],
    },
    # --- score-Fragen (1-5 Skala) ---
    "s_condition": {
        "type": "score",
        "instructions": "Wie ist der Zustand der Wohnung?",
        "criteria": ["Sehr schlecht", "Schlecht", "Durchschnittlich", "Gut", "Sehr gut"],
    },
    "s_building": {
        "type": "score",
        "instructions": "Wie ist die Qualität des Gebäudes insgesamt?",
        "criteria": ["Sehr schlecht", "Schlecht", "Durchschnittlich", "Gut", "Sehr gut"],
    },
    "s_micro_location": {
        "type": "score",
        "instructions": "Wie ist die Mikro-Lage (direkte Umgebung) der Wohnung?",
        "criteria": ["Sehr schlecht", "Schlecht", "Durchschnittlich", "Gut", "Sehr gut"],
    },
    "s_description_trust": {
        "type": "score",
        "instructions": "Wie vertrauenswürdig ist die Beschreibung (vollständig, glaubhaft, keine offensichtlichen Lügen)?",
        "criteria": ["Sehr unglaubwürdig", "Unglaubwürdig", "Durchschnittlich", "Glaubwürdig", "Sehr glaubwürdig"],
    },
}


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class Judgment:
    """Eine einzelne Judge-Antwort."""
    listing_id: str
    question_id: str
    model_version: str = "laya-0.1.0"
    answer: Optional[str] = None
    probability: Optional[float] = None
    confidence: Optional[float] = None


@dataclass
class JudgeResult:
    """Alle Judge-Antworten für ein Listing."""
    listing_id: str
    judgments: list[Judgment] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    execution_time_ms: float = 0.0


# ---------------------------------------------------------------------------
# Laya Wrapper
# ---------------------------------------------------------------------------

def _build_questions() -> dict[str, dict[str, Any]]:
    """Erzeuge das Fragen-Dictionary für Laya aus QUESTION_DEFS."""
    return dict(QUESTION_DEFS)


def _parse_laya_answer(
    qid: str,
    qtype: str,
    answer_data: dict[str, Any],
) -> Judgment:
    """
    Parst eine einzelne Laya-Antwort in ein Judgment-Objekt.

    Laya-Antwort-Formate:
      noul:   {type: 'noul', noul: float(0-1), confidence: float}
      choice: {type: 'choice', choice: str, probabilities: {label: float}, confidence: float, answer_confidence: float}
      score:  {type: 'score', score: float, legend: {idx: desc}, probabilities: {idx: float}, confidence: float, answer_confidence: float}
    """
    if qtype == "noul":
        noul_val = answer_data.get("noul")
        if noul_val is not None:
            # noul > 0.5 → "true", sonst "false"
            answer = "true" if noul_val > 0.5 else "false"
            confidence = answer_data.get("confidence", 0.0)
            probability = noul_val if noul_val > 0.5 else (1.0 - noul_val)
        else:
            answer = None
            confidence = None
            probability = None
        return Judgment(
            listing_id="",  # wird später gesetzt
            question_id=qid,
            answer=answer,
            probability=probability,
            confidence=confidence,
        )

    elif qtype == "choice":
        choice_val = answer_data.get("choice")
        answer_conf = answer_data.get("answer_confidence", 0.0)
        confidence = answer_data.get("confidence", 0.0)
        probabilities = answer_data.get("probabilities", {})
        prob = probabilities.get(choice_val) if choice_val else None
        return Judgment(
            listing_id="",
            question_id=qid,
            answer=choice_val,
            probability=prob,
            confidence=confidence,
        )

    elif qtype == "score":
        score_val = answer_data.get("score")
        legend = answer_data.get("legend", {})
        probabilities = answer_data.get("probabilities", {})
        answer_conf = answer_data.get("answer_confidence", 0.0)
        confidence = answer_data.get("confidence", 0.0)

        # Score-Wert auf nächste ganze Zahl runden und in Text umwandeln
        answer = None
        probability = None
        if score_val is not None and legend:
            rounded = round(score_val)
            # Clamp auf gültigen Bereich
            rounded = max(0, min(len(legend) - 1, rounded))
            answer = legend.get(str(rounded), str(rounded))
            probability = probabilities.get(str(rounded))

        return Judgment(
            listing_id="",
            question_id=qid,
            answer=answer,
            probability=probability,
            confidence=confidence,
        )

    else:
        logger.warning("Unbekannter Fragetyp %s für %s", qtype, qid)
        return Judgment(listing_id="", question_id=qid)



def _ensure_hf_home() -> None:
    """
    Stelle sicher, dass HF_HOME auf ein schreibbares Verzeichnis zeigt.

    Im Sandbox-Modus kann /home/vincent/.cache/huggingface/ blockiert sein.
    Wir verwenden stattdessen ein Verzeichnis im Projekt-Workspace.
    """
    hf_home = os.environ.get("HF_HOME")
    if hf_home is None:
        # Versuche ein schreibbares Verzeichnis im Projekt
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        cache_dir = os.path.join(project_root, ".hf_cache")
        os.makedirs(cache_dir, exist_ok=True)
        os.environ["HF_HOME"] = cache_dir
        logger.debug("Set HF_HOME to %s", cache_dir)


def run_judge(
    text: str,
    questions: Optional[dict[str, dict[str, Any]]] = None,
) -> JudgeResult:
    """
    Führe den Laya-Judge für einen Exposé-Text aus.

    Args:
        text: Der rohe Exposé-Text (NUR Text, KEINE Kriterien/Finanzzahlen).
        questions: Optionales Fragen-Dictionary. Standard: alle 15 Fragen.

    Returns:
        JudgeResult mit allen 15 Urteilen oder Fehlern.
    """
    start = time.time()
    result = JudgeResult(listing_id="")

    if questions is None:
        questions = _build_questions()

    # Stelle sicher, dass HF_HOME auf ein schreibbares Verzeichnis zeigt
    _ensure_hf_home()

    try:
        from laya import Router
        router = Router()
        laya_output = router.predict(text, questions)
    except Exception as e:
        result.errors.append(f"Laya-Fehler: {e}")
        logger.error("Laya prediction failed: %s", e)
        # Bei Fehler: alle Fragen mit None antworten
        for qid, qdef in questions.items():
            result.judgments.append(Judgment(
                listing_id="", question_id=qid, answer=None,
                probability=None, confidence=None,
            ))
        result.execution_time_ms = (time.time() - start) * 1000
        return result

    answers = laya_output.get("answers", {})
    for qid, qdef in questions.items():
        qtype = qdef.get("type", "noul")
        if qid in answers:
            judgment = _parse_laya_answer(qid, qtype, answers[qid])
            result.judgments.append(judgment)
        else:
            logger.warning("Keine Antwort für Frage %s", qid)
            result.judgments.append(Judgment(
                listing_id="", question_id=qid, answer=None,
                probability=None, confidence=None,
            ))

    result.execution_time_ms = (time.time() - start) * 1000
    return result


# ---------------------------------------------------------------------------
# Database storage
# ---------------------------------------------------------------------------

def store_judgments(
    conn: sqlite3.Connection,
    listing_id: str,
    judge_result: JudgeResult,
    model_version: str = "laya-0.1.0",
) -> None:
    """
    Speichere alle Judge-Ergebnisse in der judgments-Tabelle.

    Schema:
      listing_id TEXT NOT NULL,
      question_id TEXT NOT NULL,
      model_version TEXT,
      answer TEXT,
      probability REAL,
      confidence REAL,
      PRIMARY KEY (listing_id, question_id)
    """
    cursor = conn.cursor()

    for j in judge_result.judgments:
        cursor.execute("""
            INSERT OR REPLACE INTO judgments (
                listing_id, question_id, model_version, answer,
                probability, confidence
            ) VALUES (?, ?, ?, ?, ?, ?)
        """, (
            listing_id,
            j.question_id,
            model_version,
            j.answer,
            j.probability,
            j.confidence,
        ))

    conn.commit()
    logger.info(
        "Stored %d judgments for listing %s (%.0fms)",
        len(judge_result.judgments), listing_id, judge_result.execution_time_ms,
    )


# ---------------------------------------------------------------------------
# Convenience: full pipeline step (judge + store)
# ---------------------------------------------------------------------------

def judge_listing(
    conn: sqlite3.Connection,
    listing_id: str,
    text: str,
    model_version: str = "laya-0.1.0",
    questions: Optional[dict[str, dict[str, Any]]] = None,
) -> JudgeResult:
    """
    Führe Judge aus und speichere Ergebnisse in einem Schritt.

    Args:
        conn: SQLite-Connection zur Datenbank mit judgments-Tabelle.
        listing_id: ID des Listings.
        text: Exposé-Text.
        model_version: Version-String für model_version-Feld.
        questions: Optionales Fragen-Dictionary. Standard: alle 15 Fragen.

    Returns:
        JudgeResult mit allen Urteilen.
    """
    judge_result = run_judge(text, questions=questions)
    judge_result.listing_id = listing_id
    store_judgments(conn, listing_id, judge_result, model_version)
    return judge_result


# ---------------------------------------------------------------------------
# Batch processing
# ---------------------------------------------------------------------------

def judge_batch(
    conn: sqlite3.Connection,
    listings: list[tuple[str, str]],  # [(listing_id, text), ...]
    model_version: str = "laya-0.1.0",
) -> list[JudgeResult]:
    """
    Führe Judge für eine Liste von Listings aus.

    Args:
        conn: SQLite-Connection.
        listings: Liste von (listing_id, text)-Tupeln.
        model_version: Version-String.

    Returns:
        Liste von JudgeResult-Objekten.
    """
    results = []
    for listing_id, text in listings:
        result = judge_listing(conn, listing_id, text, model_version)
        results.append(result)
    return results


# ---------------------------------------------------------------------------
# Pretty-print
# ---------------------------------------------------------------------------

def format_judgment(j: Judgment) -> str:
    """Formatiere ein einzelnes Urteil als lesbaren Text."""
    parts = [f"  {j.question_id}:"]
    if j.answer is not None:
        parts.append(f"    answer={j.answer}")
    else:
        parts.append(f"    answer=None")
    if j.probability is not None:
        parts.append(f"    probability={j.probability:.4f}")
    if j.confidence is not None:
        parts.append(f"    confidence={j.confidence:.4f}")
    return "\n".join(parts)


def format_result(r: JudgeResult) -> str:
    """Formatiere ein JudgeResult als lesbaren Text."""
    lines = [f"Listing: {r.listing_id}"]
    lines.append(f"  Execution time: {r.execution_time_ms:.0f}ms")
    lines.append(f"  Questions answered: {len(r.judgments)}/{len(r.judgments) + len(r.errors)}")

    if r.errors:
        lines.append(f"  Errors ({len(r.errors)}):")
        for err in r.errors:
            lines.append(f"    ✗ {err}")

    for j in r.judgments:
        lines.append(format_judgment(j))

    return "\n".join(lines)
