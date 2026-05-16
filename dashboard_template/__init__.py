"""Plantilla de dashboard genérico tag-config-driven.

Para clonar como un nuevo módulo (ej. caudal, sst, conductividad):

    cp -r dashboard_template dashboard_<nuevo>
    cd dashboard_<nuevo>
    mv dashboard_template.py dashboard_<nuevo>.py
    grep -rli template . | xargs sed -i \\
        -e 's/template/<nuevo>/g' \\
        -e 's/Template/<Nuevo>/g' \\
        -e 's/TEMPLATE/<NUEVO>/g'

Después editar `config.py` con MODULE_LABEL, UNIT, ICON y siembrar
`<nuevo>_tag_config` con los TAGs reales (idealmente desde la UI de admin
o por SQL directo).

Ver README.md para más detalles.
"""
