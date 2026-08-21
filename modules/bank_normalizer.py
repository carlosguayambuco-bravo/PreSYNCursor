# Estándar usando Pep8
# Librerías de Python
# Librerías de Terceros
import numpy as np
import pandas as pd
# Librerías Locales

# Crear el Diccionario de Patrones Únicos
PATRONES_UNICOS_BANCOS = {
    'Icetex Centro': 'Icetex','Alianza SGP': 'Alianza Sgp','Jj Cobranzas': 'JJ Cobranzas','Liquitty' : 'Liquitty','Aecsa': 'Aecsa','Fundacion De La Mujer': 'Fundacion De La Mujer',
    'Erpo': 'ERPO','Valora Punto Com': 'Valora.com','Hoyos Y Abogados': 'Hoyos Y Abogados',
    'Konecta': 'Konecta','Renovar Financiera': 'Renovar Financiera','Central De Inversiones': 'Central De Inversiones','Logros Factoring': 'Logros Factoring','Qnt': 'QNT',
    'Corbeta': 'Corbeta','Inversionistas Estrategicos': 'Inversionistas Estrategicos','Confiar': 'Confiar',
    'Puentes Y Asociados Abogados Especializados': 'Puentes Y Asociados Abogados Especializados','Patrimonio Autonomo Risk - A&S': 'Patrimonio Autonomo Risk - A&S','Asesorias Juridicas':'Asesorias Juridicas',
    'Nexa': 'Nexa','Bancoomeva': 'Bancoomeva','Contacto Solución': 'Contacto Solutions','Alkomprar': 'Alkomprar','Interdinco': 'Interdinco',
    'Idear Negocios': 'Idear Negocios', 'Grupo Consultor Andino S.A.':'Grupo Consultor Andino', 'Cobro Activo':'Cobro Activo',
    'Mundial De Cobranzas Sas':'Mundial De Cobranzas','Sauco':'Sauco','Banca De Negocios':'Banca De Negocios',
    'Prossem':'Prossem','Cresi':'Cresi','Conalcreditos':'Conalcreditos','Zinobe':'Zinobe','Cyc':'CYC','Asesorías Gs':'Asesorías GS',
    'Contento':'Contento','Alkosto':'Alkosto','Rappicard':'Rappicard','Eyc':'EYC','Reestructura':'Reestructura','Reincar':'Reincar',
    'Fga':'FGA','Sistecredito':'SisteCredito','Asercor':'Asercor','Atm':'ATM','Covinoc':'Covinoc','Gesticobranzas':'Gesticobranzas',
    'Juancho Te Presta':'Juancho Te Presta','Free Management':'Free Management','Credivalores':'Credivalores','Sufi':'Sufi',
    'Leon Y Asociados':'Leon Y Asociados','Mora Cero':'Mora Cero','Qnt Sas':'QNT','Inversionistas Estratégicos':'Inversionistas Estrategicos',
    'A&S Soluciones Estrategicas': 'A&S Soluciones Estrategicas','Carulla':'Carulla','Coltefinanciera':'Coltefinanciera',
    'Central De Cobranza': 'Central De Cobranza','Utrahuilca':'Utrahuilca','Adcore':'Adcore','Crc Outsourcing Sa':'CRC Outsourcing',
    'Consultores Legales':'Consultores Legales','Sica Legal':'Sica Legal','Citi Summa':'Citi Summa','Empresarios Y Consultores Ltda':'Empresarios Y Consultores',
    'Cobyser':'Cobyser', 'Serlefin': 'Serlefin','Fincomercio':'Fincomercio','Cess':'CESS','Aserfin':'Aserfin','Grupo Juridico Deudu':'Deudu',
    'Litigamos Abogados Asociados':'Litigamos Abogados Asociados','Sinerjoy':'Sinerjoy','Coopcentral':'Coopcentral','Summa Valor S.A.S':'Summa Valor',
    'Megalinea':'Megalinea','Comultrasan':'Financiera Comultrasan','Asesores Legales Gama':'Asesores Legales Gama','Rapicredit':'Rappicredit',
    'Aslegal Servicios Cred':'Aslegal','Davi Bank':'Davi Bank','Recupera S.A.S':'Recupera','Aslegal':'Aslegal','Baninca':'Baninca',
    'Dinamica':'Dinamica',
}

# Agregar el Diccionario Completo
DICCIONARIO_BANCOS = {
    'Tuya': ['Tuya Contacto Soluciones','Qnt Tuya','Aecsa Tuya','Tuya S.A Contactosol','Tuya','Éxito'],
    'Bancolombia': ['Qnt Bancolombia','Bancolombia','Contento Bancolombia Sufi'],
    'Agaval': ['Agaval'],
    'Rappipay': ['Rappipay'],
    'Banco Falabella': ['Logros Factoring Falabella','Grupo Jurídico Falabella','Bancofalab Citisumma','Eyc Falabella',
                        'Citisumma Falabella','Deudu Falabella','Cobrando Falabella','Falabella','Banco Falabella Casa De Cobro',
                        'Redinstantic Falabella','Bfalabella Contactosol'],
    'Banco AV Villas': ['Deudu Av Villas','Banco Av Villas','Av Villas','Qnt Av Villas','Grupo Juridico Av Villas','Grupo Consultor Andino Av Villas',
                    'Aecsa Av Villas'],
    'BBVA Colombia': ['Aecsa Bbva','Bbva','Cobranzas Beta Origen: Bbva','Beta Bbva','Grupo Juridico Bbva','Cobrando Bbva',
                    'Deudo Bbva','Qnt Bbva'],
    'Juriscoop': ['Juriscoop'],
    'Compensar': ['Compensar','Summa Compensar'],
    'Banco Davivienda': ['Logros Factoring Davivienda','Deudu Davivienda','Logros Factoring Adcore Davivienda','Management Davivienda',
                        'Davivienda','Beta Davivienda','Cobrando Bpo Davivienda','Davivienda Cobrando Sas','Inversionistas Estratégicos Davivienda',
                        'Aecsa Davivienda','Grupo Juridico Davivienda','Ccr Jurídico Davivienda'],
    'Nubank': ['Nu Bank','Logros Factoring Nubank'],
    'Scotiabank Colpatria': ['Peruzzi Skotiabank Colpatria','Adamantine Scotiabank','Grupo Consulto Colpatria','Qnt Colpatria',
                            'Gc Andino Colpatria','Crc Colpatria','Serlefin Colpatria','Scotiabank Citibank','Scotiabank Colpatria',
                            ],
    'Puntualmente': ['Puntualmente Sas'],
    'Banco Popular': ['Banco Popular','Banco Popular Citisumma','Banco Popular','Deudu Banco Popular','Banco Popular Casa De Cobro',
                    'Peruzzicol Bcopopular','Banco Popular Contactosol','Banco Popular-Adcore'],
    'Itaú': ['Qnt Itau','Itaú','Itau Helm','Aecsa Itaú'],
    'Teleperformance': ['Teleperformance'],
    'Bancamia': ['Bancamia S.A','Bancamia','Qnt Bancamia','Colletcenter Bancamia'],
    'Banco De Bogotá': ['Banco De Bogota','Crear País Banco De Bogotá','Qnt Bogotá'],
    'Ban100': ['Banco Credi Financiera'],
    'Colsubsidio': ['Colsubsidio'],
    'Banco Mundo Mujer': ['Banco Mundo Mujer'],
    'Serfinanza': ['Serfinanza','Serfinanza Contactosol'],
    'Codensa': ['Codensa'],
    'Banco Unión': ['Qnt Giros&Finanzas','Banco Unión'],
    'Banco Pichincha': ['Pichincha Educativo','Pichincha'],
    'Coomeva': ['Coomeva','Coomeva_X'],
    'Banco Finandina': ['Finandina Incomercio','Banco Finandina'],
    'Acyr-Activos Y Recuperación': ['Acyr-Activos Y Recuperación','Acyr'],
    'Systemgroup': ['Sistemcobro','Systemgroup'],
    'Lulobank': ['Lulobank','Lulo Banck'],
    'Banco de Occidente': ['Qnt Banco De Occidente','Banco De Occidente','Deudu-Banco De Occidente'],
    'Refinancia': ['Refinancia'],
    'Banco GNB Sudameris': ['Gnb Sudameris'],
    'Banco Credijamar': ['Credijamar'],
    'Banco Caja Social': ['Caja Social'],
}

# Diccionario de Búsqueda de Patrones Únicos
DICCIONARIO_BUSQUEDA_PATRONES_BANCOS = {
    'Banco Davivienda': 'Davivienda',
    'Scotiabank Colpatria': 'Colpatria',
    'Banco de Occidente': 'Occidente',
    'Banco AV Villas': 'Av Villas',
    'Banco Falabella': 'Falabella',
    'Banco Popular': 'Popular',
    'Banco de Bogotá': 'Bogotá',
    'Bancolombia': 'Bancolombia',
    'Bancamia': 'Bancamia',
    'Banco Pichincha': 'Pichincha',
    'BBVA Colombia': 'Bbva',
    'Banco Finandina': 'Finandina',
    'Banco GNB Sudameris': 'Gnb Sudameris',
    'Banco Caja Social': 'Caja Social',
    'Tuya': 'Tuya',
    'Itaú': 'Itau',
}

# Lista de Bancos Únicos
BANCOS_UNICOS = list(PATRONES_UNICOS_BANCOS.values()) + list(DICCIONARIO_BANCOS.keys())
BANCOS_UNICOS = list(set(BANCOS_UNICOS))  # Eliminamos duplicados


# Función Normalizadora de Bancos
def normalizar_banco(banco: str) -> str:
    # Paso 1: Aplicar .title y strip
    banco_limpio = banco.title().strip()
    # Paso 2: Buscar en los Patrones Únicos
    if banco_limpio in PATRONES_UNICOS_BANCOS:
        return PATRONES_UNICOS_BANCOS[banco_limpio]
    # Paso 3: Buscar en el Diccionario Completo
    for banco_normalizado, patrones in DICCIONARIO_BANCOS.items():
        if banco_limpio in patrones:
            return banco_normalizado
    # Paso 4: Si no se encuentra, buscar por patrones 
    for banco_normalizado, patron in DICCIONARIO_BUSQUEDA_PATRONES_BANCOS.items():
        if patron in banco_limpio:
            return banco_normalizado
    # Si no se encuentra, devolver el banco limpio
    return banco_limpio

# Función de Normalización de Bancos de forma Vectorizada
def normalizar_bancos_vectorizado(bancos: pd.Series) -> pd.Series:
    # Paso 1: Aplicar .title y strip a toda la Serie
    bancos_limpios = bancos.str.title().str.strip()
    # Paso 2: Crear una Máscara para tener un seguimiento de los Bancos Cambiados
    mask_cambiados = pd.Series(False, index=bancos_limpios.index)
    # Paso 3: Crear Máscara para Patrones Únicos
    mask_unicos = bancos_limpios.isin(PATRONES_UNICOS_BANCOS.keys())

    # Paso 4: Normalizar Bancos Usando Diccionarios y Patrones

    # Procesamiento Únicos: Usar diccionario
    bancos_limpios.loc[mask_unicos] = bancos_limpios.loc[mask_unicos].map(PATRONES_UNICOS_BANCOS)
    mask_cambiados = mask_cambiados | mask_unicos

    if mask_cambiados.all():
        return bancos_limpios

    # Procesamiento Diferentes: Usar diccionario completo
    for banco_normalizado, patrones in DICCIONARIO_BANCOS.items():
        mask_patrones = bancos_limpios.isin(patrones) & ~mask_cambiados
        mask_cambiados = mask_cambiados | mask_patrones
        bancos_limpios.loc[mask_patrones] = banco_normalizado
        if mask_cambiados.all():
            return bancos_limpios

    # Procesamiento por Patrones: Usar diccionario de búsqueda
    for banco_normalizado, patron in DICCIONARIO_BUSQUEDA_PATRONES_BANCOS.items():
        mask_patron = bancos_limpios.str.contains(patron, case=False, na=False) & ~mask_cambiados
        mask_cambiados = mask_cambiados | mask_patron
        bancos_limpios.loc[mask_patron] = banco_normalizado

        if mask_cambiados.all():
            return bancos_limpios

    # Paso 5: Devolver la Serie Normalizada
    return bancos_limpios