# appy.py — 10ynueve • Sistema de Sellos
# Requisitos en requirements.txt:
# streamlit
# supabase
# python-dateutil

from _future_ import annotations
import re
from datetime import date, datetime
import streamlit as st
from supabase import create_client, Client

# ==============================
#  Configuración / conexión
# ==============================
# Coloca estos dos valores en Streamlit Cloud > Manage app > Secrets
# [general]
# SUPABASE_URL = "https://TU-PROJECTID.supabase.co"
# SUPABASE_ANON_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."

SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_ANON_KEY = st.secrets["SUPABASE_ANON_KEY"]
supabase: Client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)

# Nombres de tablas/vistas
T_CUSTOMERS = "Customers"              # columnas: "Name" text, "Phone" text (único)
T_TARJETAS  = "TARJETAS"               # id_tarjeta text, TELEFONO text, FECHA_INICIO date, FECHA_FIN date null, ESTADO text, NUMERO_TARJETA int
T_COMPRAS   = "COMPRAS"                # TELEFONO text, FECHA date, SELLO_OTORGADO bool (opcional)
T_DESCUENTOS = "DESCUENTOS"            # ID_DESCUENTO, DESCRIPCION, TIPO, VAL, ACTIVO (1=activo)
V_CUSTOMERS_API = "customers_api"      # vista minúsculas: name, phone

# ==============================
#  Utilidades de datos
# ==============================
def normalize_phone(raw: str) -> str:
    """Deja solo dígitos."""
    return "".join(re.findall(r"\d+", raw or ""))

def ensure_customers_view():
    """
    Crea/actualiza la vista customers_api (minúsculas).
    name -> "Name", phone -> "Phone"
    """
    # Usamos RPC SQL directo con PostgREST vía Supabase SQL (usa admin UI normalmente),
    # pero aquí lo hacemos con RPC 'query' del cliente Python.
    # Si falla por permisos en free tier, el app sigue; la consulta al fallback usa la tabla directa.
    sql = """
    create or replace view customers_api as
    select "Name"  as name,
           "Phone" as phone
    from "Customers";
    """
    try:
        # Supabase python SDK no tiene método SQL nativo; pero muchas instalaciones lo exponen via
        # rest:/rpc ejecutando funciones. Si no hay una RPC definida, ignoramos.
        # Así que mejor: intentamos leer la vista; si no existe, el SELECT fallará
        supabase.table(V_CUSTOMERS_API).select("*").limit(1).execute()
    except Exception:
        try:
            # Truco: si no existe la vista, mostramos la instrucción para crearla
            st.info(
                "Sugerencia (una sola vez): crea la vista customers_api en Supabase con:\n\n"
                "sql\n"
                "create or replace view customers_api as\n"
                'select "Name" as name, "Phone" as phone from "Customers";\n'
                "\n",
                icon="ℹ",
            )
        except Exception:
            pass

def get_customer_by_phone(phone: str) -> dict | None:
    """
    Busca cliente por teléfono usando la VISTA (si existe).
    Devuelve dict {name, phone} o None.
    """
    phone = normalize_phone(phone)
    try:
        res = (
            supabase.table(V_CUSTOMERS_API)
            .select("*")
            .eq("phone", phone)
            .maybe_single()
            .execute()
        )
        if res and hasattr(res, "data") and res.data:
            return res.data
    except Exception:
        # Fallback directo a tabla (por si la vista no existe)
        try:
            res = (
                supabase.table(T_CUSTOMERS)
                .select(' "Name", "Phone" ')
                .eq("Phone", phone)
                .maybe_single()
                .execute()
            )
            if res and hasattr(res, "data") and res.data:
                d = res.data
                return {"name": d.get("Name"), "phone": d.get("Phone")}
        except Exception:
            return None
    return None

def create_customer(name: str, phone: str) -> bool:
    """
    Inserta cliente si no existe. True si inserta o ya existe; False si error.
    """
    phone = normalize_phone(phone)
    # ¿ya existe?
    if get_customer_by_phone(phone):
        return True
    try:
        supabase.table(T_CUSTOMERS).insert(
            {"Name": (name or "").strip(), "Phone": phone}
        ).execute()
        return True
    except Exception:
        return False

def next_card_number() -> int:
    """
    Lee el máximo NUMERO_TARJETA y suma 1. Si no hay tarjetas, regresa 1.
    """
    try:
        res = (
            supabase.table(T_TARJETAS)
            .select("NUMERO_TARJETA")
            .order("NUMERO_TARJETA", desc=True)
            .limit(1)
            .execute()
        )
        if res and res.data:
            return int(res.data[0]["NUMERO_TARJETA"]) + 1
    except Exception:
        pass
    return 1

def ensure_open_card(phone: str) -> dict:
    """
    Devuelve tarjeta abierta del cliente. Si no existe, la crea.
    Retorno dict con id_tarjeta, TELEFONO, NUMERO_TARJETA, FECHA_INICIO, ESTADO.
    """
    phone = normalize_phone(phone)
    # ¿Existe ya abierta?
    res = (
        supabase.table(T_TARJETAS)
        .select("*")
        .eq("TELEFONO", phone)
        .eq("ESTADO", "abierta")
        .maybe_single()
        .execute()
    )
    if res and res.data:
        return res.data

    # Crear nueva
    num = next_card_number()
    card_id = f"T-{num:03d}"
    today = date.today().isoformat()
    obj = {
        "id_tarjeta": card_id,
        "TELEFONO": phone,
        "FECHA_INICIO": today,
        "FECHA_FIN": None,
        "ESTADO": "abierta",
        "NUMERO_TARJETA": num,
    }
    supabase.table(T_TARJETAS).insert(obj).execute()
    return obj

def get_stamps_count_since_start(phone: str, start_date: str) -> int:
    """Cuenta sellos (compras) de ese teléfono desde la FECHA_INICIO de la tarjeta."""
    phone = normalize_phone(phone)
    try:
        res = (
            supabase.table(T_COMPRAS)
            .select("FECHA")
            .eq("TELEFONO", phone)
            .gte("FECHA", start_date)
            .execute()
        )
        return len(res.data or [])
    except Exception:
        return 0

def get_today_stamp_status(phone: str) -> bool:
    """Regresa True si HOY ya hay sello para ese teléfono."""
    phone = normalize_phone(phone)
    today = date.today().isoformat()
    try:
        res = (
            supabase.table(T_COMPRAS)
            .select("FECHA")
            .eq("TELEFONO", phone)
            .eq("FECHA", today)
            .limit(1)
            .execute()
        )
        return bool(res.data)
    except Exception:
        return False

def give_stamp(phone: str) -> bool:
    """Inserta un sello (compra) HOY para ese teléfono."""
    phone = normalize_phone(phone)
    try:
        supabase.table(T_COMPRAS).insert(
            {"TELEFONO": phone, "FECHA": date.today().isoformat(), "SELLO_OTORGADO": True}
        ).execute()
        return True
    except Exception:
        return False

def get_discounts_catalog() -> list[dict]:
    """
    Devuelve lista ordenada por ID_DESCUENTO ascendente de descuentos activos.
    Cada item con: DESCRIPCION, TIPO, VAL
    """
    try:
        res = (
            supabase.table(T_DESCUENTOS)
            .select("ID_DESCUENTO, DESCRIPCION, TIPO, VAL, ACTIVO")
            .eq("ACTIVO", 1)
            .order("ID_DESCUENTO", desc=False)
            .execute()
        )
        return res.data or []
    except Exception:
        return []

def format_discount(desc: str, tipo: str, val) -> str:
    """Texto bonito del descuento."""
    if (tipo or "").upper().startswith("PORC"):
        try:
            n = float(val)
            pct = f"{n:.0f}%"
        except Exception:
            pct = f"{val}%"
        return f"{desc} ({pct})"
    return desc or "PROMO"

# ==============================
#  UI — Streamlit
# ==============================
st.set_page_config(page_title="10ynueve — Sistema de Sellos", page_icon="⭐", layout="wide")
st.markdown(
    """
    <style>
    .stAlert > div{ font-size: 1rem; }
    .big-title{ font-size: 2.2rem; font-weight: 800; }
    .card{ border-radius: 10px; padding: 12px 16px; margin: 6px 0; }
    .card.blue{ background:#0ea5e9; color:white; }
    .card.green{ background:#10b981; color:white; }
    .card.lime{ background:#84cc16; color:#1b2705; font-weight:700;}
    .card.teal{ background:#14b8a6; color:white;}
    .card.slate{ background:#1f2937; color:#e5e7eb;}
    .btn{ background:#ef4444; color:white; padding:.5rem 1rem; border-radius:.5rem; font-weight:700;}
    </style>
    """,
    unsafe_allow_html=True
)

st.markdown('<div class="big-title">10ynueve — Sistema de Sellos</div>', unsafe_allow_html=True)
st.caption("Listo para sellar cuando quieras. ✨🐾")

ensure_customers_view()

mode = st.radio("Selecciona una opción:", ["Cliente Perrón", "Nuevo Cliente"], horizontal=True)

phone_input = st.text_input("Ingresa el número de teléfono del cliente:", max_chars=20)
col_b = st.columns([1, 4])[0]
buscar = col_b.button("Buscar", use_container_width=False)

# ==============================
#  Lógica — CLIENTE PERRÓN
# ==============================
if buscar and mode == "Cliente Perrón":
    phone = normalize_phone(phone_input)
    if not phone:
        st.error("Escribe un teléfono válido.")
    else:
        # 1) Buscar cliente
        cust = get_customer_by_phone(phone)
        if not cust:
            st.error("Cliente no encontrado en Customers.")
        else:
            st.markdown(
                f'<div class="card green">Cliente encontrado: <b>{cust["name"]}</b> · {cust["phone"]}</div>',
                unsafe_allow_html=True,
            )
            # 2) Asegurar tarjeta abierta
            card = ensure_open_card(phone)
            st.markdown(
                f'<div class="card blue">Tarjeta activa: <b>{card["id_tarjeta"]}</b> · '
                f'Estado: <i>{card["ESTADO"]}</i> · Número: <b>{card["NUMERO_TARJETA"]}</b> · '
                f'Inicio: <b>{card["FECHA_INICIO"]}</b></div>',
                unsafe_allow_html=True,
            )
            # 3) Conteo de sellos + descuento vigente
            sellos = get_stamps_count_since_start(phone, card["FECHA_INICIO"])
            st.markdown(f'<div class="card teal">Sellos acumulados: <b>{sellos}</b></div>', unsafe_allow_html=True)

            descuentos = get_discounts_catalog()
            # índice = sellos actuales (si 0 → 1er descuento, si 1 → 2do, etc.)
            if sellos < len(descuentos):
                d = descuentos[sellos]
                desc_txt = format_discount(d.get("DESCRIPCION",""), d.get("TIPO",""), d.get("VAL"))
            else:
                desc_txt = "Sin descuento (completa la tarjeta 😉)"
            st.markdown(f'<div class="card lime">Descuento actual: {desc_txt}</div>', unsafe_allow_html=True)

            # 4) Candado: un sello por día
            if get_today_stamp_status(phone):
                st.warning("Tarjeta sellada hoy, vuelve mañana por más sellos. 🛑")
            else:
                if st.button("Sellar hoy", type="primary"):
                    ok = give_stamp(phone)
                    if ok:
                        st.success("Tarjeta sellada por Greg!! 🐾")
                        # Mostrar nuevo conteo
                        ns = get_stamps_count_since_start(phone, card["FECHA_INICIO"])
                        st.info(f"Sellos acumulados ahora: {ns}")
                    else:
                        st.error("No se pudo registrar el sello. Intenta de nuevo.")

# ==============================
#  Lógica — NUEVO CLIENTE
# ==============================
if buscar and mode == "Nuevo Cliente":
    phone = normalize_phone(phone_input)
    if not phone:
        st.error("Escribe un teléfono válido.")
    else:
        # ¿ya existe?
        exists = get_customer_by_phone(phone)
        st.subheader("Dar de alta nuevo cliente")
        name = st.text_input("Nombre", value="" if not exists else exists.get("name") or "")

        if st.button("Registrar cliente y abrir tarjeta", type="primary"):
            if exists:
                st.warning("Ese número ya tiene registro. No se creó un nuevo cliente.")
                card = ensure_open_card(phone)
                st.success(
                    f'Cliente <b>{exists["name"]}</b> confirmado. Tarjeta activa <b>{card["id_tarjeta"]}</b>.',
                    icon="✅"
                )
                st.markdown("Listo para sellar cuando quieras. ✨🐾")
            else:
                if not name.strip():
                    st.error("El nombre es obligatorio.")
                else:
                    if create_customer(name, phone):
                        card = ensure_open_card(phone)
                        st.success(
                            f'Cliente <b>{name}</b> registrado con tarjeta <b>{card["id_tarjeta"]}</b>.',
                            icon="✅"
                        )
                        st.markdown("Listo para sellar cuando quieras. ✨🐾")
                    else:
                        st.error("No se pudo registrar el cliente. Revisa conexión/permiso.")
