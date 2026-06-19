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

YEAR_COLORS = {"2024": "#3498db", "2025": "#e67e22", "2026": "#2ecc71"}
DEPOSIT_YEAR_COLORS = {"2024": "#27ae60", "2025": "#f1c40f", "2026": "#2ecc71"}  # Green shades for deposits
GAME_PALETTE = px.colors.qualitative.Vivid

# --- BULLETPROOF DATA LOADER (NATIVE EXCEL READING) ---
@st.cache_data
def load_data(uploaded_files):
    def robust_clean(val):
        if pd.isna(val):
            return 0.0
        
        # 1. Native Excel Numbers
        if isinstance(val, (int, float)):
            return float(val)
            
        # 2. Clean the string
        s = str(val).strip()
        s = re.sub(r'[\s\xa0\n\r]+', '', s)
        
        # 3. Handle negative numbers in parentheses like (1,278.00)
        if s.startswith('(') and s.endswith(')'):
            s = '-' + s[1:-1]
        
        # 4. Handle SA number format with commas and decimals
        if ',' in s:
            if '.' in s:
                s = s.replace(',', '')
            else:
                parts = s.split(',')
                if len(parts[-1]) <= 2:
                    s = s.replace(',', '.')
                else:
                    s = s.replace(',', '')
        
        s = s.replace(',', '')
        
        try:
            return float(s)
        except ValueError:
            return 0.0

    # --- Special date parser for January 2025 ---
    def parse_jan2025_date(date_val):
        if pd.isna(date_val):
            return None
        
        if isinstance(date_val, (pd.Timestamp, datetime)):
            return date_val
            
        date_str = str(date_val).strip()
        
        try:
            parts = date_str.split()
            if len(parts) >= 2:
                date_parts = parts[0].split('/')
                time_parts = parts[1].split(':')
                
                if len(date_parts) == 3 and len(time_parts) >= 2:
                    day = int(date_parts[0])
                    month = int(date_parts[1])
                    year = int(date_parts[2])
                    if year < 100:
                        year += 2000
                    hour = int(time_parts[0])
                    minute = int(time_parts[1])
                    second = int(time_parts[2]) if len(time_parts) > 2 else 0
                    
                    return pd.Timestamp(year=year, month=month, day=day, 
                                       hour=hour, minute=minute, second=second)
        except:
            pass
        
        try:
            return pd.to_datetime(date_str, format='%d/%m/%y %H:%M:%S', errors='coerce')
        except:
            try:
                return pd.to_datetime(date_str, dayfirst=True, errors='coerce')
            except:
                return None

    all_data = []
    diagnostics = {"gross_col_used": "None", "paid_in_col_used": "None", "fallback_used": False, "items_skipped": []}

    def process_raw_dataframe(df_raw, source_name):
        # Robust Header Finder
        header_idx = None
        for i, row in df_raw.iterrows():
            row_clean = [str(x).strip().lower() for x in row.values]
            if 'shop' in row_clean and 'game' in row_clean:
                header_idx = i
                break
                
        if header_idx is None: 
            return None
        
        df = df_raw.iloc[header_idx+1:].copy()
        df.columns = [str(c).strip() for c in df_raw.iloc[header_idx].values]
        
        # Dynamic Shop Column
        shop_col = next((c for c in df.columns if str(c).lower().strip() == 'shop'), None)
        if not shop_col: return None
        
        df['Shop'] = df[shop_col].astype(str).replace({'Potch': 'Potchefstroom'}).str.strip()
        
        # Dynamic Gross Win Column
        gross_col = None
        for c in df.columns:
            clean_c = re.sub(r'[\s\n\r_]+', '', str(c).lower())
            if clean_c in ['grosswin', 'ggr', 'grossrevenue', 'gross']:
                gross_col = c
                break
        
        if gross_col:
            diagnostics["gross_col_used"] = gross_col
            df['GGR'] = df[gross_col].apply(robust_clean)
        else:
            diagnostics["fallback_used"] = True
            df['GGR'] = 0.0
        
        # --- EXTRACT PAID IN (DEPOSITS) ---
        paid_in_col = None
        for c in df.columns:
            clean_c = re.sub(r'[\s\n\r_]+', '', str(c).lower())
            # Look for 'paid in' or 'paidin' 
            if clean_c in ['paidin', 'paid in']:
                paid_in_col = c
                break
        
        # If not found, look for any column with 'paid' in name
        if paid_in_col is None:
            for c in df.columns:
                clean_c = re.sub(r'[\s\n\r_]+', '', str(c).lower())
                if 'paid' in clean_c and 'out' not in clean_c:
                    paid_in_col = c
                    break
        
        if paid_in_col:
            diagnostics["paid_in_col_used"] = paid_in_col
            df['Deposits'] = df[paid_in_col].apply(robust_clean)
        else:
            df['Deposits'] = 0.0
        
        # Dynamic Date Column
        date_col = next((c for c in df.columns if 'firstslip' in str(c).lower().replace(' ', '') or 'date' in str(c).lower()), None)
        if date_col:
            if 'jan' in source_name.lower():
                df['First Slip Issued'] = df[date_col].apply(parse_jan2025_date)
            else:
                df['First Slip Issued'] = pd.to_datetime(df[date_col], errors='coerce', dayfirst=True)
            
            df = df.dropna(subset=['First Slip Issued'])
            df['Year'] = df['First Slip Issued'].dt.year.astype(int).astype(str)
            df['Month'] = df['First Slip Issued'].dt.strftime('%B')
            df['MonthNum'] = df['First Slip Issued'].dt.month
        else:
            return None
        
        return df[df['Shop'].isin(BRANCHES)]

    for file in uploaded_files:
        try:
            filename = file.name.lower()
            
            if filename.endswith('.csv'):
                if 'user' in filename and 'excl' not in filename:
                    diagnostics["items_skipped"].append(file.name)
                    continue
                df_raw = pd.read_csv(file, header=None)
                processed_df = process_raw_dataframe(df_raw, file.name)
                if processed_df is not None and not processed_df.empty:
                    all_data.append(processed_df)

            elif filename.endswith(('.xls', '.xlsx')):
                xl = pd.ExcelFile(file)
                for sheet in xl.sheet_names:
                    sheet_lower = str(sheet).lower()
                    if 'user' in sheet_lower and 'excl' not in sheet_lower:
                        diagnostics["items_skipped"].append(f"Tab: {sheet}")
                        continue
                    
                    df_raw = pd.read_excel(file, sheet_name=sheet, header=None)
                    processed_df = process_raw_dataframe(df_raw, f"{file.name} - {sheet}")
                    if processed_df is not None and not processed_df.empty:
                        all_data.append(processed_df)
                        
        except Exception as e:
            st.error(f"Error loading {file.name}: {e}")
            
    final_df = pd.concat(all_data, ignore_index=True) if all_data else pd.DataFrame()
    return final_df, diagnostics

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
if 'manual_2026_data' not in st.session_state:
    st.session_state.manual_2026_data = pd.DataFrame(columns=['Shop', 'Game', 'GGR', 'Deposits', 'Year', 'Month', 'MonthNum'])

st.sidebar.header("Navigation")
files = st.sidebar.file_uploader("Upload Excel/CSV", accept_multiple_files=True, type=["xlsx", "csv"])

st.sidebar.markdown("---")
st.sidebar.header("📥 Enter 2026 Actuals - GGR & Deposits")
entry_shop = st.sidebar.selectbox("Select Branch for 2026:", BRANCHES)
entry_month = st.sidebar.selectbox("Select Month (2026):", month_order)
entry_game = st.sidebar.text_input("Enter Game Name (2026):", value="Lucky #1")
entry_ggr = st.sidebar.number_input("Enter GGR Amount (R):", min_value=0.0, format="%.2f")
entry_deposits = st.sidebar.number_input("Enter Deposits / Paid In Amount (R):", min_value=0.0, format="%.2f")

if st.sidebar.button("Append to 2026 Ledger"):
    month_num = month_order.index(entry_month) + 1
    new_row = pd.DataFrame([{
        'Shop': entry_shop, 
        'Game': entry_game, 
        'GGR': entry_ggr,
        'Deposits': entry_deposits,
        'Year': '2026', 
        'Month': entry_month, 
        'MonthNum': month_num
    }])
    st.session_state.manual_2026_data = pd.concat([st.session_state.manual_2026_data, new_row], ignore_index=True)
    st.sidebar.success(f"Added R {entry_ggr:,.2f} GGR and R {entry_deposits:,.2f} Deposits for {entry_month}!")

if st.sidebar.button("Reset 2026 Ledger"):
    st.session_state.manual_2026_data = pd.DataFrame(columns=['Shop', 'Game', 'GGR', 'Deposits', 'Year', 'Month', 'MonthNum'])
    st.rerun()

# --- MAIN RUN LOGIC ---
if files:
    df_uploaded, diagnostics = load_data(files)
    
    if not st.session_state.manual_2026_data.empty:
        df = pd.concat([df_uploaded, st.session_state.manual_2026_data], ignore_index=True)
    else:
        df = df_uploaded

    if not df.empty:
        # --- NEW: TIME FILTERS ---
        available_months = sorted(df['Month'].unique(), key=lambda m: month_order.index(m) if m in month_order else 0)
        available_years = sorted(df['Year'].unique())
        
        st.sidebar.markdown("---")
        st.sidebar.header("⏳ Filter by Time")
        selected_year = st.sidebar.selectbox("Select Year:", ["All Time"] + available_years)
        
        if selected_year != "All Time":
            selected_month = st.sidebar.selectbox("Select Month:", ["All Months"] + available_months)
        else:
            selected_month = "All Months"

        nav_options = ["All Branches Dashboard"] + BRANCHES
        selected_view = st.sidebar.radio("Select Branch Analysis:", nav_options)
        
        # Apply filters
        df_filtered = df if selected_view == "All Branches Dashboard" else df[df['Shop'] == selected_view]
        if selected_year != "All Time":
            df_filtered = df_filtered[df_filtered['Year'] == selected_year]
        if selected_month != "All Months":
            df_filtered = df_filtered[df_filtered['Month'] == selected_month]
        
        total_ggr = df_filtered['GGR'].sum()
        total_deposits = df_filtered['Deposits'].sum() if 'Deposits' in df_filtered.columns else 0
        top_game = df_filtered.groupby('Game')['GGR'].sum().idxmax() if not df_filtered.empty else "N/A"
        
        # Calculate YoY only if viewing All Time
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
        
        # Use different color scheme for deposits (green shades)
        fig_deposits = px.bar(chart_data_deposits, x='Month', y='Deposits', color='Year', barmode='stack', category_orders={"Month": month_order}, color_discrete_map=DEPOSIT_YEAR_COLORS)
        fig_deposits.update_layout(xaxis_title=None, yaxis_title="Deposits / Paid In (ZAR)")
        st.plotly_chart(fig_deposits, use_container_width=True)
            
        st.subheader(f"Game Revenue Analysis")
        game_dist = df_filtered.groupby('Game')['GGR'].sum().reset_index()
        fig_pie = px.pie(game_dist, values='GGR', names='Game', hole=0.4, color_discrete_sequence=GAME_PALETTE)
        st.plotly_chart(fig_pie, use_container_width=True)
        
        with st.expander("📊 View Strategic Analysis & Solutions", expanded=True):
            st.markdown(generate_strategic_analysis(selected_view, yoy, total_ggr, total_deposits, top_game))
        
    else:
        st.warning("No relevant data found. The file may be empty or skipped.")
else:
    st.info("Please upload your Excel file to begin.")