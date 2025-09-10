# appy.py
import re
from datetime import date, datetime
import streamlit as st
from supabase import create_client, Client

# =====================================================
#  Configuración: variables de entorno (st.secrets)
# =====================================================
def _clean_ascii(s: str) -> str:
    s = (s or "").strip()
    return "".join(ch for ch in s if 32 <= ord(ch) < 127)

SUPABASE_URL = _clean_ascii(st.secrets["SUPABASE_URL"])
SUPABASE_ANON_KEY = _clean_ascii(st.secrets["SUPABASE_ANON_KEY"])
supabase: Client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)

# =====================================================
#  Helpers de datos
# =====================================================
def normalize_phone(raw: str) -> str:
    """Solo dígitos."""
    return "".join(re.findall(r"\d+", raw or ""))

def get_customer_by_phone(phone: str):
    """
    Busca cliente en VISTA customers_api (columnas en minúsculas: name, phone).
    Retorna dict o None.
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
    """Crea cliente en tabla Customers (columnas con mayúsculas)."""
    payload = {"Name": (name or "").strip(), "Phone": (phone or "").strip()}
    res = supabase.table("Customers").insert(payload).execute()
    return res.data[0] if res.data else None

def _next_card_id() -> str:
    """
    Lee el último ID_TARJETA (ordenado desc) y genera el siguiente.
    Evita colisiones de ID.
    """
    res = (
        supabase.table("TARJETAS")
        .select("ID_TARJETA")
        .order("ID_TARJETA", desc=True)
        .limit(1)
        .execute()
    )
    last_id = res.data[0]["ID_TARJETA"] if res.data else None
    if last_id:
        m = re.search(r"(\d+)$", last_id)
        nxt = int(m.group(1)) + 1 if m else 1
    else:
        nxt = 1
    return f"T-{nxt:03d}"

def ensure_open_card(phone: str):
    """
    Devuelve tarjeta abierta del teléfono o crea una nueva.
    Estructura TARJETAS esperada:
      - ID_TARJETA (text) PK/UNIQUE
      - TELEFONO (text, FK a Customers.Phone)
      - FECHA_INICIO (date)
      - FECHA_FIN (date|null)
      - ESTADO (text: 'abierta'|'cerrada')
      - NUMERO_TARJETA (int)  -- contador de cuántas tarjetas va (1,2,...)
    """
    # 1) ¿ya hay abierta?
    res = (
        supabase.table("TARJETAS")
        .select("*")
        .eq("TELEFONO", phone)
        .eq("ESTADO", "abierta")
        .maybe_single()
        .execute()
    )
    if res.data:
        return res.data

    # 2) contar cuántas tarjetas tiene para asignar NUMERO_TARJETA
    cnt = (
        supabase.table("TARJETAS")
        .select("ID_TARJETA", count="exact")
        .eq("TELEFONO", phone)
        .execute()
        .count
        or 0
    )
    new_id = _next_card_id()
    payload = {
        "ID_TARJETA": new_id,
        "TELEFONO": phone,
        "FECHA_INICIO": date.today().isoformat(),
        "FECHA_FIN": None,
        "ESTADO": "abierta",
        "NUMERO_TARJETA": int(cnt) + 1,
    }
    created = supabase.table("TARJETAS").insert(payload).execute()
    return created.data[0] if created.data else None

def seals_count(phone: str) -> int:
    """
    Cuenta sellos en COMPRAS por TELEFONO.
    Estructura COMPRAS esperada:
      - ID_COMPRA (text) p.ej. C-001
      - TELEFONO (text)
      - FECHA (date)
      - SELLO_OTORGADO (bool|int|null) opcional
    """
    res = (
        supabase.table("COMPRAS")
        .select("ID_COMPRA", count="exact")
        .eq("TELEFONO", phone)
        .execute()
    )
    return int(res.count or 0)

def _today_iso() -> str:
    return date.today().isoformat()

def already_stamped_today(phone: str) -> bool:
    """Candado: ¿ya se selló hoy este teléfono?"""
    res = (
        supabase.table("COMPRAS")
        .select("ID_COMPRA", count="exact")
        .eq("TELEFONO", phone)
        .eq("FECHA", _today_iso())
        .execute()
    )
    return (res.count or 0) > 0

def _next_purchase_id() -> str:
    res = (
        supabase.table("COMPRAS")
        .select("ID_COMPRA", count="exact")
        .execute()
    )
    n = int(res.count or 0) + 1
    return f"C-{n:04d}"

def stamp_today(phone: str):
    """Inserta compra de hoy (un sello). Respeta candado fuera."""
    payload = {
        "ID_COMPRA": _next_purchase_id(),
        "TELEFONO": phone,
        "FECHA": _today_iso(),
        "SELLO_OTORGADO": True,
    }
    supabase.table("COMPRAS").insert(payload).execute()

def current_discount_for(seals: int) -> dict:
    """
    Devuelve el descuento que toca dado # de sellos acumulados.
    Estrategia: toma DESCUENTOS activos ordenados por ID_DESCUENTO asc
    y hace index = min(sellos, len-1). Así el primer registro aplica con 0 sellos,
    el segundo con 1 sello, etc.
    Estructura DESCUENTOS:
      - ID_DESCUENTO (text)
      - DESCRIPCION (text)
      - TIPO (text) p.ej. 'PORCENTAJE'|'PROMO'
      - VAL (numeric) p.ej. 10, 5, ...
      - ACTIVO (int/bool) 1 = activo
    """
    res = (
        supabase.table("DESCUENTOS")
        .select("*")
        .eq("ACTIVO", 1)
        .order("ID_DESCUENTO", desc=False)
        .execute()
    )
    rows = res.data or []
    if not rows:
        return {"DESCRIPCION": "Sin descuento", "TIPO": "NINGUNO", "VAL": 0}

    idx = min(seals, len(rows) - 1)
    return rows[idx]

# =====================================================
#  UI
# =====================================================
st.set_page_config(page_title="10ynueve — Sistema de Sellos", page_icon="⭐", layout="wide")

st.markdown(
    """
    <style>
    .pill { border-radius: 12px; padding: 10px 14px; margin: 6px 0; font-weight: 600; }
    .pill-green { background:#1f6f43; color:#e8fff4; }
    .pill-blue { background:#144e66; color:#e6f7ff; }
    .pill-amber { background:#6b5800; color:#fff6d6; }
    .pill-lime { background:#274b1f; color:#ecffd7; }
    .btn-primary button { background:#ff7a1a !important; color:white !important; font-weight:700; }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("10ynueve — Sistema de Sellos")

mode = st.radio("Selecciona una opción:", ["Cliente Perrón", "Nuevo Cliente"], horizontal=True)

phone_input = st.text_input("Ingresa el número de teléfono del cliente:", "")
col_busc, _ = st.columns([1, 3])
with col_busc:
    buscar = st.button("Buscar", use_container_width=True)

def show_card_box(card: dict):
    if not card:
        return
    st.markdown(
        f"""<div class="pill pill-blue">
        <b>Tarjeta activa:</b> {card['ID_TARJETA']} &nbsp;·&nbsp;
        <b>Estado:</b> {card['ESTADO']} &nbsp;·&nbsp;
        <b>Número:</b> {card['NUMERO_TARJETA']} &nbsp;·&nbsp;
        <b>Inicio:</b> {card['FECHA_INICIO']}
        </div>""",
        unsafe_allow_html=True,
    )

def show_seals_box(n: int):
    st.markdown(f"""<div class="pill pill-lime"><b>Sellos acumulados:</b> {n}</div>""", unsafe_allow_html=True)

def show_discount_box(desc_row: dict):
    if not desc_row:
        return
    tipo = desc_row.get("TIPO", "")
    val = desc_row.get("VAL", 0)
    descripcion = desc_row.get("DESCRIPCION", "Descuento")
    label = descripcion
    if tipo.upper() == "PORCENTAJE":
        label = f"{descripcion} ({float(val):.1f}%)"
    st.markdown(f"""<div class="pill pill-amber"><b>Descuento actual:</b> {label}</div>""", unsafe_allow_html=True)

# ========== Lógica principal ==========
if buscar:
    try:
        phone = normalize_phone(phone_input)
        if not phone:
            st.warning("Ingresa un teléfono válido.")
        else:
            cust = get_customer_by_phone(phone)
            if not cust:
                st.error("Cliente no encontrado en Customers.")
                with st.expander("Sugerencia si usas la vista"):
                    st.code(
                        'CREATE OR REPLACE VIEW customers_api AS SELECT "Name" AS name, "Phone" AS phone FROM "Customers";',
                        language="sql",
                    )
            else:
                st.markdown(
                    f"""<div class="pill pill-green">
                    Cliente encontrado: <b>{cust['name']}</b> · {cust['phone']}
                    </div>""",
                    unsafe_allow_html=True,
                )
                card = ensure_open_card(phone)
                show_card_box(card)

                n_seals = seals_count(phone)
                show_seals_box(n_seals)

                desc_row = current_discount_for(n_seals)
                show_discount_box(desc_row)

                # Botón SELLAR (candado 1 por día)
                sellar = st.button("Sellar tarjeta", key="sellar_btn", type="primary")
                if sellar:
                    if already_stamped_today(phone):
                        st.warning("Tarjeta sellada hoy, vuelve mañana por más sellos.")
                    else:
                        stamp_today(phone)
                        st.success("Tarjeta sellada por Greg!! 🐾")
                        # refrescar contadores
                        n_seals = seals_count(phone)
                        show_seals_box(n_seals)
                        desc_row = current_discount_for(n_seals)
                        show_discount_box(desc_row)

    except Exception as e:
        st.error("Falló al consultar cliente.")
        st.code(f"{type(e)._name_}: {e}")

# ====== Alta de nuevo cliente ======
if mode == "Nuevo Cliente":
    st.subheader("Dar de alta nuevo cliente")
    nuevo_nombre = st.text_input("Nombre")
    if st.button("Registrar cliente y abrir tarjeta", key="alta_btn"):
        try:
            phone = normalize_phone(phone_input)
            if not nuevo_nombre.strip() or not phone:
                st.error("Nombre y teléfono obligatorios.")
            else:
                # evita duplicar clientes:
                existing = get_customer_by_phone(phone)
                if not existing:
                    create_customer(nuevo_nombre, phone)
                card = ensure_open_card(phone)
                st.success(f"Cliente {nuevo_nombre} registrado con tarjeta {card['ID_TARJETA']}.")
        except Exception as e:
            st.error(f"Error: {e}")

st.caption("Listo para sellar cuando quieras. ✨🐾")
