"""remove the demo workspace: its searches, its leads and the marker table

Until now an empty database was filled once with a demo workspace (four searches,
24 leads) and `seed_state` recorded that it had been. The app no longer ships demo
data, so a database that received it loses it here. Only the rows the seed itself
inserted are removed, and only where the marker says the seed was applied: the
user's own searches, their leads and the scrape cache stay.

Deleting a search cascades to its leads, notes, jobs and refusals.

Revision ID: 0007
Revises: 0006
Created: 2026-11-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Exactly what the demo seed inserted, frozen here: the seed file is gone.
DEMO_SEARCHES = ("srch_es_mihi", "srch_de_mihi", "srch_pl_network", "srch_it_beauty")
DEMO_LEADS = (
    "lead_alessia_ferrari",
    "lead_anna_kowalska",
    "lead_beatriz_lopes",
    "lead_carmen_delgado",
    "lead_chiara_marino",
    "lead_daniela_krause",
    "lead_elena_rossi",
    "lead_francesca_bruno",
    "lead_giulia_conti",
    "lead_ines_ferrer",
    "lead_janina_weber",
    "lead_katrin_mueller",
    "lead_lucia_fernandez",
    "lead_maria_petrova",
    "lead_miriam_schulz",
    "lead_natalia_sokol",
    "lead_oksana_hrytsenko",
    "lead_pilar_moreno",
    "lead_rocio_navarro",
    "lead_sabine_lang",
    "lead_sofia_marin",
    "lead_svetlana_richter",
    "lead_valentina_greco",
    "lead_yuliya_hoffmann",
)


def upgrade() -> None:
    connection = op.get_bind()
    seeded = connection.execute(
        sa.text("SELECT 1 FROM seed_state WHERE key = 'demo-workspace'")
    ).first()
    if seeded:
        connection.execute(
            sa.text("DELETE FROM leads WHERE id IN :ids").bindparams(
                sa.bindparam("ids", expanding=True)
            ),
            {"ids": list(DEMO_LEADS)},
        )
        connection.execute(
            sa.text("DELETE FROM searches WHERE id IN :ids").bindparams(
                sa.bindparam("ids", expanding=True)
            ),
            {"ids": list(DEMO_SEARCHES)},
        )
        # The owner row stays (everything else points at it); it just stops
        # pretending to be a demo account.
        connection.execute(
            sa.text(
                "UPDATE users SET email = NULL, name = NULL WHERE email = 'demo@ai-recruiter.local'"
            )
        )
    op.drop_table("seed_state")


def downgrade() -> None:
    # The marker table comes back empty; the demo rows are not restored.
    op.create_table(
        "seed_state",
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column(
            "applied_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("searches", sa.Integer(), nullable=False),
        sa.Column("leads", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("key"),
    )
