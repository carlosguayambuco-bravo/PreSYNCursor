# AGENTS.md

Guía de contexto para agentes de IA y desarrolladores que trabajen en **PreSYNCursor**. Describe cómo está organizado el repositorio, cómo ejecutarlo, qué reglas implementa y cómo extenderlo sin romper los flujos existentes.

> **Regla de oro:** antes de modificar una fórmula, un estado o una regla de cruce, busca si tiene tests en `tests/` y agrega uno si no existe. Este repositorio maneja información financiera y de cartera; un cambio silencioso en un cálculo puede afectar solicitudes reales.

---

## 1. Contexto de negocio 

Estamos en una empresa que funciona como una reparadora de crédito, donde basicamente los clientes ingresan al programa con muchas deudas EXCLUSIVAMENTE DE CONSUMO que se encuentran morosas y donde se evalua que efectivamente exista un sobre-endeudamiento. A partir de que el cliente ingresa al programa se realizan negociaciones por las deudas con el fin de pagarlas con un descuento. El ingreso que deja el programa es un %Comisión sobre ese descuento ahorrado.

Desde el Área de Alianzas se busca centralizar la búsqueda de estos descuentos mediante la consolidación de aliados que cuentan con las deudas en su cartera y son capaces de ofrecer un descuento por estas. El objetivo de las alianzas es trabajar en una relación simbiótica donde desde la empresa se contacte el cliente y el aliado tenga que exclusivamente ajustarse a los valores de pago que nosotros brindamos.

Dentro de los aliados que tenemos hay 2 categorías:
- **Aliados Formales**: Aliados con un NDA que nos cruzan a inicio de mes una base de los clientes y los descuentos para sus deudas.
- **Aliados Informales**: Aliados sin documentos oficiales que pueden o no cruzar una base con los clientes pero que siempre estan dispuestos a verificar oportunidades de pago por el valor que ofrecemos.

Las alianzas son importantes porque permiten disminuir la carga operativa de tener que llamar a cada cliente y a cada banco con el que el cliente tenga una deuda morosa para averiguar un posible descuento, lo que permite a los negociadores enfocarse en aquellos clientes cuyas Casas de Cobro/Aliados no se cuenta con una alianza formal, maximizando la cantidad de clientes gestionados.

### 1.1 Problema que resuelve la aplicación

- ¿Qué proceso manual reemplaza la aplicación?: El App busca evitar las comunicaciones dispersas entre negociadores y ejecutivos centralizando la información y realizando compromisos en termínos de tiempos de respuesta y liquidaciones. Adicionalmente, se permite tener más control acerca de que solicitudes bloquear porque son irrelevantes/imposibles de aceptar por el aliado. Y por último, otorgar una forma más sencilla de llevar un seguimiento a estas solicitudes.
- ¿Quiénes son los usuarios principales y qué decisión toman con ella?: Los Negociadores usan el App para escalar las propuestas de pago y solicitar los acuerdos para liquidar deudas de los clientes. Los ejecutivos la usan para centralizar la información de las peticiones y tener una facilidad de respuesta adaptada a la operación. Los Admins la usan para realizar seguimiento del uso que se le da a las alianzas y a los cumplimientos de los compromisos pactados.
- ¿Qué se considera una solicitud exitosa para el negocio?: Una solicitud exitosa quiere decir que la comunicación con el aliado fue exitosa donde se consiguió un descuento (no siempre el solicituda, puede ser mayor o menor) y se entrega el Acuerdo de Pago si aplica.

### 1.2 Actores y responsabilidades

| Actor | Rol en el negocio | Rol en la app (`admin`, `leader`, `nego`, `executive`) | Responsabilidad |
|---|---|---|---|
| Negociador | Contactar a los clientes y proponer propuestas de pago con el cliente al ejecutivo para liquidar la(s) deuda(s) | `nego` | Subir Solicitudes y Liquidar Clientes |
| Líder de negociación | Llevar el seguimiento de un equipo de negociadores dando dirección y ayudas | `leader` | Realizar seguimiento a los KPIs de los negociadores |
| Ejecutivo de alianzas | Ser el contacto intermediador con los aliados | `executive` | Contactar con los aliados, recibir descuentos y acuerdos de pago. También realizar seguimiento a los resultados por aliado |
| Administrador / gerencia | Verificar el estado actual de la proyección y dar feedback de posibles cuellos de botella | `admin` | Controlar el estado de la operación en todo momento |
| Casa de cobro / aliado | Ninguno | No accede a la app | Cruzar Bases (si es posible), verificar opciones de pago y enviar acuerdos de pago junto con paz y salvos. |

### 1.3 Flujo end-to-end

#### 1.3.1 Manejo de Solicitudes
1. El negociador identifica al cliente y sus deudas.
2. Se selecciona una casa de cobro / aliado y un tipo de solicitud.
3. Se define el monto propuesto (total y por deuda) y, si aplica, el acuerdo de pago.
4. La solicitud se envía y queda en estado `Sin Tocar`.
5. El ejecutivo de alianzas gestiona la solicitud con el aliado.
6. El aliado responde con descuentos, contraofertas, cuotas o condiciones de pago.
7. Se registra la respuesta, se valida el pago y se generan acuerdos y soportes.
8. Se hace seguimiento a liquidaciones, vencimientos y reasignaciones.

#### 1.3.2 Manejo de Bases Entregadas por aliados
1. El Ejecutivo recibe la base entregada por el aliado
2. El Ejecutivo sube la base y se realiza un pre-cruce con el algoritmo interno
3. El Ejecutivo cruza manualmente todas las deudas que no cruzaron inicialmente por el algoritmo
4. El Ejecutivo sube la información al Sheets de `Descuentos en Base`, donde se maneja la info principal

### 1.4 Glosario de negocio

| Término | Definición de negocio |
|---|---|
| Solicitud | Petición a los ejecutivos de realizar la intermediación con los aliados para conseguir un descuento y/o obtener un acuerdo de pago para liquidar alguna de las deudas del cliente |
| Aliado / Casa de cobro | Casas de cobro que manejan las deudas de los clientes y con las cuales se tiene un contacto para conseguir descuento |
| PaB | El monto a pagar por la deuda - Diferente al monto que se debe, ya que casi el 100% de las veces viene con un descuento |
| PaB Ideal | El cupo aprobado desde el área de crédito para pagar la deuda. No lo tienen todos los clientes, es exclusivo de clientes con buen comportamiento |
| PaB Propuesta | El PaB que se propone al aliado para pagar la deuda |
| Descuento en Base | El aliado a veces nos cruza a inicio de mes los descuentos para todos los clientes por sus deudas. A estos descuentos se les conoce como descuentos en Base |
| Contraoferta | Es realizar una nueva oferta de pago por alguna de las deudas del cliente por un valor menor al que llegó en base o que se respondió en la solicitud |
| Acuerdo de pago | Un documento que sirve como verificación desde el aliado para poder realizar el pago y liquidar la deuda. Cuando se requiere este documento se sube una solicitud con este tipo. |
| Validación | Una solicitud para averiguar el descuento por una o más deudas del cliente con el aliado. |
| Oferta de acuerdo | Es una solicitud combinada entre el acuerdo de pago y la validación. Significa que si se llega al descuento mostrado, enviar directamente el acuerdo de pago, eliminando la necesidad de subir otra solicitud |
| Addendum | A veces el cliente tiene deudas que no se tienen presentes. Estos son los addendums, y es importante recolectarlos ya que se vuelven una nueva oportunidad de ingreso que no se tenía prevista |
| Portafolio | El grupo de deudas de un cliente |
| Liquidación | El pago de la deuda para quedar a paz y salvo con el acreedor de la deuda |
| Reasignación | Método del área para evitar conglomeración de buenos clientes, donde bajo ciertas reglas entre los asesores se pueden robar los clientes entre sí de modo que la mayoría de clientes liquiden al menos una deuda |

### 1.5 Reglas, excepciones y acuerdos con aliados

- ¿Qué significa exactamente "descuento máximo" para un aliado?: Significa que para ciertos aliados ya se ha realizado un análisis con ellos acerca del descuento máximo, por ende no tiene sentido permitir una solicitud por un descuento mayor.
- ¿Cuándo se exige pago total obligatorio?: Cuando el aliado lo requiera. Esta a modo de input dado que depende del aliado y del cliente.
- ¿Qué aliados permiten cuotas y con qué plazos?: la info se encuentra establecida en el Sheets de `Aliados`.
- ¿Qué bancos están bloqueados por aliado y por qué?: Se bloquean bancos por aliados para robustecer las solicitudes. Si ya sabemos que un aliado trabaja exclusivamente con un Banco X no tiene sentido permitir una solicitud de otro banco.
- ¿Cuándo una solicitud se considera vencida, cancelada o reasignable?:
  - *Vencida*: Hay dos criterios que son: Más de 15 días hábiles sin tocar la solicitud o después de marcarla como solicitada (se vuelve irreverente dado que como cambia el mes ya no se puede mantener la misma gestión).
  - *Cancelada*: La solicitud aún no tiene gestión, pero por algún motivo el negociador quiere cancelarla, y se puede hacer, evitando carga operativa. Esto solo aplica para solicitudes sin responder y sin solicitar
  - *Reasignable*: Por el momento significa que un acuerdo fue solicitado por un asesor pero no se ha refelejado el pago, por lo que otro asesor puede robar el acuerdo y pagarlo. Esto solo aplica cuando la fecha límite de pago del acuerdo se vence.
- ¿Qué excepciones requieren aprobación de comité o de titular ilocalizable?: Depende del aliado, pero muchas veces bajo comité significa que se podría obtener el descuento pero el pago es obligatorio. El titular ilocalizable es para que el negociador informe cuando se puede localizar.
- ¿Cómo se interpreta una contrapropuesta máxima relativa?: En pocas palabras llega un descuento en base por un aliado, y a ese aliado ya se le ha realizado un estudio donde se entiende que la contrapropuesta no puede pasar un X% por encima del que llego en base. Entonces esta solicitud no se debería aceptar teniendo en cuenta que ya se le realizó el estudio al aliado.

### 1.6 SLA y métricas

- Tiempo de respuesta comprometido por aliado: Depende de lo establecido en el Sheets de `Aliados`.
- Días hábiles / festivos aplicables: Colombia (`holidays` paquete, zona `America/Bogota`).
- Métricas oficiales: #Solicitudes, #Solicitudes Exitosas, %Solicitudes Exitosas, #Deudas Liquidadas, #Clientes Liquidados, %Deudas Liquidadas, %Clientes Liquidados
- Definición de "cumplimiento" y "efectividad": Cumplimiento hace referencia a los tiempos de respuesta, donde se satisface que lo estipulado en el Google Sheets se cumple. Efectividad se refiere a lo bueno que es un negociador con las solicitudes que son Exitosas, de modo que a más liquidaciones de esas solicitudes se es más efectivo.

### 1.7 Fuentes de verdad

| Dato | Fuente actual | Dueño | Observaciones |
|---|---|---|---|
| Solicitudes | Google Sheets (`Solicitudes_MEC`) | Propio | Es muy importante no borrar información o escribir por éncima de, dado que esto es muy delicado |
| Cartera / deudas | Metabase + Google Sheets | MB de la Empresa | Solo hay permiso de lectura, no escritura |
| Aliados y reglas | Google Sheets (`Aliados`) | Propio | Contiene la info relevante de los aliados con los que se trabaja |
| Descuentos / masivas | Google Sheets (`Masivas`) | Propio | Lugar principal donde se registran los descuentos que llegan |
| Liquidaciones | Google Sheets (`Liquidaciones`) | Sheets de la Empresa | Lugar donde se guarda toda la facturación histórica |
| Acuerdos y soportes | Google Drive | Shared Drive | Lugar para guardar todos los PDFs que se han obtenido |

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

- `PaB_Origen`: monto original / deuda Bravo.
- `PaB_Propuesta`: valor de pago propuesto en la base de masivas.
- `PaB_Ideal_Credito`: valor ideal para pago con crédito.
- `PaB_Portafolio`: valor de pago del portafolio completo.
- `PaB_Liq`: valor pagado al banco en una liquidación.
- Para cada deuda y aliado se elige el **menor `PaB_Propuesta`** como mejor descuento.
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

- `IVA = 1.19` y `DEFAULT_DISCOUNT_PL = 0.15` están en `modules/constants.py`.

### 6.4 Distribución de un monto entre deudas

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

Invariantes que los tests protegen:

- La suma de los montos distribuidos es igual al monto total.
- Los montos son enteros cuando se usa el método de ajuste.
- Las deudas con peso positivo no se extinguen si existe una granularidad válida.
- El orden de desempate de Hamilton prioriza mayor residuo, luego mayor peso, luego orden original.

### 6.5 Días hábiles y tiempos de respuesta

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

### 6.6 Estados de solicitud

Estados en `modules/constants.py` (`ESTADOS_POSIBLES_SOLICITUD`):

- `Sin Tocar`: aún no gestionada.
- `Solicitado`: escalada al aliado.
- `Exitosa`: respondida con éxito.
- `No Exitosa`: respondida sin éxito.
- `Vencida`: no gestionada en el plazo.
- `Erronea`: datos incorrectos o incompletos.
- `Bajo Comité`: pendiente de aprobación de comité.
- `Titular Ilocalizable`: pendiente de aprobación por titular ilocalizable.
- `No esta con Aliado`: el aliado no tiene la deuda.
- `Validada por Fuera`: pago/validación por fuera.
- `Cancelada`: cancelada por el negociador antes de gestionarse.

Reglas clave:

- Una solicitud es "sin responder" si está `Sin Tocar`, `Solicitado`, `Bajo Comité` con `Estado_Comite == 3`, o `Titular Ilocalizable` con `Estado_Titular_Ilocalizable == 3`; además debe ser actual y no estar baneada.
- Una solicitud requiere aprobación si está `Bajo Comité` con `Estado_Comite == 1`, o `Titular Ilocalizable` con `Estado_Titular_Ilocalizable == 1`.
- Un acuerdo es reasignable si es `Exitosa`, no es `Validación`, no es histórico, no está liquidado y su `Fecha_Limite_Pago` ya pasó.
- La liquidación se determina comparando los `Id_Deuda` de `JSON_Respuesta` contra el set de `load_liquidaciones()`.

### 6.7 Cruce de deudas (`id_aut_deud`)

Objetivo: dado un registro de la cartera del aliado, encontrar el `Id_Deuda` interno.

Etiquetas:

- `EXACTO`: un único candidato tras aplicar todas las acotaciones.
- `DUPLICADO`: dos o más registros reclaman el mismo `Id_Deuda`, o hay múltiples candidatos con número de crédito.
- `AMBIGUO`: hay candidatos por banco, monto o casa de cobro, pero no por número de crédito.
- `ADDENDUM`: el cliente coincide, pero no hay datos de deuda que permitan acotar.
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
- Los `ADDENDUM` no se suben a la base del mes.
- Si el cruce se hizo solo por nombre y la base no trae cédula, `build_pendiente_cruce_df` guarda `Cedula` como cadena vacía para que `PendienteCruceSchema` pueda validar la fila. El cargador también normaliza cédulas vacías a `''`.

---

## 7. Tests existentes

| Archivo | Qué cubre |
|---|---|
| `tests/test_calculos.py` | Limpieza y formato de números, días hábiles, aliados y tiempos de respuesta, descuentos, comparación de descuentos, distribución de montos, descuento óptimo, validación de base y normalización de bancos. |
| `tests/test_reglas_solicitud.py` | Máscaras de solicitudes, aprobaciones, comités, valores bajo comité, liquidaciones, fechas límite, métricas de cumplimiento, promedios, tops de negociadores y resúmenes. |
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