# Estándar usando Pep8
# Librerías de Python
import os
# Librerías de Terceros
import pandas as pd
import streamlit as st

# Creamos la Clase Aliado para guardar la información de cada aliado de forma estructurada
class Aliado:
    def __init__(self,nombre: str, 
                bancos: list,
                permite_contacto: bool,
                aliado_formal: bool,
                negociacion_bloque: bool,
                pago_co_obligatorio: bool,
                brinda_descuento_max: bool,
                ):
        self.nombre = nombre
        self.bancos = bancos
        self.permite_contacto = permite_contacto
        self.aliado_formal = aliado_formal
        self.negociacion_bloque = negociacion_bloque
        self.pago_co_obligatorio = pago_co_obligatorio
        self.brinda_descuento_max = brinda_descuento_max

    def brinda_maximo_descuento(self) -> bool:
        return self.brinda_descuento_max

    def es_formal(self) -> bool:
        return self.aliado_formal

    def permite_contactar(self) -> bool:
        return self.permite_contacto

    def validar_banco(self, banco: str) -> bool:
        return banco in self.bancos

    def pagar_co_obligatorio(self) -> bool:
        return self.pago_co_obligatorio

    def negocia_en_bloque(self) -> bool:
        return self.negociacion_bloque

# Función Auxiliar para Crear un Diccionario de Aliados a partir de un DataFrame
def crear_diccionario_aliados(df: pd.DataFrame) -> dict:
    # Paso 1: Definir un Diccionario Vacío para Guardar los Aliados
    aliados_dict = {}

    # Paso 2: Iterar sobre cada Fila del DataFrame y Crear un Objeto Aliado
    for _, row in df.iterrows():
        current_aliado = Aliado(
            nombre=row['Casa de Cobro'],
            bancos=[banco.strip() for banco in row['Bancos'].split(',')],
            permite_contacto=row['Permite Contacto'] == 'SI',
            aliado_formal=row['Tipo Aliado'] == 'Formal',
            negociacion_bloque=row['Negociación en Bloque'] == 'SI',
            pago_co_obligatorio=row['Pago CO Obligatorio'] == 'SI',
            brinda_descuento_max=row['Brinda Descuento Máximo'] == 'SI'
        )
        aliados_dict[current_aliado.nombre] = current_aliado

    # Paso 3: Devolver el Diccionario de Aliados
    return aliados_dict