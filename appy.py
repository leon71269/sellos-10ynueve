# app.py
import re
from datetime import date, datetime
import streamlit as st
from supabase import create_client, Client

# ────────────────────────────────────────────────────────────────────────────────
# Config & conexión
# ────────────────────────────────────────────────────────────────────────────────
st.set_page_config(page_title="Tarjeta Perrona", page_icon="🐾", layout="centered")
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_ANON_KEY = st.secrets["SUPABASE_ANON_KEY"]
supabase: Client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)

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

# ────────────────────────────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────────────────────────────
def normalize_phone(raw: str) -> str:
    """Deja solo dígitos."""
    return "".join(re.findall(r"\d+", (raw or "")))

def safe_date(val):
    if not val:
        return None
    s = str(val)
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(s[:len(fmt)], fmt).date()
        except Exception:
            pass
    try:
        return datetime.fromisoformat(s).date()
    except Exception:
        return None

# ────────────────────────────────────────────────────────────────────────────────
# Customers (tabla oficial)
#   Tabla esperada: public."Customers" con columnas "Name"(text), "Phone"(text)
# ────────────────────────────────────────────────────────────────────────────────
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
    dbg("GET Customers by Phone", resp)
    if getattr(resp, "error", None):
        if DEBUG: st.sidebar.error(f"Customers SELECT error: {resp.error}")
        return None
    return resp.data

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

# ────────────────────────────────────────────────────────────────────────────────
# Tarjetas
#   Tabla esperada: public."TARJETAS"
#   ID_TARJETA(text) | TELEFONO(text) | FECHA_INICIO(date) | FECHA_FIN(date|null)
#   ESTADO(text) | NUMERO(int) | SELLOS(int) | fecha_ultimo_sello(date|null)
# ────────────────────────────────────────────────────────────────────────────────
def next_card_number() -> int:
    resp = supabase.table("TARJETAS").select("id_tarjeta", count="exact").execute()
    dbg("COUNT TARJETAS", resp)
    return (getattr(resp, "count", 0) or 0) + 1

def ensure_open_card(phone: str):
    """Devuelve tarjeta abierta del teléfono o crea una nueva."""
    phone = normalize_phone(phone)
    # Buscar abierta
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
    """Bloquea sellar el mismo día del alta y máximo 1 sello por día."""
    inicio = safe_date(card.get("FECHA_INICIO"))
    if inicio == date.today():
        return False
    last = safe_date(card.get("fecha_ultimo_sello"))
    if last is None:
        return True
    return last != date.today()

def reread_card(id_tarjeta: str):
    resp = (
        supabase.table("TARJETAS")
        .select("*")
        .eq("ID_TARJETA", id_tarjeta)
        .single()
        .execute()
    )
    dbg("REREAD TARJETA", resp)
    if getattr(resp, "error", None):
        raise RuntimeError(str(resp.error))
    return resp.data

def do_stamp(card: dict):
    """+1 sello y fecha_ultimo_sello = hoy. Devuelve la fila actualizada."""
    try:
        new_count = int(card.get("SELLOS", 0)) + 1
    except Exception:
        new_count = 1
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

# ────────────────────────────────────────────────────────────────────────────────
# Descuentos / Progreso
#   Vistas esperadas (si existen):
#     - v_tarjeta_con_premio         → premio/desc actual para id_tarjeta
#     - v_tarjeta_progreso (o prog*) → info de meta/siguientes
# ────────────────────────────────────────────────────────────────────────────────
def current_prize(card: dict):
    """Devuelve dict con premio actual o None."""
    resp = (
        supabase.table("v_tarjeta_con_premio")
        .select("*")
        .eq("id_tarjeta", card["ID_TARJETA"])
        .limit(1)
        .maybe_single()
        .execute()
    )
    dbg("PRIZE (v_tarjeta_con_premio)", resp)
    if getattr(resp, "error", None):
        return None
    return resp.data

def progress_info(card: dict):
    """
    Intenta leer progreso desde vistas conocidas.
    Estructura flexible: devuelve dict con llaves útiles si existen.
    """
    # 1) v_tarjeta_progreso
    for view_name in ["v_tarjeta_progreso", "v_tarjeta_prog", "v_tarjeta_progress"]:
        try:
            resp = (
                supabase.table(view_name)
                .select("*")
                .eq("id_tarjeta", card["ID_TARJETA"])
                .limit(1)
                .maybe_single()
                .execute()
            )
            dbg(f"PROGRESO ({view_name})", resp)
            if getattr(resp, "error", None):
                continue
            if resp.data:
                return resp.data
        except Exception:
            continue
    # Si no existen vistas, regresamos datos mínimos
    return {
        "sellos": int(card.get("SELLOS", 0)),
        "meta": None,
        "siguiente_meta": None,
    }

def prize_label(prize: dict | None) -> str:
    if not prize:
        return "SIN DESCUENTO"
    desc = prize.get("descripcion") or "SIN DESCUENTO"
    tipo = prize.get("tipo")
    val = prize.get("valor")
    if tipo == "PORCENTAJE" and val is not None:
        try:
            return f"{desc} ({float(val):0.1f}%)"
        except Exception:
            return f"{desc}"
    return desc

# ────────────────────────────────────────────────────────────────────────────────
# UI
# ────────────────────────────────────────────────────────────────────────────────
st.title("Tarjeta Perrona 🐾✨")
tabs = st.tabs(["🔹 Nuevo Cliente", "🔸 Sellar Tarjeta"])

# ── Nuevo Cliente ───────────────────────────────────────────────────────────────
with tabs[0]:
    st.subheader("Dar de alta nuevo cliente")
    n_name = st.text_input("Nombre", key="new_name")
    n_phone = st.text_input("Teléfono", key="new_phone", help="10 dígitos, acepta espacios o guiones")

    if st.button("Registrar cliente y abrir tarjeta", type="primary"):
        try:
            clean_phone = normalize_phone(n_phone)
            if not clean_phone or not (n_name or "").strip():
                st.error("Nombre y teléfono son obligatorios.")
                st.stop()

            # ¿Ya existe?
            if get_customer_by_phone(clean_phone):
                st.warning("Ese número ya tiene registro.")
                st.stop()

            create_customer(n_name, clean_phone)
            card = ensure_open_card(clean_phone)
            st.success(f"Cliente **{n_name}** registrado con tarjeta **{card['ID_TARJETA']}**.")
            st.caption("⛔ Política: no se puede sellar el **mismo día** del registro.")
        except Exception as e:
            st.error("Falló el registro.")
            if DEBUG: st.exception(e)

# ── Sellar Tarjeta ─────────────────────────────────────────────────────────────
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
            name  = cust.get("Name") or cust.get("name") or "Sin nombre"
            st.success(f"Cliente: {name} · {phone}")

            card = ensure_open_card(phone)

            # Mostrar estado actual
            st.info(
                f"**Tarjeta:** {card['ID_TARJETA']} · **Estado:** {card['ESTADO']} · "
                f"**Número:** {card.get('NUMERO', 1)} · **Inicio:** {card.get('FECHA_INICIO', '')}"
            )
            st.success(f"**Sellos:** {int(card.get('SELLOS', 0))}")

            # Premio y progreso actuales
            prize_before = current_prize(card)
            st.warning(f"**Descuento actual:** {prize_label(prize_before)}")

            prog = progress_info(card)
            # Render opcional de progreso si la vista lo provee
            try:
                sellos = prog.get("sellos") or int(card.get("SELLOS", 0))
                meta   = prog.get("meta") or prog.get("siguiente_meta")
                if meta:
                    # Si tu vista devuelve total del ciclo, muestra barra
                    val = min(max(float(sellos)/float(meta), 0.0), 1.0)
                    st.progress(val, text=f"Progreso: {sellos}/{meta} sellos")
            except Exception:
                pass

            # Mensaje si ya está ocupado por hoy (por re-entrada)
            flag_key = f"stamped_{card['ID_TARJETA']}_{date.today().isoformat()}"
            if st.session_state.get(flag_key, False):
                st.info("**Descuento ocupado por hoy, vuelve mañana!!**")

            # Botón sellar con candados
            if can_stamp_today(card):
                if st.button("Sellar ahora ✅", key=f"sell_btn_{card['ID_TARJETA']}"):
                    try:
                        # Escribir sello y VOLVER A LEER tarjeta
                        card = do_stamp(card)
                        st.session_state[flag_key] = True
                        st.balloons()
                        st.success("**Tarjeta sellada por Greg!! 🐾**")
                        st.caption(f"Último sello: {card.get('fecha_ultimo_sello')}")

                        # Recalcular premio tras sellar
                        prize_after = current_prize(card)
                        if prize_label(prize_after) != prize_label(prize_before):
                            st.success(f"🎉 **¡Nuevo descuento desbloqueado!** → {prize_label(prize_after)}")

                        # Refrescar contadores visibles
                        st.success(f"**Sellos:** {int(card.get('SELLOS', 0))}")
                        # Reintentar progreso
                        prog2 = progress_info(card)
                        try:
                            sellos2 = prog2.get("sellos") or int(card.get("SELLOS", 0))
                            meta2   = prog2.get("meta") or prog2.get("siguiente_meta")
                            if meta2:
                                val2 = min(max(float(sellos2)/float(meta2), 0.0), 1.0)
                                st.progress(val2, text=f"Progreso: {sellos2}/{meta2} sellos")
                        except Exception:
                            pass

                    except Exception as e:
                        st.error("No pude sellar la tarjeta.")
                        if DEBUG: st.exception(e)
            else:
                st.info("**Descuento ocupado por hoy, vuelve mañana!!**")

        except Exception as e:
            st.error("Falló la búsqueda/actualización.")
            if DEBUG: st.exception(e)
