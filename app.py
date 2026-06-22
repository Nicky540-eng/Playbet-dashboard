import streamlit as st
import pandas as pd
import plotly.express as px
import warnings
import re
from datetime import datetime
import os
from pathlib import Path
import glob

# --- CONFIGURATION ---
st.set_page_config(page_title="Playbet Performance", layout="wide")
warnings.filterwarnings('ignore')

BRANCHES = ["Malvern", "Potchefstroom", "Pretoria", "White River", "Randburg"]
month_order = ["January", "February", "March", "April", "May", "June", 
               "July", "August", "September", "October", "November", "December"]

YEAR_COLORS = {"2024": "#3498db", "2025": "#e67e22", "2026": "#9b59b6"}
DEPOSIT_YEAR_COLORS = {"2024": "#27ae60", "2025": "#f1c40f", "2026": "#8e44ad"} 
GAME_PALETTE = px.colors.qualitative.Vivid

# Define folders
HISTORICAL_FOLDER = "historical_data"
UPLOAD_FOLDER = "uploads"

# Create folders if they don't exist
Path(HISTORICAL_FOLDER).mkdir(exist_ok=True)
Path(UPLOAD_FOLDER).mkdir(exist_ok=True)

# The strict schema every file must conform to before merging
TARGET_COLS = ['Shop', 'Game', 'Deposits', 'GGR', 'Paid Out Sum', 'GW Margin %', 'Net Win', 'Net Win Margin', 'Year', 'Month', 'MonthNum']

# --- PRECISION HELPER FUNCTIONS ---
def clean_currency_string(val):
    """
    Clean currency strings with high precision handling:
    - Removes currency symbols (R, $, €, £, ZAR)
    - Removes whitespace and special characters
    - Handles comma as thousand separator
    - Handles comma as decimal separator (European format)
    - Handles parentheses for negative values
    - Converts to float with maximum precision
    """
    if pd.isna(val) or val == '' or val == 'nan' or val == 'NaN':
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    
    # Convert to string and strip
    s = str(val).strip()
    
    # Remove currency symbols (R, $, €, £, ZAR, etc.)
    s = re.sub(r'[R$€£]', '', s)
    s = re.sub(r'ZAR', '', s, flags=re.IGNORECASE)
    
    # Remove whitespace and special characters (keep only numbers, commas, dots, and minus signs)
    s = re.sub(r'[\s\xa0\n\r\t]', '', s)
    
    # Handle parentheses for negative values (e.g., (1,234.56) → -1234.56)
    if s.startswith('(') and s.endswith(')'):
        s = '-' + s[1:-1]
    
    # Handle comma as thousand separator vs decimal separator
    if ',' in s:
        # Count commas and dots
        comma_count = s.count(',')
        dot_count = s.count('.')
        
        # If there's a comma and a dot, the comma is likely thousand separator
        if comma_count > 0 and dot_count > 0:
            # European format: comma is decimal, dot is thousand (e.g., 1.234,56)
            if dot_count == 1 and comma_count == 1:
                # If there's exactly one dot and one comma, check positions
                dot_pos = s.index('.')
                comma_pos = s.index(',')
                if comma_pos > dot_pos:
                    # European format: 1.234,56 → remove dot, replace comma with dot
                    s = s.replace('.', '')
                    s = s.replace(',', '.')
                else:
                    # US format: 1,234.56 → remove comma
                    s = s.replace(',', '')
            # US format: 1,234.56 → remove commas
            elif dot_count >= 1 and comma_count >= 1:
                # US format: remove commas
                s = s.replace(',', '')
            # European format: 1.234.567,89
            elif comma_count == 1 and dot_count > 1:
                s = s.replace('.', '')
                s = s.replace(',', '.')
            # Standard format: 1,234.56
            else:
                s = s.replace(',', '')
        # If there's only a comma and no dot
        elif comma_count > 0 and dot_count == 0:
            # European format: 1234,56 → replace comma with dot
            if len(s.split(',')[1]) <= 2:
                s = s.replace(',', '.')
            else:
                # Thousands format: 1,234 → remove comma
                s = s.replace(',', '')
    
    # Remove any remaining non-numeric characters (except dot and minus)
    # But keep the dot for decimal
    s = re.sub(r'[^\d.\-]', '', s)
    
    # Handle multiple dots - keep only the last one
    if s.count('.') > 1:
        parts = s.split('.')
        s = ''.join(parts[:-1]) + '.' + parts[-1]
    
    try:
        result = float(s)
        return result
    except ValueError:
        # If conversion fails, try to extract number using regex
        match = re.search(r'[\d,\.]+', s)
        if match:
            try:
                # Clean the matched number
                num_str = match.group()
                num_str = num_str.replace(',', '')
                return float(num_str)
            except:
                return 0.0
        return 0.0

def extract_date_from_filename(filename):
    """Extracts month and year from filenames like 'January 2026.csv' or 'Cash Operations Summary - January 2026.csv'"""
    # Try to find month name and year anywhere in the filename
    month_pattern = r'(January|February|March|April|May|June|July|August|September|October|November|December)\s*(\d{4})'
    match = re.search(month_pattern, filename, re.IGNORECASE)
    if match:
        month_name = match.group(1).capitalize()
        year = int(match.group(2))
        return datetime(year, month_order.index(month_name) + 1, 1)
    
    # Try alternative: month name with underscore or dash
    month_pattern2 = r'(January|February|March|April|May|June|July|August|September|October|November|December)[_\-\s]*(\d{4})'
    match = re.search(month_pattern2, filename, re.IGNORECASE)
    if match:
        month_name = match.group(1).capitalize()
        year = int(match.group(2))
        return datetime(year, month_order.index(month_name) + 1, 1)
    
    # Try abbreviated month names (Jan, Feb, Mar, etc.)
    month_abbr_pattern = r'(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s*(\d{4})'
    match = re.search(month_abbr_pattern, filename, re.IGNORECASE)
    if match:
        month_abbr = match.group(1).capitalize()
        year = int(match.group(2))
        month_map = {
            'Jan': 'January', 'Feb': 'February', 'Mar': 'March', 'Apr': 'April',
            'May': 'May', 'Jun': 'June', 'Jul': 'July', 'Aug': 'August',
            'Sep': 'September', 'Oct': 'October', 'Nov': 'November', 'Dec': 'December'
        }
        month_name = month_map.get(month_abbr, 'January')
        return datetime(year, month_order.index(month_name) + 1, 1)
    
    # If no date found, return None
    return None

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

def find_deposit_column(df):
    """Find the correct deposit column in the dataframe"""
    deposit_keywords = [
        'paid in sum', 'paidin', 'paid in', 'deposits', 'deposit', 
        'cash in', 'cashin', 'payment', 'paid_sum',
        'paid sum', 'paid-in', 'paid_in'
    ]
    
    # First pass: exact match
    for col in df.columns:
        col_lower = str(col).lower().strip()
        if col_lower in deposit_keywords:
            return col
    
    # Second pass: partial match
    for col in df.columns:
        col_lower = str(col).lower().strip()
        for keyword in deposit_keywords:
            if keyword in col_lower:
                return col
    
    # Third pass: look for any column with 'paid' or 'deposit'
    for col in df.columns:
        col_lower = str(col).lower().strip()
        if 'paid' in col_lower or 'deposit' in col_lower:
            return col
    
    return None

def find_ggr_column(df):
    """Find the correct GGR column in the dataframe"""
    ggr_keywords = [
        'gross win', 'grosswin', 'ggr', 'gross revenue', 
        'grossrevenue', 'gross', 'win', 'revenue', 'grosswin'
    ]
    
    # First pass: exact match
    for col in df.columns:
        col_lower = str(col).lower().strip()
        if col_lower in ggr_keywords:
            return col
    
    # Second pass: partial match
    for col in df.columns:
        col_lower = str(col).lower().strip()
        for keyword in ggr_keywords:
            if keyword in col_lower:
                return col
    
    # Third pass: look for 'gross' or 'win'
    for col in df.columns:
        col_lower = str(col).lower().strip()
        if 'gross' in col_lower or 'win' in col_lower:
            return col
    
    return None

def clean_game_name(val):
    """Clean game names to ensure they are string and not NaN"""
    if pd.isna(val):
        return "Unknown Game"
    if isinstance(val, (int, float)):
        return str(int(val)) if val == int(val) else str(val)
    return str(val).strip()

def enforce_schema(df):
    """Ensures exact matching to TARGET_COLS and repairs merged Excel cells."""
    if df is None or df.empty: return None
    df = df.loc[:, ~df.columns.duplicated()]
    
    # ACCURACY FIX: Forward-fill empty shop names caused by Excel merged/grouped cells
    if 'Shop' in df.columns:
        df['Shop'] = df['Shop'].astype(str).str.strip().replace({'nan': None, 'NaN': None, 'None': None, '': None})
        df['Shop'] = df['Shop'].ffill() # Copies the last known shop down to blank rows
        df['Shop'] = df['Shop'].replace({'Potch': 'Potchefstroom'})
    else:
        df['Shop'] = 'Unknown'

    # Clean Game column
    if 'Game' in df.columns:
        df['Game'] = df['Game'].apply(clean_game_name)
    else:
        df['Game'] = 'Unknown Game'

    # Fill missing columns
    for col in TARGET_COLS:
        if col not in df.columns:
            df[col] = 0.0 if col not in ['Shop', 'Game', 'Year', 'Month'] else "Unknown"
            
    # Clean numeric columns for math - using enhanced precision function
    num_cols = ['Deposits', 'Paid Out Sum', 'GGR', 'GW Margin %', 'Net Win', 'Net Win Margin']
    for col in num_cols:
        if col in df.columns:
            df[col] = df[col].apply(clean_currency_string)
        else:
            df[col] = 0.0

    return df[TARGET_COLS].copy()

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
    
    # Find GGR column
    gross_col = find_ggr_column(df)
    if gross_col:
        df['GGR'] = df[gross_col]
    else:
        df['GGR'] = 0.0
    
    # Find Deposits column
    deposit_col = find_deposit_column(df)
    if deposit_col:
        df['Deposits'] = df[deposit_col]
    else:
        df['Deposits'] = 0.0
    
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

# --- LOAD DATA FUNCTIONS ---
@st.cache_data
def load_data(uploaded_files):
    """Original load_data function - handles both CSV and Excel files"""
    all_data = []

    for file in uploaded_files:
        try:
            filename = file.name.lower()
            file_date = extract_date_from_filename(filename)
            
            # --- PATH 1: CSV FILES (Raw or Clean) ---
            if filename.endswith('.csv'):
                df = pd.read_csv(file)
                df.columns = [str(c).strip() for c in df.columns]
                
                # Find deposit column
                deposit_col = find_deposit_column(df)
                if deposit_col:
                    df = df.rename(columns={deposit_col: 'Deposits'})
                
                # Find GGR column
                ggr_col = find_ggr_column(df)
                if ggr_col:
                    df = df.rename(columns={ggr_col: 'GGR'})
                
                # If no deposit or GGR found, try alternative column names
                if 'Deposits' not in df.columns:
                    if 'Paid In Sum' in df.columns:
                        df = df.rename(columns={'Paid In Sum': 'Deposits'})
                    elif 'Cashier' in df.columns:
                        df['Deposits'] = 0.0
                    else:
                        df['Deposits'] = 0.0
                
                if 'GGR' not in df.columns:
                    if 'Gross Win' in df.columns:
                        df = df.rename(columns={'Gross Win': 'GGR'})
                    else:
                        df['GGR'] = 0.0
                
                # Assign date
                df['Date'] = file_date
                
                # Derive Dates from the filename date
                if not df.empty and file_date:
                    df['Year'] = str(file_date.year)
                    df['Month'] = file_date.strftime('%B')
                    df['MonthNum'] = file_date.month
                    
                df_clean = enforce_schema(df)
                if df_clean is not None: 
                    all_data.append(df_clean)

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

@st.cache_data
def load_historical_from_folder():
    """Load all Excel files from the historical_data folder"""
    all_data = []
    file_count = 0
    
    # Get all Excel files from historical_data folder
    excel_files = glob.glob(os.path.join(HISTORICAL_FOLDER, "*.xlsx")) + \
                  glob.glob(os.path.join(HISTORICAL_FOLDER, "*.xls"))
    
    if not excel_files:
        return pd.DataFrame(), 0
    
    for file_path in excel_files:
        try:
            filename = os.path.basename(file_path)
            
            # Read Excel file
            xl = pd.ExcelFile(file_path)
            for sheet in xl.sheet_names:
                sheet_lower = str(sheet).lower()
                if 'user' in sheet_lower and 'excl' not in sheet_lower:
                    continue
                
                df_raw = pd.read_excel(file_path, sheet_name=sheet, header=None)
                processed_df = process_excel_dataframe(df_raw, f"{filename} - {sheet}")
                
                df_clean = enforce_schema(processed_df)
                if df_clean is not None:
                    all_data.append(df_clean)
                    file_count += 1
                    
        except Exception as e:
            st.warning(f"⚠️ Could not load {file_path}: {str(e)}")
    
    if all_data:
        final_df = pd.concat(all_data, ignore_index=True)
        return final_df, file_count
    return pd.DataFrame(), 0

@st.cache_data
def load_uploaded_csvs_from_folder():
    """Load all CSV files from the uploads folder"""
    all_data = []
    file_count = 0
    
    # Get all CSV files from uploads folder
    csv_files = glob.glob(os.path.join(UPLOAD_FOLDER, "*.csv"))
    
    if not csv_files:
        return pd.DataFrame(), 0
    
    for file_path in csv_files:
        try:
            filename = os.path.basename(file_path)
            file_date = extract_date_from_filename(filename)
            
            if file_date is None:
                continue
            
            # Read CSV file
            df = pd.read_csv(file_path)
            df.columns = [str(c).strip() for c in df.columns]
            
            # Find and rename columns with precision
            deposit_col = find_deposit_column(df)
            if deposit_col:
                df = df.rename(columns={deposit_col: 'Deposits'})
            elif 'Paid In Sum' in df.columns:
                df = df.rename(columns={'Paid In Sum': 'Deposits'})
            elif 'Deposits' not in df.columns:
                df['Deposits'] = 0.0
            
            ggr_col = find_ggr_column(df)
            if ggr_col:
                df = df.rename(columns={ggr_col: 'GGR'})
            elif 'Gross Win' in df.columns:
                df = df.rename(columns={'Gross Win': 'GGR'})
            elif 'GGR' not in df.columns:
                df['GGR'] = 0.0
            
            # Find Shop column
            shop_col = None
            for col in df.columns:
                if str(col).lower().strip() in ['shop', 'branch', 'store', 'location']:
                    shop_col = col
                    break
            
            if shop_col:
                df = df.rename(columns={shop_col: 'Shop'})
            elif 'Shop' not in df.columns:
                df['Shop'] = 'Malvern'
            
            # Assign date from filename
            df['Date'] = file_date
            
            if not df.empty:
                df['Year'] = str(file_date.year)
                df['Month'] = file_date.strftime('%B')
                df['MonthNum'] = file_date.month
                
            df_clean = enforce_schema(df)
            if df_clean is not None:
                all_data.append(df_clean)
                file_count += 1
                    
        except Exception as e:
            st.warning(f"⚠️ Could not load {file_path}: {str(e)}")
    
    if all_data:
        final_df = pd.concat(all_data, ignore_index=True)
        return final_df, file_count
    return pd.DataFrame(), 0

def ensure_numeric(df, columns):
    """Ensure specified columns are numeric, converting if necessary"""
    for col in columns:
        if col in df.columns:
            # Try to convert to numeric, coercing errors to NaN
            df[col] = pd.to_numeric(df[col], errors='coerce')
            # Fill NaN with 0
            df[col] = df[col].fillna(0)
    return df

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

st.sidebar.header("📤 Upload New CSV")
uploaded_files = st.sidebar.file_uploader(
    "Upload CSV files", 
    accept_multiple_files=True, 
    type=["csv"],
    help="Upload CSV files to add to the dashboard. Files will be saved permanently."
)
st.sidebar.info("💡 Ensure CSV filenames include the month and year (e.g., 'May 2026.csv').")

# Save uploaded files to uploads folder
if uploaded_files:
    saved_files = []
    for file in uploaded_files:
        save_path = Path(UPLOAD_FOLDER) / file.name
        if save_path.exists():
            st.sidebar.warning(f"⚠️ {file.name} already exists. Skipping duplicate.")
        else:
            with open(save_path, 'wb') as f:
                f.write(file.getbuffer())
            saved_files.append(file.name)
    
    if saved_files:
        st.sidebar.success(f"✅ Saved {len(saved_files)} file(s)")
        st.rerun()

st.sidebar.divider()

# --- SIDEBAR: MANUAL ENTRY ---
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

# --- SIDEBAR: FILTERS ---
st.sidebar.divider()
st.sidebar.header("⏳ Filters")

# --- MAIN RUN LOGIC ---
# Load historical data from folder
historical_df, historical_file_count = load_historical_from_folder()

# Load uploaded CSV files from uploads folder
uploaded_df, uploaded_file_count = load_uploaded_csvs_from_folder()

# Combine all data sources
df_parts = []

if not historical_df.empty:
    df_parts.append(historical_df)

if not uploaded_df.empty:
    df_parts.append(uploaded_df)

if not st.session_state.manual_2026_data.empty:
    df_parts.append(st.session_state.manual_2026_data)

if df_parts:
    df = pd.concat(df_parts, ignore_index=True)
    
    # Ensure numeric columns are properly typed
    numeric_cols = ['GGR', 'Deposits', 'Paid Out Sum', 'GW Margin %', 'Net Win', 'Net Win Margin']
    df = ensure_numeric(df, numeric_cols)
    
    # Ensure Game column is clean and has no NaN
    if 'Game' in df.columns:
        df['Game'] = df['Game'].fillna('Unknown Game').astype(str)
    
    if not df.empty:
        available_months = sorted(df['Month'].unique(), key=lambda m: month_order.index(m) if m in month_order else 0)
        available_years = sorted(df['Year'].unique())
        
        selected_year = st.sidebar.selectbox("Select Year:", ["All Time"] + available_years)
        selected_month = st.sidebar.selectbox("Select Month:", ["All Months"] + available_months) if selected_year != "All Time" else "All Months"

        nav_options = ["All Branches Dashboard"] + BRANCHES
        selected_view = st.sidebar.radio("Select Branch Analysis:", nav_options)
        
        df_filtered = df if selected_view == "All Branches Dashboard" else df[df['Shop'] == selected_view]
        if selected_year != "All Time": df_filtered = df_filtered[df_filtered['Year'] == selected_year]
        if selected_month != "All Months": df_filtered = df_filtered[df_filtered['Month'] == selected_month]
        
        # Ensure filtered data is numeric and Game is clean
        df_filtered = ensure_numeric(df_filtered, ['GGR', 'Deposits'])
        if 'Game' in df_filtered.columns:
            df_filtered['Game'] = df_filtered['Game'].fillna('Unknown Game').astype(str)
        
        # Calculate totals with precision
        if not df_filtered.empty and len(df_filtered) > 0:
            total_ggr = df_filtered['GGR'].sum()
            total_deposits = df_filtered['Deposits'].sum()
            # Get top game - safely
            try:
                game_ggr = df_filtered.groupby('Game')['GGR'].sum()
                top_game = game_ggr.idxmax() if not game_ggr.empty else "N/A"
            except Exception:
                top_game = "N/A"
        else:
            total_ggr = 0.0
            total_deposits = 0.0
            top_game = "N/A"
        
        yoy = 0.0
        if selected_year == "All Time" and not df_filtered.empty:
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
        if not chart_data.empty:
            fig = px.bar(chart_data, x='Month', y='GGR', color='Year', barmode='stack', category_orders={"Month": month_order}, color_discrete_map=YEAR_COLORS)
            fig.update_layout(xaxis_title=None, yaxis_title="Gross Gaming Revenue (ZAR)")
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.warning("No data available for GGR chart")
        
        st.subheader("Deposits (Paid In): Multi-Year Stacked Comparison")
        chart_data_deposits = df_filtered.groupby(['MonthNum', 'Month', 'Year'])['Deposits'].sum().reset_index().sort_values('MonthNum')
        if not chart_data_deposits.empty:
            fig_deposits = px.bar(chart_data_deposits, x='Month', y='Deposits', color='Year', barmode='stack', category_orders={"Month": month_order}, color_discrete_map=DEPOSIT_YEAR_COLORS)
            fig_deposits.update_layout(xaxis_title=None, yaxis_title="Deposits / Paid In (ZAR)")
            st.plotly_chart(fig_deposits, use_container_width=True)
        else:
            st.warning("No data available for Deposits chart")
            
        st.subheader(f"Game Revenue Analysis")
        game_dist = df_filtered.groupby('Game')['GGR'].sum().reset_index()
        if not game_dist.empty and len(game_dist) > 0:
            fig_pie = px.pie(game_dist, values='GGR', names='Game', hole=0.4, color_discrete_sequence=GAME_PALETTE)
            st.plotly_chart(fig_pie, use_container_width=True)
        else:
            st.warning("No game data available")

        st.divider()
        st.subheader("Raw Data Summary (Cleaned)")
        st.dataframe(df_filtered[['Year', 'Month', 'Shop', 'Game', 'Deposits', 'Paid Out Sum', 'GGR', 'GW Margin %', 'Net Win', 'Net Win Margin']].head(100), use_container_width=True)
        
        with st.expander("📊 View Strategic Analysis & Solutions", expanded=True):
            st.markdown(generate_strategic_analysis(selected_view, yoy, total_ggr, total_deposits, top_game))
        
    else:
        st.warning("No relevant data found. The file may be empty or invalid.")
else:
    st.info("📂 Please place your Excel files in the 'historical_data' folder or upload CSV files to begin.")