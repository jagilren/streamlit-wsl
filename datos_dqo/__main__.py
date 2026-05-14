"""Entry point: genera datos sintéticos de DQO y los carga a TimescaleDB.

Uso:
    python -m datos_dqo
    python -m datos_dqo --desde 2025-01-01 --hasta 2026-05-12 --seed 42

Si la conexión a la base falla, el programa aborta antes de generar nada
y devuelve código de salida 1.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime
from pathlib import Path

# Asegura que el directorio padre (donde vive db.py) esté en sys.path
# cuando se invoca con `python -m datos_dqo`.
_PARENT = Path(__file__).resolve().parent.parent
if str(_PARENT) not in sys.path:
    sys.path.insert(0, str(_PARENT))

# Carga .env antes de importar db (que lee os.environ al importarse).
try:
    from dotenv import load_dotenv
    load_dotenv(_PARENT / ".env")
except ModuleNotFoundError:
    pass

from datos_dqo.cargador import cargar, truncar, verificar_db
from datos_dqo.generador import generar, resumen


def _parse_fecha(txt: str) -> date:
    return datetime.strptime(txt, "%Y-%m-%d").date()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--desde", type=_parse_fecha, default=date(2025, 1, 1),
                        help="Fecha inicial inclusive (YYYY-MM-DD). Default: 2025-01-01")
    parser.add_argument("--hasta", type=_parse_fecha, default=None,
                        help="Fecha final inclusive (YYYY-MM-DD). Default: hoy.")
    parser.add_argument("--seed", type=int, default=42,
                        help="Semilla del generador pseudoaleatorio. Default: 42.")
    parser.add_argument("--solo-generar", action="store_true",
                        help="No conecta a la DB ni inserta; solo muestra el resumen.")
    parser.add_argument("--truncate", action="store_true",
                        help="Borra TODAS las filas de la tabla `dqo` antes de cargar. "
                             "Reinicia la secuencia de id. ¡Destructivo!")
    args = parser.parse_args()

    hasta = args.hasta or date.today()

    if not args.solo_generar:
        print("Verificando conexión a la base de datos…")
        if not verificar_db():
            return 1
        print("  Conexión OK.")

        if args.truncate:
            print("Truncando tabla `dqo`…")
            n_prev = truncar()
            print(f"  {n_prev:,} filas eliminadas.")

    print(f"Generando lecturas desde {args.desde} hasta {hasta} (seed={args.seed})…")
    lecturas = generar(desde=args.desde, hasta=hasta, seed=args.seed)
    print(f"  {len(lecturas):,} lecturas generadas.")
    for tag, stats in resumen(lecturas).items():
        print(f"    {tag:12s} n={stats['n']:4d}  min={stats['min']:7.2f}  "
              f"max={stats['max']:7.2f}  promedio={stats['promedio']:7.2f}")

    if args.solo_generar:
        print("\n--solo-generar: se omite la carga a la base de datos.")
        return 0

    print("\nCargando a la tabla `dqo`…")
    enviadas, insertadas = cargar(lecturas)
    print(f"  Enviadas: {enviadas:,}  |  Insertadas: {insertadas:,}  "
          f"|  Omitidas (duplicadas): {enviadas - insertadas:,}")
    print("\n✓ Proceso completado.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
