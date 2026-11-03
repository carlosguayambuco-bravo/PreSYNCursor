# AGENTS.md

Guía de contexto para agentes de IA y desarrolladores que trabajen en **PreSYNCursor**. Describe cómo está organizado el repositorio, cómo ejecutarlo, qué reglas implementa y cómo extenderlo sin romper los flujos existentes.

> **Regla de oro:** antes de modificar una fórmula, un estado o una regla de cruce, busca si tiene tests en `tests/` y agrega uno si no existe. Este repositorio maneja información financiera y de cartera; un cambio silencioso en un cálculo puede afectar solicitudes reales.

---

## 1. Contexto de negocio

Estamos en una empresa que funciona como una reparadora de crédito. Los clientes ingresan al programa con deudas **exclusivamente de consumo**, morosas, y se evalúa que exista un sobreendeudamiento real. A partir del ingreso se negocian las deudas para pagarlas con un descuento; el ingreso del programa es un **% de comisión sobre el descuento ahorrado**.

Desde el Área de Alianzas se busca centralizar la búsqueda de esos descuentos mediante la consolidación de aliados que tienen las deudas en su cartera y pueden ofrecer un descuento. La relación es simbiótica: la empresa contacta al cliente y el aliado se ajusta a los valores de pago que nosotros brindamos.

Categorías de aliados:

- **Formales:** tienen NDA y cruzan a inicio de mes una base de clientes y descuentos de sus deudas.
- **Informales:** no tienen documentos oficiales; pueden o no cruzar una base, pero están dispuestos a verificar oportunidades de pago por el valor que ofrecemos.

La categoría formal/informal se registra en la hoja de aliados, pero **la app no la usa para tomar decisiones** y no forma parte de `AliadosSchema`. Las alianzas reducen la carga operativa de llamar cliente por cliente y banco por banco; los negociadores se enfocan en clientes cuyas casas de cobro no tienen alianza formal.

### 1.1 Problema que resuelve la aplicación

- **¿Qué proceso manual reemplaza?** Evita comunicaciones dispersas entre negociadores y ejecutivos, centraliza la información y permite compromisos en términos de tiempos de respuesta y liquidaciones. También da control sobre qué solicitudes bloquear por ser irrelevantes o imposibles de aceptar, y facilita el seguimiento.
- **¿Quiénes son los usuarios principales?** Los negociadores escalan propuestas de pago y solicitan acuerdos para liquidar deudas. Los ejecutivos centralizan las peticiones y responden según la operación. Los administradores hacen seguimiento al uso de alianzas y al cumplimiento de compromisos.
- **¿Qué es una solicitud exitosa?** Una comunicación exitosa con el aliado en la que se consiguió **cualquier descuento**, no necesariamente el monto solicitado; si aplica, se entrega el Acuerdo de Pago. La app no valida automáticamente esa condición: el estado `Exitosa` lo marca el usuario con base en la respuesta del aliado.

### 1.2 Actores y responsabilidades

| Actor | Rol en el negocio | Rol en la app (`admin`, `leader`, `nego`, `executive`) | Responsabilidad |
|---|---|---|---|
| Negociador | Contactar a los clientes y proponer propuestas de pago con el cliente al ejecutivo para liquidar la(s) deuda(s) | `nego` | Subir solicitudes, liquidar clientes y aprobar/rechazar solicitudes transitorias (`Bajo Comité` / `Titular Ilocalizable`) |
| Líder de negociación | Llevar el seguimiento de un equipo de negociadores dando dirección y ayudas | `leader` | Realizar seguimiento a los KPIs de los negociadores |
| Ejecutivo de alianzas | Ser el contacto intermediador con los aliados | `executive` | Contactar con los aliados, recibir descuentos y acuerdos de pago. También realizar seguimiento a los resultados por aliado |
| Administrador / gerencia | Verificar el estado actual de la proyección y dar feedback de posibles cuellos de botella | `admin` | Controlar el estado de la operación en todo momento |
| Casa de cobro / aliado | Ninguno dentro de la app | No accede a la app | Cruzar bases (si es posible), verificar opciones de pago y enviar acuerdos de pago junto con paz y salvos |

### 1.3 Flujo end-to-end

#### 1.3.1 Manejo de solicitudes

1. El negociador identifica al cliente y sus deudas.
2. Se selecciona una casa de cobro / aliado y un tipo de solicitud.
3. Se define el monto propuesto (total y por deuda) y, si aplica, el acuerdo de pago.
4. La solicitud se envía y queda en estado `Sin Tocar`.
5. El ejecutivo de alianzas gestiona la solicitud con el aliado.
6. El aliado responde con descuentos, contraofertas, cuotas o condiciones de pago.
7. Se registra la respuesta, se valida el pago y se generan acuerdos y soportes.
8. Se hace seguimiento a liquidaciones, vencimientos y reasignaciones.

Si la solicitud cae en `Bajo Comité` o `Titular Ilocalizable`, el **negociador** aprueba o rechaza con base en lo hablado con el cliente. Si aprueba, la solicitud vuelve a la cola del ejecutivo para que la finalice.

Una respuesta exitosa se propaga automáticamente a las solicitudes espejo que comparten las mismas deudas/aliado mediante `Metadata_Solicitud["Id_Respuesta_Autom"]`. Una validación exitosa sin pago total también actualiza sub-solicitudes cuyas deudas son un subconjunto de la respuesta original. El ejecutivo puede editar la respuesta y redistribuir los cambios.

#### 1.3.2 Manejo de bases entregadas por aliados

1. El ejecutivo recibe la base entregada por el aliado.
2. El ejecutivo sube la base y se realiza un pre-cruce con el algoritmo interno.
3. El ejecutivo cruza manualmente todas las deudas que no cruzaron inicialmente por el algoritmo.
4. El ejecutivo sube la información al Sheets de descuentos en base, donde se maneja la información principal.

### 1.4 Glosario de negocio

| Término | Definición de negocio |
|---|---|
| Solicitud | Petición a los ejecutivos para intermediar con los aliados, conseguir un descuento y/o obtener un acuerdo de pago para liquidar alguna de las deudas del cliente |
| Aliado / Casa de cobro | Casa de cobro que maneja las deudas de los clientes y con la que se tiene contacto para conseguir un descuento |
| Aliado formal / informal | Categoría operativa registrada en la hoja de aliados; la app no la usa para decisiones. Ver sección 1 |
| PaB | Familia de valores de pago. No es un único campo: ver `PaB_Origen`, `PaB_Propuesta`, `PaB_PL`, `PaB_Portafolio` y `PaB_Ideal_Credito` |
| `PaB_Origen` | Monto original de la deuda; es la “Deuda Bravo” que se usa como referencia para calcular descuentos |
| `Monto_Actual` | Monto original de la deuda en la solicitud. En la práctica coincide con el valor de referencia de `PaB_Origen` |
| `PaB_Propuesta` | Oferta de pago que entrega el aliado en su base (descuento en base). Es el valor que se compara contra `Monto_Propuesto` |
| `Monto_Propuesto` | Monto de pago que propone el negociador en la solicitud para cada deuda |
| PaB Ideal / `PaB_Ideal_Credito` | Cupo aprobado desde el área de crédito para pagar una deuda. No todos los clientes lo tienen; es exclusivo de clientes con buen comportamiento |
| `PaB_PL` | PaB prometido al cliente en su Plan de Liquidación. En el código viene de `payment_to_bank`; si falta, se estima como `PaB_Origen * (1 - 0.15)` |
| `PaB_Portafolio` | Monto de pago asociado al portafolio completo |
| `Pricing` | Comisión de éxito (%) que cobra la empresa. En el código viene de `success_commission_percentage`; el IVA del 19% se suma aparte. El umbral de 60M COP de `PaB_Origen` es un criterio de elegibilidad del programa, no el valor de `pricing` |
| `Ahorro` | Ahorro con el que cuenta el cliente para pagar sus deudas (hoja de SALDOS) |
| `Por Cobrar` | Monto que el cliente debe a la empresa (hoja TOTAL) |
| `IVA` | Impuesto de Colombia: 19% |
| Deuda Bravo | Nombre operativo del monto original de la deuda (`PaB_Origen`) |
| Descuento en base | Descuento que el aliado cruza a inicio de mes para sus deudas. Se representa con `PaB_Propuesta` |
| Descuento máximo | Puede referirse a dos cosas: (1) `Brindan Máx. Descuento` en la hoja de aliados, que indica que ya se analizó el máximo y pedir más suele ser rechazado; (2) `Max_Descuento_Otorgado` en una respuesta, que indica que no se puede contraofertar. La app solo advierte en el primer caso y fuerza el flag en `Bajo Comité` |
| Contraoferta | Nueva oferta de pago por una deuda, menor al valor que llegó en base o al que se respondió en la solicitud |
| Contrapropuesta máxima relativa | Porcentaje máximo que puede bajarse el pago respecto al valor en base. El código compara `1 - monto_solicitado / monto_en_base` contra este campo |
| Acuerdo de pago | Documento de verificación del aliado para poder pagar y liquidar la deuda. Se solicita con una solicitud de este tipo |
| Validación | Solicitud para averiguar el descuento de una o más deudas con el aliado |
| Oferta de acuerdo | Solicitud combinada entre acuerdo de pago y validación: si se llega al descuento mostrado, se envía directamente el acuerdo de pago sin subir otra solicitud |
| Addendum | Deuda nueva que el cliente tiene y no estaba en la solicitud original. Se adjunta a la solicitud existente como `Metadata_Solicitud["Addendums"]`; no genera una solicitud nueva |
| Portafolio | Grupo de deudas de un cliente. Se usa `Distribuir Monto de Portafolio` cuando el aliado entrega un monto total y `Monto Individual de Portafolio` cuando cada deuda trae su propio monto |
| Liquidación | Pago de la deuda para quedar a paz y salvo con el acreedor. `Liquidado Parcial` = algunas deudas de la respuesta están pagadas; `Liquidado Total` = todas |
| Reasignación | Mecanismo para evitar la conglomeración de buenos clientes: bajo reglas, un negociador puede tomar un acuerdo vencido de otro para intentar liquidarlo |
| Directo Base | Modo de búsqueda automática del aliado que cubre todas las deudas y ofrece la menor suma de `PaB_Propuesta`, considerando también solicitudes exitosas |
| Solicitud espejo / sub-solicitud | Solicitud que comparte la misma respuesta automática (`Id_Respuesta_Autom`) o cuyas deudas son un subconjunto de otra solicitud; se actualiza cuando se distribuye una respuesta |
| `Pago_Total_Obligatorio` | Si es verdadero, el pago debe aplicarse a todas las deudas de la respuesta. En `Bajo Comité` la UI lo fuerza a verdadero |
| `Tradicional` | Tipo de pago único, sin cuotas |
| `Estructurado` | Tipo de pago en cuotas |
| `Refi` | Tipo de pago por refinanciación |
| `Crédito` | Tipo de pago que usa el PaB Ideal aprobado por crédito |
| `Pendientes_IdAutDeud` | Hoja interna donde se guardan los registros del cruce de cartera antes de subirlos a descuentos en base |

### 1.5 Reglas, excepciones y acuerdos con aliados

- **“Descuento máximo” de un aliado:** para ciertos aliados ya se hizo un análisis del descuento máximo; no tiene sentido permitir una solicitud por un descuento mayor. En la práctica `Brindan Máx. Descuento` genera una advertencia, no un bloqueo duro.
- **Pago total obligatorio:** se exige cuando el aliado lo requiera; es un input que depende del aliado y del cliente. Significa aplicar el pago a **todas las deudas** de la respuesta. En `Bajo Comité` el código fuerza `Pago_Total_Obligatorio = True`.
- **Cuotas:** la información de qué aliados permiten cuotas y con qué plazos está en la hoja de aliados (`AlianzasVigentes`).
- **Bancos bloqueados:** se bloquean bancos por aliado para robustecer las solicitudes. Si el aliado trabaja exclusivamente con un banco, no tiene sentido permitir otro. Si alguna deuda seleccionada tiene un banco no habilitado, el formulario **detiene el envío** y pide corregir la selección.
- **Vencida:** se vence a los **15 días hábiles** desde la subida (`Timestamp`) o desde que se marca como `Solicitado` (`Fecha_Solicitado`). La automatización de `automations/` usa 15 días; la introducción del notebook menciona 30 y está desactualizada. `LIMITE_MEC` (día 5) define el mes operativo, aunque hay una migración en curso para dejar de requerirlo.
- **Cancelada:** la solicitud aún no tiene gestión y el negociador que la subió decide cancelarla; solo aplica en `Sin Tocar`. La app valida que el correo del usuario sea el de la solicitud.
- **Reasignable:** un acuerdo solicitado por un asesor cuyo pago no se ha reflejado puede ser tomado por otro negociador cuando vence la fecha límite de pago. Aplica a Acuerdos y Ofertas de Acuerdo no liquidados; excluye Validaciones. Cualquier negociador puede tomarlo.
- **Aprobaciones de comité / titular ilocalizable:** `Estado_Comite` y `Estado_Titular_Ilocalizable` usan `1 = pendiente de aprobación`, `2 = rechazado`, `3 = aprobado pendiente de finalizar`. El **negociador** aprueba o rechaza con base en lo hablado con el cliente; si aprueba, la solicitud vuelve a la cola del ejecutivo para finalizarla. `Bajo Comité` suele implicar pago obligatorio y `Titular Ilocalizable` se usa para informar la situación de localización del titular.
- **Contrapropuesta máxima relativa:** llega un descuento en base del aliado y ya se hizo un estudio de hasta qué porcentaje se puede mejorar. El código calcula `1 - monto_solicitado / monto_en_base` y **detiene el envío** si supera `Contrapropuesta_Maxima_Relativa`; aplica a Validación/Oferta y cuando el aliado se resolvió por `Directo Base`.

### 1.6 SLA y métricas

- **Tiempo de respuesta comprometido:** depende de lo establecido en la hoja de aliados (`AlianzasVigentes`).
- **Días hábiles / festivos:** Colombia (`holidays`), zona `America/Bogota`.
- **Métricas oficiales:** #Solicitudes, #Solicitudes Exitosas, %Solicitudes Exitosas, #Deudas Liquidadas, #Clientes Liquidados, %Deudas Liquidadas, %Clientes Liquidados.
- **Fórmulas oficiales acordadas:**
  - `%Solicitudes Exitosas = solicitudes exitosas / total de solicitudes`.
  - `%Deudas Liquidadas = deudas liquidadas / deudas de solicitudes exitosas`.
  - `%Clientes Liquidados = clientes con al menos una deuda liquidada / clientes con solicitud exitosa`.
  - `Efectividad = solicitudes con al menos una deuda liquidada / solicitudes exitosas`.
- **Cumplimiento:** satisfacción del tiempo de respuesta del aliado. Se excluyen `Vencida` y `Cancelada` porque no representan una respuesta efectiva; el código ya aplica esta exclusión en las métricas de SLA y en el promedio de tiempos de respuesta.
- **Efectividad:** qué tan bueno es un negociador con las solicitudes exitosas; a más liquidaciones de esas solicitudes, mayor efectividad.
- **Nota de implementación:** las fórmulas oficiales se definen sobre solicitudes exitosas. Algunas funciones de reporte todavía parten de todas las solicitudes para contar liquidaciones (`obtener_resumen_liquidaciones`, `obtener_tops_negociadores`) y podrían incluir No Exitosas o Validadas por Fuera. Revisar el filtro antes de usar esos números para decisiones o de cambiar su significado.
- **Liquidaciones:** la hoja `Liquidaciones` la actualiza un área externa (finanzas/operaciones). Los soportes subidos en la app son evidencia y no cambian por sí solos el estado de liquidación.

### 1.7 Fuentes de verdad

| Dato | Fuente actual | Dueño | Observaciones |
|---|---|---|---|
| Solicitudes | Google Sheets (`Solicitudes_MEC`) | Propio | Es muy importante no borrar información ni escribir por encima; es información delicada |
| Cartera / deudas | Metabase + Google Sheets | MB de la Empresa | Solo hay permiso de lectura, no escritura |
| Aliados y reglas | Google Sheets (`AlianzasVigentes`, spreadsheet de Aliados) | Propio | Contiene la información relevante de los aliados y la categoría formal/informal, que la app no usa |
| Descuentos / masivas | Google Sheets (`Bases mes actual 2024`, spreadsheet de Masivas) | Propio | Lugar principal donde se registran los descuentos que llegan; el nombre de la hoja es legado |
| Pendientes de cruce | Google Sheets (`Pendientes_IdAutDeud`, spreadsheet de Configs) | Propio | Registros del cruce de cartera antes de subirlos a descuentos en base |
| Liquidaciones | Google Sheets (`Liquidaciones`) | Sheets de la Empresa | Guarda la facturación histórica; la actualiza un área externa |
| Acuerdos y soportes | Google Drive | Shared Drive | Guarda los PDFs de acuerdos y soportes de pago |
| Archivos subidos | Google Sheets (`Archivos_Subidos`) + Drive | Propio | Evidencia de acuerdos firmados y soportes de pago |

---

## 2. Resumen técnico de la aplicación

PreSYNCursor es una aplicación **Streamlit** que gestiona solicitudes de pago escaladas a aliados (casas de cobro). La app permite:

- Subir solicitudes de **Validación**, **Acuerdo de Pago** u **Oferta de Acuerdo**.
- Consultar y gestionar solicitudes, respuestas y aprobaciones.
- Comparar el monto solicitado contra el **PaB Ideal** y el **descuento en base** por deuda y por aliado.
- Distribuir un monto total entre varias deudas.
- Generar acuerdos de pago y soportes PDF, subirlos a Google Drive y enviarlos por correo.
- Consultar cartera, liquidaciones, logs y métricas.
- Cruzar la cartera de un aliado contra la cartera interna para obtener el **Id Deuda interno** (pestaña "Agregar Cartera").

### Stack principal

- **Frontend / runtime:** Streamlit.
- **Datos tabulares:** pandas + pandera (esquemas en `data/data_models.py`).
- **Base de datos operativa:** Google Sheets vía `gspread` / `gspread-dataframe`.
- **Consultas de deudas:** Metabase (HTTP API).
- **Archivos:** Google Drive.
- **Correo:** Gmail API.
- **PDFs:** `pypdf`, `reportlab`, `Pillow`.
- **Fuzzy matching:** `fuzzywuzzy`, `thefuzz`.
- **Días hábiles:** `holidays` (Colombia).

---

## 3. Cómo ejecutar

### 3.1 Requisitos

- Python 3.12+ para la app principal (`numpy 2.5.2` requiere `>=3.12`; el entorno local usa 3.13). Los workflows de automatización usan Python 3.10 con `automations/requirements.txt`, que es independiente.
- Acceso a los secretos de Streamlit y a las cuentas de servicio de Google.
- Dependencias de `requirements.txt`.

### 3.2 Instalación local

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 3.3 Ejecutar la app

```powershell
streamlit run app.py
```

La app requiere `.streamlit/secrets.toml` (ignorado por git). No lo imprimas, no lo subas y no pegues su contenido en issues o commits.

### 3.4 Ejecutar tests

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

También puedes ejecutar un archivo o una clase concreta:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_calculos -v
.\.venv\Scripts\python.exe -m unittest tests.test_reglas_solicitud.TestValoresBajoComite -v
.\.venv\Scripts\python.exe -m unittest tests.test_cruce_deudas -v
```

Notas:

- La suite usa **`unittest`**, igual que los tests existentes. No agregues `pytest` sin acordarlo.
- Los tests no acceden a Google Sheets, Metabase ni Gmail. Las dependencias externas se mockean.
- Verás advertencias de Streamlit del tipo `No runtime found` o `missing ScriptRunContext`; son normales al ejecutar en modo bare.
- Si falta `fuzzywuzzy`, instala las dependencias de `requirements.txt` (el paquete ya está declarado allí).

---

## 4. Estructura del repositorio

```text
.
├── app.py                     # Punto de entrada: configuración, servicios, auth y navegación
├── core/                      # Autenticación, usuarios y permisos por rol
├── data/                      # Carga/escritura de datos, esquemas pandera y modelos
├── modules/                   # Lógica de negocio y cálculos
│   ├── classes.py             # Aliado, parseo de tiempos, managers compartidos
│   ├── constants.py           # Constantes, estados, queries, IDs de hojas, configuración
│   ├── forms.py               # Descuento óptimo, validación de base, bloqueo de bancos
│   ├── gest_sols.py           # Núcleo: solicitudes, descuentos, distribución, PDFs, correos
│   ├── bank_normalizer.py     # Normalización de nombres de bancos
│   ├── acuerdo_pdf_generator/ # Generación de acuerdos en PDF
│   └── id_aut_deud/           # Cruce de cartera para obtener el Id Deuda interno
├── services/                  # Clientes de Google Sheets/Drive/Mail y Metabase
├── ui/                        # Componentes reutilizables de Streamlit
├── views/                     # Páginas de la app (scripts de Streamlit)
├── utils/                     # Helpers generales, de hojas de cálculo e inicialización
├── tests/                     # Suite de tests con unittest
├── automations/               # Notebook y workflows de vencimiento automático
├── docs/                      # Documentación funcional (NEGO_DOC.md)
├── assets/
├── requirements.txt
└── .streamlit/                # Configuración local; secrets.toml está ignorado
```

### Responsabilidades por carpeta

| Ruta | Responsabilidad |
|---|---|
| `app.py` | Inicializa servicios y datos, autentica, arma la navegación según permisos. |
| `core/auth.py` | OAuth con Google, cookies, refresh tokens, restauración de sesión. |
| `core/permissions.py` | Permisos, roles y mapeo permiso → página. |
| `core/users.py` | Objeto de usuario autenticado. |
| `data/data_loader.py` | Lecturas cacheadas de Google Sheets y Metabase; normalización de solicitudes. |
| `data/data_uploader.py` | Escrituras/actualizaciones en Google Sheets y logs. |
| `data/data_deleter.py` | Borrados controlados (por ejemplo, bases de cruce). |
| `data/data_models.py` | Esquemas pandera y TypedDicts de solicitudes, masivas, cruce, etc. |
| `services/google_sheets.py` | Cliente gspread con reintentos y manejo de errores. |
| `services/google_drive.py` | Subida/descarga/borrado de archivos. |
| `services/google_mail.py` | Envío de correos con adjuntos. |
| `services/metabase.py` | Consultas a Metabase para deudas, planes y actualizaciones. |
| `modules/gest_sols.py` | Reglas de solicitud, comparación de descuentos, distribución de montos, PDFs y notificaciones. |
| `modules/forms.py` | Fórmulas del monto recomendado, descuento óptimo y validaciones del formulario. |
| `modules/id_aut_deud/deuda_matcher.py` | Algoritmo de matching de cartera (etiquetas EXACTO/DUPLICADO/AMBIGUO/ADDENDUM/NULO). |
| `modules/id_aut_deud/helpers.py` | Limpieza, índices, pagos a cuotas, portafolios y preparación de la base del mes. |
| `ui/` | Componentes de presentación y formularios reutilizables. |
| `views/` | Páginas: subir solicitud, gestionar, ver solicitudes, cartera, logs, cache. |
| `utils/helpers_general.py` | Números, fechas hábiles, formato, meses operativos. |
| `utils/initializer.py` | Bootstrap de `st.session_state` y servicios. |
| `automations/` | Vencimiento automático de solicitudes (notebook + GitHub Actions). |

---

## 5. Flujo de arranque y estado

1. `app.py` lee `st.secrets["debugging_mode"]`.
2. `initialize_services()` crea/restaura:
   - `metabase_service`
   - `google_sheets_service`
   - `google_mail_service`
   - `google_drive_service`
   - credenciales OAuth en `st.session_state["creds_google"]`.
3. `initialize_data()` carga en `st.session_state`:
   - `aliados_dict`
   - `solicitudes_mec_df`
   - `changes_references_dict`
   - `saldos_dict`
   - `pab_ideal_dict`
   - `masivas_df`
   - `addendums_df`
   - `liquidations_set`
   - `headcount_df`
   - `app_config_dict`
   - `special_user_permissions_dict`
4. Si `debugging_mode` está activo, `initialize_test_states()` inyecta un usuario de prueba. Si no, `authenticate_user()` ejecuta OAuth.
5. `get_permit_pages(role)` crea la navegación permitida y `pg.run()` ejecuta la vista.

**Implicación para tests:** las funciones puras deben recibir DataFrames/diccionarios por parámetro. No deben depender de `st.session_state` ni de servicios de Google. Si una función lo hace, aíslala con mocks o extrae la lógica pura.

### Roles y páginas

| Rol | Páginas principales |
|---|---|
| `nego` | Subir Solicitud, Ver Mis Solicitudes, Ver Cartera Total |
| `leader` | Subir Solicitud, Ver Mis Solicitudes, Ver Cartera Total |
| `executive` | Agregar Cartera, Gestionar Solicitudes, Ver Mis Solicitudes, Ver Cartera Total |
| `admin` | Todas: incluye Logs y Manejo de Cache |

La fuente de verdad de permisos es `core/permissions.py`.

---

## 6. Reglas de cálculo implementadas

> Esta sección documenta el comportamiento actual del código. Si el negocio define una regla distinta, primero actualiza la regla, luego los tests y este documento.

### 6.1 Descuento

- Descuento = `1 - valor_pagado / monto_actual`.
- Si `monto_actual <= 0`, el descuento es `0`.
- Se usa para:
  - Valor solicitado (`Monto_Propuesto`).
  - PaB Ideal.
  - Descuento en base por aliado.
  - Totales de la solicitud.
- El formato de presentación es `$valor (porcentaje)`.

### 6.2 PaB y comparación de descuentos

- `PaB_Origen`: monto original de la deuda / “Deuda Bravo”. Es la referencia para calcular descuentos.
- `Monto_Actual`: monto original de la deuda en la solicitud; en la práctica coincide con `PaB_Origen`.
- `PaB_Propuesta`: oferta de pago que entrega el aliado en su base (descuento en base).
- `Monto_Propuesto`: monto de pago que propone el negociador para cada deuda.
- `PaB_Ideal_Credito`: cupo aprobado desde crédito para pagar la deuda; no todos los clientes lo tienen.
- `PaB_PL`: PaB prometido al cliente en su Plan de Liquidación (`payment_to_bank`). Si falta, se estima como `PaB_Origen * (1 - DEFAULT_DISCOUNT_PL)`.
- `PaB_Portafolio`: valor de pago del portafolio completo.
- `PaB_Liq`: valor pagado al banco en una liquidación.
- `Pricing`: comisión de éxito (%) que cobra la empresa (`success_commission_percentage`); el IVA del 19% se suma aparte. El umbral de 60M COP de `PaB_Origen` es un criterio de elegibilidad del programa, no el valor de `pricing`.
- `Ahorro`: ahorro del cliente para pagar sus deudas (hoja de SALDOS).
- `Por Cobrar`: monto que el cliente debe a la empresa (hoja TOTAL).
- Para cada deuda y aliado se elige el **menor `PaB_Propuesta`** como mejor descuento. Si hay varios registros de la misma deuda/aliado, gana el menor monto; el orden de carga no define la prioridad.
- Los IDs de deuda se normalizan a string y se elimina el sufijo `.0` proveniente de Sheets.
- Semáforo de comparación (`obtener_color_comparacion`):
  - Verde: `valor <= valor_solicitado`.
  - Amarillo: `valor <= valor_solicitado * 1.15`.
  - Naranja: superior al 115%.

### 6.3 Monto recomendado / descuento óptimo

`modules/forms.py` calcula dos descuentos y elige el menor:

- **Tradicional:**

  ```text
  descuento = (ahorro - por_cobrar - pago_total_original)
              / (pago_total_original * (pricing * IVA - 1))
  ```

  Se limita entre `descuento_pl` y `1`.

- **Crédito (PaB Ideal):**

  ```text
  descuento = (pago_total_original - monto_ideal - (ahorro - por_cobrar))
              / pago_total_original
  ```

  Se limita entre `0.15` y `1`. Si falta el PaB Ideal de alguna deuda, retorna `1` (no viable).

- `descuento_pl` se calcula como `1 - pago_pl / pago_original`, donde `pago_pl` es la suma de `PaB_PL`.
- `IVA = 1.19` y `DEFAULT_DISCOUNT_PL = 0.15` están en `modules/constants.py`.
- Si los dos descuentos empatan, el tipo elegido es `Tradicional` porque la comparación usa `<=`.

Tipos de pago (`Tipo_Pago`):

- `Tradicional`: pago único sin cuotas.
- `Estructurado`: pago en cuotas.
- `Refi`: refinanciación.
- `Crédito`: pago con el PaB Ideal aprobado por crédito.
- En el formulario, si hay cuotas (>1) se ofrecen `Estructurado` y `Refi`; si no hay cuotas, `Tradicional` y `Crédito`. `obtener_descuento_optimo` sugiere `Tradicional` o `Crédito` y elige el menor descuento.

### 6.4 Distribución de un monto entre deudas

El formulario inicializa el monto total en **70% de la suma de `PaB_Origen`**. Es un valor por defecto editable, no una regla de negocio obligatoria.

`distribuir_monto_por_deuda` en `modules/gest_sols.py`:

1. Si **todas** las deudas tienen descuento en base para el **mismo aliado**, distribuye proporcionalmente a esos valores (menor `PaB_Propuesta` por deuda).
2. Si falta el descuento de alguna deuda o pertenece a otro aliado, distribuye proporcionalmente al `Monto_Actual`.
3. Si la suma de pesos es `0`, reparte en partes iguales.
4. Si el total es múltiplo de `1.000` y hay más de una deuda, busca la **mayor granularidad** (potencia de 10) que cumpla:
   - `MAE <= 1%` del total.
   - `MRE <= 10%` por deuda.
   - Ninguna deuda con peso positivo queda en `0`.
5. Si ninguna granularidad es válida, usa la distribución proporcional normal y ajusta la diferencia de redondeo en la deuda de mayor peso.

Constantes relevantes:

- `DISTRIBUCION_DIVISOR_GRANULARIDAD = 1000`
- `DISTRIBUCION_UNIDAD_MINIMA = 1000`
- `DISTRIBUCION_MAE_MAXIMO = 0.01`
- `DISTRIBUCION_MRE_MAXIMO = 0.10`

Modos de portafolio:

- `Distribuir Monto de Portafolio`: se usa cuando el aliado entrega un **monto total** por el portafolio; el monto se reparte entre las deudas según su participación.
- `Monto Individual de Portafolio`: se usa cuando **cada deuda trae su propio monto** en la base; el monto del portafolio es la suma de los pagos individuales.
- La elección depende de cómo venga la base del aliado, no de una regla fija distinta.
- `Directo Base` resuelve el aliado automáticamente: busca aliados que cubran todas las deudas en masivas o solicitudes exitosas y elige el de menor suma de `PaB_Propuesta`.

Invariantes que los tests protegen:

- La suma de los montos distribuidos es igual al monto total.
- Los montos son enteros cuando se usa el método de ajuste.
- Las deudas con peso positivo no se extinguen si existe una granularidad válida.
- El orden de desempate de Hamilton prioriza mayor residuo, luego mayor peso, luego orden original.

### 6.5 Días hábiles, vencimiento y tiempos de respuesta

- Se usa el calendario de **Colombia** (`holidays`) y la zona `America/Bogota`.
- `getBDDaysDiffFloat` calcula días hábiles con fracción de día.
- `move_business_days` desplaza días hábiles.
- Los tiempos de respuesta de aliados se parsean desde textos como:
  - `1 día` → 24 horas.
  - `2 días` → 48 horas.
  - `1 semana` → 120 horas (5 días hábiles).
  - Si no se puede parsear o está vacío → `72` horas (`TIEMPOS_RESPUESTA_DEFAULT`).
- `Aliado.obtener_tr_dias()` usa `horas // 24`; para 1 semana son 5 días.
- La fecha límite de respuesta se guarda en `Metadata_Solicitud["Fecha_Limite_Respuesta"]`; si no existe, se recalcula con el tiempo del aliado y el `Timestamp` de la solicitud.
- Una solicitud se vence a los **15 días hábiles** desde `Timestamp` o desde `Fecha_Solicitado`, según la automatización de `automations/Vencimiento_Automatico_Solicitudes.ipynb`. La introducción de ese notebook menciona 30 días; el código usa 15 y es la referencia vigente.
- `LIMITE_MEC` (día 5) define el mes operativo actual. Hay una migración en curso para dejar de requerir ese corte.

### 6.6 Estados de solicitud

Estados en `modules/constants.py` (`ESTADOS_POSIBLES_SOLICITUD`):

- `Sin Tocar`: aún no gestionada.
- `Solicitado`: escalada al aliado.
- `Exitosa`: respondida con éxito. Se marca cuando se consiguió **cualquier descuento**, no necesariamente el monto solicitado.
- `No Exitosa`: respondida sin éxito.
- `Vencida`: no gestionada en el plazo.
- `Erronea`: datos incorrectos o incompletos.
- `Bajo Comité`: pendiente de aprobación de comité.
- `Titular Ilocalizable`: pendiente de aprobación por titular ilocalizable.
- `No esta con Aliado`: el aliado no tiene la deuda.
- `Validada por Fuera`: pago/validación por fuera.
- `Cancelada`: cancelada por el negociador antes de gestionarse.

Aprobaciones transitorias:

| Estado | Valor | Significado | Siguiente paso |
|---|---|---|---|
| `Bajo Comité` | `Estado_Comite = 1` | Pendiente de aprobación | El negociador aprueba o rechaza |
| `Bajo Comité` | `Estado_Comite = 2` | Rechazado | No vuelve a la cola de respuesta |
| `Bajo Comité` | `Estado_Comite = 3` | Aprobado pendiente de finalizar | Vuelve al ejecutivo para finalizar la respuesta |
| `Titular Ilocalizable` | `Estado_Titular_Ilocalizable = 1` | Pendiente de aprobación | El negociador aprueba o rechaza |
| `Titular Ilocalizable` | `Estado_Titular_Ilocalizable = 2` | Rechazado | No vuelve a la cola de respuesta |
| `Titular Ilocalizable` | `Estado_Titular_Ilocalizable = 3` | Aprobado pendiente de finalizar | Vuelve al ejecutivo para finalizar la respuesta |

La UI de aprobación se muestra en la vista de solicitudes. `actualizar_aprobacion_necesaria` no valida el rol por sí misma; la restricción efectiva depende de la vista y del permiso del usuario.

Reglas clave:

- Una solicitud es "sin responder" si está `Sin Tocar`, `Solicitado`, `Bajo Comité` con `Estado_Comite == 3`, o `Titular Ilocalizable` con `Estado_Titular_Ilocalizable == 3`; además debe ser actual y no estar baneada.
- Una solicitud requiere aprobación si está `Bajo Comité` con `Estado_Comite == 1`, o `Titular Ilocalizable` con `Estado_Titular_Ilocalizable == 1`.
- En `Bajo Comité` la UI fuerza `Pago_Total_Obligatorio = True` y `Max_Descuento_Otorgado = True`; el flujo de aprobación lo maneja el negociador desde la vista de solicitudes.
- Un acuerdo es reasignable si es `Exitosa`, no es `Validación`, no es histórico, no está liquidado y su `Fecha_Limite_Pago` ya pasó. Cualquier negociador puede tomarlo.
- `Vencida` y `Cancelada` no cuentan como respuestas efectivas para SLA ni para el promedio de tiempos de respuesta. La exclusión vive en `ESTADOS_EXCLUIDOS_METRICAS_RESPUESTA` (`modules/gest_sols.py`).
- La liquidación se determina comparando los `Id_Deuda` de `JSON_Respuesta` contra el set de `load_liquidaciones()`. `Liquidado Parcial` significa que algunas de las deudas de la respuesta están pagadas; `Liquidado Total`, que todas.
- `Liquidaciones` es una hoja externa actualizada por finanzas/operaciones. Los soportes de pago subidos en la app son evidencia documental y no cambian el estado por sí solos.
- Una respuesta exitosa se propaga a solicitudes espejo mediante `Metadata_Solicitud["Id_Respuesta_Autom"]`; una validación exitosa sin `Pago_Total_Obligatorio` también actualiza sub-solicitudes con subconjuntos de deudas. El ejecutivo puede editar la respuesta y redistribuir los cambios.

### 6.7 Cruce de deudas (`id_aut_deud`)

Objetivo: dado un registro de la cartera del aliado, encontrar el `Id_Deuda` interno.

Etiquetas:

- `EXACTO`: un único candidato tras aplicar todas las acotaciones.
- `DUPLICADO`: dos o más registros reclaman el mismo `Id_Deuda`, o hay múltiples candidatos con número de crédito.
- `AMBIGUO`: hay candidatos por banco, monto o casa de cobro, pero no por número de crédito.
- `ADDENDUM`: el cliente coincide, pero no hay datos de deuda que permitan acotar. En la operación se trata como una deuda nueva que se adjunta a la solicitud existente (`Metadata_Solicitud["Addendums"]`), no como una solicitud separada.
- `NULO`: no hay coincidencia con cédula o nombre.

Orden de acotación:

1. Cédula / nombre del cliente (determina `NULO`).
2. Banco, casa de cobro (simulando banco) y monto (determina `AMBIGUO`).
3. Número de crédito (determina `EXACTO`, `DUPLICADO` o `ADDENDUM`).
4. Resolución de duplicados entre registros `EXACTO`.

Normalizaciones importantes:

- `cleanCedula`: quita puntos y sufijo `.0`.
- `cleanNombreCliente`: quita tildes, mayúsculas y ordena palabras alfabéticamente.
- `cleanNumeroCredito`: quita puntuación, `X` y ceros a la izquierda (si quedan ≥ 4 caracteres).
- `cleanText`: normaliza bancos, elimina stopwords y aplica reglas de negocio (por ejemplo Colpatria → Davi Bank, BBVA → BBVA).
- `normalizar_banco`: mapea nombres de bancos a un catálogo normalizado.

Portafolios:

- `distribuir_montos_portafolio`: reparte el pago de un portafolio entre sus deudas según `Monto_Actual` de cada deuda.
- `agrupar_montos_portafolio`: operación inversa; suma los pagos individuales para obtener el monto del portafolio.
- Si el grupo está incompleto (falta `Id_Definitivo`, falta monto o no hay todos los datos), no se distribuye/agrupa para no guardar montos incompletos.
- En `preparar_datos_base_mes` los `ADDENDUM` no se suben como deuda nueva a la base del mes; se registran aparte con `upload_massive_addendums` en masivas.
- Si el cruce se hizo solo por nombre y la base no trae cédula, `build_pendiente_cruce_df` guarda `Cedula` como cadena vacía para que `PendienteCruceSchema` pueda validar la fila. El cargador también normaliza cédulas vacías a `''`.

---

## 7. Tests existentes

| Archivo | Qué cubre |
|---|---|
| `tests/test_calculos.py` | Limpieza y formato de números, días hábiles, aliados y tiempos de respuesta, descuentos, comparación de descuentos, distribución de montos, descuento óptimo, validación de base, normalización de bancos y bloqueo de bancos en el formulario. |
| `tests/test_reglas_solicitud.py` | Máscaras de solicitudes, aprobaciones, comités, valores bajo comité, liquidaciones, fechas límite, métricas de cumplimiento, promedios, tops de negociadores y resúmenes. Incluye la exclusión de `Vencida` y `Cancelada` de las métricas de SLA/tiempo de respuesta. |
| `tests/test_cruce_deudas.py` | Limpieza de cédula/nombre/crédito/banco, etiquetas del matcher, pagos a cuotas, estados de cruce, distribución y agrupación de portafolios, y validación de `build_pendiente_cruce_df` (incluido el cruce por nombre sin cédula). |
| `tests/test_archivos.py` | Nombres de archivos, metadata de PDFs, esquema de archivos subidos y soportes por deuda. |
| `tests/test_viabilidad.py` | Unión de PDFs y PDFs encriptados. |

### Convenciones para nuevos tests

- Usa `unittest` y `unittest.mock`; no requiere dependencias nuevas.
- No uses `st.session_state` real ni llamadas a Google/Metabase. Pasa DataFrames y diccionarios en memoria.
- Para funciones que llaman a Streamlit (`st.warning`, `st.stop`, `st.progress`), mockea la función o prueba la lógica pura extraída.
- Usa fechas de 2026 en los tests de días hábiles: el módulo `utils/helpers_general.py` construye los festivos de Colombia para el año actual al importarse. Si cambias el año de ejecución, revisa esos tests.
- No fijes valores frágiles de punto flotante; usa `assertAlmostEqual`.
- Si agregas una regla de negocio, agrega el caso feliz y al menos un borde (vacío, cero, nulo, duplicado o inconsistente).

---

## 8. Convenciones de código

- **PEP 8** y nombres descriptivos en español para lógica de negocio.
- Los comentarios suelen marcar pasos: `# Paso 1: ...`, `# Paso 2: ...`. Mantén ese estilo.
- Usa `cleanNumber` para montos que vienen de Sheets/formularios y `formatNumber` para mostrarlos.
- Normaliza IDs con `.replace('.0', '').strip()` antes de compararlos.
- Maneja fechas en `America/Bogota` y quita la zona horaria antes de comparar con datos de Sheets (`tz_localize(None)`).
- No mezcles `datetime` con zona y sin zona.
- Los esquemas de datos viven en `data/data_models.py`. Si agregas columnas, actualiza el esquema y los loaders/uploaders.
- No llames servicios de Google desde funciones de cálculo puras. Recibe los datos por parámetro.
- No cambies IDs de hojas, nombres de columnas o constantes de estados sin revisar todas las vistas y tests.
- No expongas secretos, tokens, IDs de hojas ni contenido de `.streamlit/secrets.toml`.

### Dónde poner una nueva función

- Cálculo puro y reutilizable → `modules/gest_sols.py`, `modules/forms.py` o `utils/helpers_general.py`.
- Regla de aliados / normalización → `modules/classes.py`, `modules/bank_normalizer.py`.
- Cruce de cartera → `modules/id_aut_deud/`.
- Lectura/escritura de datos → `data/data_loader.py` / `data/data_uploader.py`.
- Componente visual → `ui/`.
- Página → `views/` y registrar permiso en `core/permissions.py`.

---

## 9. Gotchas y riesgos conocidos

1. **`formatNumber` tiene un ajuste especial para `999` y `001`.** Por ejemplo, `formatNumber(999)` devuelve `1.000` y `formatNumber(1)` devuelve `0`. No lo uses para valores pequeños sin revisar el resultado; para montos normales de deuda funciona bien. Hay un test solo con montos representativos.
2. **Granularidad mínima de 1.000.** Si el monto total no permite repartir sin extinguir deudas, `_distribuir_monto_con_granularidad` devuelve `None` y se usa la distribución proporcional con ajuste de redondeo.
3. **IDs de Sheets con `.0`.** Muchos IDs llegan como `12345.0`; normalízalos antes de comparar. Los tests cubren este caso.
4. **Tildes en pruebas manuales / PowerShell.** `Tipo_Contraoferta` es un `Literal` y se valida con pydantic dentro del TypedDict. Si ejecutas snippets en PowerShell, los caracteres no ASCII pueden llegar como `?` (por ejemplo `Descuento M?ximo`) y Pandera reporta un error engañoso: `expected series 'Metadata' to have type TypedDict`. Usa archivos UTF-8 o escapes `\u00e1` al probar manualmente. Los tests cubren el caso válido y el cruce por nombre sin cédula.
5. **Dos librerías de fuzzy matching.** `requirements.txt` incluye `fuzzywuzzy` y `thefuzz`. `modules/classes.py` usa `fuzzywuzzy`; `modules/id_aut_deud/` usa `thefuzz`. No las intercambies sin probar el comportamiento de los umbrales.
6. **`co_holidays` se construye con el año actual al importar `utils/helpers_general`.** Los tests usan 2026; si ejecutas en otro año, los festivos de 2026 podrían no estar contemplados en cálculos que crucen años.
7. **Los textos de negocio usan tildes.** Al comparar estados como `Bajo Comité` o `Validación`, usa el literal exacto. Un `?` o una tilde distinta cambia la máscara.
8. **Los workflows de GitHub Actions** (`automations/`) ejecutan notebooks con `nbconvert` y credenciales en secrets. No los ejecutes localmente sin revisar qué celdas escriben en Sheets.
9. **SLA y estados de cierre.** `Vencida` y `Cancelada` se excluyen de SLA y del promedio de respuesta en `ESTADOS_EXCLUIDOS_METRICAS_RESPUESTA`. Si se agrega un estado que tampoco sea una respuesta efectiva, actualiza esa constante y sus tests.
10. **`LIMITE_MEC` está en migración.** El día 5 todavía define el mes operativo, pero el negocio está migrando a no requerir ese corte. No lo elimines sin revisar `getMesOperativo`, `load_solicitudes_mec` y los reportes.
11. **Los soportes de pago no liquidan por sí solos.** La fuente de `Estado_Liquidacion` es la hoja externa `Liquidaciones`; los archivos en Drive/`Archivos_Subidos` son evidencia.
12. **`Addendum` no es una solicitud separada.** Se adjunta a `Metadata_Solicitud["Addendums"]` y se incluye en el acuerdo/respuesta. `ADDENDUM` en el cruce solo indica que el cliente coincide pero la deuda no se pudo acotar.
13. **`Brindan Máx. Descuento` no bloquea.** La app advierte; el bloqueo duro no está implementado. Si negocio quiere bloquear, hay que cambiar formulario y tests.
14. **`Pago_Total_Obligatorio` se fuerza en `Bajo Comité`.** La UI lo pone en `True` y deshabilita el toggle; no es una elección libre en ese estado.
15. **Bloqueos duros del formulario.** El envío se detiene si hay bancos no habilitados o si se excede la contrapropuesta máxima relativa. `Brindan Máx. Descuento` sigue siendo solo una advertencia.
16. **Conteo de liquidaciones en reportes.** Las fórmulas oficiales se definen sobre solicitudes exitosas, pero `obtener_resumen_liquidaciones` y `obtener_tops_negociadores` todavía pueden contar liquidaciones de solicitudes No Exitosas o Validadas por Fuera. Revisa el filtro antes de usar esos números en decisiones.

---

## 10. Checklist antes de entregar un cambio

- [ ] ¿El cambio tiene un test en `tests/` que falla antes y pasa después?
- [ ] ¿Ejecutaste `python -m unittest discover -s tests` y pasa completo?
- [ ] ¿Actualizaste `AGENTS.md` si cambiaste una regla de cálculo, estado o flujo?
- [ ] ¿Revisaste que no se rompan los IDs con `.0`, los valores nulos y los DataFrames vacíos?
- [ ] ¿Evitaste llamadas reales a Google Sheets/Drive/Mail/Metabase en tests?
- [ ] ¿No agregaste secretos, tokens ni IDs sensibles al repositorio?
- [ ] ¿Mantuviste el estilo de comentarios y nombres del proyecto?
- [ ] ¿Revisaste el impacto en las vistas que consumen la función modificada?
- [ ] ¿Si cambiaste reglas de estado/SLA, actualizaste las constantes, los tests y este documento?
