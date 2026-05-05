"""
Utilidad de consola para gestionar usuarios del Dashboard PTAR.
Uso:
    python gestionar_usuarios.py agregar
    python gestionar_usuarios.py eliminar
    python gestionar_usuarios.py listar
"""
import sys
import bcrypt
import yaml
from pathlib import Path

CREDENTIALS_FILE = Path("credentials.yaml")


def cargar() -> dict:
    with open(CREDENTIALS_FILE, encoding="utf-8") as f:
        return yaml.safe_load(f)


def guardar(config: dict) -> None:
    with open(CREDENTIALS_FILE, "w", encoding="utf-8") as f:
        yaml.dump(config, f, allow_unicode=True, default_flow_style=False)
    print(f"Cambios guardados en {CREDENTIALS_FILE}")


def listar(config: dict) -> None:
    usuarios = config["credentials"]["usernames"]
    if not usuarios:
        print("No hay usuarios registrados.")
        return
    print(f"\n{'Usuario':<20} {'Nombre':<30} {'Email':<35} {'Roles'}")
    print("-" * 90)
    for username, info in usuarios.items():
        nombre = f"{info.get('first_name','')} {info.get('last_name','')}".strip()
        roles  = ", ".join(info.get("roles", []))
        print(f"{username:<20} {nombre:<30} {info.get('email',''):<35} {roles}")


def agregar(config: dict) -> None:
    print("\n── Agregar usuario ──")
    username   = input("Nombre de usuario (sin espacios): ").strip()
    if not username:
        print("Nombre vacío, cancelado.")
        return
    if username in config["credentials"]["usernames"]:
        print(f"El usuario '{username}' ya existe.")
        return

    first_name = input("Nombre: ").strip()
    last_name  = input("Apellido: ").strip()
    email      = input("Email: ").strip()
    password   = input("Contraseña: ").strip()
    roles_str  = input("Roles (separados por coma, ej: admin,viewer) [viewer]: ").strip()
    roles      = [r.strip() for r in roles_str.split(",")] if roles_str else ["viewer"]

    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

    config["credentials"]["usernames"][username] = {
        "email":                email,
        "first_name":           first_name,
        "last_name":            last_name,
        "logged_in":            False,
        "failed_login_attempts": 0,
        "password":             hashed,
        "roles":                roles,
    }
    guardar(config)
    print(f"\nUsuario '{username}' creado correctamente.")


def eliminar(config: dict) -> None:
    print("\n── Eliminar usuario ──")
    listar(config)
    username = input("\nUsuario a eliminar: ").strip()
    if username not in config["credentials"]["usernames"]:
        print(f"El usuario '{username}' no existe.")
        return
    confirm = input(f"¿Eliminar '{username}'? (s/N): ").strip().lower()
    if confirm == "s":
        del config["credentials"]["usernames"][username]
        guardar(config)
        print(f"Usuario '{username}' eliminado.")
    else:
        print("Cancelado.")


if __name__ == "__main__":
    if not CREDENTIALS_FILE.exists():
        print(f"No se encontró {CREDENTIALS_FILE}")
        sys.exit(1)

    config = cargar()
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""

    if cmd == "agregar":
        agregar(config)
    elif cmd == "eliminar":
        eliminar(config)
    elif cmd == "listar":
        listar(config)
    else:
        print(__doc__)
