import re
from datetime import date, datetime
import streamlit as st
from supabase import create_client, Client

# ==========================
# Conexión a Supabase (usa st.secrets)
# ==========================
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_ANON_KEY = st.secrets["SUPABASE_ANON_KEY"]
supabase: Client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)

# ==========================
# Helpers de BD
# ==========================
def normalize_phone(raw: str) -> str:
    """Deja sólo dígitos."""
    return "".join(re.findall(r"\d+", (raw or "")))

def get_customer_by_phone(phone: str):
    """
    Lee vía VISTA customers_api (name/phone en minúsculas).
    Devuelve dict o None.
    """
    phone = normalize_phone(phone)
    if not phone:
        return None
    res = (
        supabase.table("customers_api")
        .select("*")
        .eq("phone", phone)
        .maybe_single()
        .execute()
    )
    return res.data  # dict | None

def create_customer(name: str, phone: str):
    """Inserta en Customers (con Name y Phone tal cual están en la tabla)."""
    payload = {"Name": (name or "").strip(), "Phone": normalize_phone(phone)}
    return supabase.table("Customers").insert(payload).execute()

def next_card_number() -> int:
    """Cuenta filas exactas en TARJETAS y suma 1."""
    res = supabase.table("TARJETAS").select("id_tarjeta", count="exact").execute()
    return (res.count or 0) + 1

def ensure_open_card(phone: str):
    """
    Busca tarjeta abierta del teléfono; si no existe, crea una.
    Devuelve dict con la tarjeta (id_tarjeta, telefono, etc.).
    """
    phone = normalize_phone(phone)

    # ¿Tarjeta abierta?
    open_res = (
        supabase.table("TARJETAS")
        .select("*")
        .eq("TELEFONO", phone)
        .eq("ESTADO", "abierta")
        .maybe_single()
        .execute()
    )
    card = open_res.data
    if card:
        return card

    # Crear nueva
    n = next_card_number()
    new_card = {
        "ID_TARJETA": f"T-{n:03d}",
        "TELEFONO": phone,
        "FECHA_INICIO": date.today().isoformat(),
        "FECHA_FIN": None,
        "ESTADO": "abierta",
        "NUMERO": 1,
        "SELLOS": 0,
        # MUY IMPORTANTE: esta columna debe existir en la tabla con este nombre en minúsculas
        "fecha_ultimo_sello": None,
    }
    ins = supabase.table("TARJETAS").insert(new_card).execute()
    # Volver a leer lo que quedó en BD
    reread = (
        supabase.table("TARJETAS")
        .select("*")
        .eq("ID_TARJETA", new_card["ID_TARJETA"])
        .maybe_single()
        .execute()
    )
    return reread.data

def can_stamp_today(card: dict) -> bool:
    """
    Candado: sólo 1 sello por día.
    Requiere columna 'fecha_ultimo_sello' en minúsculas en TARJETAS.
    """
    last = card.get("fecha_ultimo_sello")
    if not last:
        return True
    try:
        last_dt = datetime.fromisoformat(str(last)).date()
    except Exception:
        # si viene como 'YYYY-MM-DD' -> igual funciona
        try:
            last_dt = datetime.strptime(str(last), "%Y-%m-%d").date()
        except Exception:
            return True
    return last_dt != date.today()

def do_stamp(card: dict):
    """
    +1 sello y actualiza fecha_ultimo_sello al día de hoy.
    """
    new_count = int(card.get("SELLOS", 0)) + 1
    upd = (
        supabase.table("TARJETAS")
        .update({"SELLOS": new_count, "fecha_ultimo_sello": date.today().isoformat()})
        .eq("ID_TARJETA", card["ID_TARJETA"])
        .execute()
    )
    return upd

def current_prize(card: dict):
    """
    Devuelve el premio/desc. actual de la vista v_tarjeta_con_premio.
    """
    res = (
        supabase.table("v_tarjeta_con_premio")
        .select("*")
        .eq("id_tarjeta", card["ID_TARJETA"])
        .maybe_single()
        .execute()
    )
    return res.data  # dict | None

# ==========================
# UI
# ==========================
st.set_page_config(page_title="10ynueve — Sistema de Sellos", page_icon="✨")
st.title("10ynueve — Sistema de Sellos")
st.caption("Listo para sellar cuando quieras. ✨🐾")

mode = st.radio(
    "Selecciona una opción:",
    options=["Cliente Perrón", "Nuevo Cliente"],
    horizontal=True,
)

phone_input = st.text_input("Ingresa el número de teléfono del cliente:", "")

# ---- CLIENTE PERRÓN (buscar y sellar) ----
if mode == "Cliente Perrón":
    if st.button("Buscar", type="primary"):
        try:
            cust = get_customer_by_phone(phone_input)
            if not cust:
                st.error("Cliente no encontrado en Customers.")
            else:
                phone = cust["phone"]
                name = cust["name"]

                st.success(f"Cliente encontrado: {name} - {phone}")

                # Asegura tarjeta abierta
                card = ensure_open_card(phone)

                # Resumen de tarjeta
                st.info(
                    f"**Tarjeta activa:** {card['ID_TARJETA']} · **Estado:** {card['ESTADO']} · "
                    f"**Número:** {card.get('NUMERO', 1)} · **Inicio:** {card.get('FECHA_INICIO', '')}"
                )

                # Sellos y premio
                st.success(f"**Sellos acumulados:** {int(card.get('SELLOS', 0))}")

                prize = current_prize(card) or {}
                desc_txt = prize.get("descripcion") or "SIN DESCUENTO"
                pct = prize.get("valor")
                tipo = prize.get("tipo")
                if tipo == "PORCENTAJE" and pct is not None:
                    st.warning(f"**Descuento actual:** {desc_txt} ({pct:0.1f}%)")
                else:
                    st.warning(f"**Descuento actual:** {desc_txt}")

                # Botón Sellar (con candado diario)
                if can_stamp_today(card):
                    if st.button("Sellar ahora ✅"):
                        do_stamp(card)
                        st.balloons()
                        st.success("**Tarjeta sellada por Greg!! 🐾**")
                else:
                    st.info("**Tarjeta sellada hoy, vuelve mañana por más sellos.**")

        except Exception as e:
            st.error("Falló al consultar cliente.")
            st.code(f"{type(e).__name__}: {e}")

# ---- NUEVO CLIENTE (alta+tarjeta) ----
else:
    st.subheader("Dar de alta nuevo cliente")

    # Campos **separados** para que NO se confundan con el input de arriba
    new_name = st.text_input("Nombre", key="new_name")
    new_phone = st.text_input("Teléfono", key="new_phone")

    if st.button("Registrar cliente y abrir tarjeta", type="primary"):
        try:
            # OJO: aquí usamos **new_phone**, NO el phone_input de arriba
            clean_phone = normalize_phone(new_phone)

            # Checar si ya existe exactamente ese teléfono en la vista
            already = get_customer_by_phone(clean_phone)
            if already:
                st.warning("Ese número ya tiene registro.")
            else:
                # Crear cliente
                create_customer(new_name, clean_phone)

                # Asegurar tarjeta abierta
                card = ensure_open_card(clean_phone)

                st.success(
                    f"Cliente **{new_name}** registrado con tarjeta **{card['ID_TARJETA']}**."
                )
                st.caption("Listo para sellar cuando quieras. ✨🐾")

        except Exception as e:
            st.error("Falló el registro.")
            st.code(f"{type(e).__name__}: {e}")
