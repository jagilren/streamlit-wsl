"""Gestión de metadatos de TAGs (tabla `tag_metadata`).

Esta tabla es la fuente única de verdad sobre cómo se muestran los TAGs:
nombre amigable (label), color, rol en el proceso, unidad, etc.

Diseñada para ser extensible por `tipo`: empieza con DQO pero la misma
estructura sirve para pH, Caudal, Químicos, etc.

El módulo expone:
    - cargar_catalog(tipo) → dict en el formato que usa el dashboard
    - listar_tags(tipo)    → DataFrame para la UI de administración
    - upsert_tag(...)      → INSERT...ON CONFLICT DO UPDATE
    - eliminar_tag(...)    → borrado físico (admin power-user)
    - migrar_desde_codigo() → siembra inicial desde TAG_CATALOG hardcoded
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

_PARENT = Path(__file__).resolve().parent.parent
if str(_PARENT) not in sys.path:
    sys.path.insert(0, str(_PARENT))

from db import get_connection  # noqa: E402

from .config import CACHE_TTL, TAG_CATALOG as TAG_CATALOG_FALLBACK

_log = logging.getLogger("dashboard_dqo.tag_admin")

TIPOS_VALIDOS = ("DQO", "pH", "Caudal", "Quimico")
ROLES_VALIDOS = ("afluente", "intermedio", "efluente", None)


def resolve_tag_por_rol(
    catalog: dict[str, dict[str, Any]], rol: str, fallback: str,
) -> str:
    """Devuelve el `tag_id` del catálogo con el `rol` indicado.

    Si hay 0 candidatos → fallback (constante hardcoded del config).
    Si hay 1 candidato  → ese.
    Si hay >1 (config inconsistente) → primero por orden alfabético + warning.
    Es la función que permite que afluente/efluente se gestionen desde la BD
    sin hardcodearlos en config.py.
    """
    candidatos = sorted(
        t for t, m in catalog.items() if m.get("rol") == rol
    )
    if not candidatos:
        _log.warning(
            "Catálogo DQO no tiene TAG con rol=%r; usando fallback %r.",
            rol, fallback,
        )
        return fallback
    if len(candidatos) > 1:
        _log.warning(
            "Catálogo DQO tiene %d TAGs con rol=%r (%s); usando %r.",
            len(candidatos), rol, candidatos, candidatos[0],
        )
    return candidatos[0]


_SCHEMA = [
    """
    CREATE TABLE IF NOT EXISTS tag_metadata (
        tag_id          TEXT PRIMARY KEY,
        tipo            TEXT NOT NULL,
        label           TEXT NOT NULL,
        rol             TEXT,
        unidad          TEXT,
        color           TEXT,
        orden           INT DEFAULT 0,
        activo          BOOLEAN DEFAULT TRUE,
        creado_en       TIMESTAMPTZ DEFAULT NOW(),
        actualizado_en  TIMESTAMPTZ DEFAULT NOW()
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_tag_metadata_tipo
        ON tag_metadata (tipo) WHERE activo = TRUE
    """,
]


def _ensure_tabla() -> None:
    """Crea la tabla y el índice si no existen. Idempotente."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            for sql in _SCHEMA:
                cur.execute(sql)
        conn.commit()
    finally:
        conn.close()


_tabla_lista = False


def _ensure_tabla_once() -> None:
    global _tabla_lista
    if _tabla_lista:
        return
    try:
        _ensure_tabla()
        _tabla_lista = True
    except Exception as exc:
        _log.warning("_ensure_tabla_once: DB no disponible — %s", exc)


# ── Lectura ───────────────────────────────────────────────────────────────────
@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def cargar_catalog(tipo: str = "DQO") -> dict[str, dict[str, Any]]:
    """Devuelve el catálogo de TAGs activos del tipo dado, en el formato que
    consume el dashboard: {tag_id: {nombre, rol, color, unidad}}.

    Si la BD está vacía o falla, devuelve el TAG_CATALOG hardcoded (fallback).
    El orden de las claves respeta la columna `orden` para que las etapas del
    proceso aparezcan en orden visual correcto.
    """
    _ensure_tabla_once()
    try:
        sql = """
            SELECT tag_id, label, rol, unidad, color
            FROM tag_metadata
            WHERE tipo = %s AND activo = TRUE
            ORDER BY orden, tag_id
        """
        with get_connection() as conn:
            df = pd.read_sql_query(sql, conn, params=(tipo,))
    except Exception as exc:
        _log.warning("cargar_catalog: fallback a hardcoded — %s", exc)
        return dict(TAG_CATALOG_FALLBACK) if tipo == "DQO" else {}

    if df.empty:
        _log.info("cargar_catalog: tabla vacía para tipo=%r, usando fallback", tipo)
        return dict(TAG_CATALOG_FALLBACK) if tipo == "DQO" else {}

    return {
        row["tag_id"]: {
            "nombre": row["label"],
            "rol": row["rol"],
            "color": row["color"],
            "unidad": row["unidad"],
        }
        for _, row in df.iterrows()
    }


def listar_tags(tipo: str | None = None) -> pd.DataFrame:
    """Devuelve TODOS los TAGs (activos e inactivos) opcionalmente filtrados por tipo,
    en formato adecuado para `st.data_editor`."""
    _ensure_tabla_once()
    sql = """
        SELECT tag_id, tipo, label, rol, unidad, color, orden, activo
        FROM tag_metadata
        {where}
        ORDER BY tipo, orden, tag_id
    """.format(where="WHERE tipo = %s" if tipo else "")
    params = (tipo,) if tipo else None
    with get_connection() as conn:
        return pd.read_sql_query(sql, conn, params=params)


# ── Escritura ─────────────────────────────────────────────────────────────────
def upsert_tag(
    tag_id: str, tipo: str, label: str,
    rol: str | None = None, unidad: str | None = None,
    color: str | None = None, orden: int = 0, activo: bool = True,
) -> None:
    """INSERT ... ON CONFLICT DO UPDATE. Actualiza `actualizado_en` automáticamente."""
    _ensure_tabla_once()
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO tag_metadata
                    (tag_id, tipo, label, rol, unidad, color, orden, activo)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (tag_id) DO UPDATE SET
                    tipo   = EXCLUDED.tipo,
                    label  = EXCLUDED.label,
                    rol    = EXCLUDED.rol,
                    unidad = EXCLUDED.unidad,
                    color  = EXCLUDED.color,
                    orden  = EXCLUDED.orden,
                    activo = EXCLUDED.activo,
                    actualizado_en = NOW()
                """,
                (tag_id, tipo, label, rol, unidad, color, orden, activo),
            )
        conn.commit()
    finally:
        conn.close()
    cargar_catalog.clear()  # invalida el caché del catálogo


def eliminar_tag(tag_id: str) -> None:
    """Borrado físico. Para soft-delete usa upsert_tag(..., activo=False)."""
    _ensure_tabla_once()
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM tag_metadata WHERE tag_id = %s", (tag_id,))
        conn.commit()
    finally:
        conn.close()
    cargar_catalog.clear()


def reemplazar_lote(tipo: str, filas: list[dict]) -> tuple[int, int]:
    """Upsert masivo: aplica `filas` (lista de dicts) al tipo dado.
    Retorna (filas_aplicadas, filas_borradas) — borra las que ya no aparezcan."""
    _ensure_tabla_once()
    tags_en_lote = {f["tag_id"] for f in filas}

    conn = get_connection()
    borradas = 0
    try:
        with conn.cursor() as cur:
            # Borra los que estaban en BD pero no están en el nuevo lote
            cur.execute(
                "SELECT tag_id FROM tag_metadata WHERE tipo = %s", (tipo,),
            )
            actuales = {r[0] for r in cur.fetchall()}
            a_borrar = actuales - tags_en_lote
            if a_borrar:
                cur.execute(
                    "DELETE FROM tag_metadata WHERE tag_id = ANY(%s)",
                    (list(a_borrar),),
                )
                borradas = cur.rowcount

            # Upsert cada fila del lote
            for f in filas:
                cur.execute(
                    """
                    INSERT INTO tag_metadata
                        (tag_id, tipo, label, rol, unidad, color, orden, activo)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (tag_id) DO UPDATE SET
                        tipo   = EXCLUDED.tipo,
                        label  = EXCLUDED.label,
                        rol    = EXCLUDED.rol,
                        unidad = EXCLUDED.unidad,
                        color  = EXCLUDED.color,
                        orden  = EXCLUDED.orden,
                        activo = EXCLUDED.activo,
                        actualizado_en = NOW()
                    """,
                    (
                        f["tag_id"], tipo, f["label"], f.get("rol"),
                        f.get("unidad"), f.get("color"),
                        int(f.get("orden") or 0), bool(f.get("activo", True)),
                    ),
                )
        conn.commit()
    finally:
        conn.close()
    cargar_catalog.clear()
    return len(filas), borradas


# ── Migración inicial desde el catálogo hardcoded ────────────────────────────
def migrar_desde_codigo() -> int:
    """Siembra `tag_metadata` con el contenido del TAG_CATALOG hardcoded para
    DQO. Solo inserta filas nuevas (ON CONFLICT DO NOTHING) para no pisar
    ediciones manuales hechas vía UI."""
    _ensure_tabla_once()
    conn = get_connection()
    insertadas = 0
    try:
        with conn.cursor() as cur:
            for orden, (tag_id, meta) in enumerate(TAG_CATALOG_FALLBACK.items()):
                cur.execute(
                    """
                    INSERT INTO tag_metadata
                        (tag_id, tipo, label, rol, unidad, color, orden, activo)
                    VALUES (%s, 'DQO', %s, %s, 'mg/L', %s, %s, TRUE)
                    ON CONFLICT (tag_id) DO NOTHING
                    """,
                    (tag_id, meta["nombre"], meta["rol"], meta["color"], orden),
                )
                insertadas += cur.rowcount
        conn.commit()
    finally:
        conn.close()
    cargar_catalog.clear()
    return insertadas
