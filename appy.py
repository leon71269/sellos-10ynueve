import os
from datetime import datetime, date
import streamlit as st
from supabase import create_client, Client

# === Conexión a Supabase (usa st.secrets) ===
def _clean_ascii(s: str) -> str:
    s = s.strip()
    return "".join(ch for ch in s if 32 <= ord(ch) < 127)

SUPABASE_URL = _clean_ascii(st.secrets["SUPABASE_URL"])
SUPABASE_ANON_KEY = _clean_ascii(st.secrets["SUPABASE_ANON_KEY"])

from supabase import create_client, Client
supabase: Client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
# === Helpers de BD ===
def get_customer_by_phone(phone: str):
    p = phone.strip()

    # 1) Intento directo a la tabla con nombres tal cual (case-sensitive)
    res = supabase.table("Customers").select("*").eq("Phone", p).maybe_single().execute()
    if res.data:
        return res.data

    # 2) Fallback a la vista en minúsculas
    res = supabase.table("customers_api").select("*").eq("phone", p).maybe_single().execute()
    return res.data
    except Exception as e:
        import traceback
        st.error("Fallo al consultar cliente")
        st.code(traceback.format_exc())
        # Algunas versiones exponen e.response si viene de la lib supabase/postgrest:
        try:
            st.write(getattr(e, "response", None).text)
        except:
            pass
        return None
def create_customer(name: str, phone: str):
    supabase.table("Customers").insert({"Name": name.strip(), "Phone": phone.strip()}).execute()

def next_sequential_id(prefix: str, table: str, id_col: str) -> str:
    # Cuenta filas y arma ID tipo T-001, C-001
    count = supabase.table(table).select(id_col, count="exact").execute().count or 0
    return f"{prefix}-{count+1:03d}"

def ensure_open_card(phone: str):
    # Busca tarjeta abierta, si no existe crea una
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

def stamps_count(phone: str) -> int:
    # Cuenta sellos registrados en COMPRAS para este teléfono
    res = supabase.table("COMPRAS").select("ID_COMPRA", count="exact").eq("TELEFONO", phone).execute()
    return res.count or 0

def current_discount_pct(stamps: int) -> float:
    # Toma el primer descuento activo ordenado por ID_DESCUENTO,
    # y avanza según número de sellos (mismo criterio que tu vista).
    # Si no quieres escalar, simplemente devuelve el primero.
    d = (
        supabase.table("DESCUENTOS")
        .select("*")
        .eq("ACTIVO", 1)
        .order("ID_DESCUENTO")
        .limit(1)
        .maybe_single()
        .execute()
        .data
    )
    return float(d["VALOR"]) if d else 0.0

def give_stamp_today(phone: str):
    # NO bloquea por día (como pediste). Solo inserta un registro en COMPRAS.
    comp_id = next_sequential_id("C", "COMPRAS", "ID_COMPRA")
    payload = {
        "ID_COMPRA": comp_id,
        "TELEFONO": phone,
        "FECHA": datetime.now().strftime("%Y-%m-%d"),
        "SELLO_OTORGADO": True,
    }
    supabase.table("COMPRAS").insert(payload).execute()
    return comp_id

# === UI ===
st.title("10ynueve - Sistema de Sellos")

opcion = st.radio(
    "Selecciona una opción:",
    ["Cliente Perrón", "Nuevo Cliente"],
    index=0,
    horizontal=True,
)

if opcion == "Cliente Perrón":
    phone = st.text_input("Ingresa el número de teléfono del cliente:")
    if st.button("Buscar", type="primary") and phone.strip():
        cust = get_customer_by_phone(phone.strip())
        if not cust:
            st.warning("Cliente no encontrado en *Customers*.")
        else:
            st.success(f"Cliente: *{cust['Name']}* — {cust['Phone']}")
            # Asegura tarjeta abierta
            card = ensure_open_card(phone.strip())
            st.info(f"Tarjeta abierta: *{card['ID_TARJETA']}*")

            # Progreso y descuento
            s = stamps_count(phone.strip())
            pct = current_discount_pct(s)
            st.metric("Sellos acumulados", s)
            st.metric("Descuento actual", f"{pct:.1f}%")

            # Botón para sellar (permite sellar hoy aunque ya haya visitado)
            if st.button("Dar sello hoy 🟢"):
                comp = give_stamp_today(phone.strip())
                s2 = s + 1
                pct2 = current_discount_pct(s2)
                st.success(f"Sello registrado (compra *{comp}*). Sellos: {s2} — Descuento: {pct2:.1f}%")

elif opcion == "Nuevo Cliente":
    col1, col2 = st.columns(2)
    with col1:
        name = st.text_input("Nombre")
    with col2:
        phone = st.text_input("Teléfono")

    if st.button("Registrar cliente y abrir tarjeta", type="primary"):
        if not name.strip() or not phone.strip():
            st.error("Nombre y teléfono obligatorios.")
        else:
            # Si ya existe, no duplica; si no, lo crea
            if not get_customer_by_phone(phone.strip()):
                create_customer(name.strip(), phone.strip())
            card = ensure_open_card(phone.strip())
            st.success(f"Cliente *{name}* listo. Tarjeta abierta: *{card['ID_TARJETA']}*")
            s = stamps_count(phone.strip())
            pct = current_discount_pct(s)
            st.caption(f"Sellos: {s} — Descuento actual: {pct:.1f}%")





