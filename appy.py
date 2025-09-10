import re
from datetime import date, datetime
import streamlit as st
from supabase import create_client, Client

# ================================
# Configuración: claves en st.secrets
# ================================
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_ANON_KEY = st.secrets["SUPABASE_ANON_KEY"]
supabase: Client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)

# ================================
# Helpers de BD y negocio
# ================================

def normalize_phone(raw: str) -> str:
    """Deja solo dígitos."""
    return "".join(re.findall(r"\d+", raw or ""))

def get_customer_by_phone(phone: str):
    """
    Lee vía VISTA customers_api (name/phone en minúsculas).
    Devuelve dict o None.
    """
    res = (
        supabase.table("customers_api")
        .select("*")
        .eq("phone", phone)
        .maybe_single()
        .execute()
    )
    return res.data  # dict | None

def create_customer(name: str, phone: str):
    """Inserta en Customers (respetando mayúsculas del esquema)."""
    return (
        supabase.table("Customers")
        .insert({"Name": (name or "").strip(), "Phone": (phone or "").strip()})
        .execute()
    )

def next_card_id() -> str:
    """
    Genera ID_TARJETA tipo T-001, T-002… (correlativo global).
    """
    res = supabase.table("TARJETAS").select("ID_TARJETA", count="exact").execute()
    count = res.count or 0
    return f"T-{count+1:03d}"

def ensure_open_card(phone: str) -> dict:
    """
    Si el cliente ya tiene una tarjeta abierta, la regresa.
    Si no, crea una nueva abierta con NUMERO_TARJETA=1.
    """
    # ¿ya hay abierta?
    open_card = (
        supabase.table("TARJETAS")
        .select("*")
        .eq("TELEFONO", phone)
        .eq("ESTADO", "abierta")
        .maybe_single()
        .execute()
        .data
    )
    if open_card:
        return open_card

    # crear nueva
    new_id = next_card_id()
    hoy = date.today().isoformat()
    payload = {
        "ID_TARJETA": new_id,
        "TELEFONO": phone,
        "FECHA_INICIO": hoy,
        "FECHA_FIN": None,
        "ESTADO": "abierta",
        "NUMERO_TARJETA": 1,
    }
    supabase.table("TARJETAS").insert(payload).execute()

    return (
        supabase.table("TARJETAS")
        .select("*")
        .eq("ID_TARJETA", new_id)
        .maybe_single()
        .execute()
        .data
    )

def contar_sellos(phone: str, desde_iso: str | None) -> int:
    """
    Cuenta sellos en COMPRAS para ese teléfono desde FECHA_INICIO (si viene).
    """
    q = supabase.table("COMPRAS").select("ID_COMPRA", count="exact").eq("TELEFONO", phone)
    if desde_iso:
        q = q.gte("FECHA", desde_iso)
    res = q.execute()
    return res.count or 0

def sello_ya_hecho_hoy(phone: str) -> bool:
    """Candado: ¿ya hay compra hoy?"""
    hoy = date.today().isoformat()
    res = (
        supabase.table("COMPRAS")
        .select("ID_COMPRA", count="exact")
        .eq("TELEFONO", phone)
        .eq("FECHA", hoy)
        .execute()
    )
    return (res.count or 0) > 0

def sellar(phone: str) -> tuple[bool, str]:
    """
    Inserta compra si no hay sello hoy. Devuelve (ok, mensaje).
    """
    if sello_ya_hecho_hoy(phone):
        return False, "Tarjeta sellada hoy, vuelve mañana por más sellos."

    # generar ID_COMPRA simple: C-### (conteo global)
    res = supabase.table("COMPRAS").select("ID_COMPRA", count="exact").execute()
    nxt = (res.count or 0) + 1
    comp_id = f"C-{nxt:03d}"

    payload = {
        "ID_COMPRA": comp_id,
        "TELEFONO": phone,
        "FECHA": date.today().isoformat(),
        "SELLO_OTORGADO": None,
    }
    supabase.table("COMPRAS").insert(payload).execute()
    return True, "Tarjeta sellada por Greg!! 🐾"

def descuento_actual(num_sellos: int) -> tuple[str, str]:
    """
    Lee DESCUENTOS y escoge fila por índice de sellos (capping al máximo).
    Muestra 'DESCRIPCION (VAL%)' si tipo = PORCENTAJE, o descripción tal cual si PROMO.
    """
    res = (
        supabase.table("DESCUENTOS")
        .select("*")
        .eq("ACTIVO", 1)
        .order("ID_DESCUENTO", desc=False)
        .execute()
    )
    rows = res.data or []
    if not rows:
        return "Sin descuento", ""

    idx = min(max(num_sellos, 0), len(rows) - 1)
    d = rows[idx]
    tipo = (d.get("TIPO") or "").upper()
    val = d.get("VAL")
    desc = d.get("DESCRIPCION") or ""

    if tipo == "PORCENTAJE" and val is not None:
        return f"{desc}", f"({float(val):.1f}%)"
    else:
        return f"{desc}", ""

# ================================
# Estilos (pastillas / look & feel)
# ================================
st.set_page_config(page_title="10ynueve — Sistema de Sellos", page_icon="⭐", layout="wide")
st.markdown(
    """
    <style>
    .pill{
        padding:12px 16px; border-radius:12px; margin:8px 0;
        background:#164e63; color:#e6fffa; font-weight:600;
        box-shadow: inset 0 0 0 1px rgba(255,255,255,0.1);
    }
    .pill.ok{ background:#14532d; }
    .pill.warn{ background:#3f2e06; }
    .pill.error{ background:#5b1111; }
    .title{
        font-size:44px; font-weight:800; margin-top:8px; margin-bottom:12px;
        letter-spacing:.5px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ================================
# UI
# ================================
st.markdown("<div class='title'>10ynueve — Sistema de Sellos</div>", unsafe_allow_html=True)
st.caption("Listo para sellar cuando quieras. ✨🐾")

modo = st.radio("Selecciona una opción:", ["Cliente Perrón", "Nuevo Cliente"], horizontal=True)
phone_raw = st.text_input("Ingresa el número de teléfono del cliente:", "")
phone = normalize_phone(phone_raw)

# ---------- NUEVO CLIENTE ----------
if modo == "Nuevo Cliente":
    st.subheader("Dar de alta nuevo cliente")
    nombre = st.text_input("Nombre", "")

    if st.button("Registrar cliente y abrir tarjeta", type="primary"):
        if not phone or len(phone) < 8:
            st.error("Teléfono inválido.")
            st.stop()
        if not nombre.strip():
            st.error("El nombre es obligatorio.")
            st.stop()

        ya = get_customer_by_phone(phone)
        if ya:
            # Ya existe: avisar y NO duplicar
            st.warning(f"Este número ya está registrado como *{ya['name']}*.")
            # Asegurar tarjeta abierta de todos modos
            card = ensure_open_card(phone)
            st.markdown(
                f"<div class='pill'>Tarjeta activa: <b>{card['ID_TARJETA']}</b> · "
                f"Estado: <i>{card['ESTADO']}</i> · Número: <b>{card['NUMERO_TARJETA']}</b> · "
                f"Inicio: <b>{card['FECHA_INICIO']}</b></div>",
                unsafe_allow_html=True
            )
        else:
            # Crear y abrir tarjeta
            create_customer(nombre, phone)
            card = ensure_open_card(phone)
            st.success(f"Cliente {nombre} registrado con tarjeta *{card['ID_TARJETA']}*.")
            st.caption("Listo para sellar cuando quieras. ✨🐾")

    st.stop()  # no continúa a la sección de búsqueda

# ---------- CLIENTE PERRÓN ----------
if st.button("Buscar", type="primary"):
    try:
        if not phone:
            st.warning("Ingresa un teléfono válido.")
            st.stop()

        cust = get_customer_by_phone(phone)
        if not cust:
            st.error("Cliente no encontrado en Customers.")
            with st.expander("Sugerencia si usas la vista"):
                st.code(
                    'CREATE OR REPLACE VIEW customers_api AS\n'
                    'SELECT "Name" AS name, "Phone" AS phone\nFROM "Customers";'
                )
            st.stop()

        st.markdown(f"<div class='pill ok'>Cliente encontrado: <b>{cust['name']}</b> · {cust['phone']}</div>", unsafe_allow_html=True)

        card = ensure_open_card(phone)
        st.markdown(
            f"<div class='pill'>Tarjeta activa: <b>{card['ID_TARJETA']}</b> · "
            f"Estado: <i>{card['ESTADO']}</i> · Número: <b>{card['NUMERO_TARJETA']}</b> · "
            f"Inicio: <b>{card['FECHA_INICIO']}</b></div>",
            unsafe_allow_html=True
        )

        sellos = contar_sellos(phone, card.get("FECHA_INICIO"))
        st.markdown(f"<div class='pill ok'>Sellos acumulados: <b>{sellos}</b></div>", unsafe_allow_html=True)
        txt, det = descuento_actual(sellos)
        st.markdown(f"<div class='pill warn'>Descuento actual: <b>{txt} {det}</b></div>", unsafe_allow_html=True)

        if st.button("Sellar ahora 🔐"):
            ok, msg = sellar(phone)
            if ok:
                st.success("Tarjeta sellada por Greg!! 🐾")
            else:
                st.warning("Tarjeta sellada hoy, vuelve mañana por más sellos.")

            # Refrescar vista
            sellos = contar_sellos(phone, card.get("FECHA_INICIO"))
            st.markdown(f"<div class='pill ok'>Sellos acumulados (actualizado): <b>{sellos}</b></div>", unsafe_allow_html=True)
            txt, det = descuento_actual(sellos)
            st.markdown(f"<div class='pill warn'>Descuento actual: <b>{txt} {det}</b></div>", unsafe_allow_html=True)

    except Exception as e:
        st.error("Falló al consultar cliente.")
        st.code(f"{type(e)._name_}: {e}")
