# appy.py — 10ynueve • Sistema de Sellos (Streamlit + Supabase)

import re
from datetime import date
import streamlit as st
from supabase import create_client, Client

# =========================================
# Conexión a Supabase (usa Secrets en Streamlit)
#   En Streamlit Cloud agrega:
#     SUPABASE_URL
#     SUPABASE_ANON_KEY
# =========================================
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_ANON_KEY = st.secrets["SUPABASE_ANON_KEY"]
supabase: Client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)

# =========================================
# Helpers de BD
# =========================================
def normalize_phone(raw: str) -> str:
    """Deja solo dígitos."""
    return "".join(re.findall(r"\d+", raw or ""))

def get_customer_by_phone(phone: str):
    """
    Lee desde la VISTA 'customers_api' (columnas en minúsculas: name, phone).
    Crea la vista con:
      create or replace view customers_api as
      select "Name" as name, "Phone" as phone from "Customers";
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
    """Inserta en la tabla base con columnas 'Name' y 'Phone'."""
    supabase.table("Customers").insert({"Name": name.strip(), "Phone": phone}).execute()

def next_card_number() -> str:
    """Genera ID tipo T-001 según el conteo actual."""
    res = supabase.table("TARJETAS").select("ID_TARJETA", count="exact").execute()
    n = res.count or 0
    return f"T-{n+1:03d}"

def ensure_open_card(phone: str) -> dict:
    """Devuelve una tarjeta abierta para el teléfono; si no existe, la crea."""
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
    """Agrega sello si la tarjeta no fue sellada hoy (candado)."""
    hoy = str(date.today())
    if card.get("ULTIMO_SELLO") == hoy:
        return False
    nuevos = int(card.get("NUM_SELLOS") or 0) + 1
    supabase.table("TARJETAS").update(
        {"NUM_SELLOS": nuevos, "ULTIMO_SELLO": hoy}
    ).eq("ID_TARJETA", card["ID_TARJETA"]).execute()
    return True

def get_discount_by_stamps(stamps: int) -> dict:
    """
    Devuelve la fila de DESCUENTOS acorde al número de sellos (1..n).
    Usa la columna VAL (número ordinal de sello) y DESCRIPCION (% o promo).
    """
    res = supabase.table("DESCUENTOS").select("*").order("VAL", desc=False).execute()
    rows = res.data or []
    if not rows:
        return {"DESCRIPCION": "Sin descuento", "VAL": 0}
    # clamp a rango válido 1..len(rows)
    idx = max(1, min(stamps, len(rows))) - 1
    return rows[idx]

# =========================================
# UI
# =========================================
st.set_page_config(page_title="10ynueve — Sistema de Sellos", page_icon="🐾", layout="centered")

st.title("10ynueve — Sistema de Sellos")
st.caption("Listo para sellar cuando quieras. ✨🐾")

modo = st.radio("Selecciona una opción:", ["Cliente Perrón", "Nuevo Cliente"], horizontal=True)

# ---------- Modo Cliente Perrón ----------
if modo == "Cliente Perrón":
    phone_input = st.text_input("Ingresa el número de teléfono del cliente:")
    if st.button("Buscar", use_container_width=False):
        phone = normalize_phone(phone_input)
        if not phone:
            st.error("⚠ Ingresa un número válido.")
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
                            f"*Tarjeta activa:* {card['ID_TARJETA']}  \n"
                            f"*Estado:* {card['ESTADO']}  \n"
                            f"*Inicio:* {card['FECHA_INICIO']}"
                        )
                    with col2:
                        st.success(f"*Sellos acumulados:* {card['NUM_SELLOS']}")

                    descuento = get_discount_by_stamps(int(card["NUM_SELLOS"]))
                    st.warning(f"*Descuento actual:* {descuento['DESCRIPCION']}")

                    if st.button("Sellar tarjeta", type="primary"):
                        # refresca la tarjeta por si fue creada en esta búsqueda
                        card = ensure_open_card(phone)
                        if add_stamp(card):
                            st.success("🐾 Tarjeta sellada por Greg!!")
                        else:
                            st.error("Tarjeta ya sellada hoy, vuelve mañana por más sellos ✨")

            except Exception as e:
                st.error("Falló al consultar cliente.")
                st.code(f"{type(e)._name_}: {e}")

# ---------- Modo Nuevo Cliente ----------
else:
    st.subheader("Dar de alta nuevo cliente")
    name_input = st.text_input("Nombre")
    phone_input = st.text_input("Teléfono")

    if st.button("Registrar cliente y abrir tarjeta", type="primary"):
        phone = normalize_phone(phone_input)
        name = (name_input or "").strip()
        if not name or not phone:
            st.error("Nombre y teléfono son obligatorios.")
        else:
            try:
                # ¿ya existe?
                if get_customer_by_phone(phone):
                    st.error("⚠ Este número ya está registrado.")
                else:
                    create_customer(name, phone)
                    card = ensure_open_card(phone)
                    st.success(f"Cliente *{name}* registrado con tarjeta *{card['ID_TARJETA']}*.")
            except Exception as e:
                st.error("Falló el registro.")
                st.code(f"{type(e)._name_}: {e}")
```0
