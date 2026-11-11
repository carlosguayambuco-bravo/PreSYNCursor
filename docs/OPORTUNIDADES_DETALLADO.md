# **Cálculo de Oportunidades (Detallado)**
Este archivo es una extensión a "Oportunidades.md" que esta más enfocado en definir el cálculo exacto de las oportunidades con el fin de dejar una trazabilidad exacta acerca de como se calculan las oportunidades.

Para esto, se va a detallar paso a paso el tipo de oportunidades, los datos que usa y como calcularlos, de modo que sea entendible a futuro y no se convierta en una caja negra.

Particularmente para Crédito, es importante que el cliente sea optimo (esto según el `Pipeline de Crédito`), ya que en caso de que no, no tiene sentido realizar el cálculo por crédito de un cliente que no aplica a Crédito. SIEMPRE HAY QUE REALIZAR ESTA VERIFICACIÓN ANTES DE CALCULAR OPORTUNIDADES POR CRÉDITO.

De la misma forma, no es posible calcular oportunidades para deudas ya liquidadas, ya que las oportunidades se calculan con el fin de generar una liquidación.

> **Nota de implementación:** `PaB_Actualizado` ya existe en `ActualizacionesSchema` y se carga desde la columna `payment_to_bank` de la hoja de Actualizaciones. El loader toma el primer número de `payment_to_bank` y lo divide entre 100: la fuente viene en **centavos** y el resultado queda en **COP**. Las fórmulas de este documento ya están implementadas en `modules/oportunidades.py` y cubiertas por `tests/test_oportunidades.py`.

> **Nota de la calculadora individual:** los inputs editables de Ahorro, Por Cobrar, Depósito Extra y PaB por deuda se usan para simular el escenario. Las oportunidades se recalculan con esos valores. El **Depósito Extra simulado hace parte del ahorro disponible**: se suma al Ahorro/cupo para recalcular la ContraOferta y la viabilidad, y se resta del depósito necesario en Tradicional y Crédito. El PaB simulado de cada deuda reemplaza el `PaB_Actualizado` oficial para **todas las deudas seleccionadas** (Depósito Extra, Descuento Actual, Liquidación Instantánea y la comparación de la ContraOferta) y puede superar el `PaB_Origen` si se distribuye un portafolio mayor al DUM. Las deudas seleccionadas se asumen como el portafolio analizado.

## **Descuento Actual y `PaB_Actualizado`**
El `Descuento Actual` se calcula como:

$$Descuento \: Actual = 1 - \frac{SUM(PaB\_Actualizado)}{SUM(PaB\_Origen)}$$

Para obtener `PaB_Actualizado`:
1. Se toma la actualización más reciente de la deuda.
2. Solo se confía en las etiquetas **CAMBIO DE PAB**, **ACUERDO**, **DEPOSITO** y **ACTUALIZADO_ALIANZAS**. Si la actualización más reciente tiene otra etiqueta, se usa `PaB_Origen` (Descuento Actual = 0). Si la actualización confiable deja el PaB en 0, también se usa `PaB_Origen`: un pago en 0 se interpreta como dato faltante.
3. Para **ACTUALIZADO_ALIANZAS** se cruza el último descuento en base (masivas) con la última solicitud exitosa. Si ambas fuentes tienen fecha, prevalece la más reciente; si no hay fechas comparables, se usa el valor de la fila de actualización.

> **En la calculadora individual:** el input de PaB de cada deuda inicia con el `PaB_Actualizado` (descuento actual). Si no hay actualización confiable o el PaB confiable viene en 0, inicia con `PaB_Origen` (0% de descuento), nunca con el PaB Ideal. Cuando el usuario edita el PaB, ese valor simulado reemplaza el `PaB_Actualizado` oficial para todas las deudas seleccionadas en los cálculos de oportunidades. El input de **Portafolio Total** es un texto que se limpia y formatea como los demás inputs; se recalcula cuando cambia la selección de deudas y distribuye automáticamente el monto entre ellas por `PaB_Origen`. Si el total supera el DUM, los PaB simulados pueden quedar por encima de su `PaB_Origen`.

## **Depósito Extra**
Un depósito extra hace referencia a una solicitud al cliente de conseguir un dinero adicional con el fin de liquidar una o más deudas. Estos depósitos se suelen medir en `Apartados Netos` del cliente con el fin de tener una medida estándar entre los 

Dado que las liquidaciones pueden ser realizadas por crédito o por tradicional, sus cálculos de depósito extra son diferentes. Adicionalmente se consideran 20k adicionales al depósito por restricciones de donde se guarda el ahorro.

Si la diferencia es menor a 0, NO ES OPORTUNIDAD DE DEPÓSITO EXTRA, dado que no requiere un depósito extra en sí. En estos casos se vuelve una `Oportunidad de Liquidación Instantánea`.

### **Cálculo para Crédito**:
$$Depósito \: Extra = SUM(PaB\_Actualizado) + 20k - SUM(PaB\_Ideal) - Depósito\_Extra$$
El PaB Ideal es el cupo de crédito aprobado para la deuda y el cupo total es la suma de todas las deudas analizadas. Si el pago actual (`PaB_Actualizado`) supera ese cupo, el cliente debe cubrir la diferencia con un depósito extra para que el crédito quede aprobado. Si la diferencia es negativa, el cupo de crédito cubre el pago y no se requiere depósito extra. El Depósito Extra simulado en la calculadora reduce la diferencia porque hace parte de los recursos disponibles.

### **Cálculo para Tradicional**:
$$Depósito \: Extra = SUM(PaB\_Actualizado) + max((SUM(PaB\_Origen) - SUM(PaB\_Actualizado)) * Pricing * 1.19,0) + 20k - (Ahorro + Depósito\_Extra - Por\_Cobrar)$$
Es la diferencia entre el pago total a realizar actualmente (Pago por las Deudas y Comisión) y el ahorro con el que cuenta el cliente (agregando lo que debe a la compañia). El Depósito Extra simulado se suma al Ahorro porque representa el ahorro nuevo que se proyecta a futuro.

### **Determinación de Oportundiad**
Una vez establecidos los cálculos la regla de que sea oportunidad consiste en que se cumpla alguna de estas condiciones:
- $\frac{Deposito\_Extra}{Apartado\_Neto} \leq 3$
- $Deposito\_Extra \leq 1,000,000 COP$
En caso de que el Apartado_Neto sea 0, solo aplica la segunda condición, ya que implica que no hay dinero extra a futuro con el cuál se pueda contar.

> **Agregación de `Apartado_Neto`:** es un dato del cliente que se repite por deuda en la Asignación. Para no sobrecontarlo, se toma un único valor del conjunto (el máximo de las filas seleccionadas), no la suma.

## **ContraOferta Viable**
Una ContraOferta viable hace referencia a pedir un monto por todas las deudas de modo que se cumpla el cupo de crédito o que el cliente con el ahorro pueda realizar el pago por las deudas y la comisión.

Aquí también se diferencia entre crédito y tradicional, y se mantiene que si el descuento es menor al actual NO SE CONSIDERA UNA OPORTUNIDAD DE CONTRAOFERTA, sino que se vuelve una `Oportunidad de Liquidación Instantánea`.

### **Cálculo para Crédito**
$$ContraOferta \: Viable = 1 - \frac{SUM(Pab\_Ideal) + 20k + Depósito\_Extra}{SUM(PaB\_Origen)}$$
Es simplemente calcular el descuento que se otorga por el cupo total del crédito (agregando los 20k restrictivos y el Depósito Extra simulado).

### **Cálculo para Tradicional**
$$ContraOferta \: Viable = \frac{Ahorro + Depósito\_Extra - Por\_Cobrar - SUM(PaB\_Origen) - 20k}{SUM(PaB\_Origen) * (Pricing * 1.19 - 1)}$$
Esta formula sale de despejar el descuento de acuerdo al pago que se realiza sumado a la comisión y los 20k restrictivos.

### **Determinación de Oportundiad**
Una vez establecidos los cálculos la regla de que sea oportunidad consiste en que se cumplan todas estas condiciones:
- $ContraOferta \: Viable > Descuento \:Actual$
- $ContraOferta \: Viable \leq 0.95$
- $ContraOferta \: Viable \leq Descuento\_Esperado + 0.2$
Teniendo en cuenta que el `Descuento Actual` se calcula según el `PaB Actualizado`. Para varias deudas, `Descuento_Esperado` se pondera por `PaB_Origen`: `SUM(Descuento_Esperado_i * PaB_Origen_i) / SUM(PaB_Origen_i)`.

> **En la calculadora individual:** la comparación `ContraOferta > Descuento Actual` usa el descuento simulado con los inputs de PaB. Así, si el usuario ya simuló un mejor descuento que el necesario, la ContraOferta deja de marcarse y pasa a Liquidación Instantánea. La fórmula de la ContraOferta no cambia porque no depende del PaB actual.

## **Liquidación Instantánea**
La Liquidación Instantánea hace referencia a que un cliente ya cuenta con un descuento actual suficiente para que entre dentro del cupo de crédito (Si Aplica) y/o pueda realizar el pago + comisión con el ahorro que tiene.

Para aprovechar los cálculos que se realizan de las otras oportunidades (mas exactamente de la ContraOferta Viable), con base en esos cálculos se define la liquidación instantánea.

La definición es:
- $Descuento \: Actual \geq ContraOferta \: Viable$
- $Descuento \: Actual \neq 0$
Con que se cumplan estas 2 condiciones (con descuento y con un descuento actual igual o mejor que el necesario) ya se considera una oportunidad de liquidación instantánea. También aplica cuando el Depósito Extra calculado es menor a 0 (no se requiere depósito). El Depósito Extra calculado ya viene neto del Depósito Extra simulado en la calculadora.

> **Corrección de la fórmula:** la versión anterior de este documento decía `Descuento Actual <= ContraOferta Viable`. La condición correcta es `>=`: un descuento actual mayor significa que el pago es menor y, por tanto, ya cabe en el cupo de crédito o en el ahorro.

## **Acuerdo para Robo**
La Oportunidad de Acuerdo para Robo consiste en acuerdos de pago que ya vencieron su fecha de pago, no han sido liquidados y no tienen una gestión posterior. Esto solo aplica para acuerdos de pago del MEC, donde en el MEC se tenga una actualización con Etiqueta **ACUERDO**.

Se considera que **no hay gestión posterior** cuando no existe ninguna actualización de la deuda con `Fecha_Act` posterior a la fila que registró el **ACUERDO**. Si existe cualquier actualización posterior (llamada, pago, cambio de PAB, etc.), la deuda deja de ser oportunidad de robo.

Para esto se requiere la fecha de vencimiento del acuerdo, que puede ser obtenida en 2 lugares:
- **Acuerdo de Alianzas**: Acuerdo solicitado durante el MEC en alianzas que tiene respuesta exitosa. La fecha de vencimiento es la columna `Fecha_Limite_Pago` del DF de Solicitudes.
- **Acuerdo Externo**: Acuerdo conseguido por fuera. La fecha de vencimiento se consigue desde metabase.

El flujo para conseguir la fecha es:
1. Verificar si existe en Alianzas. Si existe y está vencido, es oportunidad; si existe y está vigente, no se consulta Metabase.
2. Si no existe, verificar fecha en Meta
    - Si no hay fecha en Meta pero el resto de los datos se obtiene, se considera para robo (se reporta como "Sin fecha")
    - Si ocurrió un error al traer los datos de meta, no se considera oportunidad para evitar problemas a futuro.

La unión con Alianzas y Metabase se hace **por deuda** (`Id_Deuda`), no por referencia, porque no todas las deudas del cliente tienen un acuerdo de pago en curso.

## **IA Liquidadora**
La oportunidad de IA Liquidadora es única en su categoría ya que no requiere ningún cálculo. Esto dado que proviene de los `Prospectos de Tradicional`, que son el resultado de un modelo de probabilidad de liquidación.

Ahora, si bien existe la categoría de prospecto de liquidación, se considera como oportunidad de liquidación si cuenta con una probabilidad >= 50%. Simplemente se dá mas impulso a aquellos que cuentan con categoría.

Para varias deudas seleccionadas, basta con que **al menos una** tenga `Prob_Liq >= 0.5` para que la Referencia tenga la oportunidad. El detalle muestra las deudas que cumplen y su probabilidad.
