import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import gspread
from google.oauth2.service_account import Credentials
import json
from datetime import datetime
import pytz
import calendar

# --- CONFIGURATION & PASTEL THEME ---
st.set_page_config(page_title="Yağız's Habit Tracker", page_icon="🌿", layout="centered")
TR_TIMEZONE = pytz.timezone('Europe/Istanbul')

# Yumuşak Pastel Yeşil Renk Skalası
# -1: Boş/Gelecek günler (Yumuşak Koyu Gri)
# 0-1 Arası: Açık fıstık yeşilinden koyu pastel yeşile
PASTEL_COLORS = [
    [0.0, '#383e4a'],    # -1.0 (Boş/Gelecek): Yumuşak Gri
    [0.49, '#383e4a'],   # 0 sınırına kadar Gri
    [0.5, '#e8f5e9'],    # 0.0 (Veri var ama 0 puan): Çok uçuk pastel yeşil
    [0.75, '#81c784'],   # 0.5 (Orta başarı): Tatlı pastel yeşil
    [1.0, '#4caf50']     # 1.0 (Tam başarı): Tok ve yumuşak yeşil
]

@st.cache_resource
def connect_to_gsheets():
    try:
        creds_dict = json.loads(st.secrets["gcp_service_account"])
        scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        client = gspread.authorize(creds)
        db = client.open("HabitTrackerDB")
        return db.worksheet("Logs"), db.worksheet("Settings")
    except Exception as e:
        st.error("Veritabanı bağlantı hatası. 'Logs' ve 'Settings' sayfalarının olduğundan emin ol.")
        st.stop()

log_sheet, settings_sheet = connect_to_gsheets()

# --- HEADER ---
st.title("🌿 Yağız's Habit Tracker")
today_tr = datetime.now(TR_TIMEZONE)
st.info(f"Bugün: {today_tr.strftime('%d %B %Y')}")

# --- DATA LOADING ---
log_records = log_sheet.get_all_records()
df_logs = pd.DataFrame(log_records) if log_records else pd.DataFrame(columns=["Date", "Habit_Name", "Status"])

setting_records = settings_sheet.get_all_records()
df_settings = pd.DataFrame(setting_records) if setting_records else pd.DataFrame(columns=["Habit_Name", "Weight"])

# --- UI: MANAGE HABITS & WEIGHTS ---
with st.expander("⚙️ Alışkanlıkları ve Ağırlıkları Yönet"):
    st.markdown("Her alışkanlık için 1-10 arası önem (ağırlık) derecesi belirle.")
    
    for i, row in df_settings.iterrows():
        cols = st.columns([3, 2, 1])
        cols[0].write(row['Habit_Name'])
        new_w = cols[1].slider(f"Ağırlık: {row['Habit_Name']}", 1, 10, int(row['Weight']), key=f"w_{row['Habit_Name']}")
        if new_w != row['Weight']:
            df_settings.at[i, 'Weight'] = new_w
            if st.button(f"Güncelle", key=f"upd_{row['Habit_Name']}"):
                settings_sheet.clear()
                settings_sheet.update(values=[df_settings.columns.values.tolist()] + df_settings.values.tolist())
                st.rerun()

    st.divider()
    new_h = st.text_input("Yeni Alışkanlık Adı:")
    new_w_val = st.slider("Önem Derecesi (Ağırlık):", 1, 10, 5)
    if st.button("Yeni Alışkanlık Ekle"):
        if new_h and new_h not in df_settings['Habit_Name'].values:
            new_row = pd.DataFrame([{"Habit_Name": new_h, "Weight": new_w_val}])
            df_settings = pd.concat([df_settings, new_row], ignore_index=True)
            settings_sheet.clear()
            settings_sheet.update(values=[df_settings.columns.values.tolist()] + df_settings.values.tolist())
            st.rerun()

# --- UI: DAILY LOGGING ---
st.subheader("Bugünün Görevleri")
today_str = today_tr.strftime("%Y-%m-%d")
current_logs = []
weighted_score_num = 0
total_weight = df_settings['Weight'].sum()

for _, row in df_settings.iterrows():
    habit = row['Habit_Name']
    weight = row['Weight']
    is_done = False
    if not df_logs.empty:
        match = df_logs[(df_logs['Date'] == today_str) & (df_logs['Habit_Name'] == habit)]
        if not match.empty:
            is_done = str(match['Status'].values[0]).upper() == 'TRUE'
    
    check = st.checkbox(f"{habit} (Ağırlık: {weight})", value=is_done, key=f"day_{habit}")
    if check: weighted_score_num += weight
    current_logs.append({"Date": today_str, "Habit_Name": habit, "Status": "TRUE" if check else "FALSE"})

daily_ratio = weighted_score_num / total_weight if total_weight > 0 else 0
st.progress(daily_ratio, text=f"Günün Ağırlıklı Başarısı: %{int(daily_ratio * 100)}")

if st.button("🚀 Günü Kaydet", use_container_width=True):
    if not df_logs.empty:
        df_logs = df_logs[df_logs['Date'] != today_str]
    final_logs = pd.concat([df_logs, pd.DataFrame(current_logs)], ignore_index=True)
    log_sheet.clear()
    log_sheet.update(values=[final_logs.columns.values.tolist()] + final_logs.values.tolist())
    st.success("Veriler başarıyla Google Sheets'e kaydedildi!")
    st.rerun()

# --- UI: PASTEL ARCHIVE HEATMAPS ---
st.divider()
st.subheader("Disiplin Arşivi")

if not df_logs.empty:
    df_calc = pd.merge(df_logs, df_settings, on='Habit_Name', how='left')
    df_calc['Weight'] = df_calc['Weight'].fillna(1)
    df_calc['Status_Bool'] = df_calc['Status'].astype(str).str.upper() == 'TRUE'
    df_calc['Weighted_Val'] = df_calc['Status_Bool'] * df_calc['Weight']
    
    daily_stats = df_calc.groupby('Date').agg({'Weighted_Val': 'sum'}).reset_index()
    max_w = df_settings['Weight'].sum()
    daily_stats['Score'] = daily_stats['Weighted_Val'] / max_w
    
    daily_stats['Date'] = pd.to_datetime(daily_stats['Date']).dt.date
    all_months = pd.date_range(end=today_tr.date(), start=daily_stats['Date'].min(), freq='MS').to_period('M').unique().tolist()
    all_months = sorted(all_months, reverse=True)

    for period in all_months:
        year, month = period.year, period.month
        st.markdown(f"#### {calendar.month_name[month]} {year}")
        num_days = calendar.monthrange(year, month)[1]
        
        cal_dates = [datetime(year, month, d).date() for d in range(1, num_days + 1)]
        cal_df = pd.DataFrame({'Date': cal_dates})
        
        m_merged = pd.merge(cal_df, daily_stats[['Date', 'Score']], on='Date', how='left')
        m_merged['Score'] = m_merged['Score'].fillna(-1.0)
        m_merged['DT'] = pd.to_datetime(m_merged['Date'])
        m_merged['Week'] = m_merged['DT'].dt.isocalendar().week
        
        if month == 1: m_merged.loc[m_merged['Week'] > 5, 'Week'] = 0
        m_merged['Day_Idx'] = m_merged['DT'].dt.dayofweek
        
        # Hover (Üzerine gelince) Text Ayarı
        def make_hover(row):
            d_str = row['Date'].strftime('%d %b %Y')
            if row['Score'] == -1.0:
                return f"{d_str}<br>Veri Yok"
            return f"{d_str}<br>Başarı: %{int(row['Score']*100)}"
            
        m_merged['Hover'] = m_merged.apply(make_hover, axis=1)
        
        pivot = m_merged.pivot(index='Day_Idx', columns='Week', values='Score').reindex(range(7))
        hover_pivot = m_merged.pivot(index='Day_Idx', columns='Week', values='Hover').reindex(range(7))
        
        fig = go.Figure(data=go.Heatmap(
            z=pivot.values,
            text=hover_pivot.values,
            hoverinfo="text",
            xgap=6, ygap=6,  # Daha geniş, pastel hissiyatlı boşluklar
            showscale=False,
            zmin=-1.0, zmax=1.0,
            colorscale=PASTEL_COLORS
        ))
        
        fig.update_layout(
            height=200, 
            margin=dict(t=10, l=40, r=10, b=10),
            yaxis=dict(
                tickmode='array', 
                tickvals=list(range(7)), 
                ticktext=['Pzt', 'Sal', 'Çar', 'Per', 'Cum', 'Cmt', 'Paz'], 
                autorange='reversed'
            ),
            xaxis=dict(showticklabels=False), 
            plot_bgcolor='rgba(0,0,0,0)', 
            paper_bgcolor='rgba(0,0,0,0)'
        )
        st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})
else:
    st.info("İlk verini girdiğinde pastel yeşil takvimin canlanacak!")
