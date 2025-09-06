# consultar.py
from pathlib import Path
import sqlite3
from datetime import date
import streamlit as st
import os

# 1) Ruta de la base de datos
DB_PATH = Path(r"C:\Users\eddyr\AppData\Roaming\Microsoft\Windows\Network Shortcuts\10ynueve_loyalty.db")

# 2) Función para abrir conexión
def abrir_conexion():
    if not DB_PATH.exists():
        raise FileNotFoundError(f"No encontré la base en: {DB_PATH}")
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

# 3) Debug: mostrar tablas disponibles
def mostrar_tablas():
    conn = abrir_conexion()
    tablas = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    conn.close()
    return [t["name"] for t in tablas]

# 4) Obtener tarjeta activa de un cliente
def obtener_tarjeta_abierta(conn, telefono: str):
    cur = conn.cursor()
    cur.execute("""
        SELECT ID_TARJETA, COALESCE(NUMERO_TARJETA, 1) AS NUMERO_TARJETA
        FROM TARJETAS
        WHERE TELEFONO=? AND ESTADO='abierta'
        ORDER BY NUMERO_TARJETA DESC
        LIMIT 1
    """, (telefono,))
    row = cur.fetchone()
    return (row["ID_TARJETA"], row["NUMERO_TARJETA"]) if row else (None, None)

# 5) Dar de alta un nuevo cliente y tarjeta
def alta_cliente(nombre: str, telefono: str):
    conn = abrir_conexion()
    cur = conn.cursor()
    # Guardar cliente
    cur.execute("INSERT INTO Customers(Name, Phone) VALUES (?, ?)", (nombre, telefono))
    # Crear tarjeta inicial
    cur.execute("""
        INSERT INTO TARJETAS (ID_TARJETA, TELEFONO, FECHA_INICIO, ESTADO, NUMERO_TARJETA)
        VALUES (?, ?, ?, ?, ?)
    """, (f"T-{telefono}", telefono, date.today().isoformat(), "abierta", 1))
    conn.commit()
    conn.close()

# ==========================
# 6) Interfaz Streamlit
# ==========================
st.set_page_config(page_title="Sistema de Sellos 10ynueve", page_icon="🐶", layout="centered")

st.image("https://i.imgur.com/kbJx2Ww.png", width=150)  # 👈 Aquí puedes cambiar por la imagen de Greg si quieres
st.title("🎟 Tarjeta de Lealtad 10ynueve")

opcion = st.radio("Selecciona una opción:", ["🐾 Cliente Perrón", "✨ Nuevo Cliente"])

if opcion == "🐾 Cliente Perrón":
    telefono = st.text_input("📱 Ingresa el número de celular:")
    if st.button("Buscar"):
        try:
            conn = abrir_conexion()
            id_tarjeta, num_tarjeta = obtener_tarjeta_abierta(conn, telefono)
            conn.close()
            if id_tarjeta:
                st.success(f"Cliente encontrado ✅ Tarjeta: {id_tarjeta} | Sellos: {num_tarjeta}")
            else:
                st.warning("No encontré tarjeta activa para este cliente.")
        except Exception as e:
            st.error(f"Error: {e}")

elif opcion == "✨ Nuevo Cliente":
    nombre = st.text_input("📝 Nombre del cliente")
    telefono = st.text_input("📱 Número de celular")
    if st.button("Dar de alta"):
        try:
            alta_cliente(nombre, telefono)
            st.success(f"Cliente {nombre} agregado con éxito y tarjeta activada 🎉")
        except Exception as e:
            st.error(f"Error: {e}")

# Debug opcional: mostrar tablas disponibles en la BD
with st.expander("🔍 Ver tablas en la base de datos"):
    try:
        tablas = mostrar_tablas()
        st.write(tablas)
    except Exception as e:
        st.error(f"No pude leer la base: {e}")