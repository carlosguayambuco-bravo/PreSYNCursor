# Estándar usando Pep8
# Librerías de Python
# Librerías de Terceros
import pandas as pd
import pandera.pandas as pa
# Librerías Locales
from modules.constants import ESTADOS_POSIBLES_SOLICITUD, PAGOS_POSIBLES_SOLICITUD

class SolicitudesSchema(pa.DataFrameModel):
    """
    Esquema para validar la estructura de los datos de solicitudes.
    """
    ID_Solicitud: str = pa.Field(unique=True)  # Aseguramos que ID_Solicitud sea único
    Timestamp: pa.dtypes.Timestamp
    Correo: str = pa.Field(str_matches=r"^[\w\.-]+@[\w\.-]+\.\w+$")  # Validación de correo electrónico
    Referencia: str
    Cedula: str = pa.Field(str_matches=r"^[\d\.]{6,15}$")  # Validación de cédula
    Ids_Deuda: str  # Lista de Ids de Deuda como cadena separada por -
    Casa_Cobro: str
    Tipo_Solicitud: str = pa.Field(isin=['Validación','Acuerdo de Pago','Oferta de Acuerdo'])
    Datos_Solicitud: dict # Es un JSON que contiene el Monto por Deuda y los Plazos
    Fecha_Esperada_Pago: pa.dtypes.Timestamp
    Tipo_Pago: str = pa.Field(isin=PAGOS_POSIBLES_SOLICITUD)
    Ejecutivo: str
    Metadata_Solicitud: dict  # Es un JSON que contiene:
    # - Estado de Comité: int (0: Esperando Respuesta, 1: Aprobado, 2: Rechazado)
    # - Estado de Ilocalizable: int (0: Esperando Respuesta, 1: Aprobado, 2: Rechazado)
    # - Pago Total Obligatorio: bool
    # - Metodo de Pago: str ('Efectivo-Cheque','PSE','Transferencia')
    # - Comentario Ejecutivo: str
    # - Comentario Negociador: str
    # - Fecha Llamada: str (YYYY-MM-DD HH:MM:SS)
    Estado_Solicitud: str = pa.Field(isin=ESTADOS_POSIBLES_SOLICITUD)
    Fecha_Respuesta: pa.dtypes.Timestamp
    Fecha_Limite_Pago: pa.dtypes.Timestamp
    JSON_Respuesta: str  # Es un JSON que contiene la respuesta a la solicitud por cada Deuda

    class Config:
        strict = True  # Validación estricta de columnas
        coerce = True  # Coerción automática de tipos

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
    PaB_Ideal_Credito: float

    class Config:
        strict = True  # Validación estricta de columnas
        coerce = True  # Coerción automática de tipos

class AliadosSchema(pa.DataFrameModel):
    """
    Esquema para validar la estructura de los datos de aliados.
    """
    Casa_Cobro: str = pa.Field(alias="Casa de Cobro")
    Nombre_Normalizado: str = pa.Field(alias="Nombre Normalizado")
    Ejecutivo: str = pa.Field(nullable=True)  # Puede ser nulo si no aplica
    Bancos: str = pa.Field(nullable=True)  # Puede ser nulo si no aplica
    Tipo_Cartera: str = pa.Field(alias="Tipo Cartera", nullable=True)  # Puede ser nulo si no aplica
    Tipo_Aliado: str = pa.Field(alias="Tipo Aliado", nullable=True)  # Puede ser nulo si no aplica
    Forma_de_Contacto: str = pa.Field(alias="Forma de Contacto", nullable=True)  # Puede ser nulo si no aplica
    Tiempos_de_Respuesta: str = pa.Field(alias="Tiempos de Respuesta", nullable=True)  # Puede ser nulo si no aplica
    Comentario: str = pa.Field(nullable=True)  # Puede ser nulo si no aplica
    Permite_Contacto: bool = pa.Field(alias="Permite Contacto")
    Cruza_Base: bool = pa.Field(alias="Cruza Base")
    Sync: bool = pa.Field(alias="SYNC")
    Negociacion_en_Bloque: bool = pa.Field(alias="Negociación en Bloque")
    Contraofertas_de_Pago_Obligatorio: bool = pa.Field(alias="Contraofertas de Pago Obligatorio")
    Brindan_max_Descuento: bool = pa.Field(alias="Brindan Máx. Descuento")
    Pago_a_Cuotas: bool = pa.Field(alias="Pago a Cuotas")

    class Config:
        strict = True  # Validación estricta de columnas
        coerce = True  # Coerción automática de tipos

class MasivasSchema(pa.DataFrameModel):
    """
    Esquema para validar la estructura de los datos de masivas.
    """
    Id_Deuda: str = pa.Field(unique=True)  # Aseguramos que Id_Deuda sea único
    Referencia: str
    Casa_Cobro: str
    PaB_Propuesta: float
    PaB_Estructurado: float = pa.Field(nullable=True)  # Puede ser nulo si no aplica
    Plazo_Estructurado: int = pa.Field(nullable=True)  # Puede ser nulo si no aplica
    PaB_Portafolio: float = pa.Field(nullable=True)  # Puede ser nulo si no aplica

    class Config:
        strict = True  # Validación estricta de columnas
        coerce = True  # Coerción automática de tipos

class AddendumsSchema(pa.DataFrameModel):
    """
    Esquema para validar la estructura de los datos de addendums.
    """
    Id_Deuda: str = pa.Field(unique=True)  # Aseguramos que Id_Deuda sea único
    Cedula: str = pa.Field(str_matches=r"^[\d\.]{6,12}$")
    Referencia: str
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
    Cedula: str = pa.Field(str_matches=r"^[\d\.]{6,12}$")  # Validación de cédula
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
    Cedula: str = pa.Field(nullable=True) # En este caso la Cedula puede ser Nula
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
    Cedula: str = pa.Field(str_matches=r"^[\d\.]{6,12}$")  # Validación de cédula
    Nombre_Cliente: str
    Banco: str
    PaB_Origen: float
    PaB_PL: float
    Pricing: float

    class Config:
        strict = True  # Validación estricta de columnas
        coerce = True  # Coerción automática de tipos