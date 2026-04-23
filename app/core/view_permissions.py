from collections.abc import Iterable

from app.core.security import infer_role, normalize


COMMERCIAL_VIEW_PERMISSION_VERSION_MARKER = "comercial.views.v2"

COMMERCIAL_VIEW_PERMISSIONS = (
    "comercial.cotizador",
    "comercial.oportunidades",
    "comercial.proyectos",
    "comercial.cuentas-cobro",
    "comercial.clientes",
    "comercial.contactos",
    "comercial.productos",
)

COMMERCIAL_VIEW_PERMISSION_SET = set(COMMERCIAL_VIEW_PERMISSIONS)
COMMERCIAL_VIEW_PERMISSION_ALLOWED_SET = COMMERCIAL_VIEW_PERMISSION_SET | {
    COMMERCIAL_VIEW_PERMISSION_VERSION_MARKER
}


def normalize_view_permissions(
    permissions: Iterable[str] | None,
) -> list[str] | None:
    if permissions is None:
        return None

    dedup: dict[str, str] = {}

    for item in permissions:
        value = str(item or "").strip().lower()
        if not value:
            continue
        dedup[value] = value

    return list(dedup.values())


def normalize_commercial_view_permissions(
    permissions: Iterable[str] | None,
) -> list[str] | None:
    normalized = normalize_view_permissions(permissions)
    if normalized is None:
        return None

    return [
        permission
        for permission in normalized
        if permission in COMMERCIAL_VIEW_PERMISSION_SET
    ]


def has_view_permission_version_marker(
    permissions: Iterable[str] | None,
) -> bool:
    normalized = normalize_view_permissions(permissions) or []
    return COMMERCIAL_VIEW_PERMISSION_VERSION_MARKER in normalized


def expand_legacy_view_permissions(
    area: str | None,
    cargo: str | None,
    permissions: Iterable[str],
) -> list[str]:
    role = infer_role(area, cargo)
    selected = {
        permission
        for permission in permissions
        if permission in COMMERCIAL_VIEW_PERMISSION_SET
    }

    if (
        role in {"LOGISTICA", "INGENIERIA"}
        or "comercial.cotizador" in selected
        or "comercial.oportunidades" in selected
    ):
        selected.update(
            {"comercial.proyectos", "comercial.cuentas-cobro"}
        )

    return [
        permission
        for permission in COMMERCIAL_VIEW_PERMISSIONS
        if permission in selected
    ]


def infer_legacy_view_permissions(area: str | None, cargo: str | None) -> list[str]:
    role = infer_role(area, cargo)
    cargo_normalized = normalize(cargo)

    if role == "GERENCIA":
        return list(COMMERCIAL_VIEW_PERMISSIONS)

    permissions: list[str] = []

    if role == "COMERCIAL":
        permissions.append("comercial.cotizador")

    if cargo_normalized in {
        "gerente",
        "lider de proyectos de iluminacion",
        "gerente comercial",
        "analista de costos y presupuestos",
    }:
        permissions.append("comercial.oportunidades")

    if (
        "comercial.cotizador" in permissions
        or "comercial.oportunidades" in permissions
    ):
        permissions.extend(
            ["comercial.clientes", "comercial.contactos"]
        )

    if role == "GERENCIA" or cargo_normalized == "analista de costos y presupuestos":
        permissions.append("comercial.productos")

    return expand_legacy_view_permissions(
        area,
        cargo,
        normalize_commercial_view_permissions(permissions) or [],
    )


def resolve_view_permissions(
    area: str | None,
    cargo: str | None,
    permissions: Iterable[str] | None,
) -> list[str]:
    role = infer_role(area, cargo)

    if role == "GERENCIA":
        return list(COMMERCIAL_VIEW_PERMISSIONS)

    normalized = normalize_view_permissions(permissions)
    if normalized is None:
        return infer_legacy_view_permissions(area, cargo)

    selected = normalize_commercial_view_permissions(normalized) or []
    if has_view_permission_version_marker(normalized):
        return selected

    return expand_legacy_view_permissions(area, cargo, selected)


def has_view_permission(
    current,
    permission: str,
) -> bool:
    value = str(permission or "").strip().lower()
    if not value:
        return False

    current_permissions = resolve_view_permissions(
        getattr(current, "area", None),
        getattr(current, "cargo", None),
        getattr(current, "permisos_vistas", None),
    )
    return value in current_permissions
