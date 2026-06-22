import streamlit as st
import pandas as pd
import plotly.express as px
import warnings
import re
from datetime import datetime

# --- CONFIGURATION ---
st.set_page_config(page_title="Playbet Performance", layout="wide")
warnings.filterwarnings('ignore')

BRANCHES = ["Malvern", "Potchefstroom", "Pretoria", "White River", "Randburg"]
month_order = ["January", "February", "March", "April", "May", "June", 
               "July", "August", "September", "October", "November", "December"]

YEAR_COLORS = {"2024": "#3498db", "2025": "#e67e22", "2026": "#9b59b6"}
DEPOSIT_YEAR_COLORS = {"2024": "#27ae60", "2025": "#f1c40f", "2026": "#8e44ad"} 
GAME_PALETTE = px.colors.qualitative.Vivid

# The strict schema every file must conform to before merging
TARGET_COLS = ['Shop', 'Game', 'Deposits', 'GGR', 'Paid Out Sum', 'GW Margin %', 'Net Win', 'Net Win Margin', 'Year', 'Month', 'MonthNum']

# --- HELPER FUNCTIONS ---
def extract_date_from_filename(filename):
    """Extracts month and year from filenames like 'January 2026.csv'"""
    month_pattern = r'(January|February|March|April|May|June|July|August|September|October|November|December)\s*(\d{4})'
    match = re.search(month_pattern, filename, re.IGNORECASE)
    if match:
        month_name = match.group(1).capitalize()
        year = int(match.group(2))
        return datetime(year, month_order.index(month_name) + 1, 1)
    return datetime(2026, 1, 1) # Fallback

def robust_clean(val):
    if pd.isna(val) or val == '': return 0.0
    if isinstance(val, (int, float)): return float(val)
    s = str(val).strip()
    s = re.sub(r'[\s\xa0\n\rR]+', '', s)
    if s.startswith('(') and s.endswith(')'): s = '-' + s[1:-1]
    if ',' in s:
        if '.' in s: s = s.replace(',', '')
        else:
            parts = s.split(',')
            if len(parts[-1]) <= 2: s = s.replace(',', '.')
            else: s = s.replace(',', '')
    s = s.replace(',', '')
    try: return float(s)
    except: return 0.0

def parse_jan2025_date(date_val):
    if pd.isna(date_val): return None
    if isinstance(date_val, (pd.Timestamp, datetime)): return date_val
    date_str = str(date_val).strip()
    try:
        parts = date_str.split()
        if len(parts) >= 2:
            date_parts = parts[0].split('/')
            time_parts = parts[1].split(':')
            if len(date_parts) == 3 and len(time_parts) >= 2:
                day, month, year = int(date_parts[0]), int(date_parts[1]), int(date_parts[2])
                if year < 100: year += 2000
                hour, minute = int(time_parts[0]), int(time_parts[1])
                second = int(time_parts[2]) if len(time_parts) > 2 else 0
                return pd.Timestamp(year=year, month=month, day=day, hour=hour, minute=minute, second=second)
    except: pass
    try: return pd.to_datetime(date_str, format='%d/%m/%y %H:%M:%S', errors='coerce')
    except:
        try: return pd.to_datetime(date_str, dayfirst=True, errors='coerce')
        except: return None

def enforce_schema(df):
    """Ensures exact matching to TARGET_COLS and repairs merged Excel cells."""
    if df is None or df.empty: return None
    df = df.loc[:, ~df.columns.duplicated()]
    
    # ACCURACY FIX: Forward-fill empty shop names caused by Excel merged/grouped cells
    if 'Shop' in df.columns:
        df['Shop'] = df['Shop'].astype(str).str.strip().replace({'nan': None, 'NaN': None, 'None': None, '': None})
        df['Shop'] = df['Shop'].ffill() # Copies the last known shop down to blank rows
        df['Shop'] = df['Shop'].replace({'Potch': 'Potchefstroom'})
        df = df[df['Shop'].isin(BRANCHES)]
    else:
        df['Shop'] = 'Unknown'

    # Fill missing columns
    for col in TARGET_COLS:
        if col not in df.columns:
            df[col] = 0.0 if col not in ['Shop', 'Game', 'Year', 'Month'] else "Unknown"
            
    # Clean numeric columns for math
    num_cols = ['Deposits', 'Paid Out Sum', 'GGR', 'GW Margin %', 'Net Win', 'Net Win Margin']
    for col in num_cols:
        df[col] = df[col].apply(robust_clean)

    return df[TARGET_COLS].copy()

# --- THE UNIFIED DATA LOADER ---
@st.cache_data
def load_data(uploaded_files):
    all_data = []

    def process_excel_dataframe(df_raw, source_name):
        """High-accuracy Excel header hunting and data extraction."""
        header_idx = None
        for i, row in df_raw.iterrows():
            row_clean = [str(x).strip().lower() for x in row.values]
            if 'shop' in row_clean and 'game' in row_clean:
                header_idx = i
                break
                
        if header_idx is None: return None
        
        df = df_raw.iloc[header_idx+1:].copy()
        df.columns = [str(c).strip() for c in df_raw.iloc[header_idx].values]
        
        shop_col = next((c for c in df.columns if str(c).lower().strip() == 'shop'), None)
        if not shop_col: return None
        df['Shop'] = df[shop_col]
        
        gross_col = next((c for c in df.columns if re.sub(r'[\s\n\r_]+', '', str(c).lower()) in ['grosswin', 'ggr', 'grossrevenue', 'gross']), None)
        df['GGR'] = df[gross_col] if gross_col else 0.0
        
        paid_in_col = next((c for c in df.columns if re.sub(r'[\s\n\r_]+', '', str(c).lower()) in ['paidin', 'paid in']), None)
        if not paid_in_col:
            paid_in_col = next((c for c in df.columns if 'paid' in re.sub(r'[\s\n\r_]+', '', str(c).lower()) and 'out' not in re.sub(r'[\s\n\r_]+', '', str(c).lower())), None)
        df['Deposits'] = df[paid_in_col] if paid_in_col else 0.0
        
        date_col = next((c for c in df.columns if 'firstslip' in str(c).lower().replace(' ', '') or 'date' in str(c).lower()), None)
        if date_col:
            if 'jan' in source_name.lower(): df['First Slip Issued'] = df[date_col].apply(parse_jan2025_date)
            else: df['First Slip Issued'] = pd.to_datetime(df[date_col], errors='coerce', dayfirst=True)
            
            # ACCURACY FIX: Forward-fill dates to capture unlabelled rows beneath a grouped date
            df['First Slip Issued'] = df['First Slip Issued'].ffill()
            df = df.dropna(subset=['First Slip Issued'])
            
            df['Year'] = df['First Slip Issued'].dt.year.astype(int).astype(str)
            df['Month'] = df['First Slip Issued'].dt.strftime('%B')
            df['MonthNum'] = df['First Slip Issued'].dt.month
        else:
            return None
            
        return df

    for file in uploaded_files:
        try:
            filename = file.name.lower()
            file_date = extract_date_from_filename(filename)
            
            # --- PATH 1: CSV FILES (Raw or Clean) ---
            if filename.endswith('.csv'):
                df = pd.read_csv(file)
                df.columns = [str(c).strip() for c in df.columns]
                
                if 'Paid In Sum' in df.columns or 'Cashier' in df.columns:
                    # Raw Cash Operations format
                    df = df.rename(columns={'Paid In Sum': 'Deposits', 'Gross Win': 'GGR'})
                    df['Date'] = file_date
                else:
                    # Standard/Cleaned CSV
                    col_map = {}
                    for c in df.columns:
                        c_lower = str(c).lower().replace(' ', '')
                        if 'paidin' in c_lower: col_map[c] = 'Deposits'
                        elif 'grosswin' in c_lower or 'ggr' in c_lower: col_map[c] = 'GGR'
                        elif 'date' in c_lower or 'firstslip' in c_lower: col_map[c] = 'Date'
                    df = df.rename(columns=col_map)
                    
                    if 'Date' not in df.columns:
                        df['Date'] = file_date
                    else:
                        df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
                
                # Derive Dates & Forward-Fill for safety
                df['Date'] = df['Date'].ffill()
                df = df.dropna(subset=['Date'])
                if not df.empty:
                    df['Year'] = df['Date'].dt.year.astype(int).astype(str)
                    df['Month'] = df['Date'].dt.strftime('%B')
                    df['MonthNum'] = df['Date'].dt.month
                    
                df_clean = enforce_schema(df)
                if df_clean is not None: all_data.append(df_clean)

            # --- PATH 2: LEGACY EXCEL FILES ---
            elif filename.endswith(('.xls', '.xlsx')):
                xl = pd.ExcelFile(file)
                for sheet in xl.sheet_names:
                    sheet_lower = str(sheet).lower()
                    if 'user' in sheet_lower and 'excl' not in sheet_lower:
                        continue 
                    
                    df_raw = pd.read_excel(file, sheet_name=sheet, header=None)
                    processed_df = process_excel_dataframe(df_raw, f"{file.name} - {sheet}")
                    
                    df_clean = enforce_schema(processed_df)
                    if df_clean is not None: all_data.append(df_clean)
                        
        except Exception as e:
            st.error(f"Error loading {file.name}: {e}")
            
    if all_data:
        final_df = pd.concat(all_data, ignore_index=True)
        return final_df
    return pd.DataFrame()

# --- ADAPTIVE ANALYTICS ENGINE ---
def generate_strategic_analysis(branch_name, yoy, total_ggr, total_deposits, top_game):
    display_name = "the overall network" if branch_name == "All Branches Dashboard" else f"the {branch_name} branch"
    insights = [f"### 📊 Tailored Action Plan: {branch_name}"]

    if yoy > 20:
        insights.append(f"**🚀 Hyper-Growth Mode ({yoy:+.1f}%):** {display_name} is experiencing exceptional momentum. \n* **Action:** Shift strategy from acquisition to maximizing Lifetime Value (LTV). Consider launching VIP reward tiers to lock in the high-rollers driving this surge.")
    elif 0 <= yoy <= 20:
        insights.append(f"**📈 Steady Expansion ({yoy:+.1f}%):** {display_name} is showing healthy, sustainable growth. \n* **Action:** Focus on cross-selling. Push localized promotions to convert casual players into daily visitors to bump up the average handle.")
    elif -15 < yoy < 0:
        insights.append(f"**⚠️ Early Warning ({yoy:+.1f}%):** Revenue has cooled slightly. \n* **Action:** Deploy immediate reactivation campaigns targeting lapsed players in this specific area.")
    else:
        insights.append(f"**🚨 Critical Decline ({yoy:+.1f}%):** {display_name} requires immediate intervention. \n* **Action:** Conduct a strict operational audit. Assess local competitor promotions, review branch overheads, and consider aggressive grassroots marketing to rebuild foot traffic.")

    insights.append(f"**🎯 Product Optimization:** With **'{top_game}'** dominating the revenue share, ensure terminal availability and uptime for this game is at 100% during peak hours.")
    insights.append(f"**💰 Deposits Performance:** Total deposits of R {total_deposits:,.2f} indicate {'strong' if total_deposits > 1000000 else 'moderate'} player activity.")
    return "\n\n".join(insights)

# --- APP LAYOUT ---
st.title("Playbet Dashboard")

if 'manual_2026_data' not in st.session_state:
    st.session_state.manual_2026_data = pd.DataFrame(columns=TARGET_COLS)

st.sidebar.header("Navigation")
files = st.sidebar.file_uploader("Upload Excel/CSV", accept_multiple_files=True, type=["xlsx", "csv"])
st.sidebar.info("💡 Ensure CSV filenames include the month and year (e.g., 'May 2026.csv').")

st.sidebar.markdown("---")
st.sidebar.header("📥 Enter Manual Actuals")
entry_shop = st.sidebar.selectbox("Select Branch:", BRANCHES)
entry_month = st.sidebar.selectbox("Select Month:", month_order)
entry_game = st.sidebar.text_input("Enter Game Name:", value="Lucky #1")
entry_deposits = st.sidebar.number_input("Enter Deposits Amount (R):", min_value=0.0, format="%.2f")
entry_ggr = st.sidebar.number_input("Enter GGR Amount (R):", min_value=0.0, format="%.2f")

if st.sidebar.button("Append to Ledger"):
    month_num = month_order.index(entry_month) + 1
    new_row = pd.DataFrame([{
        'Shop': entry_shop, 'Game': entry_game, 
        'Deposits': entry_deposits, 'Paid Out Sum': 0.0,
        'GGR': entry_ggr, 'GW Margin %': 0.0, 'Net Win': 0.0, 'Net Win Margin': 0.0,
        'Year': '2026', 'Month': entry_month, 'MonthNum': month_num
    }])
    st.session_state.manual_2026_data = pd.concat([st.session_state.manual_2026_data, new_row], ignore_index=True)
    st.sidebar.success(f"Added R {entry_ggr:,.2f} GGR and R {entry_deposits:,.2f} Deposits for {entry_month}!")

if st.sidebar.button("Reset Ledger"):
    st.session_state.manual_2026_data = pd.DataFrame(columns=TARGET_COLS)
    st.rerun()

# --- MAIN RUN LOGIC ---
if files:
    df_uploaded = load_data(files)
    
    if not st.session_state.manual_2026_data.empty:
        df = pd.concat([df_uploaded, st.session_state.manual_2026_data], ignore_index=True)
    else:
        df = df_uploaded

    if not df.empty:
        available_months = sorted(df['Month'].unique(), key=lambda m: month_order.index(m) if m in month_order else 0)
        available_years = sorted(df['Year'].unique())
        
        st.sidebar.markdown("---")
        st.sidebar.header("⏳ Filter by Time")
        selected_year = st.sidebar.selectbox("Select Year:", ["All Time"] + available_years)
        selected_month = st.sidebar.selectbox("Select Month:", ["All Months"] + available_months) if selected_year != "All Time" else "All Months"

        nav_options = ["All Branches Dashboard"] + BRANCHES
        selected_view = st.sidebar.radio("Select Branch Analysis:", nav_options)
        
        df_filtered = df if selected_view == "All Branches Dashboard" else df[df['Shop'] == selected_view]
        if selected_year != "All Time": df_filtered = df_filtered[df_filtered['Year'] == selected_year]
        if selected_month != "All Months": df_filtered = df_filtered[df_filtered['Month'] == selected_month]
        
        total_ggr = df_filtered['GGR'].sum()
        total_deposits = df_filtered['Deposits'].sum()
        top_game = df_filtered.groupby('Game')['GGR'].sum().idxmax() if not df_filtered.empty else "N/A"
        
        yoy = 0.0
        if selected_year == "All Time":
            years = sorted(df_filtered['Year'].unique())
            if len(years) >= 2:
                curr = df_filtered[df_filtered['Year'] == years[-1]]['GGR'].sum()
                prev = df_filtered[df_filtered['Year'] == years[-2]]['GGR'].sum()
                yoy = ((curr - prev) / prev) * 100 if prev != 0 else 0
            
        st.subheader(f"{selected_view} Performance")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total GGR", f"R {total_ggr:,.2f}")
        c2.metric("Total Deposits (Paid In)", f"R {total_deposits:,.2f}")
        c3.metric("YoY Growth", f"{yoy:+.1f}%" if selected_year == "All Time" else "N/A (Filtered)")
        c4.metric("Top Performer", top_game)
        st.divider()

        st.subheader("GGR: Multi-Year Stacked Comparison")
        chart_data = df_filtered.groupby(['MonthNum', 'Month', 'Year'])['GGR'].sum().reset_index().sort_values('MonthNum')
        fig = px.bar(chart_data, x='Month', y='GGR', color='Year', barmode='stack', category_orders={"Month": month_order}, color_discrete_map=YEAR_COLORS)
        fig.update_layout(xaxis_title=None, yaxis_title="Gross Gaming Revenue (ZAR)")
        st.plotly_chart(fig, use_container_width=True)
        
        st.subheader("Deposits (Paid In): Multi-Year Stacked Comparison")
        chart_data_deposits = df_filtered.groupby(['MonthNum', 'Month', 'Year'])['Deposits'].sum().reset_index().sort_values('MonthNum')
        fig_deposits = px.bar(chart_data_deposits, x='Month', y='Deposits', color='Year', barmode='stack', category_orders={"Month": month_order}, color_discrete_map=DEPOSIT_YEAR_COLORS)
        fig_deposits.update_layout(xaxis_title=None, yaxis_title="Deposits / Paid In (ZAR)")
        st.plotly_chart(fig_deposits, use_container_width=True)
            
        st.subheader(f"Game Revenue Analysis")
        game_dist = df_filtered.groupby('Game')['GGR'].sum().reset_index()
        fig_pie = px.pie(game_dist, values='GGR', names='Game', hole=0.4, color_discrete_sequence=GAME_PALETTE)
        st.plotly_chart(fig_pie, use_container_width=True)

        st.divider()
        st.subheader("Raw Data Summary (Cleaned)")
        st.dataframe(df_filtered[['Year', 'Month', 'Shop', 'Game', 'Deposits', 'Paid Out Sum', 'GGR', 'GW Margin %', 'Net Win', 'Net Win Margin']].head(100), use_container_width=True)
        
        with st.expander("📊 View Strategic Analysis & Solutions", expanded=True):
            st.markdown(generate_strategic_analysis(selected_view, yoy, total_ggr, total_deposits, top_game))
        
    else:
        st.warning("No relevant data found. The file may be empty or invalid.")
else:
    st.info("Please upload your Excel or CSV file to begin. Filename MUST contain the month and year (e.g., 'May 2026.csv').")