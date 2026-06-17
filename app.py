import streamlit as st
import pandas as pd
import plotly.express as px
import warnings

# --- CONFIGURATION ---
st.set_page_config(page_title="Playbet Performance", layout="wide")
warnings.filterwarnings('ignore')

BRANCHES = ["Malvern", "Potchefstroom", "Pretoria", "White River", "Randburg"]
month_order = ["January", "February", "March", "April", "May", "June", 
               "July", "August", "September", "October", "November", "December"]

YEAR_COLORS = {"2024": "#3498db", "2025": "#e67e22", "2026": "#2ecc71"}
GAME_PALETTE = px.colors.qualitative.Vivid

# --- DATA LOADER ---
@st.cache_data
def load_data(uploaded_files):
    all_data = []
    for file in uploaded_files:
        try:
            xl = pd.ExcelFile(file)
            for sheet in xl.sheet_names:
                df_raw = pd.read_excel(file, sheet_name=sheet, header=None)
                header_idx = next((i for i, row in df_raw.iterrows() if 'Shop' in row.values and 'Game' in row.values), None)
                if header_idx is None: continue
                
                df = pd.read_excel(file, sheet_name=sheet, header=header_idx)
                df.columns = [str(c).strip() for c in df.columns]
                
                df['Shop'] = df['Shop'].astype(str).replace({'Potch': 'Potchefstroom'})
                
                for col in ['Paid In', 'Paid Out']:
                    if col in df.columns:
                        df[col] = pd.to_numeric(df[col].replace({',': ''}, regex=True), errors='coerce')
                df['GGR'] = df['Paid In'] - df['Paid Out']
                
                df['First Slip Issued'] = pd.to_datetime(df['First Slip Issued'], errors='coerce', format='mixed')
                df['Year'] = df['First Slip Issued'].dt.year.fillna(0).astype(int).astype(str)
                df['Month'] = df['First Slip Issued'].dt.strftime('%B')
                df['MonthNum'] = df['First Slip Issued'].dt.month
                
                df = df[df['Shop'].isin(BRANCHES)]
                all_data.append(df)
        except Exception as e:
            st.error(f"Error loading data: {e}")
    return pd.concat(all_data, ignore_index=True) if all_data else pd.DataFrame()

# --- ADAPTIVE ANALYTICS ENGINE ---
def generate_strategic_analysis(branch_name, yoy, total_ggr, top_game):
    # Fallback for "All Branches" view
    display_name = "the overall network" if branch_name == "All Branches Dashboard" else f"the {branch_name} branch"
    
    insights = []
    insights.append(f"### 📊 Tailored Action Plan: {branch_name}")

    # 1. Dynamic Growth Tiers
    if yoy > 20:
        insights.append(f"**🚀 Hyper-Growth Mode ({yoy:+.1f}%):** {display_name} is experiencing exceptional momentum. \n* **Action:** Shift strategy from acquisition to maximizing Lifetime Value (LTV). Consider launching VIP reward tiers to lock in the high-rollers driving this surge.")
    elif 0 <= yoy <= 20:
        insights.append(f"**📈 Steady Expansion ({yoy:+.1f}%):** {display_name} is showing healthy, sustainable growth. \n* **Action:** Focus on cross-selling. Push localized promotions to convert casual players into daily visitors to bump up the average handle.")
    elif -15 < yoy < 0:
        insights.append(f"**⚠️ Early Warning ({yoy:+.1f}%):** Revenue has cooled slightly. \n* **Action:** Deploy immediate reactivation campaigns (e.g., targeted SMS promos or deposit matches) targeting lapsed players in this specific area.")
    else:
        insights.append(f"**🚨 Critical Decline ({yoy:+.1f}%):** {display_name} requires immediate intervention. \n* **Action:** Conduct a strict operational audit. Assess local competitor promotions, review branch overheads, and consider aggressive grassroots marketing to rebuild foot traffic.")

    # 2. Dynamic Game Strategy
    insights.append(f"**🎯 Product Optimization:** With **'{top_game}'** dominating the revenue share, ensure terminal availability and uptime for this game is at 100% during peak hours. Train staff to introduce '{top_game}' players to adjacent, higher-margin games.")

    return "\n\n".join(insights)

# --- APP LAYOUT ---
st.sidebar.header("Navigation")
files = st.sidebar.file_uploader("Upload Excel/CSV", accept_multiple_files=True, type=["xlsx", "csv"])

if files:
    df = load_data(files)
    if not df.empty:
        nav_options = ["All Branches Dashboard"] + BRANCHES
        selected_view = st.sidebar.radio("Select Branch Analysis:", nav_options)
        
        df_filtered = df if selected_view == "All Branches Dashboard" else df[df['Shop'] == selected_view]
        
        # --- METRICS ---
        total_ggr = df_filtered['GGR'].sum()
        top_game = df_filtered.groupby('Game')['GGR'].sum().idxmax() if not df_filtered.empty else "N/A"
        
        years = sorted(df_filtered['Year'].unique())
        yoy = 0.0
        if len(years) >= 2:
            curr = df_filtered[df_filtered['Year'] == years[-1]]['GGR'].sum()
            prev = df_filtered[df_filtered['Year'] == years[-2]]['GGR'].sum()
            yoy = ((curr - prev) / prev) * 100 if prev != 0 else 0
            
        st.subheader(f"{selected_view} Performance")
        c1, c2, c3 = st.columns(3)
        c1.metric("Total GGR", f"R {total_ggr:,.2f}")
        c2.metric("YoY Growth", f"{yoy:+.1f}%")
        c3.metric("Top Performer", top_game)
        st.divider()

        # --- VISUALIZATIONS ---
        st.subheader("GGR: 2024 vs 2025 Stacked Comparison")
        chart_data = df_filtered.groupby(['MonthNum', 'Month', 'Year'])['GGR'].sum().reset_index().sort_values('MonthNum')
        
        fig = px.bar(chart_data, x='Month', y='GGR', color='Year', barmode='stack', 
                     category_orders={"Month": month_order}, color_discrete_map=YEAR_COLORS)
        fig.update_layout(xaxis_title=None, yaxis_title="Gross Gaming Revenue (ZAR)")
        st.plotly_chart(fig, use_container_width=True)
            
        st.subheader(f"Game Revenue Analysis")
        game_dist = df_filtered.groupby('Game')['GGR'].sum().reset_index()
        fig_pie = px.pie(game_dist, values='GGR', names='Game', hole=0.4, color_discrete_sequence=GAME_PALETTE)
        st.plotly_chart(fig_pie, use_container_width=True)
        
        # --- DYNAMIC STRATEGIC ANALYSIS ---
        with st.expander("📊 View Strategic Analysis & Solutions", expanded=True):
            st.markdown(generate_strategic_analysis(selected_view, yoy, total_ggr, top_game))
        
    else:
        st.warning("No data found.")
else:
    st.info("Please upload your data to begin.")