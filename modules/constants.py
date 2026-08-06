# Estándar usando Pep8
# Librerías de Python
# Librerías de Terceros
# Librerías Locales

IVA = 1.19

# --- Configuraciones de Streamlit ---
MIN_10_WAIT = 600 # En Segundos
HOUR_WAIT = 3600 # En Segundos
DAY_WAIT = 86400 # En Segundos
WEEK_WAIT = 604800 # En Segundos

# --- Configuración de Validación de Datos ---
ESTADOS_POSIBLES_SOLICITUD = [
    'Exitosa', # La Solicitud fue Respondida y Finalizada con Éxito (Se parte que es exitosa si se logró una validación con alguna de las deudas)
    'Vencida', # La Solicitud no fue gestionada en un lapso de XX Días Hábiles
    'No Exitosa', # La Solciitud fue validáda pero no tuvó éxito
    'Erronea', # La Solicitud fue subida con datos erroneos o incompletos
    'Bajo Comité', # Estado Transitorio: Significa que para seguir escalando la solicitud se requiere que vaya a comité y se pagué
    'No esta con Aliado', # La Solicitud fue brindada con un aliado pero no se encuentra con el mismo, por lo que no se puede continuar con la gestión
    'Titular Ilocalizable', # Estado Transitorio: Significa que el titular de la deuda no se encuentra localizable, por lo que no se puede continuar con la gestión hasta que se logré localizar al titular
    'Validada por Fuera', # Signfica que hubó una validación y/o Pago por Fuera para las Deudas
    'Sin Tocar', # Estado Transitorio: # La Solicitud no ha sido tocada por un ejecutivo
]
ESTADOS_RESPONDIBLES_SOLICITUD = [
    'Exitosa',
    'No Exitosa',
    'Erronea',
    'Vencida',
    'No esta con Aliado',
    'Validada por Fuera',
]
ESTADOS_PREFINALIZAR_SOLICITUD = [
    'Bajo Comité',
    'Titular Ilocalizable',
    'Vencida',
    'No esta con Aliado',
    'Validada por Fuera',
    'No Exitosa',
    'Erronea',
]

PAGOS_POSIBLES_SOLICITUD = [
    'Tradicional',
    'Estructuraado',
    'Refi',
    'Crédito',
]

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
    bcr.full_name AS Nombre_Cliente,
    bcrd.financial_entity_name AS Banco,
    bcrd.credit_number AS Numero_Credito,
    bcrd.amount AS PaB_Origen,
    pl.PB_PL AS PaB_PL,
    vsp.success_commission_percentage AS Pricing
FROM dealer_public.berex_credit_repair_debts bcrd
    LEFT JOIN dealer_public.berex_credit_repairs AS bcr
        ON bcr.id = bcrd.credit_repair_id
    LEFT JOIN PL_Programa AS pl
        ON bcrd.id = pl.debt_id
    LEFT JOIN vanex_public.leads_lead AS ll
        ON ll.tracker_id = bcr.tracker_id
    LEFT JOIN vanex_public.settlement_plan AS vsp
        ON vsp.lead_id = ll.id
WHERE 
    bcrd.state IN ('new','negotiation','lawsuit')
    AND NOT(bcrd.sub_state IN ('liquidated','liquidated_with_credit','liquidation_in_process','cancelled','drop_requested','liquidation_structured_payment'))
    AND vsp.winner IS TRUE
    AND bcrd.bank_reference = '{referencia}';
"""

QUERY_LAST_UPDATE = """
SELECT
    MAX(bda.updated_at) AS Ultima_Actualizacion,
    bda.debt_id AS Id_Deuda
FROM dealer_public.berex_debt_activities AS bda
WHERE 
    bda.debt_id IN ({debt_ids}) AND
    bda.end = '{email}'
GROUP BY bda.debt_id;"""

# --- Constantes de Solicitudes ---
SOLICITUDES_SHEETS_ID = "1tlHeLPJgIlRw3-_yv8lG4_w07n44o6KUxwxS1jmhjLk"
SOLICITUDES_WORKSHEET_NAME = "Solicitudes_Nuevas"

SOLICITUDES_ID_DELAY = 4601872 # El extra que se le suma al ID de la Solicitud para que no se repita con el ID de la Deuda

DEFAULT_DISCOUNT_PL = 0.15
LIMITE_MEC = 5 # El Día límite para Considerar el Día como mes operativo

# --- Constantes de Correos Electrónicos ---
EMAIL_SUBJECT_ACUERDO = "Acuerdo de Pago ({estado_solicitud}) - REF: {referencia} - {nombre_cliente}"
EMAIL_SUBJECT_OFERTA_ACUERDO = "Oferta de Acuerdo ({estado_solicitud}) - REF: {referencia} - {nombre_cliente}"
EMAIL_SUBJECT_MAPPER ={
    "Acuerdo de Pago": EMAIL_SUBJECT_ACUERDO,
    "Oferta de Acuerdo": EMAIL_SUBJECT_OFERTA_ACUERDO,
}

EMAIL_BODY_GENERAL = """Cordial saludo,

Espero que te encuentres bien.

El motivo del presente mensaje es hacer la entrega formal del acuerdo de pago que fue solicitado {string_solicitado}. Adjunto a este correo podrás encontrar todos los detalles correspondientes.

Quedo atento a cualquier comentario o paso adicional que se deba seguir.

Muchas gracias por tu atención.

Atentamente,
{nombre_ejecutivo}
"""

DEFAULT_CCS = [
    "julio.delgado@gobravo.com.co",
    "alianzasco@gobravo.com.co",
]

CCS_CREDITO = [
    "laura.guasca@gobravo.com.co",
    "nmcaro@gobravo.com.co"
]