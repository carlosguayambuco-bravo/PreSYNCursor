# Estándar usando Pep8
# Librerías de Python
from datetime import datetime
from typing import Dict, List, Optional, Literal, NotRequired
from click import Option
from pandera import Bool
from typing_extensions import TypedDict
# Librerías de Terceros
import pandas as pd
import pandera.pandas as pa
from pandera.typing import Series
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
    Datos_Solicitud: str # Es un JSON que contiene: Id_Deuda, Banco, Numero_Credito, Monto_Propuesto, Num_Cuotas y Monto_Actual
    Fecha_Esperada_Pago: pa.dtypes.Timestamp = pa.Field(nullable=True)  # Puede ser nulo si no hay fecha esperada de pago
    Tipo_Pago: str = pa.Field(isin=PAGOS_POSIBLES_SOLICITUD, nullable=True)  # Puede ser nulo si no hay tipo de pago
    Ejecutivo: str = pa.Field(nullable=True)  # Puede ser nulo si no hay ejecutivo asignado
    Metadata_Solicitud: str  # Es un JSON que contiene:
    # - Estado_Comite: int (0: NA, 1: Solicitado, 2: Aprobado, 3: Rechazado)
    # - Estado_Titular_Ilocalizable: int (0: NA, 1: Solicitado, 2: Aprobado, 3: Rechazado)
    # - Pago_Total_Obligatorio: bool
    # - Metodo_Pago: str ('Efectivo-Cheque','PSE','Transferencia')
    # - Comentario Ejecutivo: str
    # - Comentario Negociador: str
    # - Fue_Llamada: bool
    # - Id_Acuerdo_Pago: str
    # - Origen_Acuerdo: str (ID_Solicitud)
    Estado_Solicitud: str = pa.Field(isin=ESTADOS_POSIBLES_SOLICITUD, nullable=True)  # Puede ser nulo si no hay estado definido
    Fecha_Respuesta: pa.dtypes.Timestamp = pa.Field(nullable=True)  # Puede ser nulo si no hay respuesta
    Fecha_Limite_Pago: pa.dtypes.Timestamp = pa.Field(nullable=True)  # Puede ser nulo si no hay fecha límite de pago
    JSON_Respuesta: str = pa.Field(nullable=True)  # Es un JSON que contiene la respuesta a la solicitud por cada Deuda
    # Tiene: Id_Deuda, Banco, Numero_Credito, Monto_Propuesto, Num_Cuotas

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


class MasivasMetadata(TypedDict, total=False):
    Es_Maximo_Descuento: Optional[bool]
    Fecha_Limite_Uso: Optional[datetime]
    Alias: Optional[str]
    Id_Portafolio: Optional[str]
    PaB_Portafolio: Optional[float]

class MasivasSchema(pa.DataFrameModel):
    """
    Esquema para validar la estructura de los datos de masivas.
    """
    Id_Deuda: Series[str]  # Puede haber múltiples registros por Id_Deuda (varios descuentos por deuda)
    Referencia: Series[str]
    Casa_Cobro: Series[str]
    PaB_Propuesta: Series[float]
    PaB_Estructurado: Series[float] = pa.Field(nullable=True)  # Puede ser nulo si no aplica
    Plazo_Estructurado: Series[int] = pa.Field(nullable=True)  # Puede ser nulo si no aplica
    PaB_Portafolio: Series[float] = pa.Field(nullable=True)  # Puede ser nulo si no aplica
    Metadata: Series[MasivasMetadata]

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
    Lider: str
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
    Nombre_Cliente: str
    Numero_Credito: str
    Banco: str
    Monto_Actual: float

    class Config:
        strict = True  # Validación estricta de columnas
        coerce = True  # Coerción automática de tipos


class DeudasActivasSchema(pa.DataFrameModel):
    """
    Esquema para validar la estructura de los datos de deudas activas.
    """
    Id_Deuda: str = pa.Field(unique=True)  # Aseguramos que Id_Deuda sea único
    Referencia: str
    Cedula: str = pa.Field(nullable=True)  # Validación de cédula
    Nombre_Cliente: str
    Numero_Credito: str
    Banco: str
    PaB_Origen: float
    PaB_PL: float
    Pricing: float

    class Config:
        strict = True  # Validación estricta de columnas
        coerce = True  # Coerción automática de tipos

class LogsSchema(pa.DataFrameModel):
    """
    Esquema para validar la estructura de los datos de logs.
    """
    Timestamp: pa.dtypes.Timestamp
    Usuario: str = pa.Field(str_matches=r"^[\w\.-]+@[\w\.-]+\.\w+$")  # Validación de correo electrónico
    Motivo: str
    Detalle: str

    class Config:
        strict = True  # Validación estricta de columnas
        coerce = True  # Coerción automática de tipos

class PlantillaSolicitudesSchema(pa.DataFrameModel):
    """
    Esquema para validar la estructura de los datos de la plantilla de solicitudes.
    """
    Casa_Cobro: str
    Tipo_Solicitud: str = pa.Field(isin=['Validación','Acuerdo de Pago','Oferta de Acuerdo'])
    Cedula: str = pa.Field(str_matches=r"^[\d\.]{6,12}$")  # Validación de cédula
    Nombre_Cliente: str
    Banco: str
    Numero_Obligacion: str
    Propuesta: float
    Portafolio: str = pa.Field(nullable=True)  # Puede ser nulo si no aplica
    Plazos: str = pa.Field(nullable=True)  # Puede ser nulo si no aplica
    Id_Deuda: str

    class Config:
        strict = True  # Validación estricta de columnas
        coerce = True  # Coerción automática de tipos

class DeudasPosiblesCruce(TypedDict):
    Banco: str
    Monto_Actual: float
    Numero_Credito: str
    Id_Deuda: str
    Es_Liquidada: bool

class PagosCuotasCruce(TypedDict):
    Cuotas: int
    Monto: float
    En_Portafolio: bool


class MetadataPendienteCruce(TypedDict):
    Id_Registro: str
    Archivo_Origen: str
    Pagos_Cuotas: List[PagosCuotasCruce]
    Fecha_Identificacion: datetime
    Fecha_Limite_Pago: datetime
    Maximo_Descuento: bool
    Etiqueta: Literal['EXACTO','DUPLICADO','AMBIGUO','ADDENDUM','NULO']
    Deudas_Posibles: List[DeudasPosiblesCruce]
    Cruce_Status: Literal['Sin Reconocer','Reconocido','Subido Alianzas']
    Casa_Cobro: str
    Ejecutivo_Subida: str
    Alias_Casa: NotRequired[str]
    Id_Definitivo: NotRequired[str]
    Portafolio_Ids: NotRequired[str]
    Monto_Actual_Original: NotRequired[float]
    Ultima_Actualizacion: Optional[datetime]

class PendienteCruceSchema(pa.DataFrameModel):
    Id_Cruce: str # Un UUID
    Cedula: str = pa.Field(str_matches=r"^[\d\.]{6,15}$")  # Validación de cédula
    Nombre_Cliente: str = pa.Field(nullable=True)
    Banco: str = pa.Field(nullable=True)
    Monto_Actual: float = pa.Field(nullable=True)
    Numero_Credito: str = pa.Field(nullable=True)
    Metadata: Series[MetadataPendienteCruce]

class InputCruceSchema(pa.DataFrameModel):
    Cedula: Optional[Series[str]] = pa.Field(nullable=True)
    Nombre_Cliente: Optional[Series[str]] = pa.Field(nullable=True)
    Banco: Optional[Series[str]] = pa.Field(nullable=True)
    Monto_Actual: Optional[Series[float]] = pa.Field(nullable=True)
    Numero_Credito: Optional[Series[str]] = pa.Field(nullable=True)
    Id_Deuda: Optional[Series[str]]
    Liquidada: Optional[Series[bool]]

class InputFullScehma(InputCruceSchema):
    Monto_Propuesto: Optional[Series[float]]
    Fecha_Limite_Pago: Optional[Series[datetime]]

class OutputCruceSchema(pa.DataFrameModel):
    Id_Registro: str
    Ids_Candidatos: Series[List[str]]
    Etiqueta_Registro: str = pa.Field(isin=['EXACTO','DUPLICADO','AMBIGUO','ADDENDUM','NULO'])
    Motivos_Etiqueta: str