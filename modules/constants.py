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
    'Solicitado', # Se escalo la solicitud al aliado.
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
    'Solicitado',
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

QUERY_TOTAL_REPARADORAS = """
SELECT
    bcrd.id AS Id_Deuda,
    bcr.document_number AS Cedula,
    bcr.full_name AS Nombre_Cliente,
    bcrd.financial_entity_name AS Banco,
    bcrd.credit_number AS Numero_Credito,
    bcrd.amount AS Monto_Actual,
    bcrd.state as Estado_Deuda,
    bcrd.sub_state as Sub_Estado_Deuda

FROM dealer_public.berex_credit_repair_debts bcrd

LEFT JOIN dealer_public.berex_credit_repairs AS bcr
    ON bcr.id = bcrd.credit_repair_id

WHERE 
    bcr.status IN ('active','partial_credito')
    AND bcr.country = 'co'
"""

QUERY_ACTIVE_DEBTS = """
WITH PLvanex AS (
    SELECT
        cr.bank_reference,
        cr.id AS cr_id,
        vsp.success_commission_percentage AS Pricing,
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
    bcrd.state IN ('new', 'negotiation', 'lawsuit')
    AND NOT (
        bcrd.sub_state IN (
            'liquidated',
            'liquidated_with_credit',
            'liquidation_in_process',
            'cancelled',
            'drop_requested',
            'liquidation_structured_payment'
        )
    )
    AND vsp.winner IS TRUE
    AND bcrd.bank_reference = '{referencia}'

QUALIFY 
    ROW_NUMBER() OVER (
        PARTITION BY bcrd.id
        ORDER BY bcrd.updated_at DESC
    ) = 1;
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

ESTADOS_LIQUIDACION = ['liquidation_structured_payment','paid_outside_of_program','liquidation','liquidation_portfolio_payment','client_settled_outside']
SUB_ESTADOS_LIQUIDACION = ['drop_requested','cancelled','liquidated','liquidation_in_process','liquidation_structured_payment']

# --- Constantes de Solicitudes ---

SOLICITUDES_ID_DELAY = 4601872 # El extra que se le suma al ID de la Solicitud para que no se repita con el ID de la Deuda

DEFAULT_DISCOUNT_PL = 0.15
LIMITE_MEC = 5 # El Día límite para Considerar el Día como mes operativo

# --- Constantes de Correos Electrónicos ---
EMAIL_SUBJECT_ACUERDO = "Acuerdo de Pago - REF: {referencia} - {nombre_cliente}"
EMAIL_SUBJECT_OFERTA_ACUERDO = "Oferta de Acuerdo - REF: {referencia} - {nombre_cliente}"
EMAIL_SUBJECT_MAPPER ={
    "Acuerdo de Pago": EMAIL_SUBJECT_ACUERDO,
    "Oferta de Acuerdo": EMAIL_SUBJECT_OFERTA_ACUERDO,
}

EMAIL_BODY_GENERAL = """<html>
<body style="font-family: Arial, sans-serif; font-size: 14px; color: #333333; line-height: 1.5;">
    <p>Cordial saludo,</p>
    
    <p>Espero que te encuentres bien.</p>
    
    <p>El motivo del presente mensaje es hacer la entrega formal del acuerdo de pago que fue solicitado {string_solicitado}. Adjunto a este correo podrás encontrar todos los detalles correspondientes.</p>
    
    <!-- BLOQUE DE CITA LLAMATIVO (QUOTEBLOCK) -->
    <div style="background-color: #f4f6f8; border-left: 5px solid #0056b3; padding: 15px; margin: 20px 0; border-radius: 4px;">
        <p style="margin: 0; font-weight: bold; color: #0056b3;">⚠️ Recordatorio Importante:</p>
        <p style="margin: 5px 0 0 0; font-style: italic; color: #555555;">
            {comentario_llamativo}
        </p>
    </div>
    
    <p>Quedo atento a cualquier comentario o paso adicional que se deba seguir.</p>
    
    <p>Muchas gracias por tu atención.</p>
    
    <p>Atentamente,<br>
    <strong>{nombre_ejecutivo}</strong></p>
</body>
</html>
"""

DEFAULT_CCS = [
    "alianzasco@gobravo.com.co",
]

CCS_CREDITO = [
    "laura.guasca@gobravo.com.co",
    "nmcaro@gobravo.com.co"
]

# -- Ids de Spreadsheets de Sheets
SOLICITUDES_SHEET_ID = '1tlHeLPJgIlRw3-_yv8lG4_w07n44o6KUxwxS1jmhjLk'
SALDOS_SHEET_ID = '1mvxPdnyp5ip_0Lqyf6qy09BAtX323PF2Yc5-qGoukeU'
REFCHANGES_SHEET_ID = '1jcPPhtF2YK3Kr7P_A0Mgh2OqhOfnVWB2to3UPoSH5tE'
PABIDEAL_SHEET_ID = '1Obm0O5hfIIzCMy5RvdX5b1JBf3pmzIrYdYa1vPOB83M'
ALIADOS_SHEET_ID = '1px7MX8zMKPe-PeCTvpNkX4kFMp1XL5IuBUrP1oGftiw'
MASIVAS_SHEET_ID = '1sOIk9BAa2VE-P-wnMPDJh8_hYLGgO5WaJL7m9LIM2is'
LIQUIDACIONES_SHEET_ID = '1H3sYEtkeu47POnu8xZMaMtID1Vj53YIcWblWeZ8d0rc'
HCNEGO_SHEET_ID = '1KO4ImvhNZB_jtgpvs9DU-6_0FskFmxC9Xo4Rz5Yt6dM'
CONFIGS_SHEET_ID = '1_8M4GQf-n4_0gCWFfPCpUSebdmuSrVbiyQBdNzry6io'
CARTERA_ACTIVA_SHEET_ID = '1NRM51v9ENd4IOShbstNa8nNohiFWDsmx18RxsD4LB-8'

# --- Configuraciones del Cruce de Deudas ---
# --- Constantes del Algoritmo ---
COL_ID_CRUCE = 'Id_Cruce'
COL_ID_DEUDA = 'Id_Deuda'
COL_CEDULA = 'Cedula'
COL_NOMBRE = 'Nombre_Cliente'
COL_BANCO = 'Banco'
COL_MONTO_ACTUAL = 'Monto_Actual'
COL_MONTO_PROPUESTO = 'Monto_Propuesto'
COL_CREDITO = 'Numero_Credito'
COL_FECHA_LIMITE_PAGO = 'Fecha_Limite_Pago'

COLUMNAS_UNIVERSO = [COL_CEDULA, COL_NOMBRE, COL_BANCO, COL_MONTO_ACTUAL, COL_CREDITO, COL_ID_DEUDA]

ETIQUETA_EXACTO = 'EXACTO'
ETIQUETA_DUPLICADO = 'DUPLICADO'
ETIQUETA_AMBIGUO = 'AMBIGUO'
ETIQUETA_ADDENDUM = 'ADDENDUM'
ETIQUETA_NULO = 'NULO'
MOTIVO_CASA_COBRO = 'Casa de Cobro'  # Motivo exclusivo de la acotación por Casa de Cobro

DIF_MONTO_MAX = 1000.0      # Diferencia absoluta máxima aceptada entre montos
MIN_LEN_TEXTO = 4           # Longitud mínima para aplicar contención / fuzzy / crop
MIN_PALABRAS_NOMBRE = 3     # Palabras mínimas en ambos registros para aplicar contención de nombres
RATIO_FUZZY_BANCO = 85      # Umbral de ratio fuzzy para el Banco
RATIO_FUZZY_CREDITO = 90    # Umbral de ratio fuzzy para el Número de Crédito
UMBRAL_BLOQUEO = 1000       # Si hay más candidatos se usan las rutas bloqueadas (más eficientes)
LIMITE_VERIFICACION = 20000 # Tope de filas a verificar en las rutas bloqueadas
MAX_COMB_NOMBRE = 6         # Tamaño máximo de subconjuntos de palabras para la contención de nombres

ETIQUETAS_CRUCE = [ETIQUETA_EXACTO, ETIQUETA_DUPLICADO, ETIQUETA_AMBIGUO, ETIQUETA_ADDENDUM, ETIQUETA_NULO]

# --- Prioridades de Ordenamiento de las Etiquetas del Cruce ---
PRIORIDAD_ETIQUETAS_CRUCE = {
    ETIQUETA_EXACTO: 1,
    ETIQUETA_DUPLICADO: 2,
    ETIQUETA_AMBIGUO: 3,
    ETIQUETA_ADDENDUM: 4,
    ETIQUETA_NULO: 5,
}

MIMETYPES = {
    'xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    'csv': 'text/csv',
}

COLUMNAS_MAPEABLES = [
    (COL_CEDULA, 'Cedula', ['cedula', 'documento', 'identificacion','cédula']),
    (COL_NOMBRE, 'Nombre del Cliente', ['nombre', 'cliente']),
    (COL_BANCO, 'Banco', ['banco', 'entidad','portafolio']),
    (COL_CREDITO, 'Número de Crédito', ['credito', 'numero crédito','numero_producto','numero_credito']),
    (COL_MONTO_ACTUAL, 'Monto Actual', ['monto actual', 'deuda', 'saldo', 'saldo insoluto']),
    (COL_ID_DEUDA, 'Id_Deuda (Opcional)', ['id deuda', 'id_deuda', 'id de la deuda']),
    (COL_MONTO_PROPUESTO, 'Monto Propuesto (Opcional)', ['monto propuesto', 'propuesta', 'descuento']),
]