# appy.py — 10ynueve • Sistema de Sellos

import re
from datetime import date
import streamlit as st
from supabase import create_client, Client

# =====================================
# Conexión a Supabase
# =====================================
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_ANON_KEY = st.secrets["SUPABASE_ANON_KEY"]
supabase: Client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)

# =====================================
# Helpers de BD
# =====================================

def normalize_phone(raw: str) -> str:
    """Deja solo dígitos en el número."""
    return "".join(re.findall(r"\d+", raw or ""))

def get_customer_by_phone(phone: str):
    """Busca cliente en la vista customers_api."""
    res = (
        supabase.table("customers_api")
        .select("*")
        .eq("phone", phone)
        .maybe_single()
        .execute()
    )
    return res.data

def create_customer(name: str, phone: str):
    """Crea un cliente en la tabla Customers."""
    supabase.table("Customers").insert(
        {"Name": name.strip(), "Phone": phone}
    ).execute()

def next_card_number() -> str:
    """Genera ID único para nueva tarjeta."""
    res = supabase.table("TARJETAS").select("ID_TARJETA", count="exact").execute()
    n = res.count or 0
    return f"T-{n+1:03d}"

def ensure_open_card(phone: str) -> dict:
    """Devuelve tarjeta abierta, si no existe crea una nueva."""
    res = (
        supabase.table("TARJETAS")
        .select("*")
        .eq("TELEFONO", phone)
        .eq("ESTADO", "abierta")
        .maybe_single()
        .execute()
    )
    card = res.data
    if not card:
        card = {
            "ID_TARJETA": next_card_number(),
            "TELEFONO": phone,
            "ESTADO": "abierta",
            "NUM_SELLOS": 0,
            "FECHA_INICIO": str(date.today()),
            "ULTIMO_SELLO": None,
        }
        supabase.table("TARJETAS").insert(card).execute()
    return card

def add_stamp(card: dict) -> bool:
    """Agrega un sello (solo uno por día)."""
    hoy = str(date.today())
    if card.get("ULTIMO_SELLO") == hoy:
        return False
    nuevos = int(card.get("NUM_SELLOS") or 0) + 1
    supabase.table("TARJETAS").update(
        {"NUM_SELLOS": nuevos, "ULTIMO_SELLO": hoy}
    ).eq("ID_TARJETA", card["ID_TARJETA"]).execute()
    return True

def get_discount_by_stamps(stamps: int) -> dict:
    """Devuelve el descuento según los sellos acumulados."""
    res = supabase.table("DESCUENTOS").select("*").order("VAL", desc=False).execute()
    rows = res.data or []
    if not rows:
        return {"DESCRIPCION": "Sin descuento", "VAL": 0}
    idx = max(1, min(stamps, len(rows))) - 1
    return rows[idx]

# =====================================
# Interfaz Streamlit
# =====================================
st.set_page_config(page_title="10ynueve — Sistema de Sellos", page_icon="🐾", layout="centered")

st.title("10ynueve — Sistema de Sellos")
st.caption("Listo para sellar cuando quieras. ✨🐾")

modo = st.radio("Selecciona una opción:", ["Cliente Perrón", "Nuevo Cliente"], horizontal=True)

# =====================================
# Modo: Cliente Perrón
# =====================================
if modo == "Cliente Perrón":
    phone_input = st.text_input("Ingresa el número de teléfono del cliente:")
    if st.button("Buscar"):
        phone = normalize_phone(phone_input)
        if not phone:
            st.error("Ingresa un número válido.")
        else:
            try:
                cust = get_customer_by_phone(phone)
                if not cust:
                    st.error("Cliente no encontrado en Customers.")
                else:
                    st.success(f"Cliente encontrado: {cust['name']} · {cust['phone']}")
                    card = ensure_open_card(phone)

                    col1, col2 = st.columns(2)
                    with col1:
                        st.info(
                            f"Tarjeta activa: {card['ID_TARJETA']}  \n"
                            f"Estado: {card['ESTADO']}  \n"
                            f"Inicio: {card['FECHA_INICIO']}"
                        )
                    with col2:
                        st.success(f"Sellos acumulados: {card['NUM_SELLOS']}")

                    descuento = get_discount_by_stamps(int(card["NUM_SELLOS"]))
                    st.warning(f"Descuento actual: {descuento['DESCRIPCION']}")

                    if st.button("Sellar tarjeta"):
                        card = ensure_open_card(phone)
                        if add_stamp(card):
                            st.success("Tarjeta sellada por Greg!! 🐾")
                        else:
                            st.error("Tarjeta ya sellada hoy, vuelve mañana por más sellos.")

            except Exception as e:
                st.error("Falló al consultar cliente.")
                st.code(f"{type(e)._name_}: {e}")

# =====================================
# Modo: Nuevo Cliente
# =====================================
else:
    st.subheader("Dar de alta nuevo cliente")
    name_input = st.text_input("Nombre")
    phone_input = st.text_input("Teléfono")

    if st.button("Registrar cliente y abrir tarjeta"):
        phone = normalize_phone(phone_input)
        name = (name_input or "").strip()
        if not name or not phone:
            st.error("Nombre y teléfono son obligatorios.")
        else:
            try:
                if get_customer_by_phone(phone):
                    st.error("Este número ya está registrado.")
                else:
                    create_customer(name, phone)
                    card = ensure_open_card(phone)
                    st.success(f"Cliente {name} registrado con tarjeta {card['ID_TARJETA']}.")
            except Exception as e:
                st.error("Falló el registro.")
                st.code(f"{type(e)._name_}: {e}")
