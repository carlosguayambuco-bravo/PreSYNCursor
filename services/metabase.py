# Usando Pep8
# Librerías de Python
from io import StringIO
import json
# Librerías de Terceros
import pandas as pd
import requests
from requests.exceptions import ChunkedEncodingError, ConnectionError, Timeout

MAX_QUERY_ATTEMPTS = 3

# Clase de MetabaseService para interactuar con la API de Metabase
class MetabaseService:
    def __init__(self, metabase_username: str, metabase_password: str, mainDB_id: int):
        self.mb_user = metabase_username
        self.mb_pass= metabase_password
        self.mainDB_id = mainDB_id

        # Inicializamos ayudas a Metabase con Valores por Defecto
        self.session_id = None
        self.query_attempts = 0

    # Método para iniciar sesión en Metabase y obtener el Session ID
    def login(self):
        # Definimos los Requisitos del API
        authURL = 'https://metabase.resuelve.io/api/session'
        authPayload = {"username": self.mb_user, "password": self.mb_pass}

        # Ejecutamos la Request al API
        try:
            authResponse = requests.post(authURL, json=authPayload)
            authResponse.raise_for_status()
            # Verificamos que la Solicitud sea Exitosa (Código 200)
            if authResponse.status_code == 200:
                sessionID = authResponse.json()['id']
                self.session_id = sessionID
            else:
                print('🚯Error en Obtener el JWT: HTTP {}: {}'.format(
                    authResponse.status_code,
                    authResponse.text
                ))
                raise Exception('🚯Error en Obtención del Metabase Session ID')
        except Exception as e:
            print('🚯Error Durante Obtención de Session ID: {}'.format(e))

    # Método para obtener el Session ID, iniciando sesión si es necesario
    def get_session_id(self):
        if not self.session_id:
            self.login()
        return self.session_id

    # Método para ejecutar una consulta en Metabase y obtener los resultados
    def run_query(self, query: str) -> pd.DataFrame:
        # Obtenemos el Session ID actual
        current_session_id = self.get_session_id()
        # Definimos el Endpoint de la API para ejecutar la consulta
        endpointURL = 'https://metabase.resuelve.io/api/dataset/json'

        # Definimos los contenidos de la Request
        payload = {
            'database': self.mainDB_id,
            'type': 'native',
            'native': {'query': query},
        }
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'X-Metabase-Session': current_session_id,
        }

        try:
            # Se pasa la consulta serializada dentro del campo 'query' en data=
            response = requests.post(
            endpointURL, data={'query': json.dumps(payload)}, headers=headers
            )
            response.raise_for_status()

            # /api/dataset/json devuelve directamente una lista de registros [{"col1": val, ...}, ...]
            data = response.json()

            # Creación directa del DataFrame y se devuelve
            queryDF = pd.DataFrame(data)
            # Reiniciamos el contador de intentos de consulta
            self.query_attempts = 0

            return queryDF

        # Primer Error: Rechazo de Metabase
        except requests.exceptions.HTTPError as err:
            print('🚯Error por Rechazo de Metabase (Código {}): {}'.format(response.status_code,err))
            return pd.DataFrame()
        # Segundo Error: Timeout, Se aplican reintentos hasta MAX_QUERY_ATTEMPTS
        except requests.exceptions.Timeout:
            if self.query_attempts >= MAX_QUERY_ATTEMPTS:
                print('🚯Error por Timeout: Metabase esta lento, se alcanzó el máximo de intentos ({}).'.format(
                    MAX_QUERY_ATTEMPTS
                ))
                return pd.DataFrame()

            print('🚯Error por Timeout: Metabase esta lento, Aplicando Intento {}'.format(
                self.query_attempts + 1 
            ))
            self.query_attempts += 1

            return self.run_query(query)  # Reintento de la Consulta
            
        # Tercer Error: Algun Error Adicional
        except Exception as e:
            print('🚯Error Inesperado: {}'.format(e))
            return pd.DataFrame()

    # Método para Obtener la Información de un Card
    def get_card_info(self, card_id: int) -> pd.DataFrame:
        # Obtenemos el Session id
        current_session_id = self.get_session_id()
        # Definimos el Endpoint de la API para obtener la información del Card
        endpointURL = f"https://metabase.resuelve.io/api/card/{card_id}/query/csv"

        # Definimos los contenidos de la Request
        headers = {
            "X-Metabase-Session": current_session_id
        }

        # Aplicamos la Petición
        try:
            # Hacemos una petición POST (o GET, Metabase acepta ambas en este endpoint, pero POST es más segura si añades filtros después)
            response = requests.post(endpointURL, headers=headers)
            response.raise_for_status()

            # --- Creación del DF desde el CSV recibido ---
            # Usamos io.StringIO para que Pandas procese el texto plano del CSV directamente a un DataFrame
            queryDF = pd.read_csv(StringIO(response.text))

            # Actualizamos el contador de intentos de consulta
            self.query_attempts = 0

            return queryDF

        # Primer Error: Rechazo de Metabase
        except requests.exceptions.HTTPError as err:
            print(
                "🚯 Error por Rechazo de Metabase (Código {}): {}".format(
                    response.status_code, err
                )
            )
            return pd.DataFrame()
        # Segundo Error: Timeout
        except requests.exceptions.Timeout:
            # Verificamos si hemos alcanzado el máximo de intentos
            if self.query_attempts >= MAX_QUERY_ATTEMPTS:
                print(
                    "🚯 Error por Timeout: Metabase esta lento, se alcanzó el máximo de intentos ({}).".format(
                        MAX_QUERY_ATTEMPTS
                    )
                )
                return pd.DataFrame()
            print("🚯 Error por Timeout: Metabase esta lento")
            print("Aplicando Intento {}".format(self.query_attempts + 1))   
            self.query_attempts += 1
            return self.get_card_info(card_id)  # Reintento de la Consulta

        # Tercer Error: Algun Error Adicional
        except Exception as e:
            print("🚯 Error Inesperado: {}".format(e))
            return pd.DataFrame()