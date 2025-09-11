# appy.py — 10ynueve · Sistema de Sellos
# ───────────────────────────────────────────
from __future__ import annotations
import re
from datetime import date
from typing import Optional, Dict, Any

import streamlit as st
from supabase import create_client, Client

# Conexión a Supabase
SUPABASE_URL = st.secrets["SUPABASE_URL"].strip()
SUPABASE_ANON_KEY = st.secrets["SUPABASE_ANON_KEY"].strip()
supabase: Client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)

# ─────────────────────────────
# Helpers
# ─────────────────────────────
def normalize_phone(raw: str) -> str:
    return "".join(re.findall(r"\d+", raw or ""))

def safe_execute(query):
    """Envuelve .execute() y siempre regresa dict (aunque vacío)."""
    try:
        res = query.execute()
        return res.data or []
    except Exception:
        return []

def get_customer_by_phone(phone: str) -> Optional[Dict[str, Any]]:
    phone = normalize_phone(phone)
    res = safe_execute(
        supabase.table("Customers").select("Name, Phone").eq("Phone", phone).maybe_single()
    )
    if isinstance(res, dict) and res:
        return {"name": res.get("Name"), "phone": res.get("Phone")}
    return None

def customer_exists(phone: str) -> bool:
    phone = normalize_phone(phone)
    res = safe_execute(
        supabase.table("Customers").select("Phone").eq("Phone", phone).limit(1)
    )
    return bool(res)

def create_customer(name: str, phone: str) -> None:
    phone = normalize_phone(phone)
    supabase.table("Customers").insert({"Name": name.strip(), "Phone": phone}).execute()

def next_global_card_id() -> str:
    res = safe_execute(supabase.table("TARJETAS").select("ID_TARJETA").order("ID_TARJETA", desc=True).limit(1))
    last = (res or [{}])[0].get("ID_TARJETA")
    n = 0
    if isinstance(last, str) and last.startswith("T-"):
        try:
            n = int(last.split("-")[1])
        except:
            n = 0
    return f"T-{n+1:03d}"

def next_customer_card_number(phone: str) -> int:
    phone = normalize_phone(phone)
    res = safe_execute(supabase.table("TARJETAS").select("NUMERO_TARJETA").eq("TELEFONO", phone))
    return len(res) + 1

def ensure_open_card(phone: str) -> Dict[str, Any]:
    phone = normalize_phone(phone)
    res = safe_execute(
        supabase.table("TARJETAS").select("*").eq("TELEFONO", phone).eq("ESTADO", "abierta").maybe_single()
    )
    if isinstance(res, dict) and res:
        return res
    # crea nueva
    new_id = next_global_card_id()
    num_cliente = next_customer_card_number(phone)
    payload = {
        "ID_TARJETA": new_id,
        "TELEFONO": phone,
        "FECHA_INICIO": date.today().isoformat(),
        "ESTADO": "abierta",
        "NUMERO_TARJETA": num_cliente,
        "fecha_ultimo_sello": None,
    }
    supabase.table("TARJETAS").insert(payload).execute()
    return payload

def count_stamps(id_tarjeta: str) -> int:
    r = supabase.table("COMPRAS").select("ID_TARJETA", count="exact").eq("ID_TARJETA", id_tarjeta).execute()
    return r.count or 0

def today_has_stamp(card: Dict[str, Any]) -> bool:
    today = date.today().isoformat()
    fus = card.get("fecha_ultimo_sello")
    if fus and fus[:10] == today:
        return True
    r = supabase.table("COMPRAS").select("ID_TARJETA", count="exact").eq("ID_TARJETA", card["ID_TARJETA"]).eq("FECHA", today).execute()
    return (r.count or 0) > 0

def stamp_card(card: Dict[str, Any], phone: str) -> None:
    if today_has_stamp(card):
        raise Exception("Tarjeta sellada hoy, vuelve mañana por más sellos.")
    payload = {
        "ID_TARJETA": card["ID_TARJETA"],
        "TELEFONO": normalize_phone(phone),
        "FECHA": date.today().isoformat(),
    }
    supabase.table("COMPRAS").insert(payload).execute()
    supabase.table("TARJETAS").update({"fecha_ultimo_sello": date.today().isoformat()}).eq("ID_TARJETA", card["ID_TARJETA"]).execute()

# ─────────────────────────────
# UI
# ─────────────────────────────
st.set_page_config(page_title="10ynueve — Sistema de Sellos", page_icon="⭐", layout="wide")
st.title("10ynueve — Sistema de Sellos")
st.caption("Listo para sellar cuando quieras. ✨🐾")

mode = st.radio("Selecciona una opción:", ["Cliente Perrón", "Nuevo Cliente"], horizontal=True)
phone_input = st.text_input("Ingresa el número de teléfono del cliente:")

if mode == "Cliente Perrón":
    if st.button("Buscar"):
        cust = get_customer_by_phone(phone_input)
        if not cust:
            st.error("Cliente no encontrado en Customers.")
        else:
            st.success(f"Cliente encontrado: **{cust['name']}** · {cust['phone']}")
            card = ensure_open_card(phone_input)
            s_count = count_stamps(card["ID_TARJETA"])
            st.info(f"Tarjeta activa: {card['ID_TARJETA']} · Estado: {card['ESTADO']} · Número: {card['NUMERO_TARJETA']}")
            st.write(f"Sellos acumulados: {s_count}")
            if today_has_stamp(card):
                st.warning("Tarjeta sellada hoy, vuelve mañana por más sellos.")
            elif st.button("Sellar ahora ✅"):
                try:
                    stamp_card(card, phone_input)
                    st.balloons()
                    st.success("Tarjeta Sellada por Greg!! 🐾")
                except Exception as e:
                    st.error(str(e))

else:  # Nuevo Cliente
    name = st.text_input("Nombre")
    tel = st.text_input("Teléfono", value=phone_input or "")
    if st.button("Registrar cliente y abrir tarjeta"):
        if not name or not tel:
            st.error("Nombre y teléfono obligatorios.")
        elif customer_exists(tel):
            st.warning("Ese número ya tiene registro.")
        else:
            try:
                create_customer(name, tel)
                card = ensure_open_card(tel)
                st.success(f"Cliente **{name}** registrado con tarjeta **{card['ID_TARJETA']}**.")
            except Exception as e:
                st.error(f"Falló el registro: {e}")

