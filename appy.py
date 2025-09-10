import re
from datetime import date, datetime
import streamlit as st
from supabase import create_client, Client

# ============================
#  Conexión (usa st.secrets)
# ============================
def _clean_ascii(s: str) -> str:
    s = (s or "").strip()
    return "".join(ch for ch in s if 32 <= ord(ch) < 127)

SUPABASE_URL = _clean_ascii(st.secrets["SUPABASE_URL"])
SUPABASE_ANON_KEY = _clean_ascii(st.secrets["SUPABASE_ANON_KEY"])

supabase: Client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)

# ============================
#  Helpers de BD
# ============================

def normalize_phone(raw: str) -> str:
    """Deja solo dígitos."""
    return "".join(re.findall(r"\d+", (raw or "")))

def get_customer_by_phone(phone: str):
    """
    Lee via VISTA 'customers_api' (name/phone en minúsculas).
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
    supabase.table("Customers").insert(
        {"Name": (name or "").strip(), "Phone": (phone or "").strip()}
    ).execute()

def next_card_number() -> int:
    # cuenta filas exactas en TARJETAS y suma 1
    count = supabase.table("TARJETAS").select("NUMERO_TARJETA", count="exact").execute().count or 0
    return count + 1

def ensure_open_card(phone: str):
    """
    Regresa la tarjeta abierta del teléfono; si no existe, crea una.
    Campos esperados en TARJETAS:
      - ID_TARJETA (text)  ej. T-001
      - TELEFONO (text)
      - FECHA_INICIO (date)
      - FECHA_FIN (date, null)
      - ESTADO (text: 'abierta'/'cerrada')
      - NUMERO_TARJETA (int)
      - FECHA_ULTIMO_SELLO (date, null)
      - SELLOS (int, default 0)
    """
    q = (
        supabase.table("TARJETAS")
        .select("ID_TARJETA, TELEFONO, FECHA_INICIO, FECHA_FIN, ESTADO, NUMERO_TARJETA, FECHA_ULTIMO_SELLO, SELLOS")
        .eq("TELEFONO", phone)
        .eq("ESTADO", "abierta")
        .maybe_single()
        .execute()
    )
    if q.data:
        return q.data

    # crear nueva
    num = next_card_number()
    new_card = {
        "ID_TARJETA": f"T-{num:03d}",
        "TELEFONO": phone,
        "FECHA_INICIO": date.today().isoformat(),
        "ESTADO": "abierta",
        "NUMERO_TARJETA": num,
        "SELLOS": 0,
    }
    supabase.table("TARJETAS").insert(new_card).execute()
    return new_card

def get_current_discount(sell_count: int) -> str:
    """
    Devuelve la etiqueta del renglón correspondiente a los sellos actuales.
    Usa la tabla DESCUENTOS, ordenada por ID_DESCUENTO ascendente.
    OFFSET = sellos (0-based), LIMIT 1.
    """
    q = (
        supabase.table("DESCUENTOS")
        .select("DESCRIPCION, TIPO, VALOR")
        .eq("ACTIVO", 1)
        .order("ID_DESCUENTO", desc=False)
        .range(sell_count, sell_count)  # OFFSET=sellos, LIMIT=1
        .execute()
    )
    row = (q.data or [None])[0]
    if not row:
        return "Sin descuento"

    tipo = (row.get("TIPO") or "").strip().upper()
    valor = row.get("VALOR")
    desc = row.get("DESCRIPCION") or "Descuento"

    if tipo in {"PORCENTAJE", "PORCENTUAL", "PORCENTUALE"} and valor is not None:
        return f"{desc} ({int(valor)}%)"
    return desc

def rpc_sellar_hoy(phone: str):
    """
    Llama al RPC sellar_hoy(p_telefono text) que debe existir en la BD.
    Retorna dict con {id_tarjeta, sellos, fecha}.
    """
    res = supabase.rpc("sellar_hoy", {"p_telefono": phone}).execute()
    if isinstance(res.data, list) and res.data:
        return res.data[0]
    return None

# ============================
#  UI
# ============================

st.set_page_config(page_title="10ynueve — Sistema de Sellos", page_icon="⭐", layout="centered")

st.markdown(
    "<h1 style='text-align:center;'>10ynueve — Sistema de Sellos</h1>",
    unsafe_allow_html=True,
)

mode = st.radio("Selecciona una opción:", ["Cliente Perrón", "Nuevo Cliente"], horizontal=True)

phone_input = st.text_input("Ingresa el número de teléfono del cliente:")
phone_input = normalize_phone(phone_input)

# ========== CLIENTE PERRÓN ==========
if mode == "Cliente Perrón":
    if st.button("Buscar", type="primary"):
        if not phone_input:
            st.error("Escribe un teléfono.")
        else:
            try:
                cust = get_customer_by_phone(phone_input)
                if not cust:
                    st.error("Cliente no encontrado en Customers.")
                    with st.expander("Sugerencia si usas la vista"):
                        st.code('sql\nCREATE OR REPLACE VIEW customers_api AS SELECT "Name" AS name, "Phone" AS phone FROM "Customers";')
                else:
                    st.success(f"Cliente encontrado: {cust['name']} · {cust['phone']}")
                    card = ensure_open_card(phone_input)

                    # Muestra tarjeta
                    st.info(
                        f"*Tarjeta activa:* {card['ID_TARJETA']} · "
                        f"*Estado:* {card['ESTADO']} · "
                        f"*Número:* {card['NUMERO_TARJETA']} · "
                        f"*Inicio:* {card['FECHA_INICIO']}"
                    )

                    sellos = int(card.get("SELLOS") or 0)
                    st.success(f"*Sellos acumulados:* {sellos}")

                    etiqueta_desc = get_current_discount(sellos)
                    st.warning(f"*Descuento actual:* {etiqueta_desc}")

                    # --- Botón Sellar hoy (candado en BD via RPC) ---
                    if st.button("Sellar hoy", type="primary"):
                        try:
                            # Para detectar si ya estaba sellado, guardamos los sellos previos
                            prev_sellos = sellos
                            upd = rpc_sellar_hoy(phone_input)

                            # Releer tarjeta para refrescar valores
                            card_ref = ensure_open_card(phone_input)
                            new_sellos = int(card_ref.get("SELLOS") or 0)

                            if new_sellos > prev_sellos:
                                st.success(f"✅ Sello registrado. Sellos ahora: {new_sellos}.")
                            else:
                                st.warning("🔒 Ya se registró un sello hoy para este cliente.")

                            # Nuevo descuento
                            st.info(f"Descuento actual: {get_current_discount(new_sellos)}")

                        except Exception as e:
                            msg = str(e)
                            if "ux_compras_telefono_fecha" in msg or "duplicate key value" in msg:
                                st.warning("🔒 Ya se registró un sello hoy para este cliente.")
                            else:
                                st.error(f"Error al sellar: {e}")

            except Exception as e:
                st.error(f"Falló al consultar cliente.\n\n{e}")

# ========== NUEVO CLIENTE ==========
else:
    name_new = st.text_input("Nombre completo")
    phone_new = st.text_input("Teléfono")
    phone_new = normalize_phone(phone_new)

    if st.button("Registrar al cliente y abrir tarjeta", type="primary"):
        if not name_new.strip() or not phone_new:
            st.error("Nombre y teléfono son obligatorios.")
        else:
            try:
                # Crea en Customers si no existe
                exists = get_customer_by_phone(phone_new)
                if not exists:
                    create_customer(name_new, phone_new)

                # Asegura tarjeta abierta
                card = ensure_open_card(phone_new)

                st.success(f"Cliente *{name_new}* registrado. Tarjeta *{card['ID_TARJETA']}* abierta.")
                st.info("Ya puedes ir a la pestaña Cliente Perrón para sellar.")
            except Exception as e:
                st.error(f"Error al registrar: {e}")

st.caption("Listo para empezar a acumular sellos ✨")
