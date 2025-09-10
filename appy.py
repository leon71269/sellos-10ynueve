# appy.py — 10ynueve: Sistema de Sellos (Streamlit + Supabase)

import re
from datetime import date
import streamlit as st
from supabase import create_client, Client

# ===========================
# Apariencia / Branding
# ===========================
st.set_page_config(page_title="10ynueve — Sistema de Sellos", page_icon="⭐", layout="wide")
PRIMARY = "#30C594"
ACCENT   = "#FFD166"
st.markdown(
    f"""
    <style>
      .stApp {{
        background: radial-gradient(1200px 600px at 20% -10%, rgba(48,197,148,0.12), transparent),
                    radial-gradient(900px 400px at 100% 10%, rgba(255,209,102,0.12), transparent),
                    #0E1117;
      }}
      .pill {{
        padding:.7rem 1rem;border-radius:.8rem;margin:.25rem 0;font-weight:600;
        background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.08)
      }}
      .pill.ok    {{ background: rgba(48,197,148,.15); border-color: {PRIMARY}33; }}
      .pill.warn  {{ background: rgba(255,209,102,.15); border-color: {ACCENT}44; }}
      .cta button {{ border-radius:.8rem;font-weight:700 }}
    </style>
    """, unsafe_allow_html=True
)

# Pon la URL del perrillo Greg si quieres mostrarla
GREG_IMG_URL = ""

# ===========================
# Descuentos por sello
# (índice = sellos acumulados)
# ===========================
DESCUENTOS = [
    ("10% DE DESCUENTO", 10.0),
    ("5% DE DESCUENTO", 5.0),
    ("SODAS ITALIANAS 2x1", None),
    ("10% DE DESCUENTO", 10.0),
    ("5% DE DESCUENTO", 5.0),
    ("10% DE DESCUENTO", 10.0),
    ("5% DE DESCUENTO", 5.0),
    ("10% DE DESCUENTO", 10.0),
    ("15% DE DESCUENTO", 15.0),
]

# ===========================
# Conexión Supabase (st.secrets)
# ===========================
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_ANON_KEY = st.secrets["SUPABASE_ANON_KEY"]
supabase: Client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)

# ===========================
# Helpers de Datos
# ===========================
def normalize_phone(raw: str) -> str:
    """Deja solo dígitos."""
    return "".join(re.findall(r"\d+", raw or ""))

def get_customer_by_phone(phone: str):
    """Busca en la VISTA customers_api (name/phone en minúsculas)."""
    res = (
        supabase.table("customers_api")
        .select("*")
        .eq("phone", phone)
        .maybe_single()
        .execute()
    )
    return res.data  # dict | None

def create_customer(name: str, phone: str):
    supabase.table("Customers").insert(
        {"Name": (name or "").strip(), "Phone": (phone or "").strip()}
    ).execute()

def next_card_number() -> int:
    """Consecutivo para NUMERO_TARJETA (y ID_TARJETA T-###)."""
    res = supabase.table("TARJETAS").select("ID_TARJETA", count="exact").execute()
    return (res.count or 0) + 1

def ensure_open_card(phone: str) -> dict:
    """Obtén tarjeta abierta o crea una nueva."""
    hoy = date.today().isoformat()
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

    num = next_card_number()
    new_card = {
        "ID_TARJETA": f"T-{num:03d}",
        "TELEFONO": phone,
        "FECHA_INICIO": hoy,
        "FECHA_FIN": None,
        "ESTADO": "abierta",
        "NUMERO_TARJETA": num,
    }
    supabase.table("TARJETAS").insert(new_card).execute()
    return new_card

def compras_hoy_exist(phone: str) -> bool:
    """Candado: 1 sello por día."""
    hoy = date.today().isoformat()
    res = (
        supabase.table("COMPRAS")
        .select("ID_COMPRA", count="exact")
        .eq("TELEFONO", phone)
        .eq("FECHA", hoy)
        .execute()
    )
    return (res.count or 0) > 0

def contar_sellos(phone: str, desde: str | None) -> int:
    """# sellos (filas en COMPRAS) desde FECHA_INICIO de la tarjeta."""
    q = supabase.table("COMPRAS").select("ID_COMPRA", count="exact").eq("TELEFONO", phone)
    if desde:
        q = q.gte("FECHA", desde)
    res = q.execute()
    return res.count or 0

def sellar(phone: str) -> tuple[bool, str]:
    """Intentar sellar; respeta candado. Devuelve (ok, msg)."""
    if compras_hoy_exist(phone):
        return False, "Tarjeta sellada hoy, vuelve mañana por más sellos."

    # ID de compra C-###
    res_cnt = supabase.table("COMPRAS").select("ID_COMPRA", count="exact").execute()
    next_n = (res_cnt.count or 0) + 1
    compra = {
        "ID_COMPRA": f"C-{next_n:03d}",
        "TELEFONO": phone,
        "FECHA": date.today().isoformat(),
        "SELLO_OTORGADO": True,
    }
    supabase.table("COMPRAS").insert(compra).execute()
    return True, "Tarjeta sellada por Greg!! 🐾"

def descuento_actual(num_sellos: int) -> tuple[str, str]:
    """Texto y detalle del descuento según # de sellos."""
    idx = max(0, min(num_sellos, len(DESCUENTOS) - 1))
    texto, pct = DESCUENTOS[idx]
    detalle = f"({pct:.1f}%)" if isinstance(pct, (int, float)) else "(PROMO)"
    return texto, detalle

# ===========================
# UI
# ===========================
col1, col2 = st.columns([1, 3], vertical_alignment="center")
with col1:
    if GREG_IMG_URL:
        st.image(GREG_IMG_URL, caption="Greg", use_container_width=True)
with col2:
    st.markdown("# 10ynueve — Sistema de Sellos")
    st.caption("Listo para sellar cuando quieras. ✨🐾")

modo = st.radio("Selecciona una opción:", ["Cliente Perrón", "Nuevo Cliente"], horizontal=True)
phone_raw = st.text_input("Ingresa el número de teléfono del cliente:", "")
acc = st.button("Buscar", type="primary")

if acc:
    try:
        phone = normalize_phone(phone_raw)
        if not phone:
            st.warning("Ingresa un teléfono válido (10 dígitos).")
            st.stop()

        if modo == "Nuevo Cliente":
            st.subheader("Dar de alta nuevo cliente")
            nombre = st.text_input("Nombre", "")
            if st.button("Registrar cliente y abrir tarjeta"):
                if not nombre.strip():
                    st.error("El nombre es obligatorio.")
                    st.stop()
                # Evita duplicar si ya existe
                if not get_customer_by_phone(phone):
                    create_customer(nombre, phone)
                card = ensure_open_card(phone)
                st.success(f"Cliente {nombre} registrado con tarjeta *{card['ID_TARJETA']}*.")
                st.caption("Listo para sellar cuando quieras. ✨🐾")
            st.stop()

        # ======= Cliente Perrón =======
        cust = get_customer_by_phone(phone)
        if not cust:
            st.error("Cliente no encontrado en Customers.")
            with st.expander("Sugerencia si usas la vista"):
                st.code('CREATE OR REPLACE VIEW customers_api AS\nSELECT "Name" AS name, "Phone" AS phone FROM "Customers";')
            st.stop()

        st.markdown(f"<div class='pill ok'>Cliente encontrado: <b>{cust['name']}</b> · {cust['phone']}</div>", unsafe_allow_html=True)

        card = ensure_open_card(phone)
        st.markdown(
            f"<div class='pill'>Tarjeta activa: <b>{card['ID_TARJETA']}</b> · "
            f"Estado: <i>{card['ESTADO']}</i> · Número: <b>{card['NUMERO_TARJETA']}</b> · "
            f"Inicio: <b>{card['FECHA_INICIO']}</b></div>",
            unsafe_allow_html=True
        )

        # Estado actual
        sellos = contar_sellos(phone, card.get("FECHA_INICIO"))
        st.markdown(f"<div class='pill ok'>Sellos acumulados: <b>{sellos}</b></div>", unsafe_allow_html=True)
        txt, det = descuento_actual(sellos)
        st.markdown(f"<div class='pill warn'>Descuento actual: <b>{txt} {det}</b></div>", unsafe_allow_html=True)

        # CTA sellar
        if st.button("Sellar ahora 🔐", use_container_width=False):
            ok, msg = sellar(phone)
            if ok:
                st.success(msg)
            else:
                st.warning(msg)

            # Refrescar
            sellos = contar_sellos(phone, card.get("FECHA_INICIO"))
            st.markdown(f"<div class='pill ok'>Sellos acumulados (actualizado): <b>{sellos}</b></div>", unsafe_allow_html=True)
            txt, det = descuento_actual(sellos)
            st.markdown(f"<div class='pill warn'>Descuento actual: <b>{txt} {det}</b></div>", unsafe_allow_html=True)

    except Exception as e:
        st.error("Falló al consultar cliente.")
        st.code(f"{type(e)._name_}: {e}")
