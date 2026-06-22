from __future__ import annotations

import argparse
import json
import re
import unicodedata
from collections import defaultdict
from datetime import datetime
from typing import Any, Iterable

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.cliente import Cliente
from app.models.contacto import Contacto
from app.services.world_office_inventory_service import _connect


PERSON_DOCUMENT_TYPES = {
    "CC",
    "CEDULA DE EXTRANJERIA",
    "DOCUMENTO DE IDENTIFICACION EXTRANJERO",
    "DOCUMENTO EXTRANJERO",
    "PASAPORTE",
}


def _ascii(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    return "".join(char for char in text if not unicodedata.combining(char))


def _text(value: object, limit: int | None = None) -> str | None:
    clean = " ".join(str(value or "").strip().split())
    if not clean:
        return None
    return clean[:limit] if limit else clean


def _business_text(value: object, limit: int | None = None) -> str | None:
    clean = _text(value, limit)
    return clean.upper() if clean else None


def _lookup(value: object) -> str:
    return re.sub(r"[^A-Z0-9]", "", _ascii(value).upper())


def _email(value: object) -> str:
    return str(value or "").strip().casefold()


def _phone(value: object) -> str:
    return re.sub(r"\D", "", str(value or ""))


def _full_name(row: dict[str, Any]) -> str | None:
    return _business_text(
        " ".join(
            filter(
                None,
                (
                    _text(row.get("primer_nombre")),
                    _text(row.get("segundo_nombre")),
                    _text(row.get("primer_apellido")),
                    _text(row.get("segundo_apellido")),
                ),
            )
        ),
        255,
    )


def _load_world_office_customers() -> list[dict[str, Any]]:
    connection = _connect()
    try:
        cursor = connection.cursor()
        cursor.execute(
            """
            SELECT
                Tipo_Identificacion,
                Identificacion,
                Digito_Verificacion,
                Codigo,
                Primer_Nombre,
                Segundo_Nombre,
                Primer_Apellido,
                Segundo_Apellido,
                [Dirección],
                Ciudad_Direccion,
                [Teléfonos],
                Telefono2,
                Movil1,
                EMail,
                Tipo_Contribuyente,
                Codigo_Actividad_Economica,
                Descripcion_Actividad_Economica,
                FechaDeCreacion
            FROM Vista_Auxiliar_Terceros
            WHERE Propiedades LIKE '%Cliente%'
              AND NULLIF(LTRIM(RTRIM(Identificacion)), '') IS NOT NULL
            """
        )
        columns = [_ascii(column[0]).casefold() for column in cursor.description]
        return [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]
    finally:
        connection.close()


def _index_unique(
    rows: Iterable[dict[str, Any]], key_builder
) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        key = key_builder(row)
        if key:
            grouped[key].append(row)
    return {key: values[0] for key, values in grouped.items() if len(values) == 1}


def _set_if_present(target: object, field: str, value: object) -> bool:
    if value is None or value == "":
        return False
    if getattr(target, field) == value:
        return False
    setattr(target, field, value)
    return True


def _sync(commit: bool) -> dict[str, int | bool]:
    source_rows = _load_world_office_customers()
    source_by_id = _index_unique(source_rows, lambda row: _lookup(row["identificacion"]))
    person_rows = [
        row
        for row in source_rows
        if _ascii(row["tipo_identificacion"]).upper().strip()
        in PERSON_DOCUMENT_TYPES
    ]
    people_by_email = _index_unique(person_rows, lambda row: _email(row["email"]))
    people_by_phone = _index_unique(
        person_rows,
        lambda row: _phone(
            row["telefonos"] or row["movil1"] or row["telefono2"]
        ),
    )
    people_by_name = _index_unique(person_rows, lambda row: _lookup(_full_name(row)))

    db = SessionLocal()
    stats: dict[str, int | bool] = {
        "commit": commit,
        "world_office_customers": len(source_rows),
        "matched_clients": 0,
        "updated_clients": 0,
        "matched_contacts": 0,
        "updated_contacts": 0,
    }
    try:
        for client in db.scalars(select(Cliente)).all():
            row = source_by_id.get(_lookup(client.nit))
            if row is None and client.nit and "-" in client.nit:
                row = source_by_id.get(_lookup(client.nit.rsplit("-", 1)[0]))
            if row is None:
                continue

            stats["matched_clients"] += 1
            phone = _business_text(
                row["telefonos"] or row["movil1"] or row["telefono2"], 50
            )
            activity = _business_text(
                row["descripcion_actividad_economica"]
                or row["codigo_actividad_economica"]
            )
            changed = any(
                (
                    _set_if_present(client, "razon_social", _full_name(row)),
                    _set_if_present(client, "telefono", phone),
                    _set_if_present(client, "email", _text(row["email"], 255)),
                    _set_if_present(
                        client,
                        "direccion",
                        _business_text(row["direccion"], 255),
                    ),
                    _set_if_present(
                        client,
                        "ciudad",
                        _business_text(row["ciudad_direccion"], 120),
                    ),
                    _set_if_present(
                        client,
                        "world_office_id",
                        _text(row["codigo"] or row["identificacion"], 80),
                    ),
                    _set_if_present(
                        client,
                        "tipo_contribuyente",
                        _business_text(row["tipo_contribuyente"], 120),
                    ),
                    _set_if_present(client, "actividad_economica", activity),
                    _set_if_present(
                        client,
                        "fecha_creacion",
                        row["fechadecreacion"]
                        if isinstance(row["fechadecreacion"], datetime)
                        else None,
                    ),
                )
            )
            if changed:
                stats["updated_clients"] += 1

        for contact in db.scalars(select(Contacto)).all():
            row = None
            for index, key in (
                (people_by_email, _email(contact.email)),
                (people_by_phone, _phone(contact.telefono)),
                (people_by_name, _lookup(contact.nombre)),
            ):
                if key and key in index:
                    row = index[key]
                    break
            if row is None:
                continue

            stats["matched_contacts"] += 1
            phone = _business_text(
                row["telefonos"] or row["movil1"] or row["telefono2"], 50
            )
            changed = any(
                (
                    _set_if_present(contact, "nombre", _full_name(row)),
                    _set_if_present(contact, "telefono", phone),
                    _set_if_present(contact, "email", _text(row["email"], 255)),
                    _set_if_present(
                        contact,
                        "ciudad",
                        _business_text(row["ciudad_direccion"], 120),
                    ),
                )
            )
            if changed:
                stats["updated_contacts"] += 1

        if commit:
            db.commit()
        else:
            db.rollback()
        return stats
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Actualiza clientes y contactos existentes desde World Office."
    )
    parser.add_argument(
        "--commit",
        action="store_true",
        help="Confirma los cambios. Sin esta opcion solo realiza una simulacion.",
    )
    args = parser.parse_args()
    print(json.dumps(_sync(commit=args.commit), ensure_ascii=True, sort_keys=True))


if __name__ == "__main__":
    main()
