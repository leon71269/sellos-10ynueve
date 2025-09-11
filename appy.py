# appy.py — 10ynueve · Sistema de Sellos
# ─────────────────────────────────────────────────────────────────────────────
# Requiere en Streamlit Secrets:
#   SUPABASE_URL
#   SUPABASE_ANON_KEY
# Paquetes en requirements.txt: streamlit, supabase, pandas (opcional)

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Optional, Dict, Any, List

import streamlit as st
from supabase import create_client, Client


# ─────────────────────────────────────────────────────────────────────────────
# Conexión a Supabase (usa st.secrets)
# ─────────────────────────────────────────────────────────────────────────────

def _clean_ascii(s: str) -> str:
    if not isinstance(s, str):
        return ""
    s = s.strip()
    return "".join(ch for ch in s if 32 <= ord(ch) < 127)

try:
    SUPABASE_URL = _clean_ascii(st.secrets["SUPABASE_URL"])
    SUPABASE_ANON_KEY = _clean_ascii(st.secrets["SUPABASE_ANON_KEY"])
except Exception:
    st.error("Faltan secrets `SUPABASE_URL` y/o `SUPABASE_ANON_KEY` en Streamlit Cloud → Settings → Secrets.")
    st.stop()

supabase: Client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)


# ─────────────────────────────────────────────────────────────────────────────
# Utilerías de BD
# ─────────────────────────────────────────────────────────────────────────────

def normalize_phone(raw: str) -> str:
    """Deja solo dígitos."""
    return "".join(re.findall(r"\d+", raw or ""))

def get_customer_by_phone(phone: str) -> Optional[Dict[str, Any]]:
    """
    Prioriza leer via VISTA `customers_api (name, phone)`.
    Si no existe, lee directo de `Customers("Name","Phone")`.
    """
    phone = normalize_phone(phone)

    # 1) intenta vista
    try:
        res = supabase.table("customers_api").select("*").eq("phone", phone).maybe_single().execute()
        if isinstance(res.data, dict) and res.data:
            return {"name": res.data.get("name", ""), "phone": res.data.get("phone", "")}
    except Exception:
        pass  # si la vista no existe, seguimos al fallback

    # 2) fallback tabla Customers
    res = supabase.table("Customers").select("Name, Phone").eq("Phone", phone).maybe_single().execute()
    if isinstance(res.data, dict) and res.data:
        return {"name": res.data.get("Name", ""), "phone": res.data.get("Phone", "")}
    return None

def customer_exists(phone: str) -> bool:
    phone = normalize_phone(phone)
    try:
        r = supabase.table("Customers").select("Phone", count="exact").eq("Phone", phone).execute()
        return (r.count or 0) > 0
    except Exception:
        # Fallback por si el cliente solo está en la vista:
        return get_customer_by_phone(phone) is not None

def create_customer(name: str, phone: str) -> None:
    phone = normalize_phone(phone)
    supabase.table("Customers").insert({"Name": (name or "").strip(), "Phone": phone}).execute()

def next_global_card_id() -> str:
    """
    Genera ID_TARJETA global tipo T-001, T-002… buscando el mayor existente.
    """
    r = supabase.table("TARJETAS").select("ID_TARJETA").order("ID_TARJETA", desc=True).limit(1).execute()
    last = (r.data or [{}])[0].get("ID_TARJETA")
    n = 0
    if isinstance(last, str) and last.startswith("T-"):
        try:
            n = int(last.split("-")[1])
        except Exception:
            n = 0
    return f"T-{n+1:03d}"

def next_customer_card_number(phone: str) -> int:
    """
    Número de tarjeta por cliente (1,2,3…) basado en cuántas tarjetas tiene ese teléfono.
    """
    phone = normalize_phone(phone)
    r = supabase.table("TARJETAS").select("NUMERO_TARJETA", count="exact").eq("TELEFONO", phone).execute()
    cnt = r.count or 0
    return cnt + 1

def ensure_open_card(phone: str) -> Dict[str, Any]:
    """
    Devuelve tarjeta abierta del cliente; si no existe, crea una.
    Estructura devuelta: {id_tarjeta, numero_tarjeta, estado, fecha_inicio, fecha_ultimo_sello}
    """
    phone = normalize_phone(phone)

    # 1) busca abierta
    r = supabase.table("TARJETAS").select("*").eq("TELEFONO", phone).eq("ESTADO", "abierta").maybe_single().execute()
    if isinstance(r.data, dict) and r.data:
        return r.data

    # 2) crea nueva
    new_id = next_global_card_id()
    num_cliente = next_customer_card_number(phone)
    payload = {
        "ID_TARJETA": new_id,
        "TELEFONO": phone,
        "FECHA_INICIO": date.today().isoformat(),
        "FECHA_FIN": None,
        "ESTADO": "abierta",
        "NUMERO_TARJETA": num_cliente,
        "fecha_ultimo_sello": None,
    }
    supabase.table("TARJETAS").insert(payload).execute()
    return payload

def count_stamps(id_tarjeta: str) -> int:
    """Cuenta sellos desde COMPRAS."""
    r = supabase.table("COMPRAS").select("ID_TARJETA", count="exact").eq("ID_TARJETA", id_tarjeta).execute()
    return r.count or 0

def today_has_stamp(card: Dict[str, Any]) -> bool:
    """Candado: ¿ya se selló hoy? Revisa `fecha_ultimo_sello` o existencia en COMPRAS del día."""
    today = date.today().isoformat()
    # 1) campo fecha_ultimo_sello si existe
    fus = card.get("fecha_ultimo_sello")
    if isinstance(fus, str) and fus[:10] == today:
        return True
    # 2) fallback: compra hoy
    r = supabase.table("COMPRAS").select("ID_TARJETA", count="exact").eq("ID_TARJETA", card["ID_TARJETA"]).eq("FECHA", today).execute()
    return (r.count or 0) > 0

def stamp_card(card: Dict[str, Any], phone: str) -> None:
    """
    Inserta una compra (sello) y actualiza `fecha_ultimo_sello`. Respeta candado 1 por día.
    Lanza Exception si ya fue sellada hoy.
    """
    if today_has_stamp(card):
        raise Exception("Tarjeta sellada hoy, vuelve mañana por más sellos.")

    payload = {
        "ID_TARJETA": card["ID_TARJETA"],
        "TELEFONO": normalize_phone(phone),
        "FECHA": date.today().isoformat(),
    }
    supabase.table("COMPRAS").insert(payload).execute()
    supabase.table("TARJETAS").update({"fecha_ultimo_sello": date.today().isoformat()}).eq("ID_TARJETA", card["ID_TARJETA"]).execute()

def current_discount(stamps: int) -> Dict[str, Any]:
    """
    Regresa el descuento vigente según # de sellos.
    Regla: toma el (stamps+1)-ésimo renglón activo por orden de ID_DESCUENTO.
    """
    try:
        res = supabase.table("PREMIOS_TARJETA").select("*").eq("ACTIVO", 1).order("ID_DESCUENTO", asc=True).execute()
        premios = res.data or []
        if not premios:
            return {"DESC": "Sin descuento configurado", "TIPO": "PORCENTAJE", "VAL": 0}
        idx = min(stamps, max(0, len(premios) - 1))  # si ya se pasó, se queda en el último
        row = premios[idx]
        desc = str(row.get("DESCRIPCION", "")).strip() or "Descuento"
        typ = str(row.get("TIPO", "PORCENTAJE")).upper()
        val = float(row.get("VAL", 0) or 0)
        return {"DESC": desc, "TIPO": typ, "VAL": val}
    except Exception:
        return {"DESC": "Sin descuento configurado", "TIPO": "PORCENTAJE", "VAL": 0}


# ─────────────────────────────────────────────────────────────────────────────
# UI · Streamlit
# ─────────────────────────────────────────────────────────────────────────────

st.set_page_config(page_title="10ynueve — Sistema de Sellos", page_icon="⭐", layout="wide")

st.markdown(
    """
    <style>
      .big-title { font-size: 44px; font-weight: 800; letter-spacing: .5px; }
      .pill { padding:.8rem 1rem; border-radius:.8rem; font-weight:600; }
      .pill.ok { background: #1B9E77; color:white; }
      .pill.info { background:#2B6CB0; color:white; }
      .pill.warn { background:#B7791F; color:white; }
      .pill.err { background:#C53030; color:white; }
      .pill.neut { background:#2F855A22; color:#e2e8f0; }
      .btn-primary button { background:#f97316!important; color:white!important; font-weight:700!important; }
      .mt { margin-top: .75rem; }
      .mb { margin-bottom: .75rem; }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown('<div class="big-title">10ynueve — Sistema de Sellos</div>', unsafe_allow_html=True)
st.caption("Listo para sellar cuando quieras. ✨🐾")

mode = st.radio("Selecciona una opción:", ["Cliente Perrón", "Nuevo Cliente"], horizontal=True)

phone_input = st.text_input("Ingresa el número de teléfono del cliente:", placeholder="55XXXXXXXX")
col_buscar, _ = st.columns([1, 4])

# ─────────────────────────────────────────────────────────────────────────────
# MODO CLIENTE PERRÓN (consulta + sello)
# ─────────────────────────────────────────────────────────────────────────────
if mode == "Cliente Perrón":
    if col_buscar.button("Buscar", use_container_width=False):
        phone = normalize_phone(phone_input)
        if not phone:
            st.error("Ingresa un teléfono válido.")
        else:
            try:
                cust = get_customer_by_phone(phone)
                if not cust:
                    st.error("Cliente no encontrado en Customers.")
                else:
                    st.success(f"Cliente encontrado: **{cust['name']}** · {cust['phone']}")
                    # tarjeta abierta
                    try:
                        card = ensure_open_card(phone)
                    except Exception as e:
                        st.error(f"No se pudo asegurar tarjeta abierta: {e}")
                        st.stop()

                    # info tarjeta
                    info = f"**Tarjeta activa:** **{card['ID_TARJETA']}** · **Estado:** {card.get('ESTADO','')} · **Número:** {card.get('NUMERO_TARJETA','')} · **Inicio:** {card.get('FECHA_INICIO','')}"
                    st.markdown(f'<div class="pill info mb">{info}</div>', unsafe_allow_html=True)

                    # sellos + descuento
                    s_count = count_stamps(card["ID_TARJETA"])
                    st.markdown(f'<div class="pill neut mb">Sellos acumulados: <b>{s_count}</b></div>', unsafe_allow_html=True)

                    d = current_discount(s_count)
                    if d["TIPO"] == "PORCENTAJE":
                        d_text = f"{d['DESC']} ({int(d['VAL'])}%)"
                    else:
                        d_text = d["DESC"]
                    st.markdown(f'<div class="pill warn mb">Descuento actual: <b>{d_text}</b></div>', unsafe_allow_html=True)

                    # botón sellar
                    lock_msg = None
                    if today_has_stamp(card):
                        lock_msg = "Tarjeta sellada hoy, vuelve mañana por más sellos."
                        st.warning(lock_msg)
                    else:
                        sell = st.button("Sellar ahora ✅", type="primary")
                        if sell:
                            try:
                                stamp_card(card, phone)
                                st.balloons()
                                st.success("**Tarjeta Sellada por Greg!! 🐾**")
                                # refresca contadores
                                s_count = count_stamps(card["ID_TARJETA"])
                                st.markdown(f'<div class="pill neut mt">Sellos acumulados: <b>{s_count}</b></div>', unsafe_allow_html=True)
                                d = current_discount(s_count)
                                if d["TIPO"] == "PORCENTAJE":
                                    d_text = f"{d['DESC']} ({int(d['VAL'])}%)"
                                else:
                                    d_text = d["DESC"]
                                st.markdown(f'<div class="pill warn">Descuento actual: <b>{d_text}</b></div>', unsafe_allow_html=True)
                            except Exception as e:
                                # Si fue candado, mensaje claro:
                                msg = str(e)
                                if "vuelve mañana" in msg.lower():
                                    st.warning("Tarjeta sellada hoy, vuelve mañana por más sellos.")
                                else:
                                    st.error(f"No se pudo sellar: {e}")
            except Exception as e:
                st.error(f"Falló al consultar cliente: {e}")

# ─────────────────────────────────────────────────────────────────────────────
# MODO NUEVO CLIENTE (registro + abre tarjeta)
# ─────────────────────────────────────────────────────────────────────────────
else:
    st.subheader("Dar de alta nuevo cliente")
    name = st.text_input("Nombre", value="")
    tel = st.text_input("Teléfono", value=phone_input or "")

    if st.button("Registrar cliente y abrir tarjeta", key="btn_reg", type="primary"):
        n = (name or "").strip()
        p = normalize_phone(tel or phone_input)
        if not n or not p:
            st.error("Nombre y teléfono son obligatorios.")
        else:
            try:
                if customer_exists(p):
                    st.warning("Ese número **ya tiene registro**. Busca en *Cliente Perrón* para sellar.")
                else:
                    create_customer(n, p)
                    card = ensure_open_card(p)
                    st.success(f"Cliente **{n}** registrado con tarjeta **{card['ID_TARJETA']}**.")
                    st.caption("Listo para sellar cuando quieras. ✨🐾")
            except Exception as e:
                st.error(f"Falló el registro: {e}")
