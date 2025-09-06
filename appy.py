# appy.py
from pathlib import Path
from datetime import date
import sqlite3
import streamlit as st

# ====== Config ======
DB_PATH = Path.cwd() / "10ynueve_loyalty.db"

# ====== Utilerías de BD ======
def abrir_conexion() -> sqlite3.Connection:
    if not DB_PATH.exists():
        raise FileNotFoundError(f"No encontré la base en: {DB_PATH}")
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def obtener_cliente(conn: sqlite3.Connection, telefono: str):
    cur = conn.cursor()
    cur.execute("SELECT Name, Phone FROM Customers WHERE Phone=?", (telefono.strip(),))
    row = cur.fetchone()
    if row:
        return row["Name"], row["Phone"]
    return None, telefono

def obtener_tarjeta_abierta(conn: sqlite3.Connection, telefono: str):
    cur = conn.cursor()
    cur.execute(
        """
        SELECT ID_TARJETA, NUMERO_TARJETA,
               COALESCE(FECHA_ULTIMO_SELLO, NULL) AS FECHA_ULTIMO_SELLO,
               COALESCE(SELLOS, 0)               AS SELLOS
        FROM TARJETAS
        WHERE TELEFONO=? AND ESTADO='abierta'
        ORDER BY NUMERO_TARJETA DESC
        LIMIT 1
        """,
        (telefono.strip(),),
    )
    return cur.fetchone()

def siguiente_id_tarjeta(conn: sqlite3.Connection) -> str:
    cur = conn.cursor()
    cur.execute("SELECT MAX(CAST(substr(ID_TARJETA,3) AS INTEGER)) AS maxnum FROM TARJETAS")
    row = cur.fetchone()
    maxnum = row["maxnum"] if row and row["maxnum"] is not None else 0
    return f"T-{maxnum+1:03d}"

def asegurar_tarjeta_abierta(conn: sqlite3.Connection, telefono: str):
    """
    Devuelve la tarjeta abierta si ya existe.
    Si no existe, crea una nueva *marcando FECHA_ULTIMO_SELLO = hoy* para
    que NO pueda usarse (sumar sello) el mismo día del alta.
    """
    row = obtener_tarjeta_abierta(conn, telefono)
    if row:
        return row

    id_nueva = siguiente_id_tarjeta(conn)
    cur = conn.cursor()

    # Siguiente número de tarjeta para ese teléfono
    cur.execute("SELECT COALESCE(MAX(NUMERO_TARJETA),0) AS maxnum FROM TARJETAS WHERE TELEFONO=?", (telefono.strip(),))
    maxnum = cur.fetchone()["maxnum"] or 0
    siguiente_num = maxnum + 1

    # IMPORTANTE: FECHA_ULTIMO_SELLO = DATE('now') y SELLOS = 0
    cur.execute(
        """
        INSERT INTO TARJETAS (
            ID_TARJETA, TELEFONO, FECHA_INICIO, FECHA_FIN,
            ESTADO, NUMERO_TARJETA, FECHA_ULTIMO_SELLO, SELLOS
        )
        VALUES (
            ?, ?, DATE('now'), NULL,
            'abierta', ?, DATE('now'), 0
        )
        """,
        (id_nueva, telefono.strip(), siguiente_num),
    )
    conn.commit()

    # Regresamos la fila recién creada con las columnas útiles
    return obtener_tarjeta_abierta(conn, telefono)


def avanzar_sello(conn: sqlite3.Connection, id_tarjeta: str):
    """
    Suma un sello si no se ha puesto ya hoy.
    Robusto ante valores NULL en SELLOS/FECHA_ULTIMO_SELLO.
    """
    hoy = date.today().isoformat()
    cur = conn.cursor()
    cur.execute(
        "SELECT COALESCE(FECHA_ULTIMO_SELLO, NULL) AS FECHA_ULTIMO_SELLO, COALESCE(SELLOS, 0) AS SELLOS FROM TARJETAS WHERE ID_TARJETA=?",
        (id_tarjeta,),
    )
    row = cur.fetchone()
    if not row:
        return 0, False

    fecha_ultimo = row["FECHA_ULTIMO_SELLO"]
    sellos_actuales = row["SELLOS"] if row["SELLOS"] is not None else 0

    if fecha_ultimo == hoy:
        return sellos_actuales, False  # ya registró hoy

    nuevo = sellos_actuales + 1
    cur.execute(
        "UPDATE TARJETAS SET SELLOS=?, FECHA_ULTIMO_SELLO=? WHERE ID_TARJETA=?",
        (nuevo, hoy, id_tarjeta),
    )
    conn.commit()
    return nuevo, True

def consultar_descuento_por_sellos(conn: sqlite3.Connection, sellos: int):
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) AS c FROM DESCUENTOS WHERE ACTIVO=1")
    total = cur.fetchone()["c"]
    if total == 0:
        return None
    offset = max(0, min(sellos - 1, total - 1))
    cur.execute(
        """
        SELECT DESCRIPCION, TIPO, VALOR
        FROM DESCUENTOS
        WHERE ACTIVO=1
        ORDER BY ID_DESCUENTO
        LIMIT 1 OFFSET ?
        """,
        (offset,),
    )
    row = cur.fetchone()
    if not row:
        return None
    return {
        "descripcion": row["DESCRIPCION"],
        "tipo": row["TIPO"],
        "valor": float(row["VALOR"]),
        "posicion": offset + 1,
        "total_activos": total,
    }

# ====== UI ======
st.set_page_config(page_title="Sistema de Sellos 10ynueve", page_icon="🐾", layout="centered")
st.markdown("<h1>🐾 Bienvenido al sistema de sellos 10ynueve</h1>", unsafe_allow_html=True)

modo = st.radio("Selecciona una opción:", ["Cliente Perrón", "Nuevo Cliente"])

st.divider()

if modo == "Cliente Perrón":
    telefono = st.text_input("Ingresa el número de teléfono del cliente:")
    if st.button("Buscar", type="primary"):
        if not telefono.strip():
            st.error("Escribe un teléfono.")
        else:
            conn = None
            try:
                conn = abrir_conexion()
                nombre, _ = obtener_cliente(conn, telefono)
                if not nombre:
                    st.warning("Cliente no encontrado en *Customers*.")
                else:
                    st.success(f"Cliente encontrado: **{nombre}**")

                tarjeta = asegurar_tarjeta_abierta(conn, telefono)
                if tarjeta:
                    id_tarjeta = tarjeta["ID_TARJETA"]
                    num_tarjeta = tarjeta["NUMERO_TARJETA"]

                    # avanzar sello
                    sellos, avanzo = avanzar_sello(conn, id_tarjeta)
                    if avanzo:
                        st.success(f"Sello agregado. Total: {sellos}")
                    else:
                        st.warning("Este cliente ya registró visita hoy.")

                    # mostrar descuento
                    info = consultar_descuento_por_sellos(conn, sellos)
                    if info:
                        if info["tipo"].lower().startswith("porcent"):
                            st.info(f"Descuento actual: **{info['valor']}%** — {info['descripcion']}")
                        else:
                            st.info(f"Descuento actual: **${info['valor']:,.2f}** — {info['descripcion']}")
            except Exception as e:
                st.error(f"Error: {e}")
            finally:
                if conn:
                    conn.close()

else:
    st.subheader("Dar de alta nuevo cliente")
    nombre = st.text_input("Nombre")
    telefono = st.text_input("Teléfono")
    if st.button("Registrar cliente y abrir tarjeta", type="primary"):
        if not nombre.strip() or not telefono.strip():
            st.error("Nombre y teléfono obligatorios.")
        else:
            conn = None
            try:
                conn = abrir_conexion()
                cur = conn.cursor()
                cur.execute("SELECT 1 FROM Customers WHERE Phone=?", (telefono.strip(),))
                if not cur.fetchone():
                    cur.execute("INSERT INTO Customers (Name, Phone) VALUES (?,?)", (nombre.strip(), telefono.strip()))
                    conn.commit()
                tarjeta = asegurar_tarjeta_abierta(conn, telefono)
                st.success(f"Cliente {nombre} registrado con tarjeta {tarjeta['ID_TARJETA']}")
            except Exception as e:
                st.error(f"Error: {e}")
            finally:
                if conn:
                    conn.close()

st.caption("Listo para empezar a acumular sellos 🧼🥤")
