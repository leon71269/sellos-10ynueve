# appy.py — 10ynueve • Sistema de Sellos
# Requisitos en requirements.txt:
# streamlit
# supabase
# python-dateutil

import re
from datetime import date, datetime
import streamlit as st
from supabase import create_client, Client

# ============================================
# Conexión a Supabase
# ============================================
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_ANON_KEY = st.secrets["SUPABASE_ANON_KEY"]
supabase: Client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)

# ============================================
# Helpers de BD
# ============================================

def normalize_phone(raw: str) -> str:
    """Deja solo dígitos en el teléfono."""
    return "".join(re.findall(r"\d+", raw or ""))

def get_customer_by_phone(phone: str):
    """Busca cliente en la vista customers_api"""
    res = (
        supabase.table("customers_api")
        .select("*")
        .eq("phone", phone)
        .maybe_single()
        .execute()
    )
    return res.data  # dict | None

def create_customer(name: str, phone: str):
    """Crea cliente nuevo en tabla Customers"""
    supabase.table("Customers").insert(
        {"Name": name.strip(), "Phone": phone.strip()}
    ).execute()

def next_card_number() -> str:
    """Genera un ID de tarjeta incremental tipo T-001"""
    res = supabase.table("TARJETAS").select("id", count="exact").execute()
    count = res.count or 0
    return f"T-{count+1:03d}"

def ensure_open_card(phone: str):
    """Revisa si cliente tiene tarjeta abierta, si no crea una nueva"""
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
        card_id = next_card_number()
        card = {
            "ID_TARJETA": card_id,
            "TELEFONO": phone,
            "ESTADO": "abierta",
            "NUM_SELLos": 0,
            "FECHA_INICIO": str(date.today()),
            "ULTIMO_SELLO": None,
        }
        supabase.table("TARJETAS").insert(card).execute()
    return card

def add_stamp(card):
    """Agrega un sello si no se ha sellado hoy"""
    hoy = str(date.today())
    if card["ULTIMO_SELLO"] == hoy:
        return False  # ya sellado hoy

    nuevos_sellos = (card["NUM_SELLos"] or 0) + 1
    supabase.table("TARJETAS").update(
        {"NUM_SELLos": nuevos_sellos, "ULTIMO_SELLO": hoy}
    ).eq("ID_TARJETA", card["ID_TARJETA"]).execute()
    return True

def get_discount_by_stamps(stamps: int):
    """Obtiene descuento según número de sellos"""
    res = (
        supabase.table("DESCUENTOS")
        .select("*")
        .order("VAL", desc=False)
        .execute()
    )
    descuentos = res.data or []
    if not descuentos:
        return {"DESCRIPCION": "Sin descuento", "VAL": 0}

    idx = min(stamps, len(descuentos)) - 1
    if idx < 0:
        idx = 0
    return descuentos[idx]

# ============================================
# Interfaz Streamlit
# ============================================

st.title("10ynueve — Sistema de Sellos")
st.caption("Listo para sellar cuando quieras. ✨🐾")

modo = st.radio("Selecciona una opción:", ["Cliente Perrón", "Nuevo Cliente"])

phone_input = st.text_input("Ingresa el número de teléfono del cliente:")

if st.button("Buscar"):
    phone = normalize_phone(phone_input)
    if not phone:
        st.error("⚠ Ingresa un número válido.")
    else:
        if modo == "Cliente Perrón":
            # ============================
            # CLIENTE EXISTENTE
            # ============================
            cust = get_customer_by_phone(phone)
            if not cust:
                st.error("Cliente no encontrado en Customers.")
            else:
                st.success(f"Cliente encontrado: {cust['name']} - {cust['phone']}")
                card = ensure_open_card(phone)

                st.info(
                    f"Tarjeta activa: {card['ID_TARJETA']} - "
                    f"Estado: {card['ESTADO']} - "
                    f"Número: {card['NUM_SELLos']} - "
                    f"Inicio: {card['FECHA_INICIO']}"
                )

                descuento = get_discount_by_stamps(card["NUM_SELLos"])
                st.warning(
                    f"Descuento actual: {descuento['DESCRIPCION']} ({descuento['VAL']}%)"
                )

                if st.button("Sellar tarjeta"):
                    if add_stamp(card):
                        st.success("🐾 Tarjeta sellada por Greg!!")
                    else:
                        st.error("Tarjeta ya sellada hoy, vuelve mañana por más sellos ✨")

        else:
            # ============================
            # CLIENTE NUEVO
            # ============================
            cust = get_customer_by_phone(phone)
            if cust:
                st.error("⚠ Este número ya está registrado.")
            else:
                name_input = st.text_input("Nombre")
                if st.button("Registrar cliente y abrir tarjeta"):
                    if not name_input.strip():
                        st.error("El nombre no puede estar vacío.")
                    else:
                        create_customer(name_input, phone)
                        card = ensure_open_card(phone)
                        st.success(
                            f"Cliente {name_input} registrado con tarjeta {card['ID_TARJETA']}."
                        )
