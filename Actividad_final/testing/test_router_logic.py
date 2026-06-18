"""
tests/test_router_logic.py

Unit tests for ask_unified() routing logic.

Strategy: mock classify_intent_llm (the only LLM call in the router) and
stub out the downstream handlers (_answer_from_metadata, _answer_from_rag, etc.)
so no OpenAI or Postgres calls are made.

All tests run offline.
"""
from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault("OPENAI_API_KEY", "sk-test-notaria-fake-key-for-unit-tests")

from src.core.router import AskResponse, ask_unified, _answer_from_chat


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_llm_route(mode: str, **extra) -> dict:
    base = {
        "mode": mode,
        "file_id": None,
        "acto_caso": None,
        "looks_like_facultad": False,
        "is_cross_document_search": False,
        "chat_intent": None,
        "confidence": 0.95,
    }
    base.update(extra)
    return base


def _sql_response() -> AskResponse:
    return AskResponse(answer="Hay 42 escrituras.", source_type="metadata", extra={})


def _rag_response() -> AskResponse:
    return AskResponse(answer="El poder otorga facultades amplias.", source_type="rag", extra={})


# ---------------------------------------------------------------------------
# ask_unified routes to SQL
# ---------------------------------------------------------------------------

class TestRoutingToSql:
    @patch("src.core.router.classify_intent_llm", return_value=_make_llm_route("sql"))
    @patch("src.core.router._answer_from_metadata", return_value=_sql_response())
    def test_sql_mode_calls_metadata(self, mock_meta, mock_clf):
        resp = ask_unified("cuántas escrituras hay")
        mock_meta.assert_called_once()
        assert resp.source_type == "metadata"

    @patch("src.core.router.classify_intent_llm", return_value=_make_llm_route("sql"))
    @patch("src.core.router._answer_from_metadata", return_value=_sql_response())
    def test_sql_answer_content_preserved(self, mock_meta, mock_clf):
        resp = ask_unified("cuántas escrituras hay")
        assert "42" in resp.answer


# ---------------------------------------------------------------------------
# ask_unified routes to RAG
# ---------------------------------------------------------------------------

class TestRoutingToRag:
    @patch("src.core.router.classify_intent_llm", return_value=_make_llm_route("qa"))
    @patch("src.core.router._answer_from_rag", return_value=_rag_response())
    def test_qa_mode_calls_rag(self, mock_rag, mock_clf):
        resp = ask_unified("qué facultades tiene el poder 20-0287")
        mock_rag.assert_called_once()
        assert resp.source_type == "rag"


# ---------------------------------------------------------------------------
# ask_unified routes to generator
# ---------------------------------------------------------------------------

class TestRoutingToGenerator:
    @patch(
        "src.core.router.classify_intent_llm",
        return_value=_make_llm_route("generate_poder"),
    )
    @patch(
        "src.core.router.detectar_tipo_desde_query",
        return_value=None,  # type not detected
    )
    def test_generate_poder_unknown_type_asks_for_clarification(
        self, mock_detect, mock_clf
    ):
        resp = ask_unified("generar una escritura")
        assert resp.source_type == "poder_generator"
        assert "tipo" in resp.answer.lower() or "específico" in resp.answer.lower() or "especif" in resp.answer.lower()


# ---------------------------------------------------------------------------
# ask_unified routes to chat
# ---------------------------------------------------------------------------

class TestRoutingToChat:
    @patch(
        "src.core.router.classify_intent_llm",
        return_value=_make_llm_route("chat", chat_intent="greeting"),
    )
    def test_chat_greeting(self, mock_clf):
        resp = ask_unified("hola")
        assert resp.source_type == "chat"

    @patch(
        "src.core.router.classify_intent_llm",
        return_value=_make_llm_route("chat", chat_intent="help"),
    )
    def test_chat_help(self, mock_clf):
        resp = ask_unified("ayuda")
        assert resp.source_type == "chat"


# ---------------------------------------------------------------------------
# _answer_from_chat — static intent responses (no LLM)
# ---------------------------------------------------------------------------

class TestAnswerFromChat:
    def test_greeting_intent(self):
        resp = _answer_from_chat("hola", {"mode": "chat", "chat_intent": "greeting"})
        assert resp.source_type == "chat"
        assert len(resp.answer) > 0

    def test_capabilities_intent(self):
        resp = _answer_from_chat("qué podés hacer", {"mode": "chat", "chat_intent": "capabilities"})
        assert resp.source_type == "chat"

    def test_help_intent(self):
        resp = _answer_from_chat("ayuda", {"mode": "chat", "chat_intent": "help"})
        assert "ayuda" in resp.answer.lower() or "ejemplo" in resp.answer.lower() or "cómo" in resp.answer.lower()

    def test_thanks_intent(self):
        resp = _answer_from_chat("gracias", {"mode": "chat", "chat_intent": "thanks"})
        assert resp.source_type == "chat"

    def test_extra_contains_intent(self):
        resp = _answer_from_chat("hola", {"mode": "chat", "chat_intent": "greeting"})
        assert resp.extra is not None
        assert resp.extra.get("intent") == "greeting"

    @patch("openai.OpenAI")
    def test_other_intent_falls_back_without_llm_error(self, mock_openai):
        mock_client = MagicMock()
        mock_openai.return_value = mock_client
        mock_client.chat.completions.create.side_effect = Exception("network error")
        resp = _answer_from_chat("algo raro", {"mode": "chat", "chat_intent": "other"})
        assert resp.source_type == "chat"
        assert len(resp.answer) > 0


# ---------------------------------------------------------------------------
# AskResponse dataclass
# ---------------------------------------------------------------------------

class TestAskResponse:
    def test_defaults(self):
        r = AskResponse(answer="ok", source_type="metadata")
        assert r.extra is None
        assert r.tipo_escritura is None

    def test_extra_field(self):
        r = AskResponse(answer="ok", source_type="rag", extra={"hits": []})
        assert r.extra == {"hits": []}
