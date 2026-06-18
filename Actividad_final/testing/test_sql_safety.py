"""
tests/test_sql_safety.py

Unit tests for SQL safety validation (SQLGenerator.validate_sql) and
query-type detection (QueryExecutor._detect_query_type).

All tests run offline — no OpenAI calls are made (validate_sql and
_detect_query_type are pure Python / regex logic).
"""
from __future__ import annotations

import os

import pytest

os.environ.setdefault("OPENAI_API_KEY", "sk-test-notaria-fake-key-for-unit-tests")

from unittest.mock import MagicMock
from src.analytics.text_to_sql.sql_generator import SQLGenerator
from src.analytics.text_to_sql.query_executor import QueryExecutor


# ---------------------------------------------------------------------------
# SQLGenerator.validate_sql — safety checks
# ---------------------------------------------------------------------------

class TestValidateSql:
    @pytest.fixture(autouse=True)
    def gen(self):
        self.gen = SQLGenerator.__new__(SQLGenerator)

    def test_valid_select_passes(self):
        ok, err = self.gen.validate_sql("SELECT COUNT(*) FROM metadata")
        assert ok is True
        assert err is None

    def test_select_with_join_passes(self):
        ok, err = self.gen.validate_sql(
            "SELECT m.file_id FROM metadata m JOIN comparecientes c ON m.file_id = c.file_id"
        )
        assert ok is True

    def test_select_with_where_passes(self):
        ok, err = self.gen.validate_sql(
            "SELECT file_id FROM metadata WHERE acto_caso = 'compraventa_inmueble'"
        )
        assert ok is True

    def test_select_with_group_by_passes(self):
        ok, err = self.gen.validate_sql(
            "SELECT acto_caso, COUNT(*) FROM metadata GROUP BY acto_caso"
        )
        assert ok is True

    @pytest.mark.parametrize("keyword", [
        "INSERT", "UPDATE", "DELETE", "DROP", "ALTER",
        "CREATE", "TRUNCATE", "REPLACE", "ATTACH", "DETACH",
    ])
    def test_forbidden_keyword_rejected(self, keyword):
        sql = f"SELECT 1; {keyword} INTO metadata VALUES (1)"
        ok, err = self.gen.validate_sql(sql)
        assert ok is False
        assert keyword in (err or "")

    def test_non_select_start_rejected(self):
        ok, err = self.gen.validate_sql("WITH cte AS (SELECT 1) DELETE FROM metadata")
        assert ok is False

    def test_bare_with_cte_is_rejected(self):
        # WITH ... SELECT is not rejected by validate_sql because it doesn't start
        # with SELECT — but that is the expected behavior (must start with SELECT).
        ok, err = self.gen.validate_sql(
            "WITH cte AS (SELECT file_id FROM metadata) SELECT * FROM cte"
        )
        assert ok is False

    def test_empty_string_rejected(self):
        ok, err = self.gen.validate_sql("")
        assert ok is False

    def test_whitespace_only_rejected(self):
        ok, err = self.gen.validate_sql("   ")
        assert ok is False

    def test_case_insensitive_keyword_detection(self):
        ok, err = self.gen.validate_sql("select 1; delete from metadata")
        assert ok is False


# ---------------------------------------------------------------------------
# QueryExecutor._detect_query_type
# ---------------------------------------------------------------------------

class TestDetectQueryType:
    @pytest.fixture(autouse=True)
    def executor(self):
        db = MagicMock()
        gen = SQLGenerator.__new__(SQLGenerator)
        self.executor = QueryExecutor(database=db, sql_generator=gen)

    def test_count_star(self):
        sql = "SELECT COUNT(*) FROM metadata"
        qt = self.executor._detect_query_type(sql, [{"COUNT(*)": 5}])
        assert qt == "count"

    def test_count_distinct(self):
        sql = "SELECT COUNT(DISTINCT notario) FROM metadata"
        qt = self.executor._detect_query_type(sql, [{"COUNT(DISTINCT notario)": 3}])
        assert qt == "count"

    def test_count_with_group_by_is_aggregate(self):
        sql = "SELECT acto_caso, COUNT(*) FROM metadata GROUP BY acto_caso"
        qt = self.executor._detect_query_type(sql, [{"acto_caso": "x", "COUNT(*)": 1}])
        assert qt == "aggregate"

    def test_raw_json_is_detail(self):
        sql = "SELECT raw_json FROM metadata WHERE file_id = '20-0001'"
        qt = self.executor._detect_query_type(sql, [{"raw_json": "{}"}])
        assert qt == "detail"

    def test_group_by_without_count_is_aggregate(self):
        sql = "SELECT lugar, MAX(anio) FROM metadata GROUP BY lugar"
        qt = self.executor._detect_query_type(sql, [{"lugar": "Buenos Aires", "MAX(anio)": 2023}])
        assert qt == "aggregate"

    def test_default_to_list(self):
        sql = "SELECT file_id, notario FROM metadata"
        qt = self.executor._detect_query_type(
            sql, [{"file_id": "20-0001", "notario": "Juan"}]
        )
        assert qt == "list"

    def test_empty_results_default_to_list(self):
        sql = "SELECT file_id FROM metadata WHERE 1=0"
        qt = self.executor._detect_query_type(sql, [])
        assert qt == "list"


# ---------------------------------------------------------------------------
# QueryExecutor._process_results
# ---------------------------------------------------------------------------

class TestProcessResults:
    @pytest.fixture(autouse=True)
    def executor(self):
        db = MagicMock()
        gen = SQLGenerator.__new__(SQLGenerator)
        self.executor = QueryExecutor(database=db, sql_generator=gen)

    def test_count_extracts_single_value(self):
        data, n = self.executor._process_results([{"COUNT(*)": 42}], "count")
        assert data == 42
        assert n == 1

    def test_detail_parses_raw_json(self):
        payload = {"file_id": "20-0001", "acto_caso": "compraventa_inmueble"}
        import json
        data, n = self.executor._process_results(
            [{"raw_json": json.dumps(payload)}], "detail"
        )
        assert data == payload
        assert n == 1

    def test_list_with_single_column_unwraps(self):
        rows = [{"file_id": "20-0001"}, {"file_id": "20-0002"}]
        data, n = self.executor._process_results(rows, "list")
        assert data == ["20-0001", "20-0002"]
        assert n == 2

    def test_list_with_multiple_columns_returns_dicts(self):
        rows = [{"file_id": "20-0001", "notario": "Juan"}]
        data, n = self.executor._process_results(rows, "list")
        assert data == rows

    def test_aggregate_returns_rows_as_is(self):
        rows = [{"acto_caso": "x", "cnt": 3}]
        data, n = self.executor._process_results(rows, "aggregate")
        assert data == rows

    def test_empty_results_returns_none(self):
        data, n = self.executor._process_results([], "count")
        assert data is None
        assert n == 0
