import streamlit as st
import pandas as pd
import plotly.express as px
import gspread
from google.oauth2.service_account import Credentials
import json
from datetime import datetime
import pytz

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
        st.error("Database Connection Failed.")
        st.stop()

sheet = connect_to_gsheets()

# --- HEADER ---
st.title("🔥 Daily Habit Tracker")
today_tr = datetime.now(TR_TIMEZONE)
st.info(f"Today's Date (TR): {today_tr.strftime('%d %B %Y')}")

# --- DATA LOADING ---
records = sheet.get_all_records()
df = pd.DataFrame(records) if records else pd.DataFrame(columns=["Date", "Habit_Name", "Status"])

if 'habits_list' not in st.session_state:
    if not df.empty:
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
today_str = today_tr.strftime("%Y-%m-%d")

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

# --- UI: SHARP MONTHLY HEATMAPS ---
st.divider()
st.subheader("Consistency Heatmaps")

if not df.empty:
    df['Date'] = pd.to_datetime(df['Date'])
    df['Status_Bool'] = df['Status'].astype(str).str.upper() == 'TRUE'
    daily_stats = df.groupby('Date')['Status_Bool'].mean().reset_index()
    daily_stats.rename(columns={'Status_Bool': 'Score'}, inplace=True)
    
    # Sort months descending (Latest month first)
    daily_stats['Month_Year'] = daily_stats['Date'].dt.strftime('%B %Y')
    months = daily_stats['Month_Year'].unique()[::-1]

    for month in months:
        st.markdown(f"#### {month}")
        month_df = daily_stats[daily_stats['Month_Year'] == month].copy()
        month_df['Week'] = month_df['Date'].dt.isocalendar().week
        month_df['Day_Name'] = month_df['Date'].dt.day_name()
        
        fig = px.density_heatmap(
            month_df, x="Week", y="Day_Name", z="Score",
            color_continuous_scale="Greens", range_color=[0, 1],
            category_orders={"Day_Name": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]},
            text_auto=False
        )
        
        # Jilet gibi keskin tasarım ayarları
        fig.update_traces(xgap=3, ygap=3) # Kareler arası boşluk (Sharp look)
        fig.update_layout(
            height=250, coloraxis_showscale=False,
            margin=dict(t=10, l=10, r=10, b=10),
            xaxis_title=None, yaxis_title=None
        )
        st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})
else:
    st.info("Log your first habit to see the heatmap!")
