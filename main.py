import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import gspread
from google.oauth2.service_account import Credentials
import json
from datetime import datetime
import pytz
import calendar

# --- CONFIGURATION ---
st.set_page_config(page_title="Habit Tracker", page_icon="🔥", layout="centered")
TR_TIMEZONE = pytz.timezone('Europe/Istanbul')

@st.cache_resource
def connect_to_gsheets():
    try:
        creds_dict = json.loads(st.secrets["gcp_service_account"])
        scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        client = gspread.authorize(creds)
        return client.open("HabitTrackerDB").worksheet("Logs")
    except Exception as e:
        st.error("Database Connection Failed. Check Secrets.")
        st.stop()

sheet = connect_to_gsheets()

# --- HEADER ---
st.title("🔥 Daily Habit Tracker")
today_dt = datetime.now(TR_TIMEZONE).date()
st.info(f"Today's Date (TR): {today_dt.strftime('%d %B %Y')}")

# --- DATA LOADING ---
records = sheet.get_all_records()
df = pd.DataFrame(records) if records else pd.DataFrame(columns=["Date", "Habit_Name", "Status"])

if 'habits_list' not in st.session_state:
    if not df.empty and 'Habit_Name' in df.columns:
        st.session_state.habits_list = df['Habit_Name'].unique().tolist()
    else:
        st.session_state.habits_list = ["Deep Work (Study)", "Upper Body Workout", "Intermittent Fasting", "Deep Work Block 1"]

# --- UI: ADD HABIT ---
with st.expander("➕ Add/Manage Habits"):
    new_habit = st.text_input("New Habit Name:")
    if st.button("Add Habit"):
        if new_habit and new_habit not in st.session_state.habits_list:
            st.session_state.habits_list.append(new_habit)
            st.rerun()

# --- UI: DAILY LOGGING ---
st.subheader("Daily Checklist")
today_str = today_dt.strftime("%Y-%m-%d")

completed_count = 0
current_logs = []

for habit in st.session_state.habits_list:
    is_done = False
    if not df.empty:
        match = df[(df['Date'] == today_str) & (df['Habit_Name'] == habit)]
        if not match.empty:
            is_done = str(match['Status'].values[0]).upper() == 'TRUE'
    
    check = st.checkbox(habit, value=is_done, key=f"check_{habit}")
    if check: completed_count += 1
    current_logs.append({"Date": today_str, "Habit_Name": habit, "Status": "TRUE" if check else "FALSE"})

if st.button("🚀 Save Daily Progress", use_container_width=True):
    if not df.empty:
        df = df[df['Date'] != today_str]
    final_df = pd.concat([df, pd.DataFrame(current_logs)], ignore_index=True)
    sheet.clear()
    sheet.update(values=[final_df.columns.values.tolist()] + final_df.values.tolist())
    st.success("Successfully logged!")
    st.rerun()

# --- UI: FULL GRID MONTHLY HEATMAP ---
st.divider()
st.subheader("Consistency Heatmap")

# 1. Bütün ayın boş takvimini oluştur
year, month = today_dt.year, today_dt.month
num_days = calendar.monthrange(year, month)[1]
month_dates = [datetime(year, month, day).date() for day in range(1, num_days + 1)]
cal_df = pd.DataFrame({'Date': month_dates})

# 2. Gerçek veriyi takvimle birleştir
if not df.empty:
    df['Date'] = pd.to_datetime(df['Date']).dt.date
    df['Status_Bool'] = df['Status'].astype(str).str.upper() == 'TRUE'
    daily_stats = df.groupby('Date')['Status_Bool'].mean().reset_index()
    daily_stats.rename(columns={'Status_Bool': 'Score'}, inplace=True)
    merged_df = pd.merge(cal_df, daily_stats, on='Date', how='left')
else:
    merged_df = cal_df.copy()
    merged_df['Score'] = float('nan')

# Boş günlere -1 veriyoruz ki griye boyayabilelim
merged_df['Score'] = merged_df['Score'].fillna(-1.0)
merged_df['Date_DT'] = pd.to_datetime(merged_df['Date'])
merged_df['Week'] = merged_df['Date_DT'].dt.isocalendar().week

# Yıl sonu/başı hafta kaymalarını düzeltme
merged_df.loc[(merged_df['Date_DT'].dt.month == 1) & (merged_df['Week'] >= 52), 'Week'] = 0
merged_df['Day_Idx'] = merged_df['Date_DT'].dt.dayofweek

# Matris formatına çevirme (Pzt-Paz arası 7 gün)
pivot = merged_df.pivot(index='Day_Idx', columns='Week', values='Score').reindex(range(7))

# Mouse ile üzerine gelince yazacaklar
def make_hover(row):
    date_str = row['Date'].strftime('%d %b %Y')
    if row['Score'] == -1.0:
        return f"{date_str}<br>No Data"
    return f"{date_str}<br>Score: {int(row['Score']*100)}%"

merged_df['Hover'] = merged_df.apply(make_hover, axis=1)
hover_pivot = merged_df.pivot(index='Day_Idx', columns='Week', values='Hover').reindex(range(7))

# 3. Renk Skalası Ayarı (-1 gri, 0-1 arası yeşil tonları)
custom_colors = [
    [0.0, '#2d333b'],  # -1'e denk gelen yer: Koyu Gri
    [0.49, '#2d333b'], # 0 sınırına kadar: Koyu Gri
    [0.5, '#00441b'],  # 0'a denk gelen yer: Çok Koyu Yeşil
    [1.0, '#39d353']   # 1'e denk gelen yer: Parlak Yeşil
]

fig = go.Figure(data=go.Heatmap(
    z=pivot.values,
    text=hover_pivot.values,
    hoverinfo="text",
    colorscale=custom_colors,
    zmin=-1.0, zmax=1.0,
    xgap=4, ygap=4, # Jilet gibi kare boşlukları
    showscale=False
))

fig.update_layout(
    height=250,
    margin=dict(t=20, l=40, r=20, b=20),
    yaxis=dict(
        tickmode='array',
        tickvals=list(range(7)),
        ticktext=['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'],
        autorange='reversed' # Pazartesi en üstte olsun
    ),
    xaxis=dict(showticklabels=False), # Alt kısımdaki hafta sayılarını gizledik, daha temiz durur
    plot_bgcolor='rgba(0,0,0,0)',
    paper_bgcolor='rgba(0,0,0,0)'
)

st.markdown(f"### {today_dt.strftime('%B %Y')}")
st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})
