from datetime import date
import streamlit as st
import psycopg2
import psycopg2.extras

# ====== Configuración de conexión a Supabase ======
DB_CONFIG = {
    "host": "db.fncsqlfigpidyuxiyskq.supabase.co",  # cambia según tu proyecto
    "dbname": "postgres",
    "user": "postgres",
    "password": "Eda090592",  # 🔑 cambia esto por tu password real
    "port": "5432"
}

def abrir_conexion():
    conn = psycopg2.connect(**DB_CONFIG)
    return conn

# ====== Utilerías de BD ======
def obtener_cliente(conn, telefono: str):
    with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        cur.execute("SELECT name, phone FROM customers WHERE phone = %s", (telefono.strip(),))
        row = cur.fetchone()
        if row:
            return row["name"], row["phone"]
    return None, telefono

def obtener_tarjeta_abierta(conn, telefono: str):
    with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        cur.execute(
            """
            SELECT id_tarjeta, numero_tarjeta,
                   fecha_ultimo_sello,
                   COALESCE(sellos, 0) AS sellos
            FROM tarjetas
            WHERE telefono = %s AND estado = 'abierta'
            ORDER BY numero_tarjeta DESC
            LIMIT 1
            """,
            (telefono.strip(),),
        )
        return cur.fetchone()

def siguiente_id_tarjeta(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT MAX(CAST(SUBSTRING(id_tarjeta, 3) AS INTEGER)) FROM tarjetas")
        maxnum = cur.fetchone()[0] or 0
    return f"T-{maxnum+1:03d}"

def asegurar_tarjeta_abierta(conn, telefono: str):
    row = obtener_tarjeta_abierta(conn, telefono)
    if row:
        return row

    id_nueva = siguiente_id_tarjeta(conn)
    with conn.cursor() as cur:
        cur.execute("SELECT COALESCE(MAX(numero_tarjeta),0) FROM tarjetas WHERE telefono = %s", (telefono.strip(),))
        maxnum = cur.fetchone()[0] or 0
        siguiente_num = maxnum + 1

        # FECHA_ULTIMO_SELLO = hoy, para que no se pueda usar en el mismo día
        cur.execute(
            """
            INSERT INTO tarjetas (
                id_tarjeta, telefono, fecha_inicio, fecha_fin,
                estado, numero_tarjeta, fecha_ultimo_sello, sellos
            )
            VALUES (%s, %s, CURRENT_DATE, NULL,
                    'abierta', %s, CURRENT_DATE, 0)
            """,
            (id_nueva, telefono.strip(), siguiente_num),
        )
    conn.commit()
    return obtener_tarjeta_abierta(conn, telefono)

def avanzar_sello(conn, id_tarjeta: str):
    hoy = date.today().isoformat()
    with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        cur.execute(
            "SELECT fecha_ultimo_sello, COALESCE(sellos, 0) AS sellos FROM tarjetas WHERE id_tarjeta = %s",
            (id_tarjeta,),
        )
        row = cur.fetchone()
        if not row:
            return 0, False

        if row["fecha_ultimo_sello"] == hoy:
            return row["sellos"], False  # ya se registró hoy

        nuevo = row["sellos"] + 1
        cur.execute(
            "UPDATE tarjetas SET sellos = %s, fecha_ultimo_sello = %s WHERE id_tarjeta = %s",
            (nuevo, hoy, id_tarjeta),
        )
    conn.commit()
    return nuevo, True

def consultar_descuento_por_sellos(conn, sellos: int):
    with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        cur.execute("SELECT COUNT(*) FROM descuentos WHERE activo=1")
        total = cur.fetchone()[0]
        if total == 0:
            return None
        offset = max(0, min(sellos - 1, total - 1))
        cur.execute(
            """
            SELECT descripcion, tipo, valor
            FROM descuentos
            WHERE activo=1
            ORDER BY id_descuento
            LIMIT 1 OFFSET %s
            """,
            (offset,),
        )
        row = cur.fetchone()
        if not row:
            return None
        return {
            "descripcion": row["descripcion"],
            "tipo": row["tipo"],
            "valor": float(row["valor"]),
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
                    id_tarjeta = tarjeta["id_tarjeta"]
                    num_tarjeta = tarjeta["numero_tarjeta"]

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
                with conn.cursor() as cur:
                    cur.execute("SELECT 1 FROM customers WHERE phone = %s", (telefono.strip(),))
                    if not cur.fetchone():
                        cur.execute("INSERT INTO customers (name, phone) VALUES (%s, %s)", (nombre.strip(), telefono.strip()))
                        conn.commit()
                tarjeta = asegurar_tarjeta_abierta(conn, telefono)
                st.success(f"Cliente {nombre} registrado con tarjeta {tarjeta['id_tarjeta']}")
            except Exception as e:
                st.error(f"Error: {e}")
            finally:
                if conn:
                    conn.close()

st.caption("Listo para empezar a acumular sellos 🧼🥤")


