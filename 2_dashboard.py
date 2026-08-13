# -*- coding: utf-8 -*-
"""
Created on Tue Aug 11 11:23:22 2026

@author: josec
"""

import streamlit as st
import pandas as pd
import plotly.express as px

# Configuración de página
st.set_page_config(page_title="Dashboard Despacho PCP", layout="wide")
st.title("⚡ Dashboard de Generación PCP (Programa vs. Pronóstico)")

# 1. Cargar datos (Cacheado para que sea instantáneo)
@st.cache_data
def load_data():
    try:
        df = pd.read_parquet("datos_consolidados.parquet")
        # Crear columna de fecha/hora continua
        df['Fecha_Hora'] = df['Fecha'] + pd.to_timedelta(df['Hora'] - 1, unit='h')
        
        # NUEVO: Crear columna de Mes_Año para el filtro mensual
        df['Mes_Año'] = df['Fecha'].dt.strftime('%Y-%m')
        return df
    except Exception as e:
        st.error("No se encontró 'datos_consolidados.parquet'. Ejecuta el script de extracción (1_crear_parquet.py) primero.")
        return pd.DataFrame()

df = load_data()

if not df.empty:
    # --- BARRA LATERAL: FILTROS ---
    st.sidebar.header("Filtros de Búsqueda")
    
    # 1. Filtro Mensual (NUEVO)
    meses_disp = sorted(df['Mes_Año'].unique())
    meses_seleccionados = st.sidebar.multiselect("Filtrar por Mes", options=meses_disp, default=[])
    
    # Adaptar las fechas disponibles para el slider según el mes seleccionado
    if meses_seleccionados:
        df_fechas = df[df['Mes_Año'].isin(meses_seleccionados)]
    else:
        df_fechas = df
        
    fechas = sorted(df_fechas['Fecha'].dt.date.unique())
    
    if len(fechas) > 1:
        fecha_inicio, fecha_fin = st.sidebar.select_slider(
            "Rango de Fechas Diarias", 
            options=fechas, 
            value=(fechas[0], fechas[-1])
        )
    else:
        fecha_inicio = fechas[0]
        fecha_fin = fechas[0]
        st.sidebar.write(f"**Fecha única disponible:** {fecha_inicio}")
    
    # 2. Filtro Tecnología (MODIFICADO)
    tecnologias_permitidas = ["Hidroeléctricas de Pasada", "Eólicas", "Solares", "Embalses", "Reguladas"]
    # Se cruzan con los datos existentes por si alguna tecnología no está en el dataset actual
    tecnologias_disp = [t for t in df['Tecnologia'].unique() if t in tecnologias_permitidas]
    tecnologias = st.sidebar.multiselect("Filtrar por Tecnología", options=tecnologias_disp, default=tecnologias_disp)
    
    # 3. Filtro Centrales
    centrales_disp = df[df['Tecnologia'].isin(tecnologias)]['Central'].unique()
    centrales = st.sidebar.multiselect("Filtrar por Central (Opcional)", options=centrales_disp, default=[])

    # --- APLICAR FILTROS ---
    mask = (df['Fecha'].dt.date >= fecha_inicio) & (df['Fecha'].dt.date <= fecha_fin) & (df['Tecnologia'].isin(tecnologias))
    
    if meses_seleccionados:
        mask = mask & (df['Mes_Año'].isin(meses_seleccionados))
        
    if centrales:
        mask = mask & (df['Central'].isin(centrales))
        
    df_filtrado = df[mask]

    # --- METRICAS PRINCIPALES ---
    col1, col2, col3 = st.columns(3)
    total_prog = df_filtrado['Programa_MWh'].sum()
    total_pron = df_filtrado['Pronostico_MWh'].sum()
    total_vert = (df_filtrado['Pronostico_MWh'] - df_filtrado['Programa_MWh']).clip(lower=0).sum()
    
    # MODIFICADO: Uso de :,.0f para quitar los valores decimales
    col1.metric("Total Programa", f"{total_prog:,.0f} MWh")
    col2.metric("Total Pronóstico ERV", f"{total_pron:,.0f} MWh")
    col3.metric("Vertimiento Programado (Aprox)", f"{total_vert:,.0f} MWh")

    # --- GRÁFICOS ---
    st.markdown("---")
    
    # Agrupar datos por hora Y tecnología para los gráficos 1 y 3
    df_grafico_tec = df_filtrado.groupby(['Fecha_Hora', 'Tecnologia'])[['Programa_MWh', 'Pronostico_MWh']].sum().reset_index()
    
    # MODIFICADO: Cálculo de la diferencia (Resta: ERV - PROGRAMA)
    df_grafico_tec['Diferencia_ERV_Prog'] = df_grafico_tec['Pronostico_MWh'] - df_grafico_tec['Programa_MWh']
    
    # GRAFICO 1: Evolución Horaria (Diferencia ERV vs Programa por Tecnología)
    st.markdown("### 📊 Evolución Horaria: Diferencia (ERV - Programa) por Tecnología")
    fig1 = px.line(
        df_grafico_tec, 
        x='Fecha_Hora', 
        y='Diferencia_ERV_Prog',
        color='Tecnologia',
        labels={'Diferencia_ERV_Prog': 'Diferencia (MWh)', 'Fecha_Hora': 'Día y Hora'}
    )
    fig1.update_traces(line=dict(width=2.5))
    st.plotly_chart(fig1, width='stretch')

    # GRAFICO 2: Vertimiento Programado (Mantener global para ver el total de recorte)
    df_grafico_global = df_filtrado.groupby(['Fecha_Hora'])[['Programa_MWh', 'Pronostico_MWh']].sum().reset_index()
    df_grafico_global['Vertimiento_Programado'] = (df_grafico_global['Pronostico_MWh'] - df_grafico_global['Programa_MWh']).clip(lower=0)

    st.markdown("### 📉 Curva de Vertimiento Programado Total")
    fig_vert = px.line(
        df_grafico_global,
        x='Fecha_Hora',
        y='Vertimiento_Programado',
        labels={'Vertimiento_Programado': 'Vertimiento (MWh)', 'Fecha_Hora': 'Día y Hora'},
        color_discrete_sequence=['#d62728'] 
    )
    fig_vert.update_traces(line=dict(width=2.5))
    st.plotly_chart(fig_vert, width='stretch')

    # GRAFICO 3: Perfil Horario de Generación Programada por Tecnología (NUEVO)
    st.markdown("### 🏢 Generación Programada por Tecnología (Perfil Horario)")
    # Se utiliza un gráfico de área apilada que es el estándar para visualizar el despacho horario
    fig_area = px.area(
        df_grafico_tec, 
        x='Fecha_Hora', 
        y='Programa_MWh', 
        color='Tecnologia',
        labels={'Programa_MWh': 'Generación Programada (MWh)', 'Fecha_Hora': 'Día y Hora'}
    )
    st.plotly_chart(fig_area, width='stretch')

    # --- TABLA Y DESCARGA ---
    st.markdown("---")
    st.markdown("### 📑 Datos Tabulares")
    
    df_descarga = df_filtrado[['Fecha', 'Hora', 'Tecnologia', 'Central', 'Programa_MWh', 'Pronostico_MWh']].copy()
    df_descarga['Vertimiento_MWh'] = (df_descarga['Pronostico_MWh'] - df_descarga['Programa_MWh']).clip(lower=0)
    
    st.dataframe(df_descarga.head(500), width='stretch')
    
    csv = df_descarga.to_csv(index=False).encode('utf-8')
    st.download_button(
        label="📥 Descargar datos filtrados (CSV)",
        data=csv,
        file_name='datos_despacho_filtrados.csv',
        mime='text/csv',
    )
