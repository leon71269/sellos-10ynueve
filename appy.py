import sqlite3
from datetime import datetime, date
import streamlit as st

DB_PATH = "clientes.db"
GOAL_STAMPS = 10  # sellos por tarjeta

# ---------- DB ----------
def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def init_db():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS customers(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        phone TEXT NOT NULL UNIQUE,
        created_at DATE NOT NULL
    )""")
    cur.execute("""
    CREATE TABLE IF NOT EXISTS stamps(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        customer_id INTEGER NOT NULL,
        stamp_date DATE NOT NULL,
        FOREIGN KEY(customer_id) REFERENCES customers(id)
    )""")
    conn.commit()
    conn.close()

def find_customer_by_phone(phone):
    if not phone:
        return None
    conn = get_conn()
    cur = conn.cursor()
    row = cur.execute("SELECT id, name, phone, created_at FROM customers WHERE phone = ?", (phone.strip(),)).fetchone()
    conn.close()
    if row is None:
        return None
    return {"id": row[0], "name": row[1], "phone": row[2], "created_at": row[3]}

def create_customer(name, phone):
    if not name or not phone:
        return False, "Nombre y teléfono son obligatorios."
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("INSERT INTO customers(name, phone, created_at) VALUES (?, ?, ?)",
                    (name.strip(), phone.strip(), date.today().isoformat()))
        conn.commit()
        conn.close()
        return True, None
    except sqlite3.IntegrityError:
        return False, "Ese teléfono ya está registrado."

def count_stamps(customer_id):
    conn = get_conn()
    cur = conn.cursor()
    row = cur.execute("SELECT COUNT(*) FROM stamps WHERE customer_id = ?", (customer_id,)).fetchone()
    conn.close()
    return row[0] if row else 0

def last_stamp_date(customer_id):
    conn = get_conn()
    cur = conn.cursor()
    row = cur.execute("SELECT MAX(stamp_date) FROM stamps WHERE customer_id = ?", (customer_id,)).fetchone()
    conn.close()
    return row[0] if row and row[0] else None

def add_stamp(customer_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("INSERT INTO stamps(customer_id, stamp_date) VALUES (?, ?)", (customer_id, date.today().isoformat()))
    conn.commit()
    conn.close()

def reset_stamps_if_completed(customer_id):
    # Opción: cuando llegue a GOAL_STAMPS, "reiniciar" para nueva tarjeta
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM stamps WHERE customer_id = ? AND id IN (SELECT id FROM stamps WHERE customer_id = ? ORDER BY stamp_date LIMIT ?)",
                (customer_id, customer_id, GOAL_STAMPS))
    conn.commit()
    conn.close()

# ---------- UI ----------
st.set_page_config(page_title="Tarjeta Perrona 10ynueve", page_icon="🐾", layout="centered")
init_db()

st.title("Tarjeta Perrona 🐾✨")

tabs = st.tabs(["🔹 Nuevo Cliente", "🔸 Sellar Tarjeta"])

# ---- Nuevo Cliente ----
with tabs[0]:
    st.subheader("Dar de alta nuevo cliente")
    n_name = st.text_input("Nombre", value="")
    n_phone = st.text_input("Teléfono", value="", help="10 dígitos sin espacios")

    if st.button("Registrar cliente y abrir tarjeta", type="primary"):
        ok, err = create_customer(n_name, n_phone)
        if ok:
            st.success("✅ ¡Cliente registrado! No puede sellar hoy (bloqueo por día de alta).")
        else:
            st.error(f"Falló el registro. {err or ''}")

# ---- Sellar Tarjeta ----
with tabs[1]:
    st.subheader("Sellar tarjeta")
    s_phone = st.text_input("Ingresa el teléfono del cliente", value="")

    # Buscar cliente seguro (sin romper si no existe)
    customer = find_customer_by_phone(s_phone)
    if customer is None and s_phone.strip():
        st.error("No encontré ese teléfono. Verifica o da de alta el cliente en la pestaña anterior.")
    elif customer:
        st.info(f"Cliente: **{customer['name']}** | Tel: {customer['phone']}")
        total = count_stamps(customer["id"])
        last_date = last_stamp_date(customer["id"])
        created = datetime.fromisoformat(customer["created_at"]).date()
        today = date.today()

        # Reglas de bloqueo
        bloqueo_por_alta = (created == today)
        bloqueo_por_sello_hoy = (last_date is not None and datetime.fromisoformat(last_date).date() == today)

        # Progreso
        restante = max(GOAL_STAMPS - (total % GOAL_STAMPS), 0)
        progreso = total % GOAL_STAMPS
        st.progress(progreso / GOAL_STAMPS if GOAL_STAMPS else 0.0, text=f"Sellos actuales en esta tarjeta: {progreso}/{GOAL_STAMPS}")

        if bloqueo_por_alta:
            st.warning("⛔ No puedes sellar el **mismo día del registro**. Inténtalo a partir de mañana.")
        elif bloqueo_por_sello_hoy:
            st.warning("⛔ Ya se selló **hoy**. Solo 1 sello por día.")
        else:
            if st.button("Sellar ahora ✅"):
                add_stamp(customer["id"])
                total = count_stamps(customer["id"])
                progreso = total % GOAL_STAMPS
                st.success("✅ ¡Sello agregado!")

                if progreso == 0:  # acaba de completar una vuelta de 10
                    st.balloons()
                    st.success(f"🎉 ¡Completó {GOAL_STAMPS} sellos! Entrega beneficio y reinicia tarjeta.")
                    # Si prefieres *no* borrar sellos históricos, comenta la siguiente línea:
                    reset_stamps_if_completed(customer["id"])

        st.caption(f"Último sello: {last_date or 'N/A'} | Registrado: {customer['created_at']}")

# --------- Manejo fino de None (por si cambias algo) ----------
# Nota: en todos los accesos a la BD usamos .fetchone() y comprobamos si es None antes de desestructurar.
# Esto evita el AttributeError: 'NoneType' object has no attribute ...
