"""
sql_safety_demo.py — Demo standalone del validador de SQL de NotarIA

Muestra cómo el sistema previene SQL injection en el generador text-to-SQL.

Este archivo no requiere ninguna dependencia externa ni variables de entorno.
Solo Python 3.8+ estándar.

Correr con:
    python3 sql_safety_demo.py
"""

from __future__ import annotations
from typing import Optional


# ─────────────────────────────────────────────────────────────────────────────
# Lógica extraída de src/analytics/text_to_sql/sql_generator.py
# ─────────────────────────────────────────────────────────────────────────────

FORBIDDEN_KEYWORDS = frozenset([
    "INSERT", "UPDATE", "DELETE", "DROP", "ALTER",
    "CREATE", "TRUNCATE", "REPLACE", "ATTACH", "DETACH",
])


def validate_sql(sql: str) -> tuple[bool, Optional[str]]:
    """
    Valida que una query SQL generada por el LLM sea segura para ejecutar.

    Reglas:
    - Debe empezar con SELECT
    - No puede contener palabras clave de escritura/modificación

    Devuelve (True, None) si es válida, (False, motivo) si no.
    Esta función es el último control antes de ejecutar contra la DB.
    """
    sql_upper = sql.strip().upper()

    for keyword in FORBIDDEN_KEYWORDS:
        if keyword in sql_upper:
            return False, f"Forbidden keyword: {keyword}"

    if not sql_upper.startswith("SELECT"):
        return False, "Query must start with SELECT"

    return True, None


# ─────────────────────────────────────────────────────────────────────────────
# Demo: casos reales que el sistema rechaza o acepta
# ─────────────────────────────────────────────────────────────────────────────

CASOS = [
    # ── Queries legítimas (el LLM las genera en respuesta a preguntas reales) ──
    (
        "SELECT COUNT(*) FROM metadata",
        True,
        "Conteo simple — 'cuántas escrituras hay'",
    ),
    (
        "SELECT acto_caso, COUNT(*) FROM metadata GROUP BY acto_caso ORDER BY COUNT(*) DESC",
        True,
        "Distribución por tipo — 'qué tipos de actos son más frecuentes'",
    ),
    (
        "SELECT m.file_id, m.fecha_iso, m.notario FROM metadata m "
        "JOIN comparecientes c ON m.file_id = c.file_id "
        "WHERE c.nombre ILIKE '%García%' AND m.acto_caso = 'compraventa_inmueble'",
        True,
        "Query con JOIN — 'escrituras de compraventa donde aparece García'",
    ),
    (
        "SELECT file_id, raw_json FROM metadata WHERE file_id = '20-0298TER'",
        True,
        "Detalle de escritura — 'dame el detalle de 20-0298TER'",
    ),
    # ── Inyecciones que el sistema debe rechazar ──
    (
        "SELECT 1; DROP TABLE metadata",
        False,
        "Inyección clásica con semicolón + DROP",
    ),
    (
        "SELECT * FROM metadata; DELETE FROM embeddings WHERE 1=1",
        False,
        "Inyección con DELETE después de query legítima",
    ),
    (
        "INSERT INTO metadata (file_id) VALUES ('malicious')",
        False,
        "Intento de INSERT directo",
    ),
    (
        "UPDATE metadata SET notario = 'hacked' WHERE 1=1",
        False,
        "Intento de UPDATE masivo",
    ),
    (
        "WITH cte AS (SELECT 1) DELETE FROM metadata",
        False,
        "Inyección via CTE — no empieza con SELECT",
    ),
    (
        "select 1; delete from audit_log",
        False,
        "Inyección en minúsculas — detección case-insensitive",
    ),
    (
        "SELECT 1 -- DROP TABLE metadata",
        False,
        "Keyword prohibida en comentario — igual se detecta",
    ),
]


def run_demo():
    print("=" * 70)
    print("NotarIA — Validador de SQL generado por LLM")
    print("=" * 70)
    print()
    print("Contexto: el LLM genera SQL a partir de lenguaje natural.")
    print("Antes de ejecutar contra la DB, validate_sql() verifica que")
    print("la query sea segura. Este es el resultado para cada caso:\n")

    passed = 0
    failed = 0

    for sql, expected_valid, description in CASOS:
        is_valid, error = validate_sql(sql)

        # ¿El validador se comportó como esperábamos?
        correct = (is_valid == expected_valid)

        status = "OK" if correct else "FALLO"
        verdict = "ACEPTADA" if is_valid else f"RECHAZADA ({error})"

        label = "✓" if correct else "✗"
        print(f"  {label} [{status}] {description}")
        print(f"      SQL: {sql[:72]}{'...' if len(sql) > 72 else ''}")
        print(f"      Resultado: {verdict}")
        print()

        if correct:
            passed += 1
        else:
            failed += 1

    print("-" * 70)
    print(f"Resultado: {passed}/{passed + failed} casos correctos")
    print()

    if failed == 0:
        print("Todos los casos pasaron.")
        print()
        print("Nota: el validador también está cubierto en tests/test_sql_safety.py")
        print("con 30+ casos adicionales (pytest, sin dependencias externas).")
    else:
        print(f"ATENCIÓN: {failed} casos fallaron — hay un problema en el validador.")


if __name__ == "__main__":
    run_demo()
