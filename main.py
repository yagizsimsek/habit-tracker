import streamlit as st
import pandas as pd
import plotly.express as px
import gspread
from google.oauth2.service_account import Credentials
import json
from datetime import datetime

# --- UI CONFIGURATION ---
st.set_page_config(page_title="Habit Tracker", page_icon="🔥", layout="centered")

# --- DATABASE CONNECTION ---
@st.cache_resource
def connect_to_gsheets():
    try:
        # Streamlit'in gizli kasasından JSON verisini okuyoruz
        creds_dict = json.loads(st.secrets["gcp_service_account"])
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]
        creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        client = gspread.authorize(creds)
        return client.open("HabitTrackerDB").worksheet("Logs")
    except Exception as e:
        st.error("Database Connection Failed. Check your Secrets.")
        st.stop()

sheet = connect_to_gsheets()

st.title("🔥 Daily Habit Tracker")
st.markdown("Track your routines and visualize your consistency.")

# --- LOAD DATA ---
records = sheet.get_all_records()
df = pd.DataFrame(records) if records else pd.DataFrame(columns=["Date", "Habit_Name", "Status"])

if 'habits_list' not in st.session_state:
    if not df.empty and 'Habit_Name' in df.columns:
        st.session_state.habits_list = df['Habit_Name'].unique().tolist()
    else:
        st.session_state.habits_list = ["Deep Work (Study)", "Upper Body Workout", "Intermittent Fasting"]

# --- UI: ADD NEW HABIT ---
st.subheader("Add New Habit")
new_habit = st.text_input("Habit Name:")
if st.button("Add Habit"):
    if new_habit and new_habit not in st.session_state.habits_list:
        st.session_state.habits_list.append(new_habit)
        st.success(f"Added: {new_habit}")
        st.rerun()

# --- UI: DAILY CHECKLIST ---
st.divider()
st.subheader("Today's Tasks")
today_date = datetime.now().strftime("%Y-%m-%d")

completed_tasks = 0
updated_records = []

for habit in st.session_state.habits_list:
    is_done_today = False
    if not df.empty:
        match = df[(df['Date'] == today_date) & (df['Habit_Name'] == habit)]
        if not match.empty:
            is_done_today = str(match['Status'].values[0]).upper() == 'TRUE'

    is_checked = st.checkbox(habit, value=is_done_today, key=f"check_{habit}")
    if is_checked:
        completed_tasks += 1
        
    updated_records.append({
        "Date": today_date,
        "Habit_Name": habit,
        "Status": "TRUE" if is_checked else "FALSE"
    })

# Progress Calculation
total_tasks = len(st.session_state.habits_list)
daily_score = completed_tasks / total_tasks if total_tasks > 0 else 0

st.progress(daily_score, text=f"Daily Completion: {int(daily_score * 100)}%")

if st.button("Save Daily Progress"):
    if not df.empty:
        df = df[df['Date'] != today_date]
    
    new_df = pd.DataFrame(updated_records)
    final_df = pd.concat([df, new_df], ignore_index=True)
    
    sheet.clear()
    sheet.update(values=[final_df.columns.values.tolist()] + final_df.values.tolist())
    
    st.success("Progress safely logged to Database!")
    st.rerun()

# --- UI: MONTHLY HEATMAP ---
st.divider()
st.subheader("Monthly Consistency Heatmap")

if not df.empty:
    df['Status_Bool'] = df['Status'].astype(str).str.upper() == 'TRUE'
    daily_scores = df.groupby('Date')['Status_Bool'].mean().reset_index()
    daily_scores.rename(columns={'Status_Bool': 'Score'}, inplace=True)
    
    daily_scores['Date'] = pd.to_datetime(daily_scores['Date'])
    daily_scores['Week'] = daily_scores['Date'].dt.isocalendar().week
    daily_scores['Day_Name'] = daily_scores['Date'].dt.day_name()
    
    fig = px.density_heatmap(
        daily_scores, 
        x="Week", 
        y="Day_Name", 
        z="Score",
        color_continuous_scale="Greens",
        range_color=[0, 1],
        category_orders={"Day_Name": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]}
    )

    fig.update_layout(height=400, coloraxis_showscale=False, margin=dict(t=0, l=0, r=0, b=0))
    st.plotly_chart(fig, use_container_width=True)
else:
    st.info("No data yet. Complete some habits and save to see the magic!")
