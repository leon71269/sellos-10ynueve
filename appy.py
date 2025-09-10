# appy.py — 10ynueve · Sistema de Sellos
import streamlit as st
from datetime import date, datetime
from typing import Optional, Dict, Any, Tuple, List

# ========= Conexión a Supabase (usa st.secrets) =========
from supabase import create_client, Client

def _clean_ascii(s: str) -> str:
    s = (s or "").strip()
    return "".join(ch for ch in s if 32 <= ord(ch) < 127)

SUPABASE_URL  = _clean_ascii(st.secrets["SUPABASE_URL"])
SUPABASE_KEY  = _clean_ascii(st.secrets["SUPABASE_ANON_KEY"])
sb: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ========= Helpers de BD =========
def get_customer_by_phone(phone: str) -> Optional[Dict[str, Any]]:
    """Lee desde la vista customers_api (name, phone)."""
    phone = (phone or "").strip()
    res = sb.table("customers_api").select("*").eq("phone", phone).maybe_single().execute()
    data = getattr(res, "data", None)
    if isinstance(data, dict):
        return data
    return None

def next_sequential_id(prefix: str, table: str, id_col: str) -> str:
    """Genera ID tipo T-001 / C-001 según cantidad actual."""
    res = sb.table(table).select(id_col, count="exact").execute()
    count = getattr(res, "count", 0) or 0
    return f"{prefix}-{count+1:03d}"

def get_open_card(phone: str) -> Optional[Dict[str, Any]]:
    """Regresa tarjeta abierta de un teléfono (si existe)."""
    q = (
        sb.table("TARJETAS")
        .select("*")
        .eq("TELEFONO", phone)
        .eq("ESTADO", "abierta")
        .order("FECHA_INICIO", desc=True)
        .limit(1)
        .execute()
    )
    rows = q.data or []
    return rows[0] if rows else None

def ensure_open_card(phone: str) -> Dict[str, Any]:
    """Devuelve una tarjeta abierta; si no existe crea una."""
    card = get_open_card(phone)
    if card:
        return card

    new_id = next_sequential_id("T", "TARJETAS", "ID_TARJETA")
    today = str(date.today())
    payload = {
        "ID_TARJETA": new_id,
        "TELEFONO": phone,
        "FECHA_INICIO": today,
        "FECHA_FIN": None,
        "ESTADO": "abierta",
        "NUMERO_TARJETA": 1,
        "FECHA_ULTIMO_SELLO": None,
        "SELLOS": 0,
    }
    ins = sb.table("TARJETAS").insert(payload).execute()
    return ins.data[0]

def list_active_discounts() -> List[Dict[str, Any]]:
    """Obtiene descuentos activos, ordenados por ID_DESCUENTO (D-001, D-002, ...)."""
    res = (
        sb.table("DESCUENTOS")
        .select("*")
        .eq("ACTIVO", 1)
        .order("ID_DESCUENTO", desc=False)
        .execute()
    )
    return res.data or []

def current_reward_for_sellos(sellos: int, discounts: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Regresa el descuento correspondiente al índice 'sellos'.
    Regla: offset = sellos actuales (0->primer descuento, 1->segundo, etc.)
    Si se pasan los disponibles, se queda en el último.
    """
    if not discounts:
        return {"DESCRIPCION": "Sin descuentos configurados", "TIPO": "", "VALOR": 0}
    idx = min(max(sellos, 0), len(discounts) - 1)
    return discounts[idx]

def already_stamped_today(card: Dict[str, Any]) -> bool:
    """Candado diario."""
    last = card.get("FECHA_ULTIMO_SELLO")
    if not last:
        return False
    try:
        last_d = datetime.strptime(last, "%Y-%m-%d").date()
    except Exception:
        # Por si llega como datetime ISO
        try:
            last_d = datetime.fromisoformat(last).date()
        except Exception:
            return False
    return last_d == date.today()

def add_stamp_today(card: Dict[str, Any]) -> Dict[str, Any]:
    """Suma 1 sello (si no ha sellado hoy) y actualiza fecha_ultimo_sello."""
    if already_stamped_today(card):
        return card
    new_count = int(card.get("SELLOS", 0) or 0) + 1
    upd = (
        sb.table("TARJETAS")
        .update({"SELLOS": new_count, "FECHA_ULTIMO_SELLO": str(date.today())})
        .eq("ID_TARJETA", card["ID_TARJETA"])
        .execute()
    )
    return upd.data[0]

# ========= UI =========
st.set_page_config(page_title="10ynueve — Sistema de Sellos", page_icon="✨", layout="wide")
st.markdown("## 10ynueve — Sistema de Sellos")

mode = st.radio("Selecciona una opción:", ["Cliente Perrón", "Nuevo Cliente"], horizontal=True)

phone_input = st.text_input("Ingresa el número de teléfono del cliente:", value="", max_chars=20)
col_buscar, col_sp = st.columns([1, 8])
buscar = col_buscar.button("Buscar", type="primary")

discounts = list_active_discounts()

def paint_card_info(card: Dict[str, Any]):
    sellos = int(card.get("SELLOS", 0) or 0)
    reward = current_reward_for_sellos(sellos, discounts)
    st.info(
        f"*Tarjeta activa:* {card['ID_TARJETA']} · *Estado:* {card['ESTADO']} "
        f"· *Número:* {card.get('NUMERO_TARJETA', 1)} · *Inicio:* {card['FECHA_INICIO']}"
    )
    st.success(f"*Sellos acumulados:* {sellos}")
    st.warning(f"*Descuento actual:* {reward.get('DESCRIPCION', '—')} "
               f"{'(%.0f%%)' % reward['VALOR'] if reward.get('TIPO')=='PORCENTAJE' else ''}")

    # Candado diario
    if already_stamped_today(card):
        st.error("🔒 Esta tarjeta ya fue sellada hoy. Vuelve mañana.")
    else:
        if st.button("Sellar hoy ✅"):
            updated = add_stamp_today(card)
            st.success("¡Sello registrado!")
            st.session_state["_just_updated_"] = True
            st.rerun()

if buscar:
    phone = phone_input.strip()
    if not phone:
        st.error("Escribe un teléfono.")
    else:
        try:
            cust = get_customer_by_phone(phone)
            if mode == "Cliente Perrón":
                if not cust:
                    st.error("Cliente no encontrado en *Customers*.")
                    with st.expander("Sugerencia si usas la vista"):
                        st.code(
                            'CREATE OR REPLACE VIEW customers_api AS '
                            'SELECT "Name" AS name, "Phone" AS phone FROM "Customers";',
                            language="sql",
                        )
                else:
                    st.success(f"Cliente encontrado: *{cust['name']}* · {cust['phone']}")
                    card = ensure_open_card(cust["phone"])
                    paint_card_info(card)

            else:  # Nuevo Cliente
                st.subheader("Dar de alta nuevo cliente")
                name_new = st.text_input("Nombre")
                if st.button("Registrar cliente y abrir tarjeta", type="primary"):
                    if not name_new.strip():
                        st.error("Nombre obligatorio.")
                    else:
                        # Si existe, usarlo; si no, crearlo
                        if not cust:
                            sb.table("Customers").insert(
                                {"Name": name_new.strip(), "Phone": phone}
                            ).execute()
                            st.success("Cliente creado.")
                        card = ensure_open_card(phone)
                        paint_card_info(card)

        except Exception as e:
            st.error("Falló al consultar cliente.")
            st.code(str(e))
            st.stop()

st.caption("Listo para empezar a acumular sellos ✨")
