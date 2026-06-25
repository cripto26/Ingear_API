BUSINESS_TEXT_COLUMNS: dict[str, tuple[str, ...]] = {
    "apu": ("tipo_producto", "categoria"),
    "cliente": (
        "razon_social",
        "nit",
        "telefono",
        "direccion",
        "ciudad",
        "tipo_contribuyente",
        "actividad_economica",
    ),
    "contacto": ("empresa", "nombre", "telefono", "ciudad"),
    "cotizacion": (
        "tiempo_entrega",
        "nombre_cotizacion",
        "tipo_cotizacion",
        "etapa_cotizacion",
        "forma_pago",
        "contacto",
        "tipo_servicio",
    ),
    "cotizacion_versiones_v2": (
        "tiempo_entrega",
        "nombre_cotizacion",
        "tipo_cotizacion",
        "etapa_cotizacion",
        "forma_pago",
        "contacto",
        "tipo_servicio",
    ),
    "cuenta_cobro": (
        "cliente_nombre",
        "nit",
        "direccion",
        "telefono",
        "proyecto",
        "numero_contrato",
    ),
    "despachos": (
        "transportadora",
        "guia",
        "ciudad_origen",
        "contacto",
        "estado",
        "ciudad_destino",
    ),
    "empleado": (
        "nombre",
        "cargo",
        "area",
        "estado",
        "cedula",
        "telefono",
    ),
    "notificacion": ("area", "titulo", "mensaje"),
    "oportunidad": (
        "nombre_proyecto",
        "tipo_contacto",
        "ciudad",
        "tipo_servicio",
        "responsable_cotizacion",
        "marca_predominante",
        "nivel_importancia",
        "porcentaje_cierre",
        "segmento",
        "observaciones",
        "nuevo_existente",
    ),
    "pais": ("pais",),
    "producto": (
        "referencia",
        "marca",
        "descripcion",
        "pais_origen",
        "ciudad",
        "categoria",
        "tipo_producto",
        "moneda",
    ),
    "proyecto": (
        "nombre",
        "estado_logistica",
        "estado_contable",
        "estado_ingenieria",
        "estado_factura",
        "observacion",
    ),
}


def normalize_business_text_values(target: object) -> None:
    table = getattr(target, "__table__", None)
    table_name = getattr(table, "name", None)

    for field_name in BUSINESS_TEXT_COLUMNS.get(table_name, ()):
        value = getattr(target, field_name, None)
        if isinstance(value, str):
            setattr(target, field_name, value.upper())
