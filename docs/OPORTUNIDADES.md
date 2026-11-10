# **Cálculo de Oportunidades**
Las oportunidades son cálculos que se realizan de forma interna con el fin de mostrar con facilidad los clientes que son más liquidables.

Esta información se saca teniendo en cuenta que las etiquetas que se consideran con un descuento correcto son: **CAMBIO DE PAB, ACUERDO, DEPOSITO y ACTUALIZADO_ALIANZAS (Masivas)**. Cualquier otra etiqueta se toma como descuento 0% (esto solo aplica para el cálculo masivo, para cálculo individual se asume que las deudas escogidas son el portafolio).

Para tener en cuenta los portafolios, se va a tener en cuenta que las actualizaciones posteriores sean 45s o menos entre sí (ventana configurable con `VENTANA_PORTAFOLIO_SEGUNDOS`). En caso de no haber actualizaciones se toma de forma individual exceptuando los bancos **Banco de Occidente, Banco Popular, Itaú y BBVA Colombia**.

Para esto se cuenta con las siguientes oportunidades que establecen diferentes formas de dar a entender que una o más deudas son liquidables:
> **Depósito Extra**: En caso que un cliente requiera *3 Apartados Netos o menos, o 1M COP o menos* se considera como una oportunidad para pedir depósito extra. Si `Apartado_Neto` es 0, solo aplica la condición de 1M COP.

> **ContraOferta Viable**: Teniendo en cuenta el ahorro del cliente o el pab ideal de credito se calcula el *descuento necesario para pagar la(s) deuda(s)*. Esta oportunidad tiene su propio apartado para ver como ajustar los descuentos y el ingreso que se puede generar. **NO APLICAN CLIENTES YA LIQUIDABLES**. Para varias deudas, el `Descuento Esperado` se pondera por `PaB_Origen`.

> **Acuerdos para Robo**: Acuerdos Vencidos que no cuenten con una gestión posterior con el cliente. La unión con Alianzas/Metabase es por deuda (`Id_Deuda`).

> **Liquidación Instantánea**: Clientes que con el Descuento Actual pasen el PAB Ideal de Crédito o cuenten con el dinero suficiente para pagar la/las deudas.

> **IA Liquidadora**: El Modelo interno de IA para la liquidación de clientes (1 de cada 3 se paga) prioriza los clientes que se tengan en cartera

> **Estado de implementación:** la Calculadora Individual por Referencia ya implementa estas oportunidades y permite simular Ahorro, Por Cobrar, Depósito Extra y el PaB de cada deuda. El PaB simulado reemplaza el `PaB_Actualizado` en Depósito Extra, Descuento Actual (Liquidación Instantánea) y la comparación de la ContraOferta. La Calculadora Masiva sigue pendiente.
