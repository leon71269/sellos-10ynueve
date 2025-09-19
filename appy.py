# app.py
import re
from datetime import date, datetime
import streamlit as st
from supabase import create_client, Client

# ==========================
# Conexión a Supabase
# ==========================
st.set_page_config(page_title="Tarjeta Perrona", page_icon="🐾", layout="centered")
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_ANON_KEY = st.secrets["SUPABASE_ANON_KEY"]
supabase: Client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)

# ==========================
# Utilidades / Debug
# ==========================
DEBUG = st.sidebar.toggle("🔧 Modo debug", value=False)

def dbg(label, resp):
    if not DEBUG:
        return
    try:
        st.sidebar.write(f"**{label}**")
        st.sidebar.json({
            "status_code": getattr(resp, "status_code", None),
            "count": getattr(resp, "count", None),
            "data": getattr(resp, "data", None),
            "error": str(getattr(resp, "error", None))
        })
    except Exception as e:
        st.sidebar.write(f"(no parseable) {e}")

def normalize_phone(raw: str) -> str:
    """Deja sólo dígitos para comparar/guardar consistente."""
    return "".join(re.findall(r"\d+", (raw or "")))

def single(q):
    """Ejecuta .execute() y regresa data o lanza con el error."""
    resp = q.execute()
    dbg("QUERY", resp)
    if getattr(resp, "error", None):
        raise RuntimeError(str(resp.error))
    return getattr(resp, "data", None)

# ==========================
# Customers (tabla oficial)
# ==========================
# Estructura asumida: public."Customers" con columnas "Name" (text) y "Phone" (text)
def get_customer_by_phone(phone: str):
    phone = normalize_phone(phone)
    if not phone:
        return None
    resp = (
        supabase.table("Customers")
        .select("*")
        .eq("Phone", phone)
        .limit(1)
        .maybe_single()
        .execute()
    )
    dbg("GET Customers by phone", resp)
    if getattr(resp, "error", None):
        # Si hay error (p.ej. tabla no existe), lo mostramos en debug y devolvemos None
        if DEBUG:
            st.sidebar.error(f"Customers SELECT error: {resp.error}")
        return None
    return resp.data  # dict | None

def create_customer(name: str, phone: str):
    payload = {"Name": (name or "").strip(), "Phone": normalize_phone(phone)}
    resp = (
        supabase.table("Customers")
        .insert(payload)
        .select("*")
        .single()
        .execute()
    )
    dbg("INSERT Customers", resp)
    if getattr(resp, "error", None):
        raise RuntimeError(str(resp.error))
    return resp.data

# ==========================
# TARJETAS
# ==========================
# Estructura asumida:
# ID_TARJETA (text) | TELEFONO (text) | FECHA_INICIO (date) | FECHA_FIN (date|null)
# ESTADO (text: 'abierta'/'cerrada') | NUMERO (int) | SELLOS (int) | fecha_ultimo_sello (date|null)

def next_card_number() -> int:
    resp = supabase.table("TARJETAS").select("id_tarjeta", count="exact").execute()
    dbg("COUNT TARJETAS", resp)
    return (getattr(resp, "count", 0) or 0) + 1

def ensure_open_card(phone: str):
    """Devuelve tarjeta abierta del teléfono o crea una nueva. Nunca regresa None (lanza si falla)."""
    phone = normalize_phone(phone)
    # ¿Existe abierta?
    resp = (
        supabase.table("TARJETAS")
        .select("*")
        .eq("TELEFONO", phone)
        .eq("ESTADO", "abierta")
        .limit(1)
        .maybe_single()
        .execute()
    )
    dbg("GET TARJETA abierta", resp)
    if getattr(resp, "error", None):
        raise RuntimeError(str(resp.error))
    if resp.data:
        return resp.data

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
        "fecha_ultimo_sello": None,
    }
    created = (
        supabase.table("TARJETAS")
        .insert(new_card)
        .select("*")
        .single()
        .execute()
    )
    dbg("INSERT TARJETA", created)
    if getattr(created, "error", None):
        raise RuntimeError(str(created.error))
    return created.data

def can_stamp_today(card: dict) -> bool:
    """Bloquea sellar el mismo día del alta y 1 vez por día."""
    # Bloqueo por día de alta
    inicio = card.get("FECHA_INICIO")
    if inicio:
        try:
            if datetime.fromisoformat(str(inicio)).date() == date.today():
                return False
        except Exception:
            pass
    # 1 sello por día
    last = card.get("fecha_ultimo_sello")
    if not last:
        return True
    try:
        last_dt = datetime.fromisoformat(str(last)).date()
    except Exception:
        try:
            last_dt = datetime.strptime(str(last), "%Y-%m-%d").date()
        except Exception:
            return True
    return last_dt != date.today()

def do_stamp(card: dict):
    """Suma 1 sello y actualiza fecha_ultimo_sello a hoy. Devuelve la fila actualizada."""
    new_count = int(card.get("SELLOS", 0)) + 1
    resp = (
        supabase.table("TARJETAS")
        .update({"SELLOS": new_count, "fecha_ultimo_sello": date.today().isoformat()})
        .eq("ID_TARJETA", card["ID_TARJETA"])
        .select("*")
        .single()
        .execute()
    )
    dbg("UPDATE TARJETA sello", resp)
    if getattr(resp, "error", None):
        raise RuntimeError(str(resp.error))
    return resp.data

def current_prize(card: dict):
    """Opcional: vista con el premio actual."""
    resp = (
        supabase.table("v_tarjeta_con_premio")
        .select("*")
        .eq("id_tarjeta", card["ID_TARJETA"])
        .limit(1)
        .maybe_single()
        .execute()
    )
    dbg("PRIZE", resp)
    if getattr(resp, "error", None):
        # Si no existe la vista o no hay permisos, no rompemos el flujo
        if DEBUG:
            st.sidebar.warning(f"vista premio error: {resp.error}")
        return None
    return resp.data

# ==========================
# UI
# ==========================
st.title("Tarjeta Perrona 🐾✨")
tabs = st.tabs(["🔹 Nuevo Cliente", "🔸 Sellar Tarjeta"])

# -------- Nuevo Cliente --------
with tabs[0]:
    st.subheader("Dar de alta nuevo cliente")
    n_name = st.text_input("Nombre", key="new_name")
    n_phone = st.text_input("Teléfono", key="new_phone", help="10 dígitos, puede traer espacios o guiones")

    if st.button("Registrar cliente y abrir tarjeta", type="primary"):
        try:
            clean_phone = normalize_phone(n_phone)
            if not clean_phone or not (n_name or "").strip():
                st.error("Nombre y teléfono son obligatorios.")
                st.stop()

            # ¿ya existe?
            if get_customer_by_phone(clean_phone):
                st.warning("Ese número ya tiene registro.")
                st.stop()

            # Crear cliente + tarjeta abierta
            create_customer(n_name, clean_phone)
            card = ensure_open_card(clean_phone)

            st.success(f"Cliente **{n_name}** registrado con tarjeta **{card['ID_TARJETA']}**.")
            st.caption("⛔ Política: no se puede sellar el **mismo día** del registro.")
        except Exception as e:
            st.error("Falló el registro.")
            if DEBUG:
                st.exception(e)

# -------- Sellar Tarjeta --------
with tabs[1]:
    st.subheader("Sellar tarjeta")
    s_phone = st.text_input("Ingresa el teléfono del cliente", key="sell_phone")

    if st.button("Buscar", type="primary"):
        try:
            cust = get_customer_by_phone(s_phone)
            if not cust:
                st.error("No encontré ese teléfono. Verifica o da de alta el cliente en la pestaña anterior.")
                st.stop()

            phone = normalize_phone(cust.get("Phone") or cust.get("phone"))
            name = cust.get("Name") or cust.get("name") or "Sin nombre"
            st.success(f"Cliente: {name} · {phone}")

            card = ensure_open_card(phone)
            st.info(
                f"**Tarjeta:** {card['ID_TARJETA']} · **Estado:** {card['ESTADO']} · "
                f"**Número:** {card.get('NUMERO', 1)} · **Inicio:** {card.get('FECHA_INICIO', '')}"
            )
            st.success(f"**Sellos:** {int(card.get('SELLOS', 0))}")

            prize = current_prize(card) or {}
            desc_txt = prize.get("descripcion") or "SIN DESCUENTO"
            pct = prize.get("valor")
            tipo = prize.get("tipo")
            if tipo == "PORCENTAJE" and pct is not None:
                st.warning(f"**Descuento:** {desc_txt} ({pct:0.1f}%)")
            else:
                st.warning(f"**Descuento:** {desc_txt}")

            if can_stamp_today(card):
                if st.button("Sellar ahora ✅"):
                    card = do_stamp(card)
                    st.balloons()
                    st.success("**¡Sello agregado!**")
                    st.caption(f"Último sello: {card.get('fecha_ultimo_sello')}")
            else:
                st.info("⛔ No se puede sellar hoy (día de alta o ya sellado hoy).")

        except Exception as e:
            st.error("Falló al consultar/actualizar.")
            if DEBUG:
                st.exception(e)
