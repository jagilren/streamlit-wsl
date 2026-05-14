# PROMPT COMPLETO — Dashboard para Horas de Trabajo Bombas  PTAR en Streamlit
## Para usar en GitHub Copilot Chat, Cursor AI o cualquier asistente de código en VS Code

---

## 1. INSTRUCCIÓN PRINCIPAL

Con la aplicación de Streamlit ya creada y completado el modulo de dashboard_dqo, vas a crear otro módulo llamado dashboard_pump_usage que genere un dashboard profesional donde vamos a hacer un tablero del uso horario de la diferentes bombas presentes el sistema de la PTAR, 
Debes tener presente lo siguiente:

## 2. Base de datos
Usando la misma base de datos de TimeScale, en la tabla Pumps vas a encontrar 4 columnas a saber:
- ID (Autonumeric)
- TAG_ID (TAG de la Bomba)
- TimeStamp (Hora del registro)
- Value (Hours of use numeric(10,2))

## 3. Filtros
###3.1Filtros por Subsistema
Puedo filtrar por los substistemas, es decir cada bomba puede ser mapeada a un subsistema a traves de una tabla auxiliar donde  las bombas pueden pertenecer al PRETRATAMIENTO, FISICO-QUIMICO, REACTORES AEROBIOS, DESHIDRATACION. el módulo debe tener una utilidad donde a cada bomba se le puede asignar su respectivo Subsistema, de tal forma que al momento de filtrar por sub-sistema se muestren sólo las bombas pertenecientes a este. 

###3.2 Filtros por Tipo bomba
También es posible filtrar por tipo de bomba, por tanto debe existir una utilidad que me permita matricular cada bomba con  su tipo de bomba específica, los tipos de bomba usados en este proyecto son "CENTRIFUGA", "PERISTALTICA", "NEUMATICA", "ELECTRONICA DIAFRAGAMA", "PERISTALTICA", "TORNILLO".

---

## 1. ESTRUCTURA DE BASE DE DATOS
