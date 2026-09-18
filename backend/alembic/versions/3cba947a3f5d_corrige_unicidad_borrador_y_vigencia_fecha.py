"""corrige unicidad borrador y vigencia_fecha

Revision ID: 3cba947a3f5d
Revises: e96e8c9fd07d
Create Date: 2026-09-18 00:00:00.000000

Reemplaza 'ux_corte_borrador_por_vigencia' (regla D-03 superada: un
BORRADOR por vigencia) por dos índices que reflejan las reglas vigentes
(docs/DECISIONES.md):

- D11: un solo corte en BORRADOR en toda la tabla, sin importar la
  vigencia. Respaldo a nivel de BD de `existe_borrador_activo()`
  (puertos.py) contra condiciones de carrera.
- D9: no puede haber dos cortes con la misma vigencia y la misma
  fecha_corte exacta.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '3cba947a3f5d'
down_revision: Union[str, None] = 'e96e8c9fd07d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index(
        'ux_corte_borrador_por_vigencia',
        table_name='corte',
        postgresql_where=sa.text("estado = 'BORRADOR'"),
        sqlite_where=sa.text("estado = 'BORRADOR'"),
    )
    op.create_index(
        'ux_corte_borrador_unico',
        'corte',
        ['estado'],
        unique=True,
        postgresql_where=sa.text("estado = 'BORRADOR'"),
        sqlite_where=sa.text("estado = 'BORRADOR'"),
    )
    op.create_index(
        'ux_corte_vigencia_fecha',
        'corte',
        ['vigencia', 'fecha_corte'],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index('ux_corte_vigencia_fecha', table_name='corte')
    op.drop_index(
        'ux_corte_borrador_unico',
        table_name='corte',
        postgresql_where=sa.text("estado = 'BORRADOR'"),
        sqlite_where=sa.text("estado = 'BORRADOR'"),
    )
    op.create_index(
        'ux_corte_borrador_por_vigencia',
        'corte',
        ['vigencia'],
        unique=True,
        postgresql_where=sa.text("estado = 'BORRADOR'"),
        sqlite_where=sa.text("estado = 'BORRADOR'"),
    )
