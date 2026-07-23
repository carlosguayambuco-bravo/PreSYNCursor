# Estándar usando Pep8
# Librerías de Python
# Librerías de Terceros
# Librerías Locales

# --- Queries a Metabase ---
QUERY_DEBT_TO_REFERENCE = """
SELECT
    bcrd.bank_reference AS Referencia
FROM
    dealer_public.berex_credit_repair_debts bcrd
WHERE
    bcrd.id = {debt_id}
"""

QUERY_ACTIVE_DEBTS = """
WITH PLvanex AS (
    SELECT
        cr.bank_reference,
        cr.id AS cr_id,
        vsp.success_commission_percentage as Pricing,
        JSON_EXTRACT_SCALAR(debt_item, '$.financial_entity') AS financial_entity,
        CAST(JSON_EXTRACT_SCALAR(debt_item, '$.updated_amount') AS FLOAT64) AS debt_original_amount,
        CAST(JSON_EXTRACT_SCALAR(debt_item, '$.payment_to_bank') AS FLOAT64)
        + CAST(JSON_EXTRACT_SCALAR(debt_item, '$.reduction_commission') AS FLOAT64) AS PB_PL
    FROM vanex_public.settlement_plan AS vsp
    LEFT JOIN UNNEST(JSON_EXTRACT_ARRAY(vsp.debts)) AS debt_item
    LEFT JOIN vanex_public.leads_lead AS ll
        ON ll.id = vsp.lead_id
    LEFT JOIN berex_public.credit_repairs AS cr
        ON cr.tracker_id = ll.tracker_id
    WHERE cr.country = 'co'
        AND vsp.winner IS TRUE
),

-- 3) Intento mapear ese plan a debt_id
PL_Programa AS (
    SELECT
        ids.id AS debt_id,
        v.PB_PL,
        v.Pricing
    FROM PLvanex v
    LEFT JOIN (
        SELECT
        crd.id,
        CAST(crd.amount AS FLOAT64) AS monto,
        crd.financial_entity_name,
        crd.credit_repair_id
        FROM dealer_public.berex_credit_repair_debts AS crd
        LEFT JOIN berex_public.credit_repairs AS cr
        ON cr.id = crd.credit_repair_id
        WHERE cr.country = 'co'
    ) AS ids
        ON v.cr_id = ids.credit_repair_id
    AND v.financial_entity = ids.financial_entity_name
    AND v.debt_original_amount = ids.monto
)

SELECT
    bcrd.id AS Id_Deuda,
    bcrd.bank_reference AS Referencia,
    bcr.document_number AS Cedula,
    bcrd.financial_entity_name AS Banco,
    bcrd.amount AS PaB_Origen,
    pl.PB_PL AS PaB_PL,
    vsp.success_commission_percentage AS Pricing
FROM dealer_public.berex_credit_repair_debts bcrd
    LEFT JOIN PL_Programa AS pl
        ON bcrd.id = pl.debt_id
    LEFT JOIN vanex_public.leads_lead AS ll
        ON ll.tracker_id = bcrd.tracker_id
    LEFT JOIN vanex_public.settlement_plan AS vsp
        ON vsp.lead_id = ll.id
    LEFT JOIN dealer_public.berex_credit_repairs AS bcr
        ON bcr.id = bcrd.credit_repair_id
WHERE 
    bcrd.status IN ('new','negotiation','lawsuit')
    AND NOT(bcrd.sub_state IN ('liquidated','liquidated_with_credit','liquidation_in_process','cancelled','drop_requested','liquidation_structured_payment'))
    AND vsp.winner IS TRUE
    AND bcrd.bank_reference = '{referencia}'
"""

QUERY_LAST_UPDATE = """"
SELECT
    MAX(bda.updated_at) AS Ultima_Actualizacion,
    bda.debt_id AS Id_Deuda
FROM dealer_public.berex_debt_activities AS bda
WHERE 
    bda.debt_id IN ({debt_ids}) AND
    bda.end = '{email}'
GROUP BY bda.debt_id
"""

# --- Constantes de Solicitudes ---
SOLICITUDES_SHEETS_ID = "1tlHeLPJgIlRw3-_yv8lG4_w07n44o6KUxwxS1jmhjLk"
SOLICITUDES_WORKSHEET_NAME = "Solicitudes_Nuevas"

DEFAULT_DISCOUNT_PL = 0.15

MIN_NECESSARY_DAYS_FOR_DEBT_UPDATE = 5