# **Cálculo de Oportunidades (Detallado)**
Este archivo es una extensión a "Oportunidades.md" que esta más enfocado en definir el cálculo exacto de las oportunidades con el fin de dejar una trazabilidad exacta acerca de como se calculan las oportunidades.

Para esto, se va a detallar paso a paso el tipo de oportunidades, los datos que usa y como calcularlos, de modo que sea entendible a futuro y no se convierta en una caja negra.

Particularmente para Crédito, es importante que el cliente sea optimo (esto según el `Pipeline de Crédito`), ya que en caso de que no, no tiene sentido realizar el cálculo por crédito de un cliente que no aplica a Crédito. SIEMPRE HAY QUE REALIZAR ESTA VERIFICACIÓN ANTES DE CALCULAR OPORTUNIDADES POR CRÉDITO.

De la misma forma, no es posible calcular oportunidades para deudas ya liquidadas, ya que las oportunidades se calculan con el fin de generar una liquidación.

## **Depósito Extra**
Un depósito extra hace referencia a una solicitud al cliente de conseguir un dinero adicional con el fin de liquidar una o más deudas. Estos depósitos se suelen medir en `Apartados Netos` del cliente con el fin de tener una medida estándar entre los 

Dado que las liquidaciones pueden ser realizadas por crédito o por tradicional, sus cálculos de depósito extra son diferentes. Adicionalmente se consideran 20k adicionales al depósito por restricciones de donde se guarda el ahorro.

Si la diferencia es menor a 0, NO ES OPORTUNIDAD DE DEPÓSITO EXTRA, dado que no requiere un depósito extra en sí. En estos casos se vuelve una `Oportunidad de Liquidación Instantánea`.

### **Cálculo para Crédito**:
$$Depósito \: Extra = SUM(PaB\_Ideal) + 20k - SUM(PaB\_Actualizado)$$
Esto define la diferencia entre el cupo que se tiene aprobado de crédito y el descuento que se ha logrado.

### **Cálculo para Tradicional**:
$$Depósito \: Extra = SUM(PaB\_Actualizado) + max((SUM(PaB\_Origen) - SUM(PaB\_Actualizado)) * Pricing * 1.19,0) + 20k - (Ahorro - Por\_Cobrar)$$
Es la diferencia entre el pago total a realizar actualmente (Pago por las Deudas y Comisión) y el ahorro con el que cuenta el cliente (agregando lo que debe a la compañia).

### **Determinación de Oportundiad**
Una vez establecidos los cálculos la regla de que sea oportunidad consiste en que se cumpla alguna de estas condiciones:
- $\frac{Deposito\_Extra}{Apartado\_Neto} \leq 3$
- $Deposito\_Extra \leq 1,000,000 COP$

## **ContraOferta Viable**
Una ContraOferta viable hace referencia a pedir un monto por todas las deudas de modo que se cumpla el cupo de crédito o que el cliente con el ahorro pueda realizar el pago por las deudas y la comisión.

Aquí también se diferencia entre crédito y tradicional, y se mantiene que si el descuento es menor al actual NO SE CONSIDERA UNA OPORTUNIDAD DE CONTRAOFERTA, sino que se vuelve una `Oportunidad de Liquidación Instantánea`.

### **Cálculo para Crédito**
$$ContraOferta \: Viable = 1 - \frac{SUM(Pab\_Ideal) + 20k}{SUM(PaB\_Origen)}$$
Es simplemente calcular el descuento que se otorga por el cupo total del crédito (agregando los 20k restrictivos).

### **Cálculo para Tradicional**
$$ContraOferta \: Viable = 1 - \frac{Ahorro - Por\_Cobrar - SUM(PaB\_Origen) - 20k}{SUM(PaB\_Origen) * (Pricing * 1.19 - 1)}$$
Esta formula sale de despejar el descuento de acuerdo al pago que se realiza sumado a la comisión y los 20k restrictivos.

### **Determinación de Oportundiad**
Una vez establecidos los cálculos la regla de que sea oportunidad consiste en que se cumplan todas estas condiciones:
- $ContraOferta \: Viable > Descuento \:Actual$
- $ContraOferta \: Viable \leq 0.95$
- $ContraOferta \: Viable \leq Descuento\_Esperado + 0.2$
Teniendo en cuenta que el `Descuento Actual` se calcula según el `PaB Actualizado`

## **Liquidación Instantánea**
La Liquidación Instantánea hace referencia a que un cliente ya cuenta con un descuento actual suficiente para que entre dentro del cupo de crédito (Si Aplica) y/o pueda realizar el pago + comisión con el ahorro que tiene.

Para aprovechar los cálculos que se realizan de las otras oportunidades (mas exactamente de la ContraOferta Viable), con base en esos cálculos se define la liquidación instantánea.

La definición es:
- $Descuento \: Actual \leq ContraOferta \: Viable$
- $Descuento \: Actual \neq 0$
Con que se cumplan estas 2 condiciones (con descuento y menor al necesario) ya se considera una oportunidad de liquidación instantánea.

## **Acuerdo para Robo**
La Oportunidad de Acuerdo para Robo consiste en acuerdos de pago que ya vencieron su fecha de pago y aún no han sido liquidados. Esto solo aplica para acuerdos de pago del MEC, donde en el MEC se tenga una actualización con Etiqueta **ACUERDO**.

Para esto se requiere la fecha de vencimiento del acuerdo, que puede ser obtenida en 2 lugares:
- **Acuerdo de Alianzas**: Acuerdo solicitado durante el MEC en alianzas que tiene respuesta exitosa. La fecha de vencimiento es la columna `Fecha_Limite_Pago` del DF de Solicitudes.
- **Acuerdo Externo**: Acuerdo conseguido por fuera. La fecha de vencimiento se consigue desde metabase.

El flujo para conseguir la fecha es:
1. Verificar si existe en Alianzas
2. Si no existe, verificar fecha en Meta
    - Si no hay fecha en Meta pero el resto de los datos se obtiene, se considera para robo
    - Si ocurrió un error al traer los datos de meta mejor dejar como que no es oportunidad para evitar problemas a futuro.

## **IA Liquidadora**
La oportunidad de IA Liquidadora es única en su categoría ya que no requiere ningún cálculo. Esto dado que proviene de los `Prospectos de Tradicional`, que son el resultado de un modelo de probabilidad de liquidación.

Ahora, si bien existe la categoría de prospecto de liquidación, se considera como oportunidad de liquidación si cuenta con una probabilidad >= 50%. Simplemente se dá mas impulso a aquellos que cuentan con categoría.