import pandera as pa
from pandera.typing import DataFrame, Series

class AhorroSchema(pa.DataFrameModel):
    """
    Esquema para validar la estructura de los datos de ahorro.
    """
    Referencia: str
    Ahorro_Total: float

    class Config:
        strict = True  # Validación estricta de columnas
        coerce = True  # Coerción automática de tipos

class PorCobrarSchema(pa.DataFrameModel):
    """
    Esquema para validar la estructura de los datos de por cobrar.
    """
    Referencia: str
    Por_Cobrar: float

    class Config:
        strict = True  # Validación estricta de columnas
        coerce = True  # Coerción automática de tipos

class PaBIdealSchema(pa.DataFrameModel):
    """
    Esquema para validar la estructura de los datos de PaB Ideal.
    """
    Id_Deuda: str = pa.Field(unique=True)  # Aseguramos que Id_Deuda sea único
    PaB_Ideal: float

    class Config:
        strict = True  # Validación estricta de columnas
        coerce = True  # Coerción automática de tipos

class AliadosSchema(pa.DataFrameModel):
    """
    Esquema para validar la estructura de los datos de aliados.
    """
    Casa_Cobro: str = pa.Field(alias="Casa de Cobro")
    Nombre_Normalizado: str = pa.Field(alias="Nombre Normalizado")
    Ejecutivo: str
    Bancos: str
    Tipo_Cartera: str = pa.Field(alias="Tipo Cartera")
    Permite_Contacto: str = pa.Field(alias="Permite Contacto")
    Tipo_Aliado: str = pa.Field(alias="Tipo Aliado")
    Forma_de_Contacto: str = pa.Field(alias="Forma de Contacto")
    Tiempos_de_Respuesta: str = pa.Field(alias="Tiempos de Respuesta")
    Comentario: str
    Cruza_Base: str = pa.Field(alias="Cruza Base")
    Sync: str = pa.Field(alias="SYNC")
    Negociacion_en_Bloque: str = pa.Field(alias="Negociación en Bloque")
    Contraofertas_de_Pago_Obligatorio: str = pa.Field(alias="Contraofertas de Pago Obligatorio")
    Brindan_max_Descuento: str = pa.Field(alias="Brindan Máx. Descuento")
    Pago_a_Cuotas: str = pa.Field(alias="Pago a Cuotas")

    class Config:
        strict = True  # Validación estricta de columnas
        coerce = True  # Coerción automática de tipos

class MasivasSchema(pa.DataFrameModel):
    """
    Esquema para validar la estructura de los datos de masivas.
    """
    Id_Deuda: str = pa.Field(unique=True)  # Aseguramos que Id_Deuda sea único
    PaB_Propuesta: float
    PaB_Estructurado: float
    Plazo_Estructurado: int
    Es_Portafolio: bool

    class Config:
        strict = True  # Validación estricta de columnas
        coerce = True  # Coerción automática de tipos

class AddendumsSchema(pa.DataFrameModel):
    """
    Esquema para validar la estructura de los datos de addendums.
    """
    Id_Deuda: str = pa.Field(unique=True)  # Aseguramos que Id_Deuda sea único
    Cedula: str = pa.Field(str_matches=r"^[\d\.]{9,11}$")
    Banco: str
    PaB_Origen: float
    PaB_Propuesta: float
    PaB_PL: float

    class Config:
        strict = True  # Validación estricta de columnas
        coerce = True  # Coerción automática de tipos

class LiquidationsSchema(pa.DataFrameModel):
    """
    Esquema para validar la estructura de los datos de liquidaciones.
    """
    Id_Deuda: str = pa.Field(unique=True)  # Aseguramos que Id_Deuda sea único

    class Config:
        strict = True  # Validación estricta de columnas
        coerce = True  # Coerción automática de tipos

class HeadCountSchema(pa.DataFrameModel):
    """
    Esquema para validar la estructura de los datos de headcount.
    """
    Correo: str = pa.Field(str_matches=r"^[\w\.-]+@[\w\.-]+\.\w+$")  # Validación de correo electrónico
    ID_Empleado: str = pa.Field(unique=True)  # Aseguramos que ID_Empleado sea único
    Nombre: str
    Nombre_Empleo: str
    Estado: str
    Cedula: str = pa.Field(str_matches=r"^[\d\.]{9,11}$")  # Validación de cédula
    Es_Negociador: bool

    class Config:
        strict = True  # Validación estricta de columnas
        coerce = True  # Coerción automática de tipos

class ConfigsSchema(pa.DataFrameModel):
    """
    Esquema para validar la estructura de los datos de configuraciones.
    """
    Config_Name: str = pa.Field(unique=True)  # Aseguramos que Config_Name sea único
    Value: str

    class Config:
        strict = True  # Validación estricta de columnas
        coerce = True  # Coerción automática de tipos

class UserPermissionsSchema(pa.DataFrameModel):
    """
    Esquema para validar la estructura de los datos de permisos de usuario.
    """
    Correo: str = pa.Field(str_matches=r"^[\w\.-]+@[\w\.-]+\.\w+$")  # Validación de correo electrónico
    Permisos: str  # Lista de permisos como cadena separada por comas

    class Config:
        strict = True  # Validación estricta de columnas
        coerce = True  # Coerción automática de tipos

class CarteraActivaSchema(pa.DataFrameModel):
    """
    Esquema para validar la estructura de los datos de cartera activa.
    """
    Referencia: str 
    Cedula: str = pa.Field(str_matches=r"^[\d\.]{9,11}$")  # Validación de cédula
    Id_Deuda: str = pa.Field(unique=True)  # Aseguramos que Id_Deuda sea único
    Numero_Credito: str
    Banco: str
    PaB_Origen: float

    class Config:
        strict = True  # Validación estricta de columnas
        coerce = True  # Coerción automática de tipos


class DeudasActivasSchema(pa.DataFrameModel):
    """
    Esquema para validar la estructura de los datos de deudas activas.
    """
    Id_Deuda: str = pa.Field(unique=True)  # Aseguramos que Id_Deuda sea único
    Referencia: str
    Cedula: str = pa.Field(str_matches=r"^[\d\.]{9,11}$")  # Validación de cédula
    Banco: str
    PaB_Origen: float
    PaB_PL: float
    Pricing: float

    class Config:
        strict = True  # Validación estricta de columnas
        coerce = True  # Coerción automática de tipos