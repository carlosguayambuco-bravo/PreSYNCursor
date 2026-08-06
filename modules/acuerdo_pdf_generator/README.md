# Generador de acuerdos de pago

La función pública no depende de Streamlit y devuelve los bytes listos para
`st.download_button`:

```python
from agreement_pdf import generate_payment_agreement_pdf

pdf_bytes = generate_payment_agreement_pdf(fila, font="Vera", orientation="horizontal")
st.download_button("Descargar acuerdo", pdf_bytes, "acuerdo_pago.pdf", "application/pdf")
```

La Serie debe contener `Referencia`, `Cedula`, `Fecha_Limite_Pago`,
`Casa_Cobro`, `Ejecutivo`, y `Metadata_Solicitud` con `Nombre_Cliente`,
`Metodo_Pago` y, opcionalmente, `Comentario_Ejecutivo`. La lista (o cadena
JSON) de deudas puede estar en `Deudas`, `Detalle de Deudas` o
`JSON_Respuesta`; cada deuda admite los objetos anidados `JSON_Respuesta`
(`Id_Deuda`, `Numero_Credito`, `Monto_Propuesto`, `Num_Cuotas`) y
`Datos_Solicitud` (`Banco`).

El tamaño predeterminado es Carta horizontal; pase `orientation="vertical"`
para Carta vertical. En horizontal, la tabla queda a la izquierda, el
comentario ejecutivo a la derecha y las recomendaciones ocupan el ancho total
debajo de ambos. Si no hay comentario, se muestra el texto predeterminado.

Ubique los recursos en `assets/logo.png` y `assets/water_mark.svg`. En el
formato horizontal, el SVG se dibuja como fondo de la hoja, sin invadir
encabezado ni pie, y queda detrás de las tarjetas. Personalice la fuente con
`font`, colores con `colors_config` y las recomendaciones con
`considerations`. El PDF incorpora una metadata invisible `/AgreementMetadata`
con el JSON normalizado del acuerdo.
