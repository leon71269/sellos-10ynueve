# appy.py
# -- coding: utf-8 --

import os
from datetime import date, datetime
import streamlit as st
from supabase import create_client, Client

# =========================
#  Conexión a Supabase
# =========================

def _clean_ascii(s: str) -> str:
    s = s.strip()
    return "".join(ch for ch in s if 32 <= ord(ch) < 127)

SUPABASE_URL = _clean_ascii(st.secrets["SUPABASE_URL"])
SUPABASE_ANON_KEY = _clean_ascii(st.secrets["SUPABASE_ANON_KEY"])
supabase: Client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)

# =========================
#  Helpers de BD
# =========================

def get_customer_by_phone(phone: str):
    """Busca cliente por teléfono. Intenta primero tabla con Mayúsculas,
    luego (si existe) la vista customers_api en minúsculas."""
    p = phone.strip()

    # 1) Tabla principal (mayúsculas tal como en Supabase)
    res = supabase.table("Customers").select("*").eq("Phone", p).maybe_single().execute()
    if res.data:
        return res.data

    # 2) Fallback a vista en minúsculas (opcional)
    try:
        res = supabase.table("customers_api").select("*").eq("phone", p).maybe_single().execute()
        if res.data:
            # Normalizamos campos para que el resto de la app no falle
            return {"Name": res.data.get("name"), "Phone": res.data.get("phone")}
    except Exception:
        # Si no existe la vista, ignoramos y devolvemos None
        pass

    return None

def create_customer(name: str, phone: str):
    supabase.table("Customers").insert({"Name": name.strip(), "Phone": phone.strip()}).execute()
    return {"Name": name.strip(), "Phone": phone.strip()}

def next_sequential_id(prefix: str, table: str, id_col: str) -> str:
    """Arma ID tipo T-001, T-002… en base al conteo exacto."""
    count = supabase.table(table).select(id_col, count="exact").execute().count or 0
    return f"{prefix}-{count+1:03d}"

def ensure_open_card(phone: str):
    """Asegura que exista una tarjeta abierta para el teléfono dado.
    Si existe, la regresa; si no, la crea en TARJETAS."""
    # ¿Ya hay abierta?
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

    # Crear una nueva
    new_id = next_sequential_id("T", "TARJETAS", "ID_TARJETA")
    payload = {
        "ID_TARJETA": new_id,
        "TELEFONO": phone,
        "FECHA_INICIO": date.today().isoformat(),
        "FECHA_FIN": None,
        "ESTADO": "abierta",
        "NUMERO_TARJETA": 1,
    }
    supabase.table("TARJETAS").insert(payload).execute()
    return payload

# =========================
#  UI
# =========================

st.set_page_config(page_title="10ynueve - Sistema de Sellos", layout="centered")
st.title("10ynueve - Sistema de Sellos")

modo = st.radio("Selecciona una opción:", ["Cliente Perrón", "Nuevo Cliente"], horizontal=False)

phone = st.text_input("Ingresa el número de teléfono del cliente:")

if st.button("Buscar"):
    if not phone.strip():
        st.error("Ingresa un teléfono.")
    else:
        if modo == "Cliente Perrón":
            try:
                cust = get_customer_by_phone(phone)
                if not cust:
                    st.warning("Cliente no encontrado en Customers.")
                else:
                    st.success(f"Cliente: {cust['Name']}  |  Tel: {cust['Phone']}")
                    card = ensure_open_card(cust["Phone"])
                    st.info(
                        f"Tarjeta activa: {card['ID_TARJETA']}  •  Estado: {card['ESTADO']}  •  Desde: {card['FECHA_INICIO']}"
                    )
            except Exception as e:
                st.error("Falló al consultar cliente.")
                st.code(repr(e))
        else:  # Nuevo Cliente
            nombre = st.text_input("Nombre del nuevo cliente")
            if st.button("Registrar y abrir tarjeta"):
                if not nombre.strip():
                    st.error("El nombre es obligatorio.")
                else:
                    try:
                        cust = get_customer_by_phone(phone)
                        if not cust:
                            cust = create_customer(nombre, phone)
                        card = ensure_open_card(cust["Phone"])
                        st.success(
                            f"Cliente {cust['Name']} registrado/validado con tarjeta {card['ID_TARJETA']} abierta."
                        )
                    except Exception as e:
                        st.error("No se pudo registrar al cliente.")
                        st.code(repr(e))







