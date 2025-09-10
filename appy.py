# appy.py — 10ynueve (versión limpia y estable)

import os
from datetime import date, datetime
import streamlit as st
from supabase import create_client, Client

# ---------------------------
#  Configuración / conexión
# ---------------------------

def _clean_ascii(s: str) -> str:
    """Evita caracteres raros en URL/Keys cuando se copian desde el dashboard."""
    s = (s or "").strip()
    return "".join(ch for ch in s if 32 <= ord(ch) < 127)

SUPABASE_URL = _clean_ascii(st.secrets["SUPABASE_URL"])
SUPABASE_ANON_KEY = _clean_ascii(st.secrets["SUPABASE_ANON_KEY"])

supabase: Client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)

# ---------------------------
#  Helpers de BD
# ---------------------------

def get_customer_by_phone(phone: str):
    """
    Intenta primero desde la vista en minúsculas customers_api.
    Si no existe o viene vacía, intenta directo a la tabla "Customers".
    Devuelve dict o None sin reventar la app.
    """
    phone = (phone or "").strip()

    # 1) Vista en minúsculas (recomendada para evitar temas de mayúsculas)
    try:
        res = supabase.table("customers_api").select("*").eq("phone", phone).maybe_single().execute()
        if isinstance(res.data, dict) and res.data:
            # normaliza llaves por si vienen como name/phone
            return {"Name": res.data.get("name") or res.data.get("Name"),
                    "Phone": res.data.get("phone") or res.data.get("Phone")}
    except Exception:
        pass  # seguimos con el plan B

    # 2) Tabla con mayúsculas
    try:
        res = supabase.table("Customers").select("*").eq("Phone", phone).maybe_single().execute()
        if isinstance(res.data, dict) and res.data:
            return {"Name": res.data.get("Name"), "Phone": res.data.get("Phone")}
    except Exception:
        pass

    return None


def create_customer(name: str, phone: str):
    """Inserta en tabla Customers (mayúsculas tal cual la tienes)."""
    payload = {"Name": (name or "").strip(), "Phone": (phone or "").strip()}
    res = supabase.table("Customers").insert(payload).execute()
    return payload


def _next_tarjeta_id() -> str:
    """
    Genera el siguiente ID tipo T-001, T-002… contando filas existentes.
    (Si más adelante quieres algo a prueba de concurrencia, lo cambiamos por un contador en SQL)
    """
    try:
        cnt = supabase.table("TARJETAS").select("ID_TARJETA", count="exact").execute().count or 0
    except Exception:
        cnt = 0
    return f"T-{cnt+1:03d}"


def ensure_open_card(phone: str):
    """
    Si el cliente ya tiene tarjeta abierta en TARJETAS, la regresa.
    Si no, crea una nueva tarjeta abierta.
    """
    phone = (phone or "").strip()

    # Busca tarjeta abierta existente
    try:
        res = (
            supabase.table("TARJETAS")
            .select("*")
            .eq("TELEFONO", phone)
            .eq("ESTADO", "abierta")
            .limit(1)
            .execute()
        )
        if res.data:
            return res.data[0]
    except Exception:
        pass

    # No había: creamos una
    nueva = {
        "ID_TARJETA": _next_tarjeta_id(),
        "TELEFONO": phone,
        "FECHA_INICIO": date.today().isoformat(),
        "FECHA_FIN": None,
        "ESTADO": "abierta",
        "NUMERO_TARJETA": 1
    }
    ins = supabase.table("TARJETAS").insert(nueva).execute()
    return nueva


# ---------------------------
#  UI
