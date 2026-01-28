from flask import Flask, render_template, jsonify
import pandas as pd
from datetime import datetime, timedelta
import os

app = Flask(__name__)

def load_data():
    """Load and process the rewards CSV file"""
    csv_path = 'rewards.csv'
    
    if not os.path.exists(csv_path):
        return None
    
    # Read CSV normally (header is the first row)
    df = pd.read_csv(csv_path)
    
    # Rename licenseId to alias for consistency in the code
    if 'licenseId' in df.columns:
        df = df.rename(columns={'licenseId': 'alias'})
    
    df['date'] = pd.to_datetime(df['date'])
    df['amount_usd'] = df['amount_usd'].astype(float)
    
    return df

def generate_monthly_table(df):
    """Generate monthly financial table from rewards data"""
    if df is None or df.empty:
        return None, None
    
    # Group rewards by month
    df['year_month'] = df['date'].dt.to_period('M')
    monthly_rewards = df.groupby('year_month')['amount_usd'].sum().sort_index()
    
    # Get all months from data
    months = monthly_rewards.index.tolist()
    
    # Initialize table data
    table_data = []
    saldo_inicial = -5000  # Starting balance
    
    for i, month in enumerate(months):
        # Convert period to datetime for formatting
        month_date = month.to_timestamp()
        next_month_date = (month + 1).to_timestamp()
        
        # Format dates as dd/mm/yy
        mes_ref = month_date.strftime('%d/%m/%y') if i > 0 else '-'
        mes = next_month_date.strftime('%d/%m/%y')
        
        # Financial calculations
        gastos = 0  # Currently 0
        bruto = monthly_rewards[month]
        liquido = bruto + gastos  # bruto - gastos (but gastos is 0)
        saldo_final = saldo_inicial + liquido
        
        table_data.append({
            'Mês Ref.': mes_ref,
            'Mês': mes,
            'Saldo inicial': saldo_inicial,
            'Gastos / mês': gastos,
            'Bruto / mês': bruto,
            'Líquido / mês': liquido,
            'Saldo final': saldo_final
        })
        
        # Next month's starting balance is this month's final balance
        saldo_inicial = saldo_final
    
    # Create DataFrame
    monthly_df = pd.DataFrame(table_data)
    
    # Calculate SUM row
    sum_row = {
        'Mês Ref.': 'TOTAL',
        'Mês': '',
        'Saldo inicial': '',
        'Gastos / mês': monthly_df['Gastos / mês'].sum(),
        'Bruto / mês': monthly_df['Bruto / mês'].sum(),
        'Líquido / mês': monthly_df['Líquido / mês'].sum(),
        'Saldo final': f"{((monthly_df.iloc[-1]['Saldo final'] + 5000) / 5000 * 100):.1f}%" if len(monthly_df) > 0 else '%'
    }
    
    return monthly_df, sum_row

def calculate_stats(df):
    """Calculate all relevant statistics"""
    if df is None or df.empty:
        return None
    
    stats = {}
    
    # Overall stats
    stats['total_earned'] = df['amount_usd'].sum()
    stats['total_entries'] = len(df)
    stats['phone_count'] = df['alias'].nunique()
    stats['date_range'] = {
        'start': df['date'].min().strftime('%Y-%m-%d'),
        'end': df['date'].max().strftime('%Y-%m-%d'),
        'days': (df['date'].max() - df['date'].min()).days + 1
    }
    
    # Per phone stats
    phone_stats = df.groupby('alias').agg({
        'amount_usd': ['sum', 'mean', 'count', 'std']
    }).round(4)
    phone_stats.columns = ['total', 'avg_per_entry', 'entries', 'std_dev']
    stats['by_phone'] = phone_stats.to_dict('index')
    
    # Daily stats
    daily = df.groupby('date')['amount_usd'].sum().reset_index()
    stats['avg_per_day'] = daily['amount_usd'].mean()
    stats['best_day'] = {
        'date': daily.loc[daily['amount_usd'].idxmax(), 'date'].strftime('%Y-%m-%d'),
        'amount': daily['amount_usd'].max()
    }
    stats['worst_day'] = {
        'date': daily.loc[daily['amount_usd'].idxmin(), 'date'].strftime('%Y-%m-%d'),
        'amount': daily['amount_usd'].min()
    }
    
    # Recent trends (last 7, 14, 30 days)
    today = df['date'].max()
    for days in [7, 14, 30]:
        cutoff = today - timedelta(days=days-1)
        recent = df[df['date'] >= cutoff]
        if not recent.empty:
            stats[f'last_{days}_days'] = {
                'total': recent['amount_usd'].sum(),
                'avg_per_day': recent.groupby('date')['amount_usd'].sum().mean(),
                'entries': len(recent)
            }
    
    # Weekly averages
    df['week'] = df['date'].dt.isocalendar().week
    df['year'] = df['date'].dt.year
    weekly = df.groupby(['year', 'week'])['amount_usd'].sum()
    stats['avg_per_week'] = weekly.mean()
    
    # Calculate week-over-week change
    if len(weekly) >= 2:
        current_week = weekly.iloc[-1]
        previous_week = weekly.iloc[-2]
        stats['weekly_change'] = {
            'amount': current_week - previous_week,
            'percent': ((current_week - previous_week) / previous_week * 100) if previous_week > 0 else 0
        }
    
    # Monthly stats
    df['month'] = df['date'].dt.to_period('M')
    monthly = df.groupby('month')['amount_usd'].sum()
    stats['avg_per_month'] = monthly.mean()
    stats['total_months'] = len(monthly)
    stats['monthly_breakdown'] = {
        str(k): round(v, 2) for k, v in monthly.to_dict().items()
    }
    
    # Calculate month-over-month change
    if len(monthly) >= 2:
        current_month = monthly.iloc[-1]
        previous_month = monthly.iloc[-2]
        stats['monthly_change'] = {
            'amount': current_month - previous_month,
            'percent': ((current_month - previous_month) / previous_month * 100) if previous_month > 0 else 0
        }
    
    # Daily change (today vs yesterday or latest vs second-latest)
    daily = df.groupby('date')['amount_usd'].sum().reset_index()
    if len(daily) >= 2:
        latest_day = daily.iloc[-1]['amount_usd']
        previous_day = daily.iloc[-2]['amount_usd']
        stats['daily_change'] = {
            'amount': latest_day - previous_day,
            'percent': ((latest_day - previous_day) / previous_day * 100) if previous_day > 0 else 0
        }
    
    # Growth analysis - compare first half vs second half of all data
    mid_point = df['date'].min() + (df['date'].max() - df['date'].min()) / 2
    first_half = df[df['date'] < mid_point]['amount_usd'].sum()
    second_half = df[df['date'] >= mid_point]['amount_usd'].sum()
    
    if first_half > 0:
        growth_rate = ((second_half - first_half) / first_half) * 100
        stats['growth_rate'] = round(growth_rate, 2)
    
    # Daily timeline for chart
    daily_timeline = df.groupby('date')['amount_usd'].sum().reset_index()
    stats['daily_timeline'] = {
        'dates': daily_timeline['date'].dt.strftime('%Y-%m-%d').tolist(),
        'amounts': daily_timeline['amount_usd'].round(4).tolist()
    }
    
    # Per phone timeline
    phone_timeline = df.groupby(['date', 'alias'])['amount_usd'].sum().reset_index()
    stats['phone_timeline'] = {}
    for phone in df['alias'].unique():
        phone_data = phone_timeline[phone_timeline['alias'] == phone]
        stats['phone_timeline'][phone] = {
            'dates': phone_data['date'].dt.strftime('%Y-%m-%d').tolist(),
            'amounts': phone_data['amount_usd'].round(4).tolist()
        }
    
    # Round numeric values
    for key in ['total_earned', 'avg_per_day', 'avg_per_week', 'avg_per_month']:
        if key in stats:
            stats[key] = round(stats[key], 4)
    
    return stats

@app.route('/')
def index():
    """Main dashboard page"""
    df = load_data()
    
    if df is None:
        return "Erro: rewards.csv não encontrado. Por favor, coloque-o no mesmo diretório que app.py", 404
    
    stats = calculate_stats(df)
    
    # Generate monthly table from rewards data
    monthly_df, monthly_sum = generate_monthly_table(df)
    
    return render_template('dashboard.html', stats=stats, monthly_df=monthly_df, monthly_sum=monthly_sum)

@app.route('/api/stats')
def api_stats():
    """API endpoint for stats (useful for refreshing without reload)"""
    df = load_data()
    if df is None:
        return jsonify({'error': 'Data file not found'}), 404
    
    stats = calculate_stats(df)
    return jsonify(stats)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5010, debug=True)
