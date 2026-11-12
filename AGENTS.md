# AGENTS.md

Guía de contexto para agentes de IA y desarrolladores que trabajen en **PreSYNCursor**. Describe cómo está organizado el repositorio, cómo ejecutarlo, qué reglas implementa y cómo extenderlo sin romper los flujos existentes.

> **Regla de oro:** antes de modificar una fórmula, un estado o una regla de cruce, busca si tiene tests en `tests/` y agrega uno si no existe. Este repositorio maneja información financiera y de cartera; un cambio silencioso en un cálculo puede afectar solicitudes reales. Adicionalmente, en caso de tener preguntas, SIEMPRE REALIZAR LAS PREGUNTAS ANTES DE LA EJECUCIÓN, para realizar correctamente los cambios requeridos.

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
| Negociador | Contactar a los clientes y proponer propuestas de pago con el cliente al ejecutivo para liquidar la(s) deuda(s) | `nego` | Subir solicitudes, liquidar clientes, aprobar/rechazar solicitudes transitorias (`Bajo Comité` / `Titular Ilocalizable`) y consultar oportunidades de sus Referencias |
| Líder de negociación | Llevar el seguimiento de un equipo de negociadores dando dirección y ayudas | `leader` | Realizar seguimiento a los KPIs de los negociadores y consultar oportunidades propias y de su equipo |
| Ejecutivo de alianzas | Ser el contacto intermediador con los aliados | `executive` | Contactar con los aliados, recibir descuentos y acuerdos de pago. También realizar seguimiento a los resultados por aliado |
| Administrador / gerencia | Verificar el estado actual de la proyección y dar feedback de posibles cuellos de botella | `admin` | Controlar el estado de la operación en todo momento y consultar oportunidades de todas las Referencias |
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
9. Al finalizar, el usuario puede enviar feedback desde el componente `mostrar_componente_feedback`; se guarda en la hoja `Feedback` de Configs.

Si la solicitud cae en `Bajo Comité` o `Titular Ilocalizable`, el **negociador** aprueba o rechaza con base en lo hablado con el cliente. Si aprueba, la solicitud vuelve a la cola del ejecutivo para que la finalice.

Una respuesta exitosa se propaga automáticamente a las solicitudes espejo que comparten las mismas deudas/aliado mediante `Metadata_Solicitud["Id_Respuesta_Autom"]`. Una validación exitosa sin pago total también actualiza sub-solicitudes cuyas deudas son un subconjunto de la respuesta original. El ejecutivo puede editar la respuesta y redistribuir los cambios.

#### 1.3.2 Manejo de bases entregadas por aliados

1. El ejecutivo recibe la base entregada por el aliado.
2. El ejecutivo sube la base y se realiza un pre-cruce con el algoritmo interno.
3. El ejecutivo cruza manualmente todas las deudas que no cruzaron inicialmente por el algoritmo.
4. El ejecutivo sube la información al Sheets de descuentos en base, donde se maneja la información principal.

#### 1.3.3 Cálculo de oportunidades

1. El negociador entra a **Calculadora de Oportunidades** y selecciona una Referencia habilitada (propias; el líder también ve las de su equipo; el admin ve todas).
2. Revisa el ahorro neto, el pricing, el prospecto de crédito (`Batch`/`Cr Parcial`) y el prospecto de tradicional (`Trad 1-4`).
3. Selecciona las deudas a analizar. La app bloquea deudas ya liquidadas.
4. Elige el tipo de análisis: **Tradicional** (ahorro del cliente) o **Crédito** (PaB Ideal). Crédito exige un estado apto en el Pipeline de Crédito y analiza únicamente las deudas con PaB Ideal > 0. Los prospectos `Cr Parcial` solo pueden analizarse por Crédito y los `Tradicional` solo por Tradicional.
5. La app muestra las oportunidades aplicables: Depósito Extra, ContraOferta Viable, Liquidación Instantánea, Acuerdo para Robo e IA Liquidadora. También permite enviar feedback.
6. El resultado es informativo: no crea ni modifica solicitudes por sí solo.

> **Estado actual:** la calculadora individual y la calculadora masiva están implementadas. Las fórmulas puras viven en `modules/oportunidades.py`, la UI individual en `ui/calculadora_components.py`, la UI masiva en `ui/calculadora_masiva_components.py` y los tests en `tests/test_oportunidades.py` y `tests/test_oportunidades_masivas.py`. La calculadora masiva usa Masivas cuando el toggle está activo y Actualizaciones cuando está inactivo, y calcula las oportunidades por portafolio/unidad de análisis. Ver sección 6.8.

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
| `PaB_Actualizado` | Monto de pago asociado a la última actualización confiable de la deuda (etiquetas `CAMBIO DE PAB`, `ACUERDO`, `DEPOSITO` y `ACTUALIZADO_ALIANZAS`). Se toma la actualización más reciente: si su etiqueta no es confiable, se usa `PaB_Origen`. Para `ACTUALIZADO_ALIANZAS` se cruza el último descuento en base con la última solicitud exitosa y prevalece la fuente con fecha más reciente. Se carga en `ActualizacionesSchema` desde `payment_to_bank`; el loader toma el primer número y lo divide entre 100 porque viene en centavos, dejando el valor en COP. |
| `Apartado_Neto` | Ahorro mensual neto del cliente: `max(Apartado_Mensual - Comision_Mensual, 0)`. Es un dato del cliente que se repite por deuda; para las oportunidades se toma un único valor (máximo de las filas), no la suma. |
| `Pricing` | Comisión de éxito (%) que cobra la empresa. En el código viene de `success_commission_percentage`; el IVA del 19% se suma aparte. El umbral de 60M COP de `PaB_Origen` es un criterio de elegibilidad del programa, no el valor de `pricing` |
| `Ahorro` | Ahorro con el que cuenta el cliente para pagar sus deudas (hoja de SALDOS) |
| `Por Cobrar` | Monto que el cliente debe a la empresa (hoja TOTAL) |
| `IVA` | Impuesto de Colombia: 19% |
| `Descuento Esperado` | Descuento esperado por deuda según el modelo de ML histórico, considerando el banco. En la Asignación de Cartera viene de la columna `Descuento` (`Descuento_Esperado`). |
| `Ingreso Esperado` | Ingreso estimado por deuda: `PaB_Origen * Descuento_Esperado * Pricing`, **sin IVA** y con mínimo 0. Se calcula en `load_asignacion_cartera`. |
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
| `Prospectos de Crédito / Batch` | Clientes con buen comportamiento de ahorro que son aptos para crédito. Se clasifican en `Batch 1` a `Batch 4` y `Cr Parcial`; es **por cliente**. |
| `Prospectos de Tradicional` | Deudas con mayor probabilidad de liquidación según el modelo de ML. Se alimentan de `Prosp_MEC_D_Liq` + `Mec_Probs`; es **por deuda**. Se clasifican como `Trad 1` a `Trad 4` y se usan para `IA Liquidadora` cuando `Prob_Liq >= 0.5`. |
| `Actualizaciones` | Gestiones registradas sobre las deudas (etiqueta, fecha, correo, nombre, referencia y `PaB_Actualizado`). Son la fuente para `PaB_Actualizado` y para detectar portafolios. |
| `Mes en Curso (MEC)` | Mes operativo actual. **Implementación actual:** `load_mes_operativo_liquidaciones()` toma `load_liquidaciones_mec()['Fecha_Liq'].min().normalize().replace(day=1)`; si no hay liquidaciones válidas, cae a `getMesOperativo()` (día 5). |

### 1.5 Reglas, excepciones y acuerdos con aliados

- **“Descuento máximo” de un aliado:** para ciertos aliados ya se hizo un análisis del descuento máximo; no tiene sentido permitir una solicitud por un descuento mayor. En la práctica `Brindan Máx. Descuento` genera una advertencia, no un bloqueo duro.
- **Pago total obligatorio:** se exige cuando el aliado lo requiera; es un input que depende del aliado y del cliente. Significa aplicar el pago a **todas las deudas** de la respuesta. En `Bajo Comité` el código fuerza `Pago_Total_Obligatorio = True`.
- **Cuotas:** la información de qué aliados permiten cuotas y con qué plazos está en la hoja de aliados (`AlianzasVigentes`).
- **Bancos bloqueados:** se bloquean bancos por aliado para robustecer las solicitudes. Si el aliado trabaja exclusivamente con un banco, no tiene sentido permitir otro. Si alguna deuda seleccionada tiene un banco no habilitado, el formulario **detiene el envío** y pide corregir la selección.
- **Vencida:** se vence a los **15 días hábiles** desde la subida (`Timestamp`) o desde que se marca como `Solicitado` (`Fecha_Solicitado`). La automatización de `automations/` usa 15 días; la introducción del notebook menciona 30 y está desactualizada. `load_mes_operativo_liquidaciones()` es la fuente principal del MEC; `LIMITE_MEC` (día 5) queda como fallback.
- **Cancelada:** la solicitud aún no tiene gestión y el negociador que la subió decide cancelarla; solo aplica en `Sin Tocar`. La app valida que el correo del usuario sea el de la solicitud.
- **Reasignable:** un acuerdo solicitado por un asesor cuyo pago no se ha reflejado puede ser tomado por otro negociador cuando vence la fecha límite de pago. Aplica a Acuerdos y Ofertas de Acuerdo no liquidados; excluye Validaciones. Cualquier negociador puede tomarlo.
- **Aprobaciones de comité / titular ilocalizable:** `Estado_Comite` y `Estado_Titular_Ilocalizable` usan `1 = pendiente de aprobación`, `2 = rechazado`, `3 = aprobado pendiente de finalizar`. El **negociador** aprueba o rechaza con base en lo hablado con el cliente; si aprueba, la solicitud vuelve a la cola del ejecutivo para finalizarla. `Bajo Comité` suele implicar pago obligatorio y `Titular Ilocalizable` se usa para informar la situación de localización del titular.
- **Contrapropuesta máxima relativa:** llega un descuento en base del aliado y ya se hizo un estudio de hasta qué porcentaje se puede mejorar. El código calcula `1 - monto_solicitado / monto_en_base` y **detiene el envío** si supera `Contrapropuesta_Maxima_Relativa`; aplica a Validación/Oferta y cuando el aliado se resolvió por `Directo Base`.
- **Prospecto de Crédito y tipo de pago:** los clientes con `Prospecto de Crédito = "Cr Parcial"` solo pueden aplicar a pagos/oportunidades por **Crédito**. Los clientes con `Prospecto de Crédito = "Tradicional"` solo pueden aplicar a pagos/oportunidades por **Tradicional**. Los `Batch 1-4` pueden usar ambos, siempre que Crédito sea viable.
- **Descuento Actual**: `1 - PaB_Actualizado / PaB_Origen` para el conjunto de deudas analizado. En la calculadora individual, de las actualizaciones solo se confía en las etiquetas `CAMBIO DE PAB`, `ACUERDO`, `DEPOSITO` y `ACTUALIZADO_ALIANZAS`; se toma la actualización más reciente y, si su etiqueta no es confiable, el descuento actual es 0%. Para `ACTUALIZADO_ALIANZAS` se cruza el último descuento en base con la última solicitud exitosa y prevalece la fuente con fecha más reciente. En el cálculo individual se asume que las deudas escogidas son el portafolio. `PaB_Actualizado` ya está en `ActualizacionesSchema` y se alimenta de `payment_to_bank` (centavos convertidos a COP). **En la calculadora masiva el descuento sale de Masivas con el toggle activo y de Actualizaciones con el toggle inactivo; nunca usa PaB simulado.**
- **Búsqueda de Portafolios**: para definir las deudas que se agrupan como portafolio existen 2 reglas:
  1. **Con Actualización:** se toman solo las deudas con una actualización dentro de la ventana configurable `VENTANA_PORTAFOLIO_SEGUNDOS` (por defecto `45` segundos) y que además compartan la misma etiqueta. Las deudas que cumplan se consideran en portafolio.
  2. **Sin Actualizaciones:** si no existen actualizaciones, se agrupan las deudas por los bancos exclusivamente listados en `BANCOS_PORTAFOLIO`: `BBVA Colombia`, `Itaú`, `Banco de Occidente` y `Banco Popular`.

  En la **calculadora masiva** cada portafolio es una unidad de análisis y las oportunidades se calculan por unidad; las deudas que no caen en un portafolio se analizan individualmente. En Masivas, `Metadata.Id_Portafolio` vacío significa deuda individual. Para Crédito, una unidad solo entra si todas sus deudas tienen PaB Ideal.

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
| Cartera / deudas | Metabase | MB de la Empresa | Solo hay permiso de lectura, no escritura |
| Aliados y reglas | Google Sheets (`AlianzasVigentes`, spreadsheet de Aliados) | Propio | Contiene la información relevante de los aliados y la categoría formal/informal, que la app no usa |
| Descuentos / masivas | Google Sheets (`Bases mes actual 2024`, spreadsheet de Masivas) | Propio | Lugar principal donde se registran los descuentos que llegan; el nombre de la hoja es legado |
| Pendientes de cruce | Google Sheets (`Pendientes_IdAutDeud`, spreadsheet de Configs) | Propio | Registros del cruce de cartera antes de subirlos a descuentos en base |
| Liquidaciones | Google Sheets (`Liquidaciones`) | Sheets de la Empresa | Guarda la facturación histórica; la actualiza un área externa |
| Acuerdos y soportes | Google Drive | Shared Drive | Guarda los PDFs de acuerdos y soportes de pago |
| Actualizaciones | Google Sheets (`Actualizaciones`) + Metabase | Propio / MB de la Empresa | Sheets es el backup que consume la app e incluye `PaB_Actualizado` desde `payment_to_bank`; Metabase se usa para consultar vencimiento de acuerdos (`QUERY_VENCIMIENTO_ACTS`) |
| Archivos subidos | Google Sheets (`Archivos_Subidos`) + Drive | Propio | Evidencia de acuerdos firmados y soportes de pago |
| Prospectos de Crédito | Google Sheets (`Prospectos de Crédito`) | Del Área de Crédito | Solo se toma la hoja del mes en curso (la más reciente). Es por cliente (`Batch 1-4`, `Cr Parcial`) |
| Prospectos de Tradicional | Google Sheets (`Prosp_MEC_D_Liq` + `Mec_Probs`) | Propio | Se unen por `Id_Deuda`; es por deuda (`Trad 1-4`) y trae `Prob_Liq`, `Prob_Liq_Cred`, `Prob_Liq_Trad` |
| Pipeline de Crédito | Google Sheets (`Pipeline Crédito`, hoja `Pipeline`) | Del área de crédito | Flujo de los procesos de crédito con el cliente. NO SE DEBE EDITAR. Se toma el último estado por `Referencia` |
| Asignación de Cartera | Google Drive Excel `Asignaciones de Cartera` | Propio | Se asigna una vez al mes. Archivo `...-MesAA.xlsx` y hoja `Mes AAAA`; se toma el más reciente. NO SE DEBE EDITAR |
| Feedback de la app | Google Sheets (`Feedback`, spreadsheet de Configs) | Propio | Una fila por envío: `Fecha`, `Usuario`, `Positivo`, `Origen`, `Comentario` y `Configuraciones` (JSON). Solo se escribe; la app no lo lee |
| Cambios de Masivas | Google Sheets (`Cambios_Masivas`, spreadsheet de Configs) | Propio | Trazabilidad del Mando de Operaciones: `Fecha_Cambio`, `Usuario`, `Nombre_Aliado_Cambio`, `Fecha_Aliado_Cambio`, `Num_Registros` y `Num_Cambiados`. Una fila por cada fecha procesada |
| Roles y permisos especiales | Google Sheets (`Usuarios`, spreadsheet de Configs) | Propio | `Correo` + `Cargo_Interno` para reemplazar el rol del headcount (`admin`, `leader`, `nego`, `executive`). La columna `Permisos` es opcional/legada; si no existe, se usan los permisos por defecto del rol |

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
- Calcular **oportunidades por Referencia** (Depósito Extra, ContraOferta Viable, Liquidación Instantánea, Acuerdo para Robo e IA Liquidadora) en la calculadora individual y en la **calculadora masiva vectorizada**. La masiva usa Masivas o Actualizaciones según el toggle, calcula por portafolio/unidad de análisis y presenta tarjetas paginadas por cliente; ver sección 6.8.
- Cargar **Asignación de Cartera**, **Prospectos de Tradicional** y **Pipeline de Crédito** como fuentes nuevas de la calculadora.
- Enviar **feedback de la app** a la hoja `Feedback` del spreadsheet de Configs.

### Stack principal

- **Frontend / runtime:** Streamlit.
- **Datos tabulares:** pandas + pandera (esquemas en `data/data_models.py`).
- **Excel de Asignación de Cartera:** `pandas.read_excel` con motor `calamine` (`python-calamine`); `openpyxl` está disponible como alternativa.
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
- Dependencias de `requirements.txt`. La lectura de la Asignación de Cartera usa `python-calamine` (motor `calamine`); no lo elimines sin cambiar el loader.

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

Secretos nuevos relacionados con la calculadora:

- `google_drive.folder_asignaciones`: carpeta de Drive donde están los Excel de Asignación de Cartera.
- `PERMITIR_CALCULO_NO_ASIGNADO`: booleano. Si es `true`, la calculadora habilita todas las Referencias para cualquier rol. Úsalo solo para pruebas; en producción el alcance debe salir de la Asignación/Headcount.

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
│   ├── oportunidades.py       # Cálculo de oportunidades y acceso a datos
│   ├── control_masivas.py     # Metadata y distribución de portafolios en la Base del Mes
│   ├── bank_normalizer.py     # Normalización de nombres de bancos
│   ├── acuerdo_pdf_generator/ # Generación de acuerdos en PDF
│   └── id_aut_deud/           # Cruce de cartera para obtener el Id Deuda interno
├── services/                  # Clientes de Google Sheets/Drive/Mail y Metabase
├── ui/                        # Componentes reutilizables de Streamlit
├── views/                     # Páginas de la app (scripts de Streamlit)
├── utils/                     # Helpers generales, de hojas de cálculo e inicialización
├── tests/                     # Suite de tests con unittest
├── automations/               # Notebook y workflows de vencimiento automático
├── docs/                      # Documentación funcional (NEGO_DOC.md, OPORTUNIDADES*.md)
├── assets/
├── requirements.txt
└── .streamlit/                # Configuración local; secrets.toml está ignorado
```

### Responsabilidades por carpeta

| Ruta | Responsabilidad |
|---|---|
| `app.py` | Inicializa servicios y datos, autentica, arma la navegación según permisos. |
| `core/auth.py` | OAuth con Google, cookies, refresh tokens, restauración de sesión y resolución del rol (headcount + roles especiales de la hoja `Usuarios`). |
| `core/permissions.py` | Permisos, roles (`PERMITTED_USERS`) y mapeo permiso → página. |
| `core/users.py` | Objeto de usuario autenticado y carga de permisos especiales. |
| `data/data_loader.py` | Lecturas cacheadas de Google Sheets, Google Drive y Metabase; normalización de solicitudes, asignación, prospectos, pipeline y control de masivas. |
| `data/data_uploader.py` | Escrituras/actualizaciones en Google Sheets, logs, feedback y control de masivas. |
| `data/data_deleter.py` | Borrados controlados (por ejemplo, bases de cruce). |
| `data/data_models.py` | Esquemas pandera y TypedDicts de solicitudes, masivas, cruce, asignación, prospectos, pipeline y control de masivas. |
| `services/google_sheets.py` | Cliente gspread con reintentos y manejo de errores. |
| `services/google_drive.py` | Subida/descarga/borrado de archivos. La descarga usa `MediaIoBaseDownload`. |
| `services/google_mail.py` | Envío de correos con adjuntos. |
| `services/metabase.py` | Consultas a Metabase para deudas, planes y actualizaciones. |
| `modules/gest_sols.py` | Reglas de solicitud, comparación de descuentos, distribución de montos, PDFs y notificaciones. |
| `modules/forms.py` | Fórmulas del monto recomendado, descuento óptimo y validaciones del formulario. |
| `modules/oportunidades.py` | Acceso a Asignación/Headcount/Prospectos/Pipeline, fórmulas puras de oportunidades y agregador `calcular_oportunidades_referencia`. |
| `modules/control_masivas.py` | Metadata y distribución de portafolios sobre la Base del Mes ya cargada. |
| `modules/id_aut_deud/deuda_matcher.py` | Algoritmo de matching de cartera (etiquetas EXACTO/DUPLICADO/AMBIGUO/ADDENDUM/NULO). |
| `modules/id_aut_deud/helpers.py` | Limpieza, índices, pagos a cuotas, portafolios y preparación de la base del mes. |
| `ui/calculadora_components.py` | UI de la calculadora individual por Referencia: selección de deudas, simulación de PaB/descuento, viabilidad y oportunidades. |
| `ui/calculadora_masiva_components.py` | UI de la calculadora masiva: filtros, tarjetas por cliente, oportunidades por portafolio/unidad, ingreso estimado, detalle por portafolio, redirección a la calculadora individual y paginación entera. |
| `ui/forms_components.py` | Componentes del formulario de solicitudes y componente de feedback. |
| `ui/` | Componentes de presentación y formularios reutilizables. |
| `views/` | Páginas: subir solicitud, gestionar, ver solicitudes, cartera, calculadora, logs, cache y mando de operaciones. |
| `docs/OPORTUNIDADES.md` | Explicación funcional de oportunidades para negociadores. |
| `docs/OPORTUNIDADES_DETALLADO.md` | Fórmulas y reglas exactas de cada oportunidad. Fuente de verdad de negocio. |
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

**Datos de la calculadora:** `load_asignacion_cartera()`, `load_prospectos_tradicional()` y `load_pipeline_credito()` se cargan **bajo demanda** con `st.cache_data`; no están en `initialize_data()`. `load_mes_operativo_liquidaciones()` (caché de 1 hora) obtiene el MEC desde `load_liquidaciones_mec()` y cae a `getMesOperativo()` si no hay liquidaciones válidas.

**Roles especiales:** `load_permisos_especiales()` también se carga **bajo demanda** al resolver el rol del usuario (`get_user_role`) y se cachea 1 hora. No está en `initialize_data()`. Se puede reiniciar desde **Manejo de Cache**. Un cambio de rol en la hoja `Usuarios` no afecta a una sesión ya autenticada hasta que el usuario vuelva a iniciar sesión.

**Implicación para tests:** las funciones puras deben recibir DataFrames/diccionarios por parámetro. No deben depender de `st.session_state` ni de servicios de Google. Si una función lo hace, aíslala con mocks o extrae la lógica pura.

### Roles y páginas

| Rol | Páginas principales |
|---|---|
| `nego` | Subir Solicitud, Ver Mis Solicitudes, Ver Cartera Total, Calculadora de Oportunidades |
| `leader` | Subir Solicitud, Ver Mis Solicitudes, Ver Cartera Total, Calculadora de Oportunidades |
| `executive` | Agregar Cartera, Gestionar Solicitudes, Ver Mis Solicitudes, Ver Cartera Total |
| `admin` | Todas: incluye Calculadora de Oportunidades, Logs y Manejo de Cache |

La fuente de verdad de permisos es `core/permissions.py`. El permiso `calcular_opps` está en `admin`, `leader` y `nego`; `executive` no lo tiene.

**Roles especiales (override de rol):** la hoja `Usuarios` del spreadsheet de Configs permite que un correo use un rol distinto al que le asigna el headcount.

- Columnas: `Correo` y `Cargo_Interno`.
- `Cargo_Interno` debe ser uno de `admin`, `leader`, `nego` o `executive` (se acepta cualquier combinación de mayúsculas/minúsculas y espacios alrededor). Un valor vacío o inválido se ignora y el usuario conserva el rol del headcount.
- El correo se compara sin distinguir mayúsculas/minúsculas. Si está repetido, prevalece la última fila válida de la hoja.
- `get_user_role()` consulta primero los roles especiales y, si el correo no tiene uno válido, sigue con la lógica del headcount. Por eso un correo puede usar la app aunque no esté registrado en el headcount.
- El nombre del usuario se toma del headcount; si no está allí, se usa el nombre del perfil de Google.
- El override no cambia el alcance de datos que depende del Headcount (por ejemplo, Referencias de la calculadora o correos a cargo). Un correo fuera del Headcount con rol `leader` o `nego` puede iniciar sesión, pero no tendrá Referencias/equipo asignados.
- El cambio se refleja al iniciar sesión (o al renovar la sesión). El loader tiene caché de 1 hora y se puede limpiar desde **Manejo de Cache**.
- La columna `Permisos` es opcional/legada. `load_special_user_permissions()` la lee si existe y devuelve `{}` si no; en ese caso `User.build_permits()` aplica los permisos por defecto del rol.

**Alcance de Referencias en la calculadora:**

- `admin`: todas las Referencias de la Asignación de Cartera.
- `leader`: sus Referencias y las de los negociadores cuyo `Lider` en el Headcount sea su nombre.
- `nego`: solo las Referencias donde `Negociador` coincide con su nombre del Headcount.
- `PERMITIR_CALCULO_NO_ASIGNADO=true`: habilita todas para cualquier rol (solo pruebas).

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
- `PaB_Actualizado`: monto de pago de la última actualización confiable (etiquetas `CAMBIO DE PAB`, `ACUERDO`, `DEPOSITO` y `ACTUALIZADO_ALIANZAS`); si no aplica, `PaB_Origen`. Se carga en `ActualizacionesSchema` desde `payment_to_bank`.
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
- `LIMITE_MEC` (día 5) sigue siendo el fallback de `getMesOperativo()`. La fuente principal es `load_mes_operativo_liquidaciones()` (caché de 1 hora), que toma `load_liquidaciones_mec()['Fecha_Liq'].min().normalize().replace(day=1)` y cae al fallback si no hay liquidaciones válidas.

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
2. Banco de la base, bancos seleccionados del aliado, casa de cobro (simulando banco) y monto (determina `AMBIGUO`).
3. Número de crédito (determina `EXACTO`, `DUPLICADO` o `ADDENDUM`).
4. Resolución de duplicados entre registros `EXACTO`.

Bancos seleccionados:

- Cuando la base del aliado no trae una columna `Banco`, el formulario de `views/agregar_cartera.py` permite seleccionar uno o más bancos de `BANCOS_UNICOS` (`modules/bank_normalizer.py`).
- `match_deudas(..., bancos_seleccionados=[...])` acota los candidatos a la unión de esos bancos. La acotación se registra con el motivo `Bancos Seleccionados` y, si no hay número de crédito, el registro queda `AMBIGUO` en lugar de `ADDENDUM`.
- Si ninguno de los bancos seleccionados existe en el universo, la acotación no se aplica y el resto del algoritmo sigue igual.
- Cambiar la selección de bancos invalida el resultado del cruce ya ejecutado en la sesión.

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

### 6.8 Cálculo de oportunidades (calculadora)

> **Estado actual:** la **calculadora individual** y la **calculadora masiva** están implementadas. `modules/oportunidades.py` contiene las fórmulas puras (`calcular_*`, `evaluar_*`), el agregador individual `calcular_oportunidades_referencia`, el motor vectorizado `calcular_oportunidades_masivas_datos` y la envoltura de datos `calcular_oportunidades_masivas`. La UI individual vive en `ui/calculadora_components.py` y la masiva en `ui/calculadora_masiva_components.py`. Los tests están en `tests/test_oportunidades.py` y `tests/test_oportunidades_masivas.py`. La fuente de verdad de negocio es `docs/OPORTUNIDADES_DETALLADO.md`.

**Fuentes y supuestos:**

- Se analiza un conjunto de deudas seleccionadas. En la calculadora individual se asume que **las deudas escogidas son el portafolio**.
- `PaB_Origen`: monto original de la deuda.
- `PaB_Actualizado`: monto de pago de la última actualización confiable. Se carga en `ActualizacionesSchema` desde `payment_to_bank`; el loader toma el primer número y lo divide entre 100 porque la fuente viene en **centavos** y el resultado queda en **COP**. Se toma la actualización **más reciente**: si su etiqueta no es confiable, se usa `PaB_Origen` (Descuento Actual = 0). Si la actualización confiable deja el PaB en 0, también se usa `PaB_Origen`: un pago en 0 se interpreta como dato faltante, no como descuento total. Para `ACTUALIZADO_ALIANZAS` se cruza el último descuento en base (masivas) con la última solicitud exitosa; si ambas fuentes tienen fecha, prevalece la más reciente, y si no hay fechas comparables se usa el valor de la fila de actualización.
- `PaB_Ideal_Credito`: cupo aprobado por crédito. En la calculadora individual, para análisis por crédito **todas** las deudas seleccionadas deben tener PaB Ideal > 0. En la calculadora masiva, una **unidad de análisis** (portafolio o deuda individual) solo se analiza por Crédito si **todas** sus deudas tienen PaB Ideal > 0; si falta una, la unidad completa queda fuera de Crédito y sigue participando de Tradicional. Las deudas individuales sin PaB Ideal quedan fuera de Crédito.
- `Ahorro` y `Por_Cobrar`: valores del cliente desde SALDOS/TOTAL. En la calculadora individual se pueden simular con los inputs editables.
- `PaB simulado`: en la calculadora individual, el input de PaB de cada deuda inicia con `PaB_Actualizado` (o `PaB_Origen` si no hay actualización confiable o si el PaB confiable viene en 0) y reemplaza el `PaB_Actualizado` oficial en Depósito Extra, Descuento Actual, Liquidación Instantánea y la comparación de la ContraOferta. La fórmula de la ContraOferta no cambia. La calculadora pasa el diccionario `pab_por_deuda` a `calcular_oportunidades_referencia`. El PaB simulado **puede superar el `PaB_Origen`** cuando se distribuye un monto de portafolio mayor al DUM total; en ese caso el descuento se muestra como 0% y el pago/ingreso se calculan con el valor simulado.
- `Depósito Extra` simulado: el input de la calculadora representa el ahorro nuevo que se proyecta a futuro y **hace parte del ahorro disponible**. Se suma al Ahorro para calcular la ContraOferta y la viabilidad, y se resta del Depósito Extra requerido en Tradicional y Crédito. No se cuenta dos veces: el depósito calculado ya queda neto del input.
- `Portafolio Total`: la columna de Resultados tiene un input de texto (`st.text_input`) para escribir un monto total del portafolio. Se limpia y formatea con `cleanNumber` igual que Ahorro, Por Cobrar y Depósito Extra. Se inicializa y recalcula con la suma de los PaB actuales cuando cambia el conjunto de deudas seleccionadas. Se distribuye automáticamente entre las deudas seleccionadas con `distribuir_monto_por_deuda` y **siempre por `PaB_Origen`** (`aliado=None`). No tiene tope: si el monto supera el DUM, los PaB simulados pueden superar su `PaB_Origen`.
- `Descuentos en Base`: cada deuda muestra un popover con `get_descuento_en_base` para comparar y copiar el valor al input de PaB. La casa de cobro solo se muestra si el usuario es `admin`; para los demás se muestra como `Directo Base`.
- La lista de deudas tiene una altura máxima fija (`ALTO_MAXIMO_LISTA_DEUDAS = 600` px, ajustable) con scroll. Si las deudas no llenan ese alto, el espacio restante se rellena con el bloque azul "Espacio para Reflexionar".
- `Apartado_Neto = max(Apartado_Mensual - Comision_Mensual, 0)`. Es un dato del cliente que se repite por deuda; para el cálculo se toma un **único valor** (el máximo de las filas seleccionadas), no la suma.
- `Pricing`: 0.15, 0.20 o 0.25 (`AsignacionSchema` lo valida estrictamente). `IVA = 1.19`.
- `Descuento_Esperado`: descuento esperado por deuda (modelo de ML, columna `Descuento` de la Asignación).
- `20_000`: COP 20.000 fijos por restricción de dónde se guarda el ahorro.
- `Descuento Actual = 1 - SUM(PaB_Actualizado) / SUM(PaB_Origen)` para el conjunto analizado.

**Bloqueos y validaciones:**

- Si alguna deuda seleccionada está liquidada (`obtener_estado_liquidacion_deudas`), la calculadora individual se detiene. La calculadora masiva excluye las deudas liquidadas y no analiza clientes cuyas deudas activas queden vacías.
- Análisis por crédito en la calculadora individual: se bloquea si el cliente está en `ESTADOS_NO_OPP_CREDITO` (`NO_PERFILA`, `NO_VIABLE_MEC`, `DTO_INSUFICIENTE`) o si alguna deuda no tiene PaB Ideal. Si está en `ESTADOS_NO_QUIERE_CREDITO` (`NO_LE_INTERESA`) solo se advierte. No estar en el Pipeline no bloquea.
- Análisis por crédito en la calculadora masiva: si el cliente no tiene fila en el Pipeline de Crédito **no** se bloquea; se asume viable porque aún no ha sido analizado. Si tiene fila, se considera no apto cuando el estado es `ESTADOS_NO_OPP_CREDITO` o `ESTADOS_NO_QUIERE_CREDITO`. No se exige que el estado sea exactamente `CERRADO`.
- `Prospectos de Crédito`: si el prospecto es `Tradicional`, no se permite Crédito; si contiene `parcial` (`Cr Parcial`), solo se permite Crédito y se deshabilita Tradicional. Los `Batch 1-4` permiten ambos análisis.
- `Prospectos de Tradicional`: `IA Liquidadora` usa `Prob_Liq >= 0.5` (probabilidad total, no `Prob_Liq_Cred` ni `Prob_Liq_Trad`).

**Fórmulas:**

- **Depósito Extra (Crédito):**

  ```text
  deposito_extra = SUM(PaB_Actualizado) + 20_000 - SUM(PaB_Ideal_Credito) - Deposito_Extra
  ```

- **Depósito Extra (Tradicional):**

  ```text
  deposito_extra = SUM(PaB_Actualizado)
                   + max((SUM(PaB_Origen) - SUM(PaB_Actualizado)) * Pricing * 1.19, 0)
                   + 20_000
                   - (Ahorro + Deposito_Extra - Por_Cobrar)
  ```

- **ContraOferta Viable (Crédito):**

  ```text
  contraoferta = 1 - (SUM(PaB_Ideal_Credito) + 20_000 + Deposito_Extra) / SUM(PaB_Origen)
  ```

- **ContraOferta Viable (Tradicional):**

  ```text
  contraoferta = (Ahorro + Deposito_Extra - Por_Cobrar - SUM(PaB_Origen) - 20_000)
                 / (SUM(PaB_Origen) * (Pricing * 1.19 - 1))
  ```

- **Depósito Extra como oportunidad:** se cumple si `deposito_extra / Apartado_Neto <= 3` **o** `deposito_extra <= 1_000_000`. El `deposito_extra` evaluado ya viene neto del input de Depósito Extra simulado. Si `deposito_extra < 0`, no es oportunidad de depósito extra: pasa a evaluarse como Liquidación Instantánea (en Tradicional solo si cumple el descuento mínimo del 3%). Si `Apartado_Neto == 0`, solo aplica la condición de `deposito_extra <= 1_000_000`.
- **ContraOferta Viable como oportunidad:** se cumplen **todas**:
  - `contraoferta > Descuento Actual`
  - `contraoferta <= 0.95`
  - `contraoferta <= Descuento_Esperado + 0.2`
  Para varias deudas, `Descuento_Esperado = SUM(Descuento_Esperado_i * PaB_Origen_i) / SUM(PaB_Origen_i)`.
- **Liquidación Instantánea:** cambia según el tipo de análisis.
  - **Tradicional:** exige `Descuento Actual >= UMBRAL_DESCUENTO_MINIMO_LIQ_INSTA` (3% por defecto) y además `Descuento Actual >= contraoferta` o `deposito_extra < 0`. El mínimo se aplica incluso cuando no se requiere depósito: tener el ahorro no basta si la deuda no tiene un descuento real. Con `Descuento Actual < 3%` no hay oportunidad.
  - **Crédito:** no exige el mínimo del 3%. Se cumple si `Descuento Actual >= contraoferta` y `Descuento Actual != 0`, o si `deposito_extra < 0`.
  El `deposito_extra` evaluado ya viene neto del input de Depósito Extra simulado. Un descuento actual mayor es mejor: el pago es menor y cabe en el cupo/ahorro.
- **Acuerdo para Robo:** acuerdos de pago del MEC ya vencidos, no liquidados y **sin gestión posterior**. Se considera que no hay gestión posterior si no existe ninguna actualización de la deuda con `Fecha_Act` posterior a la fila que registró el `ACUERDO`. La fecha de vencimiento sale de:
  1. Alianzas: `Fecha_Limite_Pago` de la solicitud exitosa. Si existe y está vigente, no se consulta Metabase.
  2. Si no existe, Metabase: `QUERY_VENCIMIENTO_ACTS` (`bda.expiration`, `type = 'agreement'`, últimos 30 días).
  3. Si no hay fecha en Metabase pero el resto de datos se obtiene, se considera para robo ("Sin fecha"); si la consulta falla, **no** se considera oportunidad.
  La unión con Alianzas/Metabase es por deuda (`Id_Deuda`), no por referencia.
- **IA Liquidadora:** no requiere cálculo; se activa con `Prospectos de Tradicional` y `Prob_Liq >= 0.5`. Para varias deudas, basta con que **al menos una** cumpla el umbral. Tener categoría `Trad 1-4` da prioridad, pero el umbral es la probabilidad.

### 6.8.1 Calculadora masiva de oportunidades

La pestaña **🛠️ Oportunidades Masivas** de `views/calculadora_opps.py` ejecuta el cálculo para todas las Referencias habilitadas del usuario (mismo alcance de `obtener_referencias_habilitadas`). La UI está en `ui/calculadora_masiva_components.py` y el motor en `modules/oportunidades.py`.

**Fuente del descuento:**

- El cálculo se hace por **unidad de análisis**: cada portafolio detectado o cada deuda individual. Luego se consolidan las unidades a nivel de cliente.
- `Solo de Masivas de Alianzas` (toggle activo por defecto):
  - **Activo:** el `PaB_Actualizado` sale **exclusivamente de la Base del Mes de Masivas** (`load_masivas`). Solo se analizan deudas con descuento vigente; los clientes sin deudas en Masivas no aparecen.
  - **Inactivo:** el `PaB_Actualizado` sale de **Actualizaciones**, con las etiquetas confiables (`CAMBIO DE PAB`, `ACUERDO`, `DEPOSITO`, `ACTUALIZADO_ALIANZAS`) y la regla individual de `ACTUALIZADO_ALIANZAS` (cruce con Masivas y Solicitudes). Antes de resolver el PaB se eliminan los duplicados por `Id_Deuda` + `Fecha_Act` conservando la última fila. Se analizan todas las deudas activas; las deudas sin actualización usan `PaB_Origen` (Descuento Actual = 0%).
- `seleccionar_descuentos_masivas` elige un único registro por deuda:
  - Solo considera `PaB_Propuesta > 0`.
  - Descarta registros con `Metadata.Fecha_Limite_Uso` vencida.
  - Los registros sin metadata (o con metadata inválida) se consideran vigentes.
  - Si hay varios vigentes, toma el **menor `PaB_Propuesta`** (mejor descuento). Los empates se resuelven por la masiva más reciente (`Fecha_Masiva` y luego `Fila_Sheets`).
  - Devuelve `Id_Portafolio`, `PaB_Portafolio` y `Portafolio_Completo` para armar las unidades.
- Las deudas liquidadas se excluyen del análisis. `Tiene_Deudas_Liquidaciones` queda disponible como filtro.

**Portafolios y pago actual:**

- **Masivas:** una deuda pertenece a un portafolio cuando `Metadata.Id_Portafolio` no está vacío; si está vacío, es una unidad individual. Para el portafolio se usa `PaB_Portafolio` como total y se distribuye por `PaB_Origen`. Si falta el total o el portafolio está incompleto (no están todas las deudas que reporta la base), se usa la suma de `PaB_Propuesta` de las deudas disponibles.
- **Actualizaciones:** se agrupan las actualizaciones confiables consecutivas con la misma etiqueta y a ≤ `VENTANA_PORTAFOLIO_SEGUNDOS` (45 s por defecto). Si todas las deudas del grupo tienen el mismo `PaB_Actualizado`, el pago se usa **una sola vez**; si difieren, se **suman**. Las actualizaciones no confiables no forman portafolio de pago.
- **Sin actualizaciones:** si el cliente no tiene ninguna actualización, se agrupan las deudas por cada banco de `BANCOS_PORTAFOLIO` (`BBVA Colombia`, `Itaú`, `Banco de Occidente`, `Banco Popular`). Cada banco forma su propio grupo; si el grupo tiene una sola deuda, queda individual. Si el cliente tiene al menos una actualización, esta regla no se aplica.
- Las deudas que no quedan en un portafolio se analizan **individualmente**.
- El pago de un portafolio se distribuye por `PaB_Origen` entre sus deudas para que la suma por deuda coincida con el total de la unidad. `Pago_Compartido` indica si el pago se usó una sola vez (Masivas con `PaB_Portafolio` o Actualizaciones con valores iguales).

**Reglas de Crédito:**

- `Credito_Viable` se determina con el estado del Pipeline cuando existe: es falso si el estado es `ESTADOS_NO_OPP_CREDITO` o `ESTADOS_NO_QUIERE_CREDITO`. Si no hay fila en el Pipeline se asume viable, porque la ausencia de gestión no implica inviabilidad. No se exige `CERRADO`.
- `Tradicional_Habilitado = prospecto no Cr Parcial`.
- `Cr Parcial` solo permite Crédito; `Tradicional` solo permite Tradicional; `Batch 1-4` permite ambos.
- Una unidad se analiza por Crédito solo si **todas** sus deudas tienen `PaB Ideal > 0`. Si falta una, la unidad completa queda fuera de Crédito (no se analiza con un subconjunto). Las deudas individuales sin PaB Ideal quedan fuera de Crédito y siguen en Tradicional.
- `Credito_Habilitado` es verdadero si al menos una unidad del cliente se analiza por Crédito.
- `Credito_Detalle` informa cuántas unidades entran y cuántas quedan fuera por deudas sin PaB Ideal.

**Oportunidades y resultado:**

- Se aplican las mismas fórmulas de Depósito Extra, ContraOferta Viable y Liquidación Instantánea de la calculadora individual, sin PaB simulado ni Depósito Extra simulado. El cálculo se hace **por unidad** (Tradicional y Crédito). En Tradicional, `Trad_Liq_Insta_Aplica` exige el mismo descuento mínimo del 3% (`UMBRAL_DESCUENTO_MINIMO_LIQ_INSTA`); en Crédito no se aplica.
- Acuerdo para Robo e IA Liquidadora son oportunidades generales por cliente:
  - Acuerdo para Robo se calcula de forma vectorizada sobre las actualizaciones del MEC. Primero resuelve Alianzas; para las deudas sin fecha de Alianza hace **una consulta batch** a Metabase con `load_vencimientos_acuerdos` y `QUERY_VENCIMIENTO_ACTS`. Si la consulta falla, no se asume la oportunidad; si trae datos pero no un acuerdo para la deuda/correo, se reporta "Sin fecha".
  - IA Liquidadora usa la máxima `Prob_Liq` de las deudas analizadas y aplica si `>= 0.5`.
- El resultado es un DataFrame con una fila por Referencia. Incluye métricas globales, métricas `Trad_*` y `Cred_*`, banderas por unidad, `Portafolios_Detalle`, `Oportunidades`, `Oportunidades_Generales`, `Num_Oportunidades`, `Num_Oportunidades_Calculadas`, `Num_Oportunidades_Generales`, `Es_Viable`, `Viable_Por`, `Tipos_Analisis` y `Deudas_Detalle`.
- `Num_Oportunidades` cuenta **incidencias por unidad** para las oportunidades calculadas (por ejemplo, Liquidación Instantánea en 3 portafolios suma 3) y **una vez** cada oportunidad general (Robo o IA). Los badges del encabezado muestran los tipos únicos.
- `Es_Viable` es verdadero si al menos una unidad es viable; `Viable_Por` indica si es por Tradicional, Crédito o ambos.
- El cálculo reporta avance con `st.progress` a través de `progreso_callback`.

**Filtros y visualización:**

- Los filtros se muestran dentro de un `st.container(border=True)`.
- Filtros: búsqueda por Referencia/Cliente, Negociador, Prospecto de Crédito, Tipo de Análisis (Tradicional/Crédito/ambos), multiselect de Oportunidad, Solo con oportunidades, Solo viables, rango de Descuento Actual, rango de DUM Total y exclusión de clientes con deudas liquidadas.
- **Combinación de Tipo de Análisis con Oportunidad:** con **Solo con oportunidades** activo, el Tipo de Análisis filtra el **resultado** y no la viabilidad del cálculo.
  - `Tradicional` o `Crédito`: solo quedan los clientes con al menos una oportunidad seleccionada en ese bloque. Si no hay oportunidad seleccionada, se exige al menos una oportunidad calculada del tipo (`Depósito Extra`, `ContraOferta Viable` o `Liquidación Instantánea`).
  - `Tradicional y Crédito`: la oportunidad debe existir en **ambos** bloques.
  - Las oportunidades generales (`Acuerdo para Robo`, `IA Liquidadora`) no pertenecen a un tipo: se exigen **además** y deben coexistir con al menos una oportunidad del tipo elegido.
  - Con **Solo con oportunidades** inactivo se conserva el filtro anterior de viabilidad (`Tradicional_Habilitado` / `Credito_Habilitado`).
  - El filtro se evalúa por unidad con `Portafolios_Detalle`, de modo que coincide con las oportunidades que muestran las tarjetas. Si el detalle no existe, usa como respaldo las banderas agregadas `Trad_*_Aplica` / `Cred_*_Aplica`.
- Ordenamiento: **Mayor Ingreso Estimado (por defecto)**, más oportunidades, mayor Descuento Actual, mayor DUM, mayor Ahorro Neto, Referencia A-Z o Nombre del Cliente A-Z.
- Debajo del ordenamiento hay un toggle **Invertir orden** (desactivado por defecto). Cada criterio conserva su orden natural (numéricos de mayor a menor, A-Z de A a Z); el toggle lo invierte.
- `Ingreso Estimado = max((DUM - PaB Actual) * Pricing, 0)`, sin IVA. Reemplaza a `Apartado_Neto` como quinto KPI y es el orden por defecto.
- La tarjeta del cliente muestra:
  - Un primer `st.container(horizontal=True)` con el número de oportunidades, si es viable y por dónde.
  - Un segundo `st.container(horizontal=True)` con los badges de todos los tipos de oportunidad.
  - Métricas: DUM, PaB Actual (Masivas o Actualizaciones según la fuente), Descuento Actual, Ahorro Neto e Ingreso Estimado.
  - Los bloques **Tradicional** y **Crédito lado a lado, con borde**, con una fila por unidad y oportunidad en 4 columnas: Oportunidad, Descripción, Valor y Deudas Involucradas. Las deudas muestran el nombre de la unidad y su cantidad como `st.caption` y los Ids como badges `🆔`; se inserta `st.divider()` entre oportunidades.
  - El bloque **Oportunidades Generales** con Robo/IA y sus deudas, con el mismo esquema de columnas, captions y separadores.
  - El expander **🔎 Ver deudas analizadas**.
  - El expander **📦 Detalle por portafolio / unidad de análisis**, con altura fija y scroll, que muestra cada unidad, sus deudas y sus oportunidades.
  - Un popover **🔁 Analizar en la calculadora individual** para escoger la unidad y el tipo de análisis. El botón deja la pestaña individual con la Referencia, las deudas del portafolio en `True`, las demás deudas del cliente en `False`, el tipo de análisis y `Continuar con Cálculo` listos. Limpia la simulación previa de PaB/descuento y el portafolio total.
- La paginación es local y **siempre usa enteros**: `_normalizar_pagina_actual` convierte strings/floats y `_calcular_slice_pagina` devuelve inicio/fin enteros antes de `iloc`. Los clientes por página se configuran en 10/20/30/50.
- Las descripciones y los detalles con montos se renderizan escapando `$` como `\$` para que Markdown no los interprete como LaTeX (`escapar_dolar_markdown`).

**Pendientes de definición/implementación:**

- Validar con negocio si la regla de "sin gestión posterior" del Acuerdo para Robo debe excluir también actualizaciones que no sean de pago (hoy excluye cualquier actualización posterior al `ACUERDO`).
- Validar el comportamiento de `ACTUALIZADO_ALIANZAS` cuando la metadata de masivas no trae `Fecha_Limite_Uso` y la solicitud exitosa tampoco tiene `Fecha_Respuesta`: hoy se usa el valor de la fila de actualización.

### 6.9 Carga y transformación de fuentes de la calculadora

**Asignación de Cartera (`load_asignacion_cartera`):**

1. Lista `google_drive.folder_asignaciones`, se queda con los `.xlsx` y elige el de mayor prioridad según `...-MesAA.xlsx`.
2. Dentro del Excel elige la hoja de mayor prioridad con formato `Mes AAAA` y calcula `Fecha_Cartera` = primer día de ese mes. Esa columna es metadata temporal y se descarta antes de validar.
3. Renombra columnas con `COL_MAPPER_ASIGNACION`, normaliza `Referencia`/`Id_Deuda` a string y aplica los cambios de referencia.
4. Imputa valores:
   - `PaB_Origen`, `Meses_en_Programa`, `Mora_Deuda`, `Apartado_Mensual`, `Comision_Mensual` y `Descuento_Esperado`: `0` si son nulos.
   - `Pricing`: `0.15` si es nulo; solo se aceptan `0.15`, `0.20` o `0.25`.
   - `Meses_Sin_Contacto`: `6` si es nulo.
   - `PaB_PL`: si falta, se imputa con el descuento promedio del banco; si el banco no tiene histórico, `30%`.
   - `Descuento_PL = 1 - PaB_PL / PaB_Origen`; si `PaB_Origen = 0`, `1`.
5. Mapea moras:
   - `Mora_Estructurado`: `No tiene estructurado = 0`, `No = 1`, `Sí = 2`.
   - `Mora_Credito`: `No = 0`, `Sí = 1`.
6. Calcula:
   - `Ingreso_Esperado = PaB_Origen * Descuento_Esperado * Pricing` (sin IVA, mínimo 0).
   - `Apartado_Neto = max(Apartado_Mensual - Comision_Mensual, 0)`.
7. Elimina `Comision_Mensual`, `PaB_PL`, `Apartado_Mensual` y `Fecha_Cartera`; conserva `Banco`. `Negociador` nulo queda como `Sin Negociador Asignado`.
8. Valida con `AsignacionSchema` (`Id_Deuda` único, `Pricing` permitido, `Banco` presente).

**Prospectos de Tradicional (`load_prospectos_tradicional`):**

- Lee `Prosp_MEC_D_Liq` (prospecto por deuda) y `Mec_Probs` (probabilidades).
- Normaliza `Id_Deuda`/`Referencia`, aplica cambios de referencia y convierte `Prob_Liq*` a numérico; los nulos se imputan a `0`.
- Hace `merge` por `Id_Deuda` y valida `ProspectosTradicionalSchema`.
- `Prospecto` debe cumplir `Trad \d`; `Id_Deuda` debe ser único.
- `Prob_Liq` total es la que usa `IA Liquidadora`; `Prob_Liq_Cred` y `Prob_Liq_Trad` quedan disponibles para futuros cálculos.

**Pipeline de Crédito (`load_pipeline_credito`):**

- Lee la hoja `Pipeline`, renombra `Fecha de Subida`/`Status`, normaliza `Referencia` y aplica cambios de referencia.
- Ordena por `Fecha_Subida` y deja el último registro por `Referencia`.
- `Rechazo_Credito = Status_Credito in ESTADOS_NO_QUIERE_CREDITO` (`NO_LE_INTERESA`).
- `No_Opta_Credito = Status_Credito in ESTADOS_NO_OPP_CREDITO` (`NO_PERFILA`, `NO_VIABLE_MEC`, `DTO_INSUFICIENTE`).

**Actualizaciones (`load_actualizacines_negos`):**

- Abre la hoja `act {año}` del año del MEC (`load_mes_operativo_liquidaciones().year`).
- Renombra `end/debt_id/inserted_at/bank_reference/Status_Act/payment_to_bank` a `Correo/Id_Deuda/Fecha_Act/Referencia/Etiqueta_Act/PaB_Actualizado`.
- Resta 5 horas a `Fecha_Act` (UTC → Bogotá), limpia `Etiqueta_Act` con `cleanText` (mayúsculas, sin tildes; los espacios se conservan), filtra correos no relevantes y hace `left join` con Headcount para obtener `Nombre`.
- `PaB_Actualizado` se extrae de `payment_to_bank`: se toma el primer número y se divide entre 100. Las filas sin valor válido se descartan para cumplir el esquema.
- Elimina duplicados por `Id_Deuda` + `Fecha_Act` conservando la **última** fila de la hoja. La misma limpieza se aplica de forma defensiva en `_deduplicar_actualizaciones` para los cálculos que reciben un DataFrame crudo.

**Vencimientos de acuerdos masivos (`load_vencimientos_acuerdos`):**

- Consulta `QUERY_VENCIMIENTO_ACTS` en bloques de 500 `debt_ids` para evitar una consulta por deuda en la calculadora masiva.
- Devuelve el DataFrame crudo de actividades del último mes, un DataFrame vacío si no hay datos, o `None` si Metabase falla. El filtro por `Correo_Act`, etiqueta `agreement` y la selección de la máxima `Fecha_Expiracion` se hace en `_construir_fechas_metabase_acuerdos`.

**MEC (`load_mes_operativo_liquidaciones`):**

- Caché de 1 hora. Toma `load_liquidaciones_mec()` (caché de 1 día) y calcula `Fecha_Liq.min().normalize().replace(day=1)`.
- Si no hay liquidaciones, todas las fechas son nulas o falla la lectura, usa `getMesOperativo()` (día 5) como fallback.

### 6.10 Centro de Control de Masivas (Mando de Operaciones)

La pestaña **🪭Mando de Operaciones** de `views/agregar_cartera.py` controla la metadata y los portafolios de las bases que **ya están cargadas** en `Bases mes actual 2024`. No reemplaza el flujo de la pestaña **🟢 Control**: esa sube registros del cruce a la Base del Mes; esta transforma registros existentes.

**Flujo:**

1. Muestra el panel general de `Cambios_Masivas` (historial y métricas) y una notificación global de las bases sin metadata completa.
2. Selectores: **Casa de Cobro** siempre específica y **Fechas de Subida** con selección múltiple. El multiselect inicia vacío y exige al menos una fecha; las fechas seleccionadas delimitan el alcance. Ya no existe la opción `Todas`: para procesar todo se seleccionan todas las fechas.
3. Si el alcance no tiene metadata completa, muestra **un solo formulario por aliado** que aplica a todas las fechas seleccionadas, con:
   - `Tipo_Contraoferta` (valores de `TIPOS_CONTRAOFERTAS`; se sugiere según el aliado).
   - `Fecha_Limite_Uso` (mínimo el día 5 del mes actual).
   - `Alias` opcional.
   El resto de la metadata se completa solo: `Id_Cruce` (UUID), `Id_Portafolio` y `PaB_Portafolio` (si la fila ya trae `PaB_Portafolio` en la columna, se conserva en la metadata).
4. Si toda la metadata ya existe, solo se muestra el botón de reprocesar portafolios. Las filas con metadata completa conservan su `Tipo_Contraoferta`, `Fecha_Limite_Uso` y `Alias`.
5. Antes de procesar, el toggle **Distribuir Portafolios** define el modo:
   - **Activado:** se ejecuta la distribución de portafolios, se consulta Metabase para `PaB_Origen`/`Referencia` y se actualiza `Id_Portafolio`/`PaB_Portafolio`.
   - **Desactivado (solo metadata):** no se consulta Metabase, no se ejecuta la distribución y no se llama `actualizar_metadata_portafolios`. Solo se aplica `completar_metadata_masivas`; `PaB_Propuesta`, `Id_Portafolio` y `PaB_Portafolio` quedan intactos. Esto se usa cuando la base se entregó con montos individuales o no maneja portafolios.
   La elección del modo forma parte de la firma del resultado: cambiarla invalida la comparación anterior.
6. **Procesar Portafolios** (o **Procesar Metadata** en modo solo metadata) no escribe en Sheets. Aplica el procesamiento y muestra la comparación de `PaB` total y el detalle por deuda cuando aplica.
7. **Subir Cambios a Google Sheets** actualiza `Metadata` y, en modo distribución, `Propuesta Pago`, `Monto Portafolio` y `Portafolio` (solo si cambió) por fila con `batch_update`. En modo solo metadata los valores de pago y portafolio no cambian. Después muestra globos, espera 2 segundos y hace rerun.
8. La subida registra una fila por cada fecha procesada en `Cambios_Masivas` (con su `Fecha_Aliado_Cambio`, `Num_Registros` y `Num_Cambiados`) y guarda los cambios locales en `local_masivas_changes`.

**Reinicio manual:** al inicio de la pestaña, el botón **🔄 Reiniciar Datos de Masivas y Cambios** limpia los caches de `load_masivas`, `load_masivas_control` y `load_cambios_masivas`, y descarta `masivas_df`, `local_masivas_changes`, `mando_resultado` y `mando_exito`. Así un ejecutivo ve de inmediato una base o un cambio recién subido sin esperar el TTL de 1 hora ni depender de **Manejo de Cache**.

**Distribución de portafolios (`modules/control_masivas.py`):**

- `GrupoCol = Masiva_ + Referencia + Casa_Cobro`. La `Fecha_Masiva` **no** forma parte de la llave: el alcance de fechas se define en la vista y llega ya filtrado, de modo que una base subida por partes en fechas distintas se distribuye como una sola base. La marca `Es_Portafolio` **no** forma parte de la llave: filas marcadas y no marcadas del mismo cliente/base se agrupan y distribuyen juntas.
- `%Pago = PaB_Origen / SUM(PaB_Origen)` dentro del grupo.
- **Regla de portafolio ya distribuido (bases por lotes):** si el grupo ya tiene `PaB_Portafolio` (columna `Monto Portafolio` o `Metadata.PaB_Portafolio`) con valor > 0, se usa el valor de la fila con `Fecha_Masiva` más reciente como total del portafolio y se redistribuye entre **todas** las deudas del grupo por `%Pago`. Esta regla tiene prioridad sobre la regla especial y JCAP, es idempotente y permite corregir un portafolio que quedó incompleto al subir la base por lotes. Si hay varios valores distintos de `PaB_Portafolio`, se usa el más reciente y se reporta una alerta.
- **Protección del modo `Monto Individual de Portafolio`:** como la Base del Mes no guarda qué modo de portafolio se usó, la regla anterior solo se aplica cuando los pagos previos del grupo son proporcionales a `PaB_Origen` (propio de `Distribuir Monto de Portafolio`) o cuando una deuda nueva trae el total del portafolio repetido. Si los pagos previos no guardan esa proporción, se asume un portafolio individual, no se redistribuye y se reporta la alerta **Portafolio Individual**. Así no se alteran pagos individuales que no deben repartirse.
- **Regla especial:** si todas las filas del grupo tienen el mismo `PaB_Propuesta` y hay más de una deuda, `PaB_Propuesta = PaB_Propuesta_Original * %Pago`. No se exige que las filas estén marcadas como portafolio; el grupo se marca automáticamente cuando aplica la regla.
- **Regla JCAP:** para `Casa_Cobro == 'JCAP'`, si al menos dos filas del grupo tienen `PaB_Propuesta <= 100` y no aplicó la regla especial, `PaB_Propuesta = SUM(PaB_Propuesta_Original del grupo) * %Pago`. Este grupo también se marca automáticamente como portafolio.
- Si algún `PaB_Propuesta` del grupo es nulo, no se aplica ninguna regla para no inventar montos. En particular, si el grupo tiene `PaB_Portafolio` pero falta el pago de alguna deuda, el portafolio no se redistribuye y se reporta la alerta **Pago Faltante**. Si falta el `PaB_Origen` para calcular `%Pago`, se reporta **PaB_Origen Faltante**.
- `Id_Portafolio` es la unión de `Id_Cruce` del grupo con `-`; `PaB_Portafolio` es la suma de `PaB_Propuesta` del grupo. La marca `Es_Portafolio` se escribe automáticamente en los grupos donde aplicó alguna regla; la metadata solo se completa para grupos con la marca en todas sus filas, tamaño > 1 y montos completos. Si el grupo ya era un portafolio y no se puede recalcular (por ejemplo, llegó una deuda nueva sin pago), se conserva su metadata y su `PaB_Portafolio` en lugar de borrarlos. La columna `Portafolio` de Sheets deja de ser un requisito manual y pasa a ser un resultado del proceso.
- La vista advierte cuando el alcance de fechas deja por fuera fechas del mismo aliado y referencia que ya tienen `PaB_Portafolio`. En ese caso el portafolio no se puede reconstruir completo y el usuario debe seleccionar también esas fechas antes de procesar.
- `PaB_Origen` y `Referencia` se consultan en Metabase (`QUERY_DEUDAS_PAB_ORIGEN`, dbId 12, `DISTINCT ON (bcrd.id) ORDER BY bcrd.id, bcrd.inserted_at DESC NULLS LAST`). Si la consulta falla o no trae una deuda, se usa `Deuda Bravo` y `Referencia` de la hoja.
- Los cambios se comparan por `Fila_Sheets`; `PaB_Portafolio` se mantiene sincronizado en la columna de la hoja (`Monto Portafolio`).

**Hoja `Cambios_Masivas` (Configs):**

| Columna | Tipo | Descripción |
|---|---|---|
| `Fecha_Cambio` | Timestamp | Momento de la subida (hora de Bogotá). |
| `Usuario` | str | Correo del usuario que ejecutó la subida. |
| `Nombre_Aliado_Cambio` | str | `Casa_Cobro` de la base procesada. |
| `Fecha_Aliado_Cambio` | Timestamp | `Fecha_Masiva` de la base procesada. |
| `Num_Registros` | int | Registros de la base incluidos en el alcance. |
| `Num_Cambiados` | int | Registros de esa base con al menos un cambio. |

**Funciones nuevas:**

- `modules/control_masivas.py`: `completar_metadata_masivas`, `distribuir_portafolios_masivas`, `distribuir_portafolios_masivas_con_alertas`, `detectar_fechas_portafolio_fuera_alcance`, `actualizar_metadata_portafolios`, `construir_cambios_masivas`, `construir_log_cambios_masivas`, `resumen_bases_sin_metadata`, `metadata_masiva_completa`.
- `data/data_loader.py`: `load_masivas_control`, `load_masivas_control_con_cambios`, `load_cambios_masivas`, `load_pab_origen_deudas`.
- `data/data_uploader.py`: `upload_masivas_control`, `upload_cambios_masivas_log`.
- `data/data_models.py`: `MasivasControlSchema`, `CambiosMasivasSchema`.

**Gotchas:**

- La hoja actual puede tener la columna `Portafolio` vacía; en ese caso no hay distribución de portafolios y solo se completa la metadata.
- El `.title()` de pandas convierte `PaB_Origen` en `Pab_Origen`; `load_pab_origen_deudas` restaura el nombre antes de usarlo.
- `Cambios_Masivas` puede estar vacía: el uploader crea los headers antes del primer `append`.
- `Monto Portafolio` vive lejos en la hoja (columna AN en la versión actual); no asumas que está junto a `Portafolio`.
- No se debe editar `Asignación de Cartera`, `Pipeline de Crédito` ni `Prospectos` desde este flujo.

---

## 7. Tests existentes

| Archivo | Qué cubre |
|---|---|
| `tests/test_calculos.py` | Limpieza y formato de números, días hábiles, aliados y tiempos de respuesta, descuentos, comparación de descuentos, distribución de montos, descuento óptimo, validación de base, normalización de bancos y bloqueo de bancos en el formulario. |
| `tests/test_reglas_solicitud.py` | Máscaras de solicitudes, aprobaciones, comités, valores bajo comité, liquidaciones, fechas límite, métricas de cumplimiento, promedios, tops de negociadores y resúmenes. Incluye la exclusión de `Vencida` y `Cancelada` de las métricas de SLA/tiempo de respuesta. |
| `tests/test_cruce_deudas.py` | Limpieza de cédula/nombre/crédito/banco, etiquetas del matcher, pagos a cuotas, estados de cruce, distribución y agrupación de portafolios, y validación de `build_pendiente_cruce_df` (incluido el cruce por nombre sin cédula). |
| `tests/test_filtros_cruce.py` | Construcción de columnas internas, filtros de Identificación Manual (Casa de Cobro, Alias, archivo, etiqueta, estado, Id_Definitivo, No Validados, búsqueda global, banco, cédula, monto y fechas) y ordenamiento ascendente/descendente. |
| `tests/test_archivos.py` | Nombres de archivos, metadata de PDFs, esquema de archivos subidos y soportes por deuda. |
| `tests/test_viabilidad.py` | Unión de PDFs y PDFs encriptados. |
| `tests/test_oportunidades.py` | Parseo de nombres de archivo/hoja de Asignación, prioridades, MEC desde `load_liquidaciones_mec` (`Fecha_Liq.min().normalize().replace(day=1)`) y fallback, alcance de Referencias (admin/líder/negociador), override por secreto, última actualización de deuda, fórmulas de Depósito Extra/ContraOferta/Liquidación Instantánea, descuento mínimo del 3% en Liquidación Instantánea Tradicional (sin aplicarlo a Crédito), Depósito Extra simulado como parte del ahorro, portafolio distribuido por `PaB_Origen`, PaB simulado mayor al Origen, umbrales, `PaB_Actualizado` con etiquetas confiables, fallback a `PaB_Origen` cuando el PaB es 0 y `ACTUALIZADO_ALIANZAS`, Acuerdos para Robo, IA Liquidadora y viabilidad del cliente. |
| `tests/test_oportunidades_masivas.py` | Selección del mejor descuento vigente de Masivas (fechas vencidas, metadata ausente, empates), metadatos y completitud de portafolios, pago de portafolios de Masivas y de Actualizaciones (valores iguales vs. distintos), deduplicación de Actualizaciones por `Id_Deuda` + `Fecha_Act` conservando la última fila, regla de bancos, cálculo por unidad de Tradicional y Crédito, Crédito por portafolio (todas las deudas con PaB Ideal), `Cr Parcial`/`Tradicional` como restricción de tipo de pago, incidencias de oportunidades, ingreso estimado y orden, redirección a la calculadora individual, filtros de la vista masiva, escape de `$` en Markdown, paginación entera y benchmark de portafolios/unidades con 10k deudas (umbral 20 s). |
| `tests/test_control_masivas.py` | Distribución de portafolios en la Base del Mes (regla de pagos iguales, regla JCAP, portafolio ya distribuido con `PaB_Portafolio`, prioridad sobre la regla especial, uso del valor más reciente y alertas, protección del modo individual no proporcional, deuda nueva con el total repetido, pago faltante e idempotencia), distribución entre fechas distintas de una base subida por partes, separación por Referencia/Casa, detección de fechas con portafolios fuera del alcance, completado y preservación de metadata (incluida la misma configuración de aliado replicada a varias fechas), `Id_Portafolio`/`PaB_Portafolio`, construcción de cambios y log por base. |
| `tests/test_cache_components.py` | Helper de reinicio de caches: limpia todas las funciones y llaves de `session_state` recibidas, ignora llaves inexistentes y tolera listas vacías. |
| `tests/test_permisos_especiales.py` | Normalización de `Cargo_Interno` a roles permitidos, descarte de valores inválidos/vacíos, construcción del mapa de roles, tolerancia de la hoja `Usuarios` a columnas adicionales o a la ausencia de `Permisos`, prioridad del rol especial sobre el headcount, fallback al rol del headcount y carga del nombre de Google cuando el usuario no está en el headcount. |

### Convenciones para nuevos tests

- Usa `unittest` y `unittest.mock`; no requiere dependencias nuevas.
- No uses `st.session_state` real ni llamadas a Google/Metabase. Pasa DataFrames y diccionarios en memoria.
- Para funciones que llaman a Streamlit (`st.warning`, `st.stop`, `st.progress`), mockea la función o prueba la lógica pura extraída. Para `modules/oportunidades.py` puedes reemplazar `modules.oportunidades.st` por un mock con `session_state` y `secrets`.
- Para la Asignación de Cartera, mockea `load_asignacion_cartera` y `load_headcount_negociacion`; no descargues el Excel en tests.
- Usa fechas de 2026 en los tests de días hábiles: el módulo `utils/helpers_general.py` construye los festivos de Colombia para el año actual al importarse. Si cambias el año de ejecución, revisa esos tests.
- No fijes valores frágiles de punto flotante; usa `assertAlmostEqual`.
- Si agregas una regla de negocio, agrega el caso feliz y al menos un borde (vacío, cero, nulo, duplicado o inconsistente).
- Si implementas una oportunidad en `modules/oportunidades.py`, agrega tests de la fórmula y de los umbrales antes de conectarla a la UI.

---

## 8. Convenciones de código

- **PEP 8** y nombres descriptivos en español para lógica de negocio.
- Los comentarios suelen marcar pasos: `# Paso 1: ...`, `# Paso 2: ...`. Mantén ese estilo.
- Usa `cleanNumber` para montos que vienen de Sheets/formularios y `formatNumber` para mostrarlos.
- Normaliza IDs con `.replace('.0', '').strip()` antes de compararlos.
- Maneja fechas en `America/Bogota` y quita la zona horaria antes de comparar con datos de Sheets (`tz_localize(None)`).
- No mezcles `datetime` con zona y sin zona.
- Los esquemas de datos viven en `data/data_models.py`. Si agregas columnas, actualiza el esquema y los loaders/uploaders.
- Los loaders nuevos (`load_asignacion_cartera`, `load_prospectos_tradicional`, `load_pipeline_credito`, `load_mes_operativo_liquidaciones`) están cacheados con `st.cache_data`. No los llames desde funciones puras; recibe el DataFrame por parámetro.
- La Asignación de Cartera, el Pipeline de Crédito y los Prospectos son **solo lectura**. No los edites desde la app.
- El feedback se escribe únicamente con `send_feedback` en la hoja `Feedback` del spreadsheet de Configs. No inventes otra hoja ni cambies los campos sin actualizar el esquema/documentación.
- Para leer Excel de Asignación se usa `engine='calamine'`; si cambias a `openpyxl`, actualiza `requirements.txt` y el loader.
- `AsignacionSchema` conserva `Banco`; `Fecha_Cartera` se calcula temporalmente para priorizar y se descarta antes de validar.
- No llames servicios de Google desde funciones de cálculo puras. Recibe los datos por parámetro.
- No cambies IDs de hojas, nombres de columnas o constantes de estados sin revisar todas las vistas y tests.
- No expongas secretos, tokens, IDs de hojas ni contenido de `.streamlit/secrets.toml`.

### Dónde poner una nueva función

- Cálculo puro y reutilizable → `modules/gest_sols.py`, `modules/forms.py` o `utils/helpers_general.py`.
- Cálculo de oportunidades → `modules/oportunidades.py` (mantén la especificación en `docs/OPORTUNIDADES_DETALLADO.md`).
- Regla de aliados / normalización → `modules/classes.py`, `modules/bank_normalizer.py`.
- Cruce de cartera → `modules/id_aut_deud/`.
- Lectura/escritura de datos → `data/data_loader.py` / `data/data_uploader.py`.
- Componente visual → `ui/`. La calculadora individual vive en `ui/calculadora_components.py` y la masiva en `ui/calculadora_masiva_components.py`.
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
10. **`LIMITE_MEC` está en migración.** El día 5 sigue como fallback de `getMesOperativo()`, pero la fuente principal del MEC es `load_mes_operativo_liquidaciones()` (`Fecha_Liq.min().normalize().replace(day=1)`). No borres `LIMITE_MEC` sin revisar `getMesOperativo`, `load_solicitudes_mec` y los reportes.
11. **Los soportes de pago no liquidan por sí solos.** La fuente de `Estado_Liquidacion` es la hoja externa `Liquidaciones`; los archivos en Drive/`Archivos_Subidos` son evidencia.
12. **`Addendum` no es una solicitud separada.** Se adjunta a `Metadata_Solicitud["Addendums"]` y se incluye en el acuerdo/respuesta. `ADDENDUM` en el cruce solo indica que el cliente coincide pero la deuda no se pudo acotar.
13. **`Brindan Máx. Descuento` no bloquea.** La app advierte; el bloqueo duro no está implementado. Si negocio quiere bloquear, hay que cambiar formulario y tests.
14. **`Pago_Total_Obligatorio` se fuerza en `Bajo Comité`.** La UI lo pone en `True` y deshabilita el toggle; no es una elección libre en ese estado.
15. **Bloqueos duros del formulario.** El envío se detiene si hay bancos no habilitados o si se excede la contrapropuesta máxima relativa. `Brindan Máx. Descuento` sigue siendo solo una advertencia.
16. **Conteo de liquidaciones en reportes.** Las fórmulas oficiales se definen sobre solicitudes exitosas, pero `obtener_resumen_liquidaciones` y `obtener_tops_negociadores` todavía pueden contar liquidaciones de solicitudes No Exitosas o Validadas por Fuera. Revisa el filtro antes de usar esos números en decisiones.
17. **La calculadora individual y la masiva están implementadas.** La individual usa PaB simulado y Actualizaciones; la masiva usa Masivas con el toggle activo y Actualizaciones con el toggle inactivo, calcula por portafolio/unidad de análisis y no acepta PaB simulado. El input de **Portafolio Total** de la individual se aplica con un callback `on_change` y distribuye por `PaB_Origen`; si el total supera el DUM, los PaB simulados quedan por encima de su `PaB_Origen` y el descuento se muestra como 0%. La masiva pagina las tarjetas y normaliza la página a entero antes de hacer `iloc`.
18. **`PaB_Actualizado` viene de `payment_to_bank` en centavos.** El loader toma el primer número, lo divide entre 100 y descarta filas sin valor válido; el resultado queda en COP. Para `ACTUALIZADO_ALIANZAS` se cruza el último descuento en base con la última solicitud exitosa y prevalece la fuente con fecha más reciente. Si la actualización confiable deja el PaB en 0, `obtener_pab_actualizado_deuda` devuelve `PaB_Origen` para no interpretar un dato faltante como descuento del 100%.
19. **`AsignacionSchema` es estricto con `Pricing` y `Id_Deuda`.** Solo acepta `Pricing` 0.15, 0.20 o 0.25; si el Excel trae otro valor (o 15/20/25 sin dividir entre 100), la validación falla. `Id_Deuda` debe ser único. Conserva `Banco`; `Fecha_Cartera` es temporal y se descarta antes de validar.
20. **Formato de la Asignación de Cartera.** El archivo debe terminar en `-MesAA.xlsx` (mes de 3 letras + año de 2 dígitos) y la hoja debe llamarse `Mes AAAA` (por ejemplo, `Octubre 2025`). Si el nombre no cumple, `obtener_prioridad_archivo`/`obtener_prioridad_hoja` devuelven prioridad 0 y el loader puede caer a un archivo anterior. El MEC ya no depende de la Asignación.
21. **Descarga de Google Drive.** `GoogleDriveService.obtain_file` usa `MediaIoBaseDownload` y devuelve un `BytesIO` con el puntero al inicio. Si la descarga falla, `_obtener_df_asignacion` devuelve un DataFrame vacío y la calculadora muestra advertencia; revisa el archivo/carpeta antes de asumir que no hay asignación.
22. **Prospectos de Tradicional.** Se unen `Prosp_MEC_D_Liq` y `Mec_Probs` por `Id_Deuda` con `how='left'`; las probabilidades faltantes se imputan a 0. `Prospecto` debe cumplir `Trad \d` y `Id_Deuda` debe ser único. `IA Liquidadora` usa `Prob_Liq` total, no `Prob_Liq_Cred` ni `Prob_Liq_Trad`.
23. **Zona horaria de Actualizaciones.** `load_actualizacines_negos` resta 5 horas a `Fecha_Act` para pasar de UTC a hora local de Bogotá. No vuelvas a restar 5 horas ni mezcles `Fecha_Act` con timestamps con zona.
24. **MEC: dos rutas.** `getMesOperativo()` (día 5) sigue existiendo como fallback. `load_mes_operativo_liquidaciones()` (caché 1 hora) usa `load_liquidaciones_mec()` y calcula `Fecha_Liq.min().normalize().replace(day=1)`; si no hay liquidaciones válidas, cae al fallback. No borres `LIMITE_MEC` sin revisar tests y reportes.
25. **Última actualización de deuda.** `obtener_ultima_actualizacion_deuda` acepta `fecha_min=None` (muestra la última disponible) y usa la columna `Nombre`; no existe `Origen_Act` en `ActualizacionesSchema`.
26. **Ruta de la documentación.** `views/calculadora_opps.py` resuelve `docs/OPORTUNIDADES.md` desde `__file__`; si mueves la carpeta `docs/`, actualiza esa ruta.
27. **`PERMITIR_CALCULO_NO_ASIGNADO` es un override de pruebas.** Si está activo, cualquier rol ve todas las Referencias. No lo dejes activo en producción.
28. **El feedback no se lee desde la app.** Se escribe en la hoja `Feedback` de Configs con `Fecha`, `Usuario`, `Positivo`, `Origen`, `Comentario` y `Configuraciones` (JSON). Si cambias el esquema, actualiza `send_feedback` y la documentación.
29. **El App comparte el cliente OAuth con el MCP de Google Workspace.** Si el MCP ya concedió scopes adicionales, Google devuelve el conjunto completo en el token y `oauthlib` lanza `Warning: Scope has changed...`. `core/auth_scopes.py` configura `OAUTHLIB_RELAX_TOKEN_SCOPE=1` y `core/auth.py` valida que los scopes propios del App estén presentes. No quites esa configuración ni cambies `SCOPES` sin probar el login con la skill activa. La solución definitiva (cliente/proyecto OAuth separado) requiere acceso a GCP; hoy no está disponible.
30. **La hoja `Usuarios` cambió de estructura.** Hoy contiene `Correo` y `Cargo_Interno`; la columna `Permisos` es opcional/legada. `load_permisos_especiales()` normaliza el rol (mayúsculas/minúsculas y espacios) y descarta valores fuera de `PERMITTED_USERS`; `load_special_user_permissions()` devuelve `{}` si no existe `Permisos` y `User.build_permits()` cae a los permisos por defecto del rol. Los dos loaders proyectan solo sus columnas antes de validar, así que agregar columnas nuevas a la hoja no rompe el esquema estricto. Si agregas una columna obligatoria, actualiza `UserPermissionsSchema` y los tests.
31. **Actualizaciones duplicadas.** `load_actualizacines_negos` y `_deduplicar_actualizaciones` eliminan filas con el mismo `Id_Deuda` + `Fecha_Act` conservando la última fila de la hoja. Sin esta limpieza, dos actualizaciones del mismo instante con distinto `PaB_Actualizado` dejan el resultado a merced del orden de `sort_values`/`drop_duplicates`. No elimines esa deduplicación sin agregar una prueba que fije la fila ganadora.
32. **Rendimiento del cálculo masivo.** La identificación de portafolios/unidades con Actualizaciones está vectorizada por referencia, etiqueta y ventana; no vuelvas a introducir bucles `for referencia, grupo in ...` con `.loc` por grupo ni escaneos de Masivas/Solicitudes por cada actualización. El test `TestRendimientoPortafoliosActualizaciones` (10k deudas, 4k actualizaciones, 300 solicitudes) falla si el pipeline supera 20 s; antes de la optimización tardaba ~64 s.
33. **Bases por lotes y `PaB_Portafolio`.** Cuando un portafolio ya fue distribuido, `PaB_Propuesta` ya no es el pago total sino la parte de cada deuda. Para poder redistribuirlo al llegar un lote nuevo, `distribuir_portafolios_masivas_con_alertas` usa el `PaB_Portafolio` más reciente del grupo como total y lo reparte entre todas las deudas por `PaB_Origen`. No cambies esa prioridad por la regla de pagos iguales: los pagos ya distribuidos dejarían de coincidir. La regla solo se aplica si los pagos previos son proporcionales a `PaB_Origen` o si una deuda nueva trae el total repetido; de lo contrario se asume `Monto Individual de Portafolio` y se reporta **Portafolio Individual**. Si hay varias fechas con portafolio y el alcance no las incluye todas, la vista solo advierte; el portafolio no se puede reconstruir completo.
34. **Modo solo metadata del Mando.** El toggle **Distribuir Portafolios** desactivado debe limitarse a `completar_metadata_masivas` y `construir_cambios_masivas`. No agregues allí la consulta a Metabase, `distribuir_portafolios_masivas_con_alertas` ni `actualizar_metadata_portafolios`: el objetivo es no mover `PaB_Propuesta`, `Id_Portafolio` ni `PaB_Portafolio`. La elección del modo forma parte de `firma_actual` para invalidar comparaciones viejas.

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
- [ ] ¿Si cambiaste una fórmula de oportunidad, actualizaste `docs/OPORTUNIDADES_DETALLADO.md`, `docs/OPORTUNIDADES.md` y `AGENTS.md`?
- [ ] ¿Agregaste tests de la fórmula, los umbrales y los bordes (sin deudas, deuda liquidada, sin PaB Ideal, `Apartado_Neto = 0`, sin actualizaciones) antes de conectar una oportunidad a la UI?
- [ ] ¿Si tocaste la calculadora masiva, probaste el toggle `Solo de Masivas`, la selección del mejor descuento vigente, la fuente de Actualizaciones con toggle inactivo, los portafolios de Masivas/Actualizaciones/Bancos, `Cr Parcial`/`Tradicional`, Crédito por unidad solo si todas las deudas tienen PaB Ideal, la combinación de Tipo de Análisis con Oportunidad, el orden por ingreso y la paginación entera?
- [ ] ¿Verificaste que la calculadora masiva use Masivas con el toggle activo y Actualizaciones con el toggle inactivo (nunca PaB simulado) y que calcule por portafolio/unidad?
- [ ] ¿Verificaste que la Asignación de Cartera tenga `Banco`, `Pricing` válido e `Id_Deuda` único?
- [ ] ¿Verificaste que `load_liquidaciones_mec()` tenga `Fecha_Liq` válida para calcular el MEC?
- [ ] ¿Verificaste que `PaB_Actualizado` se extraiga correctamente de `payment_to_bank` (centavos → COP) antes de usarlo en oportunidades?
- [ ] ¿Evitaste escribir en Asignación de Cartera, Pipeline de Crédito o Prospectos?
- [ ] ¿Si cambió el formato de archivo/hoja de Asignación, actualizaste `_parse_mes_anio_desde_nombre_archivo`, `obtener_prioridad_hoja` y sus tests?
- [ ] ¿Si tocaste la hoja `Usuarios` o `get_user_role`, probaste el override de rol, el fallback al headcount, los valores inválidos/vacíos y la ausencia de la columna `Permisos`?
