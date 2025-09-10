# appy.py — 10ynueve (versión “a prueba de pantallas negras”)

from datetime import date
import streamlit as st

# Pintamos la cabecera antes de tocar secretos/BD
st.set_page_config(page_title="10ynueve - Sistema de Sellos", page_icon="🟣", layout="centered")
st.title("10ynueve — Sistema de Sellos")

# ---- Conexión perezosa (lazy), con errores visibles en UI ----
@st.cache_resource(show_spinner=False)
def get_supabase():
    """Crea el cliente de Supabase usando secrets.
    Si falta algo, no crashea la app: devuelve (None, msg_de_error)."""
    try:
        from supabase import create_client, Client
    except Exception as e:
        return None, f"No se pudo importar 'supabase'. ¿Está en requirements.txt? Detalle: {e}"

    def _clean_ascii(s: str) -> str:
        s = (s or "").strip()
        return "".join(ch for ch in s if 32 <= ord(ch) < 127)

    try:
        url = _clean_ascii(st.secrets["SUPABASE_URL"])
        key = _clean_ascii(st.secrets["SUPABASE_ANON_KEY"])
    except Exception as e:
        return None, f"Faltan secrets SUPABASE_URL / SUPABASE_ANON_KEY. Detalle: {e}"

    try:
        client = create_client(url, key)
        return client, None
    except Exception as e:
        return None, f"No se pudo crear el cliente de Supabase. Detalle: {e}"

supabase, conn_err = get_supabase()
if conn_err:
    st.error("No me pude conectar a Supabase.")
    with st.expander("Ver detalle"):
        st.write(conn_err)
    st.stop()

# ---- Helpers BD (con manejo de errores) ----
def get_customer_by_phone(phone: str):
    phone = (phone or "").strip()

    # 1) Vista minúsculas
    try:
        res = supabase.table("customers_api").select("*").eq("phone", phone).maybe_single().execute()
        if isinstance(res.data, dict) and res.data:
            return {"Name": res.data.get("name") or res.data.get("Name"),
                    "Phone": res.data.get("phone") or res.data.get("Phone")}
    except Exception:
        pass

    # 2) Tabla con mayúsculas
    try:
        res = supabase.table("Customers").select("*").eq("Phone", phone).maybe_single().execute()
        if isinstance(res.data, dict) and res.data:
            return {"Name": res.data.get("Name"), "Phone": res.data.get("Phone")}
    except Exception:
        pass

    return None

def create_customer(name: str, phone: str):
    payload = {"Name": (name or "").strip(), "Phone": (phone or "").strip()}
    return supabase.table("Customers").insert(payload).execute()

def _next_tarjeta_id() -> str:
    try:
        cnt = supabase.table("TARJETAS").select("ID_TARJETA", count="exact").execute().count or 0
    except Exception:
        cnt = 0
    return f"T-{cnt+1:03d}"

def ensure_open_card(phone: str):
    phone = (phone or "").strip()
    try:
        res = (supabase.table("TARJETAS").select("*")
               .eq("TELEFONO", phone).eq("ESTADO", "abierta")
               .limit(1).execute())
        if res.data:
            return res.data[0]
    except Exception:
        pass

    nueva = {
        "ID_TARJETA": _next_tarjeta_id(),
        "TELEFONO": phone,
        "FECHA_INICIO": date.today().isoformat(),
        "FECHA_FIN": None,
        "ESTADO": "abierta",
        "NUMERO_TARJETA": 1
    }
    supabase.table("TARJETAS").insert(nueva).execute()
    return nueva

# ---- UI ----
modo = st.radio("Selecciona una opción:", ["Cliente Perrón", "Nuevo Cliente"], horizontal=True)

if modo == "Cliente Perrón":
    phone = st.text_input("Ingresa el número de teléfono del cliente:", max_chars=15)
    if st.button("Buscar", type="primary"):
        if not phone.strip():
            st.warning("Pon un teléfono, porfa.")
        else:
            try:
                cust = get_customer_by_phone(phone)
                if not cust:
                    st.error("Cliente no encontrado en *Customers*.")
                    with st.expander("Sugerencia si usas la vista"):
                        st.markdown(
                            "Crea/actualiza la vista:\n\n"
                            "sql\n"
                            "CREATE OR REPLACE VIEW customers_api AS\n"
                            "SELECT \"Name\" AS name, \"Phone\" AS phone FROM \"Customers\";\n"
                            "\n"
                        )
                else:
                    card = ensure_open_card(cust["Phone"])
                    st.success(
                        f"Cliente: *{cust['Name']}*  \n"
                        f"Tel: *{cust['Phone']}*  \n"
                        f"Tarjeta abierta: *{card['ID_TARJETA']}* (inicio {card['FECHA_INICIO']})"
                    )
            except Exception as e:
                st.error("Fallo al consultar/abrir tarjeta.")
                with st.expander("Ver error"):
                    st.exception(e)

else:
    name = st.text_input("Nombre")
    phone = st.text_input("Teléfono", max_chars=15)
    if st.button("Registrar cliente y abrir tarjeta", type="primary"):
        if not name.strip() or not phone.strip():
            st.warning("Nombre y teléfono obligatorios.")
        else:
            try:
                if not get_customer_by_phone(phone):
                    create_customer(name, phone)
                card = ensure_open_card(phone)
                st.success(f"Cliente *{name}* listo y tarjeta *{card['ID_TARJETA']}* abierta ✅")
            except Exception as e:
                st.error("Error al registrar cliente / abrir tarjeta.")
                with st.expander("Ver error"):
                    st.exception(e)

st.caption("Listo para empezar a acumular sellos ✨")
