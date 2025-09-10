# appy.py  —  10ynueve - Sistema de Sellos (versión estable)

import streamlit as st
from datetime import date, datetime
from supabase import create_client, Client

# ========== Conexión a Supabase (via st.secrets) ==========
def _ascii(s: str) -> str:
    s = (s or "").strip()
    return "".join(ch for ch in s if 32 <= ord(ch) < 127)

SUPABASE_URL = _ascii(st.secrets["SUPABASE_URL"])
SUPABASE_ANON_KEY = _ascii(st.secrets["SUPABASE_ANON_KEY"])
supabase: Client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)

# ========== Helpers de BD ==========
def get_customer_by_phone(phone: str):
    """Lee desde la VISTA customers_api (name, phone en minúsculas)."""
    phone = (phone or "").strip()
    res = supabase.table("customers_api").select("*").eq("phone", phone).maybe_single().execute()
    return res.data

def create_customer(name: str, phone: str):
    """Inserta en la tabla real Customers (columnas TitleCase)."""
    payload = {"Name": (name or "").strip(), "Phone": (phone or "").strip()}
    supabase.table("Customers").insert(payload).execute()
    return payload

def next_sequential_id(prefix: str, table: str, id_col: str) -> str:
    """Genera ID tipo T-001, C-001 contando filas exactamente."""
    count = supabase.table(table).select(id_col, count="exact").execute().count or 0
    return f"{prefix}-{count+1:03d}"

def ensure_open_card(phone: str):
    """
    Busca tarjeta abierta en TARJETAS por TELEFONO.
    Si no existe, la crea con NUMERO_TARJETA = 1 y ESTADO='abierta'.
    """
    phone = (phone or "").strip()
    q = (
        supabase.table("TARJETAS")
        .select("*")
        .eq("TELEFONO", phone)
        .eq("ESTADO", "abierta")
        .limit(1)
        .execute()
    )
    open_card = (q.data or [None])[0]

    if open_card:
        return open_card

    # Crear nueva
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

# ========== UI ==========
st.set_page_config(page_title="10ynueve — Sistema de Sellos", page_icon="✨", layout="centered")
st.title("10ynueve — Sistema de Sellos")

modo = st.radio("Selecciona una opción:", ["Cliente Perrón", "Nuevo Cliente"], horizontal=True)

phone_input = st.text_input("Ingresa el número de teléfono del cliente:")
buscar = st.button("Buscar", type="primary")

# ====== Flujo: Cliente existente ======
if buscar and modo == "Cliente Perrón":
    if not phone_input.strip():
        st.error("Ingresa un teléfono.")
    else:
        try:
            cust = get_customer_by_phone(phone_input)
            if not cust:
                st.error("Cliente no encontrado en Customers.")
                with st.expander("Sugerencia si usas la vista"):
                    st.code('CREATE OR REPLACE VIEW customers_api AS SELECT "Name" AS name, "Phone" AS phone FROM "Customers";', language="sql")
            else:
                st.success(f"Cliente encontrado: *{cust.get('name', '')}* · {cust.get('phone', '')}")
                card = ensure_open_card(cust["phone"])
                st.info(
                    f"Tarjeta activa: *{card['ID_TARJETA']}* · Estado: *{card['ESTADO']}* · "
                    f"Número: *{card['NUMERO_TARJETA']}* · Inicio: {card['FECHA_INICIO']}"
                )
                st.caption("Listo para sellar cuando quieras. 🧋✨")
        except Exception as e:
            st.error("Falló al consultar cliente.")
            st.exception(e)

# ====== Flujo: Nuevo cliente ======
if modo == "Nuevo Cliente":
    with st.form("nuevo_cliente"):
        nombre = st.text_input("Nombre")
        telefono_nuevo = st.text_input("Teléfono")
        submitted = st.form_submit_button("Registrar cliente y abrir tarjeta", type="primary")

    if submitted:
        if not nombre.strip() or not telefono_nuevo.strip():
            st.error("Nombre y teléfono son obligatorios.")
        else:
            try:
                # Evita duplicados por teléfono (checa la vista)
                exists = get_customer_by_phone(telefono_nuevo)
                if exists:
                    st.warning("Ese teléfono ya existe, abriendo/asegurando tarjeta…")
                else:
                    create_customer(nombre, telefono_nuevo)
                    st.success(f"Cliente *{nombre}* creado.")

                card = ensure_open_card(telefono_nuevo)
                st.info(
                    f"Tarjeta activa: *{card['ID_TARJETA']}* · Estado: *{card['ESTADO']}* · "
                    f"Número: *{card['NUMERO_TARJETA']}* · Inicio: {card['FECHA_INICIO']}"
                )
                st.caption("Cliente listo para acumular sellos. ✨")
            except Exception as e:
                st.error("Error al registrar/abrir tarjeta.")
                st.exception(e)
