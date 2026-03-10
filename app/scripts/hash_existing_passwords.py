from pathlib import Path
import sys

# Permite importar "app.*" al ejecutar el script desde C:\API_Ingear
sys.path.append(str(Path(__file__).resolve().parents[2]))

from app.db.session import SessionLocal
from app.models.empleado import Empleado
from app.core.security import hash_password


def already_hashed(value: str | None) -> bool:
    return bool(value) and value.startswith("$2")


def main():
    db = SessionLocal()
    total = 0
    migrated = 0
    skipped = 0
    missing = 0

    try:
        empleados = db.query(Empleado).all()

        for emp in empleados:
            total += 1

            current_password = (emp.contrasena or "").strip()

            if already_hashed(current_password):
                skipped += 1
                continue

            if not current_password:
                # Fallback si alguna fila no tiene contraseña cargada
                fallback = (emp.cedula or "").strip()
                if not fallback:
                    missing += 1
                    print(f"[SIN PASSWORD] id={emp.id} email={emp.email!r}")
                    continue
                current_password = fallback

            emp.contrasena = hash_password(current_password)
            migrated += 1
            print(f"[MIGRADO] id={emp.id} email={emp.email!r}")

        db.commit()

        print("\n--- RESUMEN ---")
        print(f"Total empleados : {total}")
        print(f"Migrados        : {migrated}")
        print(f"Ya hasheados    : {skipped}")
        print(f"Sin password    : {missing}")

    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
