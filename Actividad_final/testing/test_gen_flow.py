"""
tests/test_gen_flow.py

Integration tests for the GEN conversation flow (document generation).

Tests are isolated from real DB and OpenAI calls:
- DB pool is mocked (or set to None for pure in-memory tests)
- ask_unified is patched to return a poder_generator intent on demand
- BaseConversationalManager.process_answer is patched to simulate user turns

Running:
    python -m pytest tests/test_gen_flow.py -v

These tests run fully offline (no OPENAI_API_KEY or DATABASE_URL required).
"""
from __future__ import annotations

import json
import os
import tempfile
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Set dummy API key before any module that reads it is imported.
# BaseConversationalManager.__init__ calls OpenAI(api_key=...) — it fails
# without a key even when process_answer is mocked. The actual network call
# is never made because process_answer is always patched in these tests.
os.environ.setdefault("OPENAI_API_KEY", "sk-test-notaria-fake-key-for-unit-tests")

# ── App factory ───────────────────────────────────────────────────────────────

def _make_test_app(pool=None):
    """
    Minimal FastAPI app with only the chat router.
    Avoids the lifespan in main.py (which requires DATABASE_URL).
    """
    from fastapi import FastAPI
    from backend.routers import chat as chat_module

    app = FastAPI()
    app.include_router(chat_module.router, prefix="/chat")
    app.state.pool = pool
    return app


# ── Mock AI responses ─────────────────────────────────────────────────────────

ACTO_CASO = "poder_general_adm_y_judicial"


def _poder_generator_response():
    """ask_unified returns a GEN intent."""
    return SimpleNamespace(
        answer="Perfecto, voy a ayudarte a generar un Poder General.",
        source_type="poder_generator",
        extra={
            "tiene_conversacional": True,
            "tipo_nombre": "Poder General Administrativo y Judicial",
            "acto_caso": ACTO_CASO,
        },
        tipo_escritura=SimpleNamespace(value=ACTO_CASO),
    )


def _sql_response():
    """ask_unified returns a plain SQL response (non-GEN)."""
    return SimpleNamespace(
        answer="Hay 42 escrituras en total.",
        source_type="metadata",
        extra={},
        tipo_escritura=None,
    )


# ── Mock DB pool ──────────────────────────────────────────────────────────────

def _make_mock_pool(gen_state_for_conv: dict | None = None, conv_id: str | None = None):
    """
    Build a mock asyncpg pool.

    - fetchrow("… gen_state …")  → {"gen_state": gen_state_for_conv}
    - fetchrow("… SELECT id …")  → {"id": conv_id}  (conversation existence)
    - execute(…)                 → None (success)
    - fetch(…)                   → []

    Returns (pool, conn, execute_calls_list).
    """
    execute_calls: list[dict] = []

    def _fetchrow_side_effect(query, *args):
        if "gen_state" in query:
            if gen_state_for_conv is not None:
                return {"gen_state": gen_state_for_conv}
            return {"gen_state": None}
        # Conversation existence check ("SELECT id FROM conversations …")
        if conv_id:
            return {"id": conv_id}
        return None

    def _execute_side_effect(query, *args):
        execute_calls.append({"query": query.strip(), "args": args})

    mock_conn = MagicMock()
    mock_conn.fetchrow = AsyncMock(side_effect=_fetchrow_side_effect)
    mock_conn.execute = AsyncMock(side_effect=_execute_side_effect)
    mock_conn.fetch = AsyncMock(return_value=[])

    class _Acquire:
        async def __aenter__(self):
            return mock_conn

        async def __aexit__(self, *_):
            pass

    mock_pool = MagicMock()
    mock_pool.acquire.return_value = _Acquire()

    return mock_pool, mock_conn, execute_calls


# ── Shared store cleanup fixture ──────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _clear_store():
    """Reset the global in-memory session store before every test."""
    from backend.conversation_state import get_store
    get_store()._store.clear()
    yield
    get_store()._store.clear()


# ═══════════════════════════════════════════════════════════════════════════════
# Test 1 — Full in-memory flow
# ═══════════════════════════════════════════════════════════════════════════════

class TestFullInMemoryFlow:
    """
    4 requests with the same conversation_id, no DB (pool=None).
    Verifies that the source_type sequence is:
        gen_active → gen_active → gen_active → gen_complete
    and that DOCX bytes are stored in the session entry after completion.
    """

    def test_gen_flow_four_turns(self):
        from starlette.testclient import TestClient
        from backend.conversation_state import get_store

        store = get_store()
        app = _make_test_app(pool=None)
        client = TestClient(app)

        # ── Turn 1: Trigger GEN intent via ask_unified ────────────────────────
        with patch("src.core.router.ask_unified", return_value=_poder_generator_response()):
            r1 = client.post("/chat", json={"message": "quiero generar un poder general"})

        assert r1.status_code == 200, r1.text
        d1 = r1.json()
        assert d1["source_type"] == "gen_active", (
            f"Turn 1: expected gen_active, got '{d1['source_type']}'"
        )
        conv_id = d1["conversation_id"]
        assert conv_id, "Turn 1 must produce a conversation_id"
        assert store.has(conv_id), "Session must be in memory store after Turn 1"

        # ── Turn 2: Provide poderdante data ──────────────────────────────────
        with patch(
            "src.generators.generators.BaseConversationalManager.process_answer",
            return_value={
                "status": "ok",
                "next_question": "Datos del apoderado.",
                "complete": False,
            },
        ):
            r2 = client.post("/chat", json={
                "message": "Juan Pérez, DNI 12345678, argentino",
                "conversation_id": conv_id,
            })

        assert r2.status_code == 200, r2.text
        d2 = r2.json()
        assert d2["source_type"] == "gen_active", (
            f"Turn 2: expected gen_active, got '{d2['source_type']}'"
        )

        # ── Turn 3: Provide apoderado data ────────────────────────────────────
        with patch(
            "src.generators.generators.BaseConversationalManager.process_answer",
            return_value={
                "status": "ok",
                "next_question": "¿Cuál es el objeto del poder?",
                "complete": False,
            },
        ):
            r3 = client.post("/chat", json={
                "message": "María García, DNI 87654321",
                "conversation_id": conv_id,
            })

        assert r3.status_code == 200, r3.text
        d3 = r3.json()
        assert d3["source_type"] == "gen_active", (
            f"Turn 3: expected gen_active, got '{d3['source_type']}'"
        )

        # ── Turn 4: Complete the flow ─────────────────────────────────────────
        fake_docx = b"PK\x03\x04FAKE_DOCX_CONTENT"

        def _fake_generate_docx(data, output_path=None):
            """Write fake bytes to output_path (the caller owns the temp file)."""
            if output_path is None:
                import tempfile as _tf
                fd, output_path = _tf.mkstemp(suffix=".docx")
                os.close(fd)
            with open(output_path, "wb") as _f:
                _f.write(fake_docx)
            return output_path

        with patch(
            "src.generators.generators.BaseConversationalManager.process_answer",
            return_value={
                "status": "complete",
                "message": "✅ Documento generado.",
                "complete": True,
            },
        ), patch(
            "src.generators.generators.UniversalGenerator.generate_docx",
            side_effect=_fake_generate_docx,
        ):
            r4 = client.post("/chat", json={
                "message": "actos de administración y disposición en general",
                "conversation_id": conv_id,
            })

        assert r4.status_code == 200, r4.text
        d4 = r4.json()
        assert d4["source_type"] == "gen_complete", (
            f"Turn 4: expected gen_complete, got '{d4['source_type']}'"
        )

        # Session stays in store so the /generate/docx/:id endpoint can serve it
        assert store.has(conv_id), "Entry must remain in store after gen_complete"
        entry = store.get(conv_id)
        assert entry is not None
        assert entry.docx_bytes == fake_docx, "DOCX bytes must be stored in session entry"


# ═══════════════════════════════════════════════════════════════════════════════
# Test 2 — DB restore after in-memory eviction
# ═══════════════════════════════════════════════════════════════════════════════

class TestDbRestore:
    """
    Simulates a server restart between GEN turns.

    1. Turn 1 starts a GEN session (pool=None → pure in-memory).
    2. The in-memory store is forcibly cleared (simulating restart).
    3. Turn 2 is sent with a mocked pool that returns the serialized gen_state.
    4. The router must restore the session from DB and continue the conversation.
    """

    def test_session_restored_from_db(self):
        from starlette.testclient import TestClient
        from backend.conversation_state import get_store, serialize_manager_state

        store = get_store()

        # ── Turn 1: start GEN session (no DB) ────────────────────────────────
        app_no_db = _make_test_app(pool=None)
        client_no_db = TestClient(app_no_db)

        with patch("src.core.router.ask_unified", return_value=_poder_generator_response()):
            r1 = client_no_db.post("/chat", json={"message": "generar poder general"})

        assert r1.status_code == 200, r1.text
        conv_id = r1.json()["conversation_id"]
        assert store.has(conv_id), "Session must be in store after Turn 1"

        # Capture serialized state before clearing store
        entry = store.get(conv_id)
        saved_gen_state = serialize_manager_state(entry.manager, entry.tipo_nombre)
        fields_done_before = set(saved_gen_state["data"].keys())

        # Simulate server restart
        store._store.clear()
        assert not store.has(conv_id), "Store must be empty (simulating restart)"

        # ── Turn 2: send next answer — pool now has gen_state in DB ──────────
        mock_pool, _, execute_calls = _make_mock_pool(
            gen_state_for_conv=saved_gen_state,
            conv_id=conv_id,
        )
        app_with_db = _make_test_app(pool=mock_pool)
        client_with_db = TestClient(app_with_db)

        with patch(
            "src.generators.generators.BaseConversationalManager.process_answer",
            return_value={
                "status": "ok",
                "next_question": "Perfecto. Siguiente dato:",
                "complete": False,
            },
        ):
            r2 = client_with_db.post("/chat", json={
                "message": "Información del apoderado",
                "conversation_id": conv_id,
            })

        assert r2.status_code == 200, r2.text
        d2 = r2.json()

        assert d2["source_type"] == "gen_active", (
            f"DB restore failed: expected gen_active after restore, got '{d2['source_type']}'. "
            "Router went to ask_unified instead of restoring the session."
        )

        # Session should now be back in the in-memory store
        assert store.has(conv_id), "Session must be in store after DB restore"

        # The restored manager must have the same acto_caso
        restored_entry = store.get(conv_id)
        assert restored_entry.acto_caso == ACTO_CASO, (
            f"Restored acto_caso '{restored_entry.acto_caso}' != expected '{ACTO_CASO}'"
        )

        # gen_state must have been written back to DB on this turn
        gen_state_writes = [
            c for c in execute_calls
            if "gen_state" in c["query"] and "UPDATE" in c["query"]
        ]
        assert gen_state_writes, (
            "gen_state must be written back to DB after a successful turn post-restore"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Test 3 — Cancellation clears gen_state
# ═══════════════════════════════════════════════════════════════════════════════

class TestCancellation:
    """
    After a GEN session is started, sending "cancelar" must:
    - Remove the session from the in-memory store.
    - Return source_type = "chat".
    - Update DB gen_state to NULL (when DB is available).
    """

    def test_cancel_clears_session_in_memory(self):
        """Cancel with pool=None — verifies in-memory cleanup only."""
        from starlette.testclient import TestClient
        from backend.conversation_state import get_store

        store = get_store()
        app = _make_test_app(pool=None)
        client = TestClient(app)

        # Start GEN session
        with patch("src.core.router.ask_unified", return_value=_poder_generator_response()):
            r1 = client.post("/chat", json={"message": "generar poder"})

        assert r1.status_code == 200, r1.text
        conv_id = r1.json()["conversation_id"]
        assert store.has(conv_id), "Session must be in store after start"

        # Cancel — "cancelar" is a special command that bypasses LLM extraction
        r_cancel = client.post("/chat", json={
            "message": "cancelar",
            "conversation_id": conv_id,
        })

        assert r_cancel.status_code == 200, r_cancel.text
        d_cancel = r_cancel.json()

        assert d_cancel["source_type"] == "chat", (
            f"Cancellation must return source_type='chat', got '{d_cancel['source_type']}'"
        )
        assert not store.has(conv_id), (
            "Session must be removed from store after cancellation"
        )

    def test_cancel_clears_gen_state_in_db(self):
        """Cancel with mocked DB — verifies gen_state is set to NULL."""
        from starlette.testclient import TestClient
        from backend.conversation_state import get_store, serialize_manager_state

        store = get_store()

        # Turn 1: start GEN (no DB for simplicity)
        app_no_db = _make_test_app(pool=None)
        client_no_db = TestClient(app_no_db)

        with patch("src.core.router.ask_unified", return_value=_poder_generator_response()):
            r1 = client_no_db.post("/chat", json={"message": "generar poder"})

        conv_id = r1.json()["conversation_id"]
        entry = store.get(conv_id)
        saved_gen_state = serialize_manager_state(entry.manager, entry.tipo_nombre)

        # Turn 2: cancel via mocked DB (so gen_state cleanup can be verified)
        mock_pool, _, execute_calls = _make_mock_pool(
            gen_state_for_conv=saved_gen_state,
            conv_id=conv_id,
        )
        app_with_db = _make_test_app(pool=mock_pool)
        client_with_db = TestClient(app_with_db)

        r_cancel = client_with_db.post("/chat", json={
            "message": "cancelar",
            "conversation_id": conv_id,
        })

        assert r_cancel.status_code == 200, r_cancel.text
        assert r_cancel.json()["source_type"] == "chat"
        assert not store.has(conv_id), "Session removed from memory after cancel"

        # Verify gen_state was set to NULL in DB
        null_writes = [
            c for c in execute_calls
            if "gen_state = NULL" in c["query"] and "UPDATE" in c["query"]
        ]
        assert null_writes, (
            "gen_state must be set to NULL in DB after cancellation. "
            f"execute calls: {[c['query'] for c in execute_calls]}"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Test 4 — Two concurrent GEN conversations don't interfere
# ═══════════════════════════════════════════════════════════════════════════════

class TestConcurrency:
    """
    Two GEN conversations run interleaved on the same app instance.
    Each must maintain its own independent session state.
    """

    def test_two_conversations_are_independent(self):
        from starlette.testclient import TestClient
        from backend.conversation_state import get_store

        store = get_store()
        app = _make_test_app(pool=None)
        client = TestClient(app)

        # ── Start both sessions ───────────────────────────────────────────────
        with patch("src.core.router.ask_unified", return_value=_poder_generator_response()):
            r_a1 = client.post("/chat", json={"message": "quiero un poder general"})
            r_b1 = client.post("/chat", json={"message": "necesito generar un poder"})

        assert r_a1.status_code == 200, r_a1.text
        assert r_b1.status_code == 200, r_b1.text

        conv_a = r_a1.json()["conversation_id"]
        conv_b = r_b1.json()["conversation_id"]
        assert conv_a != conv_b, "Two requests without conversation_id must get distinct IDs"

        assert store.has(conv_a), "Conv A must be in store"
        assert store.has(conv_b), "Conv B must be in store"

        # ── Advance conv_a one turn ────────────────────────────────────────────
        with patch(
            "src.generators.generators.BaseConversationalManager.process_answer",
            return_value={
                "status": "ok",
                "next_question": "Datos del apoderado de A.",
                "complete": False,
            },
        ):
            r_a2 = client.post("/chat", json={
                "message": "Poderdante A: Carlos López",
                "conversation_id": conv_a,
            })

        assert r_a2.status_code == 200, r_a2.text
        assert r_a2.json()["source_type"] == "gen_active"

        # ── Conv B must not have been affected by conv_a's turn ───────────────
        assert store.has(conv_b), "Conv B session must still exist after conv_a advanced"
        assert store.has(conv_a), "Conv A session must still exist"

        # Conv B should still respond to gen flow (not SQL)
        with patch(
            "src.generators.generators.BaseConversationalManager.process_answer",
            return_value={
                "status": "ok",
                "next_question": "Datos del apoderado de B.",
                "complete": False,
            },
        ):
            r_b2 = client.post("/chat", json={
                "message": "Poderdante B: Ana Rodríguez",
                "conversation_id": conv_b,
            })

        assert r_b2.status_code == 200, r_b2.text
        assert r_b2.json()["source_type"] == "gen_active", (
            f"Conv B should still be in GEN mode, got '{r_b2.json()['source_type']}'"
        )

        # ── Cancel conv_a — must not affect conv_b ───────────────────────────
        r_a_cancel = client.post("/chat", json={
            "message": "cancelar",
            "conversation_id": conv_a,
        })
        assert r_a_cancel.status_code == 200, r_a_cancel.text
        assert r_a_cancel.json()["source_type"] == "chat"

        assert not store.has(conv_a), "Conv A cancelled — removed from store"
        assert store.has(conv_b), "Conv B must still be active after conv_a was cancelled"

        # ── Conv B must still accept GEN turns ───────────────────────────────
        with patch(
            "src.generators.generators.BaseConversationalManager.process_answer",
            return_value={
                "status": "ok",
                "next_question": "Objeto del poder de B.",
                "complete": False,
            },
        ):
            r_b3 = client.post("/chat", json={
                "message": "Luis Fernández, DNI 11111111",
                "conversation_id": conv_b,
            })

        assert r_b3.status_code == 200, r_b3.text
        assert r_b3.json()["source_type"] == "gen_active", (
            f"Conv B turn after conv_a cancel: expected gen_active, got '{r_b3.json()['source_type']}'"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Test 5 — Regression: router must start session, not return intro message
# ═══════════════════════════════════════════════════════════════════════════════

class TestNoIntroMessageRegression:
    """
    Regression test for the critical bug where the endpoint returned
    source_type="poder_generator" and answer="Iniciando generación de..."
    instead of source_type="gen_active" and the first question.

    Root cause: _start_generator_session was never called because the server
    process was stale (running old code without the session-start logic).

    This test verifies that:
    1. When ask_unified returns poder_generator + tiene_conversacional=True,
       the endpoint MUST return gen_active (not poder_generator).
    2. The answer must be the first question from the manager,
       NOT the intro message ("Iniciando generación de...").
    3. The session must be in the in-memory store after the first turn.
    """

    INTRO_MESSAGE = "Iniciando generación de Poder General de Administración y Judicial..."

    def test_first_response_is_not_intro_message(self):
        """
        The intro message must never reach the frontend as the final response.
        _start_generator_session must replace it with the first question.
        """
        from starlette.testclient import TestClient
        from backend.conversation_state import get_store

        store = get_store()
        app = _make_test_app(pool=None)
        client = TestClient(app)

        # Build a poder_generator response that exactly matches what the real
        # ask_unified returns (including the intro message as answer).
        intro_response = SimpleNamespace(
            answer=self.INTRO_MESSAGE,
            source_type="poder_generator",
            extra={
                "tiene_conversacional": True,
                "tipo_nombre": "Poder General de Administración y Judicial",
                "acto_caso": ACTO_CASO,
            },
            tipo_escritura=SimpleNamespace(value=ACTO_CASO),
        )

        with patch("src.core.router.ask_unified", return_value=intro_response):
            r = client.post("/chat", json={"message": "generar un poder general"})

        assert r.status_code == 200, r.text
        d = r.json()

        # ── Source type must be gen_active, never poder_generator ─────────────
        assert d["source_type"] == "gen_active", (
            f"REGRESSION: endpoint returned source_type='{d['source_type']}' instead of 'gen_active'. "
            "The _start_generator_session call is missing or was removed from post_chat."
        )

        # ── Answer must NOT be the intro message ─────────────────────────────
        assert d["answer"] != self.INTRO_MESSAGE, (
            f"REGRESSION: endpoint returned the intro message verbatim instead of the first question. "
            "The intro message must be replaced by the first question from BaseConversationalManager."
        )

        # ── Answer must be non-empty ──────────────────────────────────────────
        assert d["answer"].strip(), "First question must not be empty"

        # ── Session must be in memory store ──────────────────────────────────
        conv_id = d["conversation_id"]
        assert store.has(conv_id), (
            f"REGRESSION: session not found in memory store after first GEN turn. "
            "The manager was not persisted to the store."
        )

        # ── Extra must carry gen_active=True ─────────────────────────────────
        assert d.get("extra", {}).get("gen_active") is True, (
            f"extra.gen_active must be True after first GEN turn, got: {d.get('extra')}"
        )

    def test_intro_message_never_stored_as_user_visible_answer(self):
        """
        Even if ask_unified is called multiple times (e.g., retries),
        the intro message string must never appear as the final ChatResponse.answer.
        """
        from starlette.testclient import TestClient

        app = _make_test_app(pool=None)
        client = TestClient(app)

        # Call the endpoint 3 times (different conversations)
        # and verify none return the intro message
        intro_response = SimpleNamespace(
            answer=self.INTRO_MESSAGE,
            source_type="poder_generator",
            extra={"tiene_conversacional": True, "tipo_nombre": "Poder General"},
            tipo_escritura=SimpleNamespace(value=ACTO_CASO),
        )

        with patch("src.core.router.ask_unified", return_value=intro_response):
            for i in range(3):
                r = client.post("/chat", json={"message": f"generar un poder general {i}"})
                assert r.status_code == 200
                assert r.json()["answer"] != self.INTRO_MESSAGE, (
                    f"Iteration {i}: intro message returned as final answer — regression detected"
                )
                assert r.json()["source_type"] == "gen_active", (
                    f"Iteration {i}: source_type='{r.json()['source_type']}' — expected gen_active"
                )


# ═══════════════════════════════════════════════════════════════════════════════
# Test 6 — Extracción de Compareciente con datos separados por comas
# ═══════════════════════════════════════════════════════════════════════════════

class TestCompariecienteExtraction:
    """
    Regression tests for the compareciente extraction bug where the old
    _extract_list split comma-separated field values (name, DNI, address,
    birthdate, nationality) into separate "persons", causing extraction failure.

    The new LLM-based process_answer handles extraction holistically via
    _process_with_llm. These tests mock _process_with_llm directly to verify
    that process_answer correctly passes through and accumulates the results.
    """

    def _make_manager(self):
        """Manager with poderdante already filled so we're on apoderados."""
        from src.generators.generators import BaseConversationalManager
        m = BaseConversationalManager(ACTO_CASO)
        m.data["poderdante"] = {
            "nombre": "test poderdante",
            "dni": "12345678",
            "estado_civil": "soltero",
            "domicilio": "Av. Corrientes 1234",
            "fecha_nacimiento": "1980-01-01",
            "nacionalidad": "argentina",
        }
        m.historial_campos = ["poderdante"]
        # Pre-populate historial so LLM has context
        m.historial_mensajes.append({
            "role": "assistant",
            "content": "Datos del/los APODERADO/S (quien recibe el poder)"
        })
        return m

    def _llm_response_for(self, data_collected: dict, complete: bool = False,
                           next_question: str = "¿Qué facultades?") -> dict:
        """Build the dict that _process_with_llm returns."""
        return {
            "data_collected": data_collected,
            "complete": complete,
            "next_question": next_question,
        }

    def test_single_compareciente_comma_separated(self):
        """
        REGRESSION: 'lucila mazzochi, 4387177, pueyrredon 2449, 17/12/2001, argentina'
        must be treated as ONE person with all fields, not 5 separate tokens.

        The new LLM sees the full message and returns the correct structure.
        """
        m = self._make_manager()
        llm_result = self._llm_response_for({
            "apoderados": [{
                "nombre": "lucila mazzochi",
                "dni": "4387177",
                "estado_civil": None,
                "domicilio": "pueyrredon 2449",
                "fecha_nacimiento": "2001-12-17",
                "nacionalidad": "argentina",
            }]
        })

        with patch.object(m, "_process_with_llm", return_value=llm_result):
            result = m.process_answer(
                "lucila mazzochi, 4387177, pueyrredon 2449, 17/12/2001, argentina"
            )

        assert result["status"] == "ok", (
            f"REGRESSION: status='{result['status']}' — extraction failed. "
            f"msg: {result.get('message', '')}"
        )
        apoderados = m.data.get("apoderados", [])
        assert len(apoderados) == 1, f"Expected 1 apoderado, got {len(apoderados)}"
        assert apoderados[0]["nombre"] == "lucila mazzochi"
        assert apoderados[0]["dni"] == "4387177"
        assert apoderados[0]["domicilio"] == "pueyrredon 2449"

    def test_single_compareciente_with_all_fields(self):
        """All fields including estado_civil extracted correctly."""
        m = self._make_manager()
        llm_result = self._llm_response_for({
            "apoderados": [{
                "nombre": "María García",
                "dni": "30112233",
                "estado_civil": "casada",
                "domicilio": "Av. Santa Fe 567, Buenos Aires",
                "fecha_nacimiento": "1990-05-20",
                "nacionalidad": "argentina",
            }]
        })

        with patch.object(m, "_process_with_llm", return_value=llm_result):
            result = m.process_answer(
                "María García, 30112233, casada, Av. Santa Fe 567 Buenos Aires, 20/05/1990, argentina"
            )

        assert result["status"] == "ok"
        assert m.data["apoderados"][0]["estado_civil"] == "casada"

    def test_two_comparecientes_separated_by_semicolon(self):
        """Two persons separated by ';' → two distinct comparecientes."""
        m = self._make_manager()
        llm_result = self._llm_response_for({
            "apoderados": [
                {"nombre": "Ana López", "dni": "11111111", "estado_civil": None,
                 "domicilio": "Callao 100", "fecha_nacimiento": "1985-03-10",
                 "nacionalidad": "argentina"},
                {"nombre": "Pedro Díaz", "dni": "22222222", "estado_civil": None,
                 "domicilio": "Lavalle 200", "fecha_nacimiento": "1979-07-22",
                 "nacionalidad": "argentina"},
            ]
        })

        with patch.object(m, "_process_with_llm", return_value=llm_result):
            result = m.process_answer(
                "Ana López, 11111111, Callao 100, 10/03/1985; Pedro Díaz, 22222222, Lavalle 200, 22/07/1979"
            )

        assert result["status"] == "ok"
        apoderados = m.data.get("apoderados", [])
        assert len(apoderados) == 2, f"Expected 2, got {len(apoderados)}"
        nombres = {c["nombre"] for c in apoderados}
        assert "Ana López" in nombres
        assert "Pedro Díaz" in nombres

    def test_multiple_fields_in_one_message(self):
        """
        User provides poderdante AND apoderado in a single message.
        The LLM extracts both simultaneously — must not require two turns.
        """
        from src.generators.generators import BaseConversationalManager
        m = BaseConversationalManager(ACTO_CASO)  # fresh manager, no data yet
        m.get_next_question()  # registers first question in historial

        llm_result = self._llm_response_for(
            data_collected={
                "poderdante": {
                    "nombre": "Nicolas Rodriguez", "dni": "43724971",
                    "estado_civil": "soltero", "domicilio": "Uruguay 766",
                    "fecha_nacimiento": "2002-01-17", "nacionalidad": "argentino",
                },
                "apoderados": [{
                    "nombre": "Lucila Mazzochi", "dni": "4387177",
                    "domicilio": "Pueyrredon 2449",
                    "fecha_nacimiento": "2001-12-17", "nacionalidad": "argentina",
                }],
            },
            next_question="¿Qué facultades debe tener este poder?",
        )

        with patch.object(m, "_process_with_llm", return_value=llm_result):
            result = m.process_answer(
                "Poderdante: Nicolas Rodriguez DNI 43724971. Apoderada: Lucila Mazzochi DNI 4387177."
            )

        assert result["status"] == "ok"
        assert "poderdante" in m.data, "poderdante must be extracted from single message"
        assert "apoderados" in m.data, "apoderados must be extracted from single message"
        assert m.data["poderdante"]["nombre"] == "Nicolas Rodriguez"
        assert m.data["apoderados"][0]["nombre"] == "Lucila Mazzochi"

    def test_no_crash_when_llm_returns_empty(self):
        """If _process_with_llm returns empty data_collected, process_answer must not crash."""
        m = self._make_manager()
        llm_result = {
            "data_collected": {},
            "complete": False,
            "next_question": "No entendí. ¿Podés repetir los datos del apoderado?",
        }

        with patch.object(m, "_process_with_llm", return_value=llm_result):
            result = m.process_answer("algo incomprensible")

        assert result["status"] == "ok"
        assert result.get("next_question"), "Must ask a follow-up when nothing was extracted"
        # Manager data must not have gained new keys
        assert "apoderados" not in m.data
