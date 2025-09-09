from datetime import date
import streamlit as st
import psycopg2
import psycopg2.extras

# ====== Configuración de conexión a Supabase ======
import streamlit as st
from supabase import create_client

# 🔑 Usa tus credenciales de Supabase
url = "https://TU_PROJECT_URL.supabase.co"
key = "TU_API_KEY"  # Usa la service_role si necesitas escribir
supabase = create_client(url, key)

st.title("10ynueve - Sistema de Sellos")

telefono = st.text_input("Ingresa el número de teléfono del cliente:")

if st.button("Buscar"):
    data = supabase.table("Customers").select("*").eq("Phone", telefono).execute()
    if data.data:
        st.success(f"Cliente encontrado: {data.data[0]['Name']}")
    else:
        st.error("Cliente no encontrado")
