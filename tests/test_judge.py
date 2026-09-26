"""
Property Investment Finder — Judge Unit Tests

Testet:
  - _parse_laya_answer für noul, choice, score Typen
  - run_judge mit gemocktem Laya Router
  - store_judgments mit echter SQLite-Datenbank
  - judge_listing (vollständiger Durchlauf)
  - judge_batch (Batch-Verarbeitung)
  - Fehlerbehandlung (Laya-Exception)
  - format_judgment / format_result (Pretty-Print)
"""

import json
import os
import sqlite3
import sys
import time
from unittest.mock import MagicMock, patch, ANY

import pytest

# Projekt-Root zum Path hinzufügen
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from src.judge import (
    Judgment,
    JudgeResult,
    QUESTION_DEFS,
    _parse_laya_answer,
    _build_questions,
    run_judge,
    store_judgments,
    judge_listing,
    judge_batch,
    format_judgment,
    format_result,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_noul_answer():
    """Simulierte Laya-Antwort für eine noul-Frage (noul > 0.5 = true)."""
    return {
        "type": "noul",
        "noul": 0.82,
        "confidence": 0.82,
        "answer_confidence": 0.82,
        "action": {"act_probability": 1.0},
    }


@pytest.fixture
def sample_noul_false_answer():
    """Simulierte Laya-Antwort für eine noul-Frage (noul < 0.5 = false)."""
    return {
        "type": "noul",
        "noul": 0.31,
        "confidence": 0.31,
        "answer_confidence": 0.31,
        "action": {"act_probability": 1.0},
    }


@pytest.fixture
def sample_choice_answer():
    """Simulierte Laya-Antwort für eine choice-Frage."""
    return {
        "type": "choice",
        "choice": "let",
        "probabilities": {"let": 0.55, "vacant": 0.30, "owner-occupied": 0.12, "unclear": 0.03},
        "confidence": 0.22,
        "answer_confidence": 0.55,
        "action": {"act_probability": 1.0},
    }


@pytest.fixture
def sample_score_answer():
    """Simulierte Laya-Antwort für eine score-Frage."""
    return {
        "type": "score",
        "score": 3.2,
        "legend": {"0": "Sehr schlecht", "1": "Schlecht", "2": "Durchschnittlich", "3": "Gut", "4": "Sehr gut"},
        "probabilities": {"0": 0.02, "1": 0.05, "2": 0.10, "3": 0.70, "4": 0.13},
        "confidence": 0.28,
        "answer_confidence": 0.70,
        "action": {"act_probability": 1.0},
    }


@pytest.fixture
def sample_score_low_answer():
    """Simulierte Laya-Antwort für eine score-Frage (niedriger Score)."""
    return {
        "type": "score",
        "score": 1.4,
        "legend": {"0": "Sehr schlecht", "1": "Schlecht", "2": "Durchschnittlich", "3": "Gut", "4": "Sehr gut"},
        "probabilities": {"0": 0.08, "1": 0.65, "2": 0.20, "3": 0.05, "4": 0.02},
        "confidence": 0.25,
        "answer_confidence": 0.65,
        "action": {"act_probability": 1.0},
    }


@pytest.fixture
def temp_db(tmp_path):
    """Erstelle eine temporäre SQLite-Datenbank mit judgments-Tabelle."""
    db_path = str(tmp_path / "test_judgments.db")
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS judgments (
            listing_id    TEXT NOT NULL,
            question_id   TEXT NOT NULL,
            model_version TEXT,
            answer        TEXT,
            probability   REAL,
            confidence    REAL,
            created_at    TEXT NOT NULL DEFAULT (datetime('now')),
            PRIMARY KEY (listing_id, question_id)
        )
    """)
    conn.commit()
    yield conn
    conn.close()


# ---------------------------------------------------------------------------
# Tests: QUESTION_DEFS
# ---------------------------------------------------------------------------

class TestQuestionDefs:
    """Teste die 14 Frage-Definitionen."""

    def test_all_14_questions_defined(self):
        assert len(QUESTION_DEFS) == 15

    def test_noul_questions(self):
        noul_ids = [
            "f_sonderumlage", "f_milieuschutz", "f_erbpacht", "f_staffelmiete",
            "f_renovation", "f_heating_fossil", "f_small_weg", "f_tenant_issue", "f_wg_layout",
        ]
        for qid in noul_ids:
            assert qid in QUESTION_DEFS
            assert QUESTION_DEFS[qid]["type"] == "noul"
            assert "instructions" in QUESTION_DEFS[qid]
            assert "criteria" in QUESTION_DEFS[qid]

    def test_choice_questions(self):
        choice_ids = ["c_tenant_type", "c_letting_status"]
        for qid in choice_ids:
            assert qid in QUESTION_DEFS
            assert QUESTION_DEFS[qid]["type"] == "choice"
            assert "instructions" in QUESTION_DEFS[qid]
            assert "criteria" in QUESTION_DEFS[qid]

    def test_score_questions(self):
        score_ids = ["s_condition", "s_building", "s_micro_location", "s_description_trust"]
        for qid in score_ids:
            assert qid in QUESTION_DEFS
            assert QUESTION_DEFS[qid]["type"] == "score"
            assert "instructions" in QUESTION_DEFS[qid]
            assert "criteria" in QUESTION_DEFS[qid]

    def test_build_questions_returns_copy(self):
        questions = _build_questions()
        assert len(questions) == 15
        assert isinstance(questions, dict)


# ---------------------------------------------------------------------------
# Tests: _parse_laya_answer
# ---------------------------------------------------------------------------

class TestParseLayaAnswer:
    """Teste das Parsen von Laya-Antworten."""

    def test_noul_true(self, sample_noul_answer):
        j = _parse_laya_answer("f_heating_fossil", "noul", sample_noul_answer)
        assert j.answer == "true"
        assert j.probability == 0.82
        assert j.confidence == 0.82

    def test_noul_false(self, sample_noul_false_answer):
        j = _parse_laya_answer("f_erbpacht", "noul", sample_noul_false_answer)
        assert j.answer == "false"
        assert j.probability == 0.69  # 1.0 - 0.31
        assert j.confidence == 0.31

    def test_noul_no_answer(self):
        j = _parse_laya_answer("f_heating_fossil", "noul", {"type": "noul"})
        assert j.answer is None
        assert j.probability is None
        assert j.confidence is None

    def test_choice(self, sample_choice_answer):
        j = _parse_laya_answer("c_letting_status", "choice", sample_choice_answer)
        assert j.answer == "let"
        assert j.probability == 0.55
        assert j.confidence == 0.22

    def test_score_rounded_up(self, sample_score_answer):
        j = _parse_laya_answer("s_condition", "score", sample_score_answer)
        assert j.answer == "Gut"  # round(3.2) = 3
        assert j.probability == 0.70
        assert j.confidence == 0.28

    def test_score_rounded_down(self, sample_score_low_answer):
        j = _parse_laya_answer("s_condition", "score", sample_score_low_answer)
        assert j.answer == "Schlecht"  # round(1.4) = 1
        assert j.probability == 0.65
        assert j.confidence == 0.25

    def test_score_no_legend(self):
        j = _parse_laya_answer("s_condition", "score", {
            "type": "score", "score": 2.5,
            "confidence": 0.3,
        })
        assert j.answer is None
        assert j.probability is None
        assert j.confidence == 0.3

    def test_unknown_type(self):
        j = _parse_laya_answer("unknown_q", "mystery", {"type": "mystery"})
        assert j.answer is None
        assert j.question_id == "unknown_q"


# ---------------------------------------------------------------------------
# Tests: run_judge (mit gemocktem Laya)
# ---------------------------------------------------------------------------

class TestRunJudge:
    """Teste run_judge mit gemocktem Laya Router."""

    def _make_mock_laya_output(self):
        """Erzeuge eine simulierte Laya-Antwort für alle 15 Fragen."""
        return {
            "answers": {
                "f_sonderumlage": {"type": "noul", "noul": 0.65, "confidence": 0.65},
                "f_milieuschutz": {"type": "noul", "noul": 0.40, "confidence": 0.40},
                "f_erbpacht": {"type": "noul", "noul": 0.75, "confidence": 0.75},
                "f_staffelmiete": {"type": "noul", "noul": 0.55, "confidence": 0.55},
                "f_renovation": {"type": "noul", "noul": 0.30, "confidence": 0.30},
                "f_heating_fossil": {"type": "noul", "noul": 0.90, "confidence": 0.90},
                "f_small_weg": {"type": "noul", "noul": 0.45, "confidence": 0.45},
                "f_tenant_issue": {"type": "noul", "noul": 0.20, "confidence": 0.20},
                "f_wg_layout": {"type": "noul", "noul": 0.85, "confidence": 0.85},
                "c_tenant_type": {
                    "type": "choice", "choice": "family",
                    "probabilities": {"student": 0.10, "single": 0.20, "couple": 0.30, "family": 0.40},
                    "confidence": 0.18, "answer_confidence": 0.40,
                },
                "c_letting_status": {
                    "type": "choice", "choice": "let",
                    "probabilities": {"let": 0.50, "vacant": 0.30, "owner-occupied": 0.15, "unclear": 0.05},
                    "confidence": 0.25, "answer_confidence": 0.50,
                },
                "s_condition": {
                    "type": "score", "score": 3.5,
                    "legend": {"0": "Sehr schlecht", "1": "Schlecht", "2": "Durchschnittlich", "3": "Gut", "4": "Sehr gut"},
                    "probabilities": {"0": 0.01, "1": 0.02, "2": 0.05, "3": 0.60, "4": 0.32},
                    "confidence": 0.30, "answer_confidence": 0.60,
                },
                "s_building": {
                    "type": "score", "score": 2.8,
                    "legend": {"0": "Sehr schlecht", "1": "Schlecht", "2": "Durchschnittlich", "3": "Gut", "4": "Sehr gut"},
                    "probabilities": {"0": 0.01, "1": 0.03, "2": 0.50, "3": 0.40, "4": 0.06},
                    "confidence": 0.22, "answer_confidence": 0.50,
                },
                "s_micro_location": {
                    "type": "score", "score": 1.6,
                    "legend": {"0": "Sehr schlecht", "1": "Schlecht", "2": "Durchschnittlich", "3": "Gut", "4": "Sehr gut"},
                    "probabilities": {"0": 0.02, "1": 0.55, "2": 0.30, "3": 0.10, "4": 0.03},
                    "confidence": 0.20, "answer_confidence": 0.55,
                },
                "s_description_trust": {
                    "type": "score", "score": 4.1,
                    "legend": {"0": "Sehr unglaubwürdig", "1": "Unglaubwürdig", "2": "Durchschnittlich", "3": "Glaubwürdig", "4": "Sehr glaubwürdig"},
                    "probabilities": {"0": 0.01, "1": 0.02, "2": 0.05, "3": 0.20, "4": 0.72},
                    "confidence": 0.35, "answer_confidence": 0.72,
                },
            },
            "routing": {"model": "multilingual"},
            "usage": {"input_tokens": 300, "output_tokens": 0},
        }

    @patch("laya.Router")
    def test_all_14_questions_answered(self, mock_router_class):
        """Alle 15 Fragen sollten beantwortet werden."""
        mock_router = MagicMock()
        mock_router.predict.return_value = self._make_mock_laya_output()
        mock_router_class.return_value = mock_router

        result = run_judge("Test text")
        assert len(result.judgments) == 15
        assert len(result.errors) == 0

    @patch("laya.Router")
    def test_noul_answers_correct(self, mock_router_class):
        """noul-Fragen sollten true/false korrekt zuordnen."""
        mock_router = MagicMock()
        mock_router.predict.return_value = self._make_mock_laya_output()
        mock_router_class.return_value = mock_router

        result = run_judge("Test text")
        answers = {j.question_id: j.answer for j in result.judgments}

        # noul > 0.5 → true
        assert answers["f_sonderumlage"] == "true"   # 0.65
        assert answers["f_erbpacht"] == "true"       # 0.75
        assert answers["f_heating_fossil"] == "true" # 0.90

        # noul < 0.5 → false
        assert answers["f_milieuschutz"] == "false"  # 0.40
        assert answers["f_renovation"] == "false"    # 0.30
        assert answers["f_tenant_issue"] == "false"  # 0.20

    @patch("laya.Router")
    def test_choice_answers_correct(self, mock_router_class):
        """choice-Fragen sollten das Label mit höchster Wahrscheinlichkeit wählen."""
        mock_router = MagicMock()
        mock_router.predict.return_value = self._make_mock_laya_output()
        mock_router_class.return_value = mock_router

        result = run_judge("Test text")
        answers = {j.question_id: j.answer for j in result.judgments}

        assert answers["c_tenant_type"] == "family"  # 0.40
        assert answers["c_letting_status"] == "let"  # 0.50

    @patch("laya.Router")
    def test_score_answers_rounded(self, mock_router_class):
        """score-Fragen sollten auf ganze Zahl gerundet werden."""
        mock_router = MagicMock()
        mock_router.predict.return_value = self._make_mock_laya_output()
        mock_router_class.return_value = mock_router

        result = run_judge("Test text")
        answers = {j.question_id: j.answer for j in result.judgments}

        # Python 3 banker's rounding: round(3.5) = 4, round(2.8) = 3, round(1.6) = 2, round(4.1) = 4
        assert answers["s_condition"] == "Sehr gut"       # round(3.5) = 4
        assert answers["s_building"] == "Gut"              # round(2.8) = 3
        assert answers["s_micro_location"] == "Durchschnittlich"  # round(1.6) = 2
        assert answers["s_description_trust"] == "Sehr glaubwürdig"  # round(4.1) = 4

    @patch("laya.Router")
    def test_laya_exception_handled(self, mock_router_class):
        """Bei Laya-Fehler sollten alle Fragen mit None antworten."""
        mock_router = MagicMock()
        mock_router.predict.side_effect = Exception("Connection timeout")
        mock_router_class.return_value = mock_router

        result = run_judge("Test text")
        assert len(result.errors) == 1
        assert "Laya-Fehler" in result.errors[0]
        assert len(result.judgments) == 15
        assert all(j.answer is None for j in result.judgments)

    @patch("laya.Router")
    def test_execution_time_tracked(self, mock_router_class):
        """Die Ausführungszeit sollte erfasst werden."""
        mock_router = MagicMock()
        mock_router.predict.return_value = self._make_mock_laya_output()
        mock_router_class.return_value = mock_router

        result = run_judge("Test text")
        assert result.execution_time_ms > 0


# ---------------------------------------------------------------------------
# Tests: store_judgments
# ---------------------------------------------------------------------------

class TestStoreJudgments:
    """Teste das Speichern von Judge-Ergebnissen in die Datenbank."""

    def test_store_single_listing(self, temp_db):
        """Ein Listing mit allen 15 Urteilen speichern."""
        judgments = [
            Judgment(listing_id="test-001", question_id=qid, answer="true",
                     probability=0.8, confidence=0.8)
            for qid in list(QUESTION_DEFS.keys())
        ]
        judge_result = JudgeResult(
            listing_id="test-001",
            judgments=judgments,
            execution_time_ms=1500.0,
        )
        # Set listing_id on each judgment too (for consistency)
        for j in judge_result.judgments:
            j.listing_id = "test-001"

        store_judgments(temp_db, "test-001", judge_result)

        # Prüfe, dass alle 14 Zeilen gespeichert wurden
        rows = temp_db.execute("SELECT COUNT(*) FROM judgments WHERE listing_id = ?",
                               ("test-001",)).fetchone()
        assert rows[0] == 15

        # Prüfe, dass die Primärschlüssel korrekt sind
        for j in judgments:
            row = temp_db.execute(
                "SELECT answer, probability, confidence FROM judgments WHERE listing_id = ? AND question_id = ?",
                ("test-001", j.question_id),
            ).fetchone()
            assert row is not None
            assert row[0] == j.answer

    def test_replace_existing(self, temp_db):
        """Bestehende Urteile sollten überschrieben werden (INSERT OR REPLACE)."""
        # Erstes Mal speichern
        j1 = Judgment(listing_id="test-002", question_id="f_heating_fossil",
                      answer="true", probability=0.9, confidence=0.9)
        store_judgments(temp_db, "test-002", JudgeResult(listing_id="test-002", judgments=[j1]))

        # Zweites Mal mit anderem Wert
        j2 = Judgment(listing_id="test-002", question_id="f_heating_fossil",
                      answer="false", probability=0.3, confidence=0.3)
        store_judgments(temp_db, "test-002", JudgeResult(listing_id="test-002", judgments=[j2]))

        # Sollte nur eine Zeile geben
        count = temp_db.execute(
            "SELECT COUNT(*) FROM judgments WHERE listing_id = ? AND question_id = ?",
            ("test-002", "f_heating_fossil"),
        ).fetchone()[0]
        assert count == 1

        # Der neue Wert sollte gespeichert sein
        row = temp_db.execute(
            "SELECT answer, probability FROM judgments WHERE listing_id = ? AND question_id = ?",
            ("test-002", "f_heating_fossil"),
        ).fetchone()
        assert row[0] == "false"
        assert row[1] == 0.3


# ---------------------------------------------------------------------------
# Tests: judge_listing
# ---------------------------------------------------------------------------

class TestJudgeListing:
    """Teste judge_listing (Judge + Store in einem Schritt)."""

    @patch("laya.Router")
    def test_full_pipeline(self, mock_router_class, temp_db):
        """Vollständiger Durchlauf: Judge aufrufen und speichern."""
        mock_router = MagicMock()
        mock_router.predict.return_value = {
            "answers": {
                "f_heating_fossil": {"type": "noul", "noul": 0.9, "confidence": 0.9},
                "c_letting_status": {
                    "type": "choice", "choice": "vacant",
                    "probabilities": {"let": 0.1, "vacant": 0.7, "owner-occupied": 0.15, "unclear": 0.05},
                    "confidence": 0.25, "answer_confidence": 0.7,
                },
                "s_condition": {
                    "type": "score", "score": 3.0,
                    "legend": {"0": "Sehr schlecht", "1": "Schlecht", "2": "Durchschnittlich", "3": "Gut", "4": "Sehr gut"},
                    "probabilities": {"0": 0.01, "1": 0.02, "2": 0.10, "3": 0.75, "4": 0.12},
                    "confidence": 0.30, "answer_confidence": 0.75,
                },
            },
            "routing": {"model": "multilingual"},
            "usage": {},
        }
        mock_router_class.return_value = mock_router

        # Nur 3 Fragen testen (die gemockten)
        questions = {qid: QUESTION_DEFS[qid] for qid in ["f_heating_fossil", "c_letting_status", "s_condition"]}

        result = judge_listing(temp_db, "test-003", "Test text", questions=questions)

        assert len(result.judgments) == 3
        # Prüfe DB
        count = temp_db.execute("SELECT COUNT(*) FROM judgments WHERE listing_id = ?",
                                ("test-003",)).fetchone()[0]
        assert count == 3


# ---------------------------------------------------------------------------
# Tests: judge_batch
# ---------------------------------------------------------------------------

class TestJudgeBatch:
    """Teste judge_batch (Batch-Verarbeitung)."""

    @patch("laya.Router")
    def test_batch_processing(self, mock_router_class, temp_db):
        """Batch-Verarbeitung mehrerer Listings."""
        mock_router = MagicMock()
        mock_router.predict.return_value = {
            "answers": {
                "f_heating_fossil": {"type": "noul", "noul": 0.8, "confidence": 0.8},
                "c_letting_status": {
                    "type": "choice", "choice": "let",
                    "probabilities": {"let": 0.6, "vacant": 0.3, "owner-occupied": 0.08, "unclear": 0.02},
                    "confidence": 0.20, "answer_confidence": 0.6,
                },
                "s_condition": {
                    "type": "score", "score": 2.0,
                    "legend": {"0": "Sehr schlecht", "1": "Schlecht", "2": "Durchschnittlich", "3": "Gut", "4": "Sehr gut"},
                    "probabilities": {"0": 0.01, "1": 0.10, "2": 0.70, "3": 0.15, "4": 0.04},
                    "confidence": 0.25, "answer_confidence": 0.70,
                },
            },
            "routing": {"model": "multilingual"},
            "usage": {},
        }
        mock_router_class.return_value = mock_router

        listings = [
            ("batch-001", "Text für Listing 1"),
            ("batch-002", "Text für Listing 2"),
            ("batch-003", "Text für Listing 3"),
        ]

        results = judge_batch(temp_db, listings)

        assert len(results) == 3
        for r in results:
            assert len(r.judgments) == 15

        # Alle 3 * 15 = 45 Zeilen in DB
        count = temp_db.execute("SELECT COUNT(*) FROM judgments").fetchone()[0]
        assert count == 45


# ---------------------------------------------------------------------------
# Tests: Pretty-print
# ---------------------------------------------------------------------------

class TestPrettyPrint:
    """Teste format_judgment und format_result."""

    def test_format_judgment_with_values(self):
        j = Judgment(listing_id="test", question_id="f_heating_fossil",
                     answer="true", probability=0.85, confidence=0.85)
        output = format_judgment(j)
        assert "f_heating_fossil" in output
        assert "answer=true" in output
        assert "probability=0.8500" in output
        assert "confidence=0.8500" in output

    def test_format_judgment_none_values(self):
        j = Judgment(listing_id="test", question_id="f_heating_fossil",
                     answer=None, probability=None, confidence=None)
        output = format_judgment(j)
        assert "answer=None" in output
        assert "probability=" not in output
        assert "confidence=" not in output

    def test_format_result_with_errors(self):
        r = JudgeResult(
            listing_id="test-001",
            judgments=[Judgment(listing_id="test-001", question_id="f_heating_fossil",
                                answer="true", probability=0.8, confidence=0.8)],
            errors=["Laya-Fehler: Connection timeout"],
            execution_time_ms=2500.0,
        )
        output = format_result(r)
        assert "test-001" in output
        assert "2500ms" in output
        assert "Laya-Fehler" in output

    def test_format_result_clean(self):
        r = JudgeResult(
            listing_id="test-002",
            judgments=[
                Judgment(listing_id="test-002", question_id=qid, answer="test",
                         probability=0.5, confidence=0.5)
                for qid in ["f_heating_fossil", "c_letting_status"]
            ],
            execution_time_ms=1000.0,
        )
        output = format_result(r)
        assert "test-002" in output
        assert "1000ms" in output
        assert "Errors" not in output


# ---------------------------------------------------------------------------
# Tests: Integration mit echten Listings (THE-510)
# ---------------------------------------------------------------------------

class TestIntegrationRealListings:
    """Integrationstests mit echten Listings aus THE-510."""

    @pytest.fixture
    def real_listings_db(self, tmp_path):
        """Kopiere die THE-510-Datenbank in ein temporäres Verzeichnis."""
        src_db = "/home/vincent/multica_workspaces/the-beast-c9aa2abd75c1/the-510-ee031b484b39/workdir/listings.db"
        dst_db = str(tmp_path / "listings.db")

        if os.path.exists(src_db):
            import shutil
            shutil.copy2(src_db, dst_db)

            # Füge judgments-Tabelle hinzu (falls nicht vorhanden)
            conn = sqlite3.connect(dst_db)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS judgments (
                    listing_id    TEXT NOT NULL,
                    question_id   TEXT NOT NULL,
                    model_version TEXT,
                    answer        TEXT,
                    probability   REAL,
                    confidence    REAL,
                    created_at    TEXT NOT NULL DEFAULT (datetime('now')),
                    PRIMARY KEY (listing_id, question_id)
                )
            """)
            conn.commit()
            conn.close()
            return dst_db
        return None

    @patch("laya.Router")
    def test_judge_real_listing(self, mock_router_class, real_listings_db, tmp_path):
        """Teste mit einem echten Listing-Text."""
        if real_listings_db is None:
            pytest.skip("THE-510 listings.db nicht gefunden")

        # Lese ein echtes Listing
        conn = sqlite3.connect(real_listings_db)
        listing = conn.execute(
            "SELECT listing_id, title, raw_data FROM listing LIMIT 1"
        ).fetchone()
        conn.close()

        if listing is None:
            pytest.skip("Keine Listings in Datenbank")

        listing_id, title, raw_data = listing
        # raw_data ist bei allen THE-510-Listings leer (THE-510-Bug)
        # Verwende einen synthetischen, realistischen Exposé-Text
        text = ("Helle und freundliche 3-Zimmer-Wohnung in Leipzig-Plagwitz, "
                "75 qm, 3. OG mit Aufzug, Parkettboden, Einbauküche vorhanden. "
                "Zentralheizung (Gas), bezugsfrei ab sofort. "
                "Kein Erbbaurecht, keine Sonderumlage. "
                "Die Wohnung ist aktuell vermietet. "
                "Die Lage ist sehr gut, nah an ÖPNV und Einkaufsmöglichkeiten. "
                "Kaltmiete 750 Euro inklusive NK. Kaufpreis 185.000 Euro.")

        # Mocke Laya für deterministische Ergebnisse
        mock_router = MagicMock()
        mock_router.predict.return_value = {
            "answers": {
                "f_heating_fossil": {"type": "noul", "noul": 0.85, "confidence": 0.85},
                "f_erbpacht": {"type": "noul", "noul": 0.20, "confidence": 0.20},
                "c_letting_status": {
                    "type": "choice", "choice": "let",
                    "probabilities": {"let": 0.6, "vacant": 0.3, "owner-occupied": 0.08, "unclear": 0.02},
                    "confidence": 0.20, "answer_confidence": 0.6,
                },
                "s_condition": {
                    "type": "score", "score": 3.0,
                    "legend": {"0": "Sehr schlecht", "1": "Schlecht", "2": "Durchschnittlich", "3": "Gut", "4": "Sehr gut"},
                    "probabilities": {"0": 0.01, "1": 0.02, "2": 0.10, "3": 0.75, "4": 0.12},
                    "confidence": 0.30, "answer_confidence": 0.75,
                },
            },
            "routing": {"model": "multilingual"},
            "usage": {},
        }
        mock_router_class.return_value = mock_router

        # Teste nur 4 Fragen
        questions = {qid: QUESTION_DEFS[qid] for qid in [
            "f_heating_fossil", "f_erbpacht", "c_letting_status", "s_condition"
        ]}

        # Erstelle eine separate DB für den Test
        test_db_path = str(tmp_path / "test.db")
        test_conn = sqlite3.connect(test_db_path)
        test_conn.execute("""
            CREATE TABLE judgments (
                listing_id TEXT NOT NULL, question_id TEXT NOT NULL,
                model_version TEXT, answer TEXT, probability REAL, confidence REAL,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                PRIMARY KEY (listing_id, question_id)
            )
        """)
        test_conn.commit()

        result = judge_listing(test_conn, listing_id, text, questions=questions)

        assert len(result.judgments) == 4
        assert result.errors == []

        # Prüfe DB
        count = test_conn.execute(
            "SELECT COUNT(*) FROM judgments WHERE listing_id = ?",
            (listing_id,),
        ).fetchone()[0]
        assert count == 4

        # Prüfe spezifische Antworten (aus dem synthetischen Text)
        answers = {j.question_id: j.answer for j in result.judgments}
        assert answers["f_heating_fossil"] == "true"   # Gas-Zentralheizung
        assert answers["f_erbpacht"] == "false"        # Kein Erbbaurecht
        assert answers["c_letting_status"] == "let"    # Aktuell vermietet
        assert answers["s_condition"] == "Gut"         # bezugsfrei/hell/freundlich

        test_conn.close()
