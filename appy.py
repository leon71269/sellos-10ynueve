import re
from datetime import datetime, date, timezone, timedelta

import streamlit as st
from supabase import create_client, Client

# =========================
#  Conexión a Supabase
# =========================
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_ANON_KEY = st.secrets["SUPABASE_ANON_KEY"]
supabase: Client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)

# =========================
#  Utils
# =========================
MX_TZ = timezone(timedelta(hours=-6))  # sin DST. Si quieres DST, cámbialo por pendulum/pytz.
TODAY = lambda: datetime.now(MX_TZ).date()

def normalize_phone(raw: str) -> str:
    """Deja solo dígitos en el teléfono."""
    return "".join(re.findall(r"\d+", raw or ""))

# =========================
#  Funciones de BD
# =========================
def get_customer_by_phone(phone: str):
    """
    Lee cliente desde la VISTA customers_api (name/phone en minúsculas).
    La vista debe ser:
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
    return (
        supabase.table("Customers")
        .insert({"Name": (name or "").strip(), "Phone": (phone or "").strip()})
        .execute()
    )

def next_sequential_id(prefix: str, table: str, id_col: str) -> str:
    """Cuenta filas exactas en table y genera ID estilo T-001 / C-001."""
    count = supabase.table(table).select(id_col, count="exact").execute().count or 0
    return f"{prefix}-{count+1:03d}"

def ensure_open_card(phone: str):
    """
    Busca tarjeta abierta para el teléfono. Si no existe, crea una:
      - ID_TARJETA: T-###
      - NUMERO_TARJETA: entero secuencial
      - ESTADO: 'abierta'
      - FECHA_INICIO: hoy
    """
    # 1) ¿hay tarjeta abierta?
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

    # 2) no hay: crear una
    new_id = next_sequential_id("T", "TARJETAS", "ID_TARJETA")
    # NUMERO_TARJETA = cuántas tarjetas tiene la persona + 1
    num_tarjetas = (
        supabase.table("TARJETAS")
        .select("ID_TARJETA", count="exact")
        .eq("TELEFONO", phone)
        .execute()
        .count
        or 0
    )
    numero_tarjeta = num_tarjetas + 1

    created = (
        supabase.table("TARJETAS")
        .insert(
            {
                "ID_TARJETA": new_id,
                "TELEFONO": phone,
                "FECHA_INICIO": str(TODAY()),
                "FECHA_FIN": None,
                "ESTADO": "abierta",
                "NUMERO_TARJETA": numero_tarjeta,
            }
        )
        .execute()
        .data
    )
    # Devuelve la fila recién creada
    return (
        supabase.table("TARJETAS")
        .select("*")
        .eq("ID_TARJETA", new_id)
        .maybe_single()
        .execute()
        .data
    )

def count_stamps(phone: str) -> int:
    """Cuenta sellos en COMPRAS por teléfono."""
    return (
        supabase.table("COMPRAS")
        .select("ID_COMPRA", count="exact")
        .eq("TELEFONO", phone)
        .execute()
        .count
        or 0
    )

def has_stamp_today(phone: str) -> bool:
    """¿Ya tiene un sello hoy? Candado 1 por día."""
    today_str = str(TODAY())
    rows = (
        supabase.table("COMPRAS")
        .select("ID_COMPRA")
        .eq("TELEFONO", phone)
        .eq("FECHA", today_str)
        .execute()
        .data
        or []
    )
    return len(rows) > 0

def seal_today(phone: str):
    """
    Inserta sello (una vez al día). Devuelve tupla (ok: bool, msg: str).
    Inserta en COMPRAS: ID_COMPRA, TELEFONO, FECHA, SELLO_OTORGADO=1
    """
    if has_stamp_today(phone):
        return False, "Tarjeta sellada hoy, vuelve mañana por más sellos"

    new_id = next_sequential_id("C", "COMPRAS", "ID_COMPRA")
    data = {
        "ID_COMPRA": new_id,
        "TELEFONO": phone,
        "FECHA": str(TODAY()),
        "SELLO_OTORGADO": 1,
    }
    supabase.table("COMPRAS").insert(data).execute()
    return True, "Tarjeta sellada por Greg!! 🐾"

def get_discount_for_count(sellos: int):
    """
    Devuelve el descuento 'actual' según total de sellos.
    Toma la fila de DESCUENTOS (ACTIVO=1) en el orden de ID_DESCUENTO;
    usa índice = min(sellos, len-1).
    """
    rows = (
        supabase.table("DESCUENTOS")
        .select("*")
        .eq("ACTIVO", 1)
        .order("ID_DESCUENTO", desc=False)
        .execute()
        .data
        or []
    )
    if not rows:
        return None
    idx = min(sellos, len(rows) - 1)
    return rows[idx]

# =========================
#  UI
# =========================
st.set_page_config(page_title="10ynueve — Sistema de Sellos", layout="wide")
st.title("10ynueve — Sistema de Sellos")

mode = st.radio("Selecciona una opción:", ["Cliente Perrón", "Nuevo Cliente"], horizontal=True)

phone_input = st.text_input("Ingresa el número de teléfono del cliente:")
phone_input = normalize_phone(phone_input)

col_btn, _ = st.columns([1, 5])
buscar = col_btn.button("Buscar", type="primary")

if "last_phone" not in st.session_state:
    st.session_state.last_phone = None

if buscar:
    if not phone_input:
        st.error("Escribe un teléfono.")
    else:
        st.session_state.last_phone = phone_input

phone = st.session_state.last_phone

if phone:
    if mode == "Cliente Perrón":
        # Buscar cliente
        try:
            cust = get_customer_by_phone(phone)
            if not cust:
                st.error("Cliente no encontrado en Customers.")
            else:
                st.success(f"Cliente encontrado: *{cust['name']}* · {phone}")

                # Asegurar tarjeta abierta
                card = ensure_open_card(phone)
                st.info(
                    f"*Tarjeta activa:* {card['ID_TARJETA']} · *Estado:* {card['ESTADO']} · "
                    f"*Número:* {card['NUMERO_TARJETA']} · *Inicio:* {card['FECHA_INICIO']}"
                )

                # Mostrar sellos y descuento
                total_sellos = count_stamps(phone)
                st.success(f"*Sellos acumulados:* {total_sellos}")

                disc = get_discount_for_count(total_sellos)
                if disc:
                    st.warning(
                        f"*Descuento actual:* {disc['DESCRIPCION']} ({disc['VALOR']}{'%' if disc['TIPO']=='PORCENTAJE' else ''})"
                    )
                else:
                    st.warning("No hay descuentos activos configurados.")

                # ----- Botón SELLAR -----
                colA, colB = st.columns([1.2, 6])
                if colA.button("Sellar"):
                    ok, msg = seal_today(phone)
                    if ok:
                        st.success(msg)
                    else:
                        st.warning(msg)

                    # Recalcular y mostrar de nuevo
                    total_sellos = count_stamps(phone)
                    st.info(f"*Sellos acumulados (actualizado):* {total_sellos}")

                    disc = get_discount_for_count(total_sellos)
                    if disc:
                        st.info(
                            f"*Descuento actual:* {disc['DESCRIPCION']} ({disc['VALOR']}{'%' if disc['TIPO']=='PORCENTAJE' else ''})"
                        )

        except Exception as e:
            st.error("Falló al consultar cliente.")
            with st.expander("Ver detalle del error"):
                st.code(str(e))

    else:
        # Nuevo cliente
        st.subheader("Dar de alta nuevo cliente")
        name = st.text_input("Nombre")
        if st.button("Registrar cliente y abrir tarjeta", type="primary"):
            if not name or not phone:
                st.error("Nombre y teléfono obligatorios.")
            else:
                try:
                    # Si no existe lo creo
                    if not get_customer_by_phone(phone):
                        create_customer(name, phone)
                    # Aseguro tarjeta abierta
                    card = ensure_open_card(phone)
                    st.success(
                        f"Cliente *{name}* registrado con tarjeta *{card['ID_TARJETA']}*."
                    )
                except Exception as e:
                    st.error("Error al registrar.")
                    with st.expander("Ver detalle del error"):
                        st.code(str(e))

st.caption("Listo para sellar cuando quieras. ✨🐾"
