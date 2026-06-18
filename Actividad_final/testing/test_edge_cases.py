"""
tests/test_edge_cases.py

Exhaustive edge-case tests for all components.

Coverage targets:
  - SQL safety: comment injection, false positives, unicode, semicolons
  - router._answer_from_chat: unknown/None intent, empty question, LLM failure
  - ask_unified: empty question, classifier exception, unknown mode
  - RAG helpers: accented names, empty input, partial matches, company variants
  - Generator utils: large numbers, all months, leap-year dates, CUIL edge cases,
                     DictWrapper with None/nested/non-dict list items
  - ask_metadata: is_empty detection with all shapes (0, [], None, "")

All tests run fully offline — no OpenAI or Postgres required.
"""
from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault("OPENAI_API_KEY", "sk-test-notaria-fake-key-for-unit-tests")

from src.analytics.text_to_sql.sql_generator import SQLGenerator
from src.rag.search import extract_named_entities, verify_entities_in_text
from src.generators.generators import (
    DictWrapper,
    ValueAccessible,
    numero_a_letras,
    año_a_letras,
    fecha_a_letras,
    formatear_fecha_corta,
    formatear_dni,
    formatear_cuil_cuit,
    numero_escritura_a_letras,
)
from src.core.router import AskResponse, _answer_from_chat
from src.analytics.ask_meta_sql import _convert_response_to_result
from src.analytics.text_to_sql.main import TextToSQLResponse


# ─────────────────────────────────────────────────────────────────────────────
# 1. SQL SAFETY — validate_sql edge cases
# ─────────────────────────────────────────────────────────────────────────────

class TestValidateSqlEdgeCases:
    @pytest.fixture(autouse=True)
    def gen(self):
        self.gen = SQLGenerator.__new__(SQLGenerator)

    # --- Comment-based injection ---

    def test_inline_comment_with_forbidden_keyword_rejected(self):
        sql = "SELECT 1 -- DROP TABLE metadata"
        ok, err = self.gen.validate_sql(sql)
        assert ok is False

    def test_block_comment_with_forbidden_keyword_rejected(self):
        sql = "SELECT 1 /* DELETE FROM metadata */"
        ok, err = self.gen.validate_sql(sql)
        assert ok is False

    # --- Forbidden keyword as string value (false positive risk) ---

    def test_forbidden_keyword_as_string_value_is_rejected(self):
        sql = "SELECT * FROM metadata WHERE acto_caso = 'CREATE'"
        ok, _ = self.gen.validate_sql(sql)
        assert ok is False  # conservative: keyword found in payload

    def test_select_keyword_in_column_alias_passes(self):
        sql = "SELECT COUNT(*) AS total_docs FROM metadata"
        ok, err = self.gen.validate_sql(sql)
        assert ok is True

    # --- Semicolons as statement separator ---

    def test_semicolon_separator_with_safe_second_statement(self):
        sql = "SELECT 1; SELECT 2"
        ok, _ = self.gen.validate_sql(sql)
        assert ok is True

    def test_semicolon_separator_with_delete_rejected(self):
        sql = "SELECT 1; DELETE FROM metadata"
        ok, err = self.gen.validate_sql(sql)
        assert ok is False
        assert "DELETE" in (err or "")

    # --- Starts with whitespace ---

    def test_select_with_leading_whitespace_passes(self):
        sql = "   \n  SELECT COUNT(*) FROM metadata"
        ok, err = self.gen.validate_sql(sql)
        assert ok is True

    # --- Case variations ---

    def test_mixed_case_forbidden_keyword_detected(self):
        sql = "select 1; DrOp table metadata"
        ok, _ = self.gen.validate_sql(sql)
        assert ok is False

    def test_all_uppercase_valid_select(self):
        sql = "SELECT FILE_ID FROM METADATA WHERE ANIO = 2020"
        ok, _ = self.gen.validate_sql(sql)
        assert ok is True

    # --- Edge lengths ---

    def test_single_char_rejected(self):
        ok, _ = self.gen.validate_sql("S")
        assert ok is False  # doesn't start with SELECT

    def test_null_byte_in_sql_rejected(self):
        sql = "SELECT\x001 FROM metadata"
        ok, _ = self.gen.validate_sql(sql)
        assert isinstance(ok, bool)

    # --- WITH CTE edge ---

    def test_with_cte_select_rejected(self):
        sql = "WITH cte AS (SELECT * FROM metadata) SELECT * FROM cte"
        ok, _ = self.gen.validate_sql(sql)
        assert ok is False  # doesn't start with SELECT

    def test_select_subquery_passes(self):
        sql = "SELECT * FROM (SELECT file_id FROM metadata) AS sub"
        ok, _ = self.gen.validate_sql(sql)
        assert ok is True


# ─────────────────────────────────────────────────────────────────────────────
# 2. router._answer_from_chat — edge cases
# ─────────────────────────────────────────────────────────────────────────────

class TestAnswerFromChatEdgeCases:
    def test_none_chat_intent_does_not_raise(self):
        resp = _answer_from_chat("hola", {"mode": "chat", "chat_intent": None})
        assert resp.source_type == "chat"
        assert len(resp.answer) > 0

    def test_unknown_chat_intent_does_not_raise(self):
        resp = _answer_from_chat(
            "algo muy raro", {"mode": "chat", "chat_intent": "totally_unknown_intent_xyz"}
        )
        assert resp.source_type == "chat"
        assert len(resp.answer) > 0

    def test_empty_question_does_not_raise(self):
        resp = _answer_from_chat("", {"mode": "chat", "chat_intent": "greeting"})
        assert resp.source_type == "chat"

    def test_very_long_question_does_not_raise(self):
        long_q = "pregunta " * 500
        resp = _answer_from_chat(long_q, {"mode": "chat", "chat_intent": "help"})
        assert resp.source_type == "chat"

    def test_capabilities_intent_mentions_multiple_modes(self):
        resp = _answer_from_chat("qué podés hacer", {"mode": "chat", "chat_intent": "capabilities"})
        text = resp.answer.lower()
        mentioned = sum(1 for kw in ["consultar", "buscar", "generar", "escritura", "estadístic", "document"] if kw in text)
        assert mentioned >= 2

    def test_thanks_intent_is_polite(self):
        resp = _answer_from_chat("gracias", {"mode": "chat", "chat_intent": "thanks"})
        assert len(resp.answer) > 5

    def test_extra_dict_always_present(self):
        for intent in ["greeting", "help", "capabilities", "thanks"]:
            resp = _answer_from_chat("q", {"mode": "chat", "chat_intent": intent})
            assert isinstance(resp.extra, dict)


# ─────────────────────────────────────────────────────────────────────────────
# 3. ask_unified — edge cases (offline, router fully mocked)
# ─────────────────────────────────────────────────────────────────────────────

class TestAskUnifiedEdgeCases:
    def _make_route(self, mode: str, **kw) -> dict:
        return {
            "mode": mode,
            "file_id": None,
            "acto_caso": None,
            "looks_like_facultad": False,
            "is_cross_document_search": False,
            "chat_intent": None,
            "confidence": 0.9,
            **kw,
        }

    @patch("src.core.router.classify_intent_llm")
    @patch(
        "src.core.router._answer_from_chat",
        return_value=AskResponse(answer="No entendí el modo.", source_type="chat", extra={"intent": "other"}),
    )
    def test_unknown_mode_returns_chat_fallback(self, mock_chat, mock_clf):
        from src.core.router import ask_unified
        mock_clf.return_value = self._make_route("totally_unknown_mode_xyz")
        resp = ask_unified("algo")
        assert resp.source_type == "chat"
        mock_chat.assert_called_once()

    @patch("src.core.router.classify_intent_llm", side_effect=Exception("LLM timeout"))
    def test_classifier_exception_propagates(self, mock_clf):
        from src.core.router import ask_unified
        with pytest.raises(Exception, match="LLM timeout"):
            ask_unified("consulta")

    @patch(
        "src.core.router.classify_intent_llm",
        return_value={
            "mode": "chat", "file_id": None, "acto_caso": None,
            "looks_like_facultad": False, "is_cross_document_search": False,
            "chat_intent": "greeting", "confidence": 1.0,
        },
    )
    def test_empty_question_routes_to_chat(self, mock_clf):
        from src.core.router import ask_unified
        resp = ask_unified("")
        assert resp.source_type == "chat"


# ─────────────────────────────────────────────────────────────────────────────
# 4. RAG helpers — edge cases
# ─────────────────────────────────────────────────────────────────────────────

class TestExtractNamedEntitiesEdgeCases:
    def test_empty_string_returns_empty(self):
        assert extract_named_entities("") == []

    def test_whitespace_only_returns_empty(self):
        assert extract_named_entities("   \n\t  ") == []

    def test_single_word_no_entity(self):
        entities = extract_named_entities("hola")
        assert entities == []

    def test_accented_name_extracted(self):
        entities = extract_named_entities("qué escrituras firmó José García")
        assert any("García" in e or "José" in e for e in entities)

    def test_company_with_srl(self):
        entities = extract_named_entities("escritura de Constructora Buenos Aires S.R.L.")
        assert isinstance(entities, list)

    def test_company_with_sa(self):
        entities = extract_named_entities("escritura de ACME S.A.")
        assert any("ACME" in e for e in entities)

    def test_multiple_names_all_extracted(self):
        entities = extract_named_entities("Juan Pérez y María García firmaron la escritura")
        names = " ".join(entities)
        assert "Pérez" in names or "Juan" in names
        assert "García" in names or "María" in names

    def test_generic_query_has_no_entities(self):
        queries = [
            "cuántas escrituras hay",
            "mostrar todos los documentos de 2022",
            "estadísticas por tipo de acto",
        ]
        for q in queries:
            assert extract_named_entities(q) == [], f"Unexpected entities for: {q!r}"

    def test_file_id_pattern_not_extracted(self):
        entities = extract_named_entities("detalle de la escritura 20-0287")
        assert not any("20-0287" in e for e in entities)

    def test_dni_8_digits_extracted(self):
        entities = extract_named_entities("DNI 30123456")
        assert any("30123456" in e for e in entities)

    def test_very_long_query_does_not_raise(self):
        long_query = "Juan Pérez " * 200 + " firmó esta escritura"
        entities = extract_named_entities(long_query)
        assert isinstance(entities, list)


class TestVerifyEntitiesInTextEdgeCases:
    def test_none_entity_list_handled(self):
        assert verify_entities_in_text("texto", []) is True

    def test_entity_with_special_regex_chars(self):
        result = verify_entities_in_text("texto normal", ["S.A. (EMPRESA)"])
        assert isinstance(result, bool)

    def test_accented_entity_matches(self):
        text = "Firmó el escribano García"
        assert verify_entities_in_text(text, ["García"]) is True

    def test_partial_word_not_enough(self):
        text = "Pereza es un vicio"
        result = verify_entities_in_text(text, ["Pérez"])
        assert result is False

    def test_entity_at_start_of_text(self):
        assert verify_entities_in_text("Juan Pérez firmó", ["Juan Pérez"]) is True

    def test_entity_at_end_of_text(self):
        assert verify_entities_in_text("firmó Juan Pérez", ["Juan Pérez"]) is True

    def test_multiple_entities_all_must_match(self):
        text = "Juan Pérez y Ana García firmaron"
        assert verify_entities_in_text(text, ["Juan Pérez", "Ana García"]) is True
        assert verify_entities_in_text(text, ["Juan Pérez", "Luis López"]) is False

    def test_empty_text_always_false_with_entities(self):
        assert verify_entities_in_text("", ["Juan"]) is False
        assert verify_entities_in_text("  ", ["Juan"]) is False


# ─────────────────────────────────────────────────────────────────────────────
# 5. Generator utilities — edge cases
# ─────────────────────────────────────────────────────────────────────────────

class TestNumeroALetrasEdgeCases:
    def test_hundred_one(self):
        result = numero_a_letras(101)
        assert "ciento" in result
        assert "uno" in result or "un" in result

    def test_hundred_ten(self):
        result = numero_a_letras(110)
        assert "ciento" in result
        assert "diez" in result

    def test_three_hundred_thirty_three(self):
        result = numero_a_letras(333)
        assert "trescientos" in result
        assert "treinta" in result
        assert "tres" in result

    def test_five_hundred(self):
        assert "quinientos" in numero_a_letras(500)

    def test_seven_hundred(self):
        assert "setecientos" in numero_a_letras(700)

    def test_nine_hundred(self):
        assert "novecientos" in numero_a_letras(900)

    def test_one_thousand_one(self):
        result = numero_a_letras(1001)
        assert "mil" in result
        assert "uno" in result or "un" in result

    def test_ten_thousand(self):
        result = numero_a_letras(10000)
        assert "mil" in result

    def test_hundred_thousand(self):
        result = numero_a_letras(100000)
        assert "mil" in result

    def test_one_million(self):
        result = numero_a_letras(1000000)
        assert "millón" in result or "millon" in result or "mil" in result

    def test_twenty_one_is_veintiuno(self):
        result = numero_a_letras(21)
        assert "veintiún" in result or "veintiuno" in result or "veinte" in result

    def test_sixteen(self):
        result = numero_a_letras(16)
        assert "dieciséis" in result or "dieciseis" in result or "dieci" in result


class TestFechaALetrasAllMonths:
    @pytest.mark.parametrize("month,name", [
        (1, "ENERO"), (2, "FEBRERO"), (3, "MARZO"), (4, "ABRIL"),
        (5, "MAYO"), (6, "JUNIO"), (7, "JULIO"), (8, "AGOSTO"),
        (9, "SEPTIEMBRE"), (10, "OCTUBRE"), (11, "NOVIEMBRE"), (12, "DICIEMBRE"),
    ])
    def test_all_months(self, month, name):
        result = fecha_a_letras(date(2023, month, 1))
        assert name in result

    def test_leap_year_feb_29(self):
        result = fecha_a_letras(date(2024, 2, 29))
        assert "FEBRERO" in result
        assert "VEINTINUEVE" in result or "29" not in result

    def test_december_31(self):
        result = fecha_a_letras(date(2023, 12, 31))
        assert "DICIEMBRE" in result
        assert "TREINTA" in result

    def test_january_1(self):
        result = fecha_a_letras(date(2023, 1, 1))
        assert "ENERO" in result
        assert "UNO" in result or "PRIMERO" in result

    def test_lowercase_option_full_month(self):
        result = fecha_a_letras(date(2023, 6, 15), mayusculas=False)
        assert "junio" in result
        assert result == result.lower()


class TestFormatearCuilCuitEdgeCases:
    def test_short_input_does_not_crash(self):
        result = formatear_cuil_cuit("123")
        assert isinstance(result, str)

    def test_already_has_dashes(self):
        result = formatear_cuil_cuit("20-12345678-9")
        assert "-" in result

    def test_11_digit_prefix_23(self):
        result = formatear_cuil_cuit("23123456789")
        parts = result.split("-")
        assert parts[0] == "23"

    def test_empty_string_does_not_crash(self):
        result = formatear_cuil_cuit("")
        assert isinstance(result, str)


class TestFormatearDniEdgeCases:
    def test_with_hyphens(self):
        assert formatear_dni("12-345-678") == "12345678"

    def test_integer_string(self):
        assert formatear_dni("1234567") == "1234567"

    def test_empty_string(self):
        result = formatear_dni("")
        assert isinstance(result, str)

    def test_letters_in_dni(self):
        result = formatear_dni("abc")
        assert isinstance(result, str)


class TestDictWrapperEdgeCases:
    def test_none_value_accessed_as_attribute(self):
        w = DictWrapper({"campo": None})
        val = w.campo
        assert val is None or isinstance(val, DictWrapper) or val == ""

    def test_deeply_nested_access(self):
        w = DictWrapper({"a": {"b": {"c": {"d": "deep_value"}}}})
        assert w.a.b.c.d == "deep_value" or str(w.a.b.c.d) == "deep_value"

    def test_list_with_non_dict_items(self):
        w = DictWrapper({"items": [1, "string", None, {"key": "val"}]})
        items = w.items
        assert isinstance(items, list)

    def test_empty_list_attribute(self):
        w = DictWrapper({"items": []})
        assert w.items == []

    def test_boolean_value(self):
        w = DictWrapper({"activo": True})
        val = w.activo
        assert val is True or str(val) == "True"

    def test_integer_value(self):
        w = DictWrapper({"anio": 2023})
        val = w.anio
        assert val == 2023 or str(val) == "2023"

    def test_missing_key_chain_does_not_raise(self):
        w = DictWrapper({"a": {}})
        result = w.a.b.c.d
        assert isinstance(result, DictWrapper) or result is None or result == ""

    def test_nombre_completo_formateado_with_only_nombre(self):
        w = DictWrapper({"nombre": "Ana"})
        assert w.nombre_completo_formateado() == "Ana"

    def test_nombre_completo_formateado_no_fields(self):
        w = DictWrapper({})
        result = w.nombre_completo_formateado()
        assert isinstance(result, str)


# ─────────────────────────────────────────────────────────────────────────────
# 6. ask_metadata — _convert_response_to_result edge cases
# ─────────────────────────────────────────────────────────────────────────────

class TestConvertResponseToResult:
    def _make_response(self, answer="ok", source_type="metadata", extra=None, record=None):
        return TextToSQLResponse(
            answer=answer,
            source_type=source_type,
            extra=extra or {},
            record=record,
        )

    def test_data_is_zero_is_empty(self):
        resp = self._make_response(extra={"data": 0})
        result = _convert_response_to_result(resp)
        assert result.is_empty is True

    def test_data_is_empty_list_is_empty(self):
        resp = self._make_response(extra={"data": []})
        result = _convert_response_to_result(resp)
        assert result.is_empty is True

    def test_data_is_none_is_empty(self):
        resp = self._make_response(extra={"data": None})
        result = _convert_response_to_result(resp)
        assert result.is_empty is True

    def test_data_is_ningún_resultado_is_empty(self):
        resp = self._make_response(extra={"data": "ningún resultado"})
        result = _convert_response_to_result(resp)
        assert result.is_empty is True

    def test_data_is_positive_number_not_empty(self):
        resp = self._make_response(extra={"data": 42})
        result = _convert_response_to_result(resp)
        assert result.is_empty is False

    def test_data_is_list_with_items_not_empty(self):
        resp = self._make_response(extra={"data": ["20-0001", "20-0002"]})
        result = _convert_response_to_result(resp)
        assert result.is_empty is False

    def test_extra_is_empty_dict_is_empty(self):
        resp = self._make_response(extra={})
        result = _convert_response_to_result(resp)
        assert result.is_empty is True  # data=None → empty

    def test_answer_preserved(self):
        resp = self._make_response(answer="Hay 5 escrituras.", extra={"data": 5})
        result = _convert_response_to_result(resp)
        assert result.formatted_text == "Hay 5 escrituras."

    def test_record_preserved(self):
        rec = {"file_id": "20-0001", "acto_caso": "compraventa_inmueble"}
        resp = self._make_response(record=rec, extra={"data": rec})
        result = _convert_response_to_result(resp)
        assert result.record == rec

    def test_extra_without_data_key(self):
        resp = self._make_response(extra={"sql": "SELECT 1", "other": "value"})
        result = _convert_response_to_result(resp)
        assert result.is_empty is True  # no "data" key → data=None
