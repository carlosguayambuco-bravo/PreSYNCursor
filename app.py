# Estándar usando Pep8
# Librerías de Python
# Librerías de Terceros
# Librerías Locales
from utils.initializer import initialize_services, initialize_test_states
from views.rellenar_forms import rellenar_formulario

# Inicializamos los servicios
initialize_services()

# Inicializamos los estados de prueba
initialize_test_states()

# Ejecutamos la view de rellenar formulario
rellenar_formulario()