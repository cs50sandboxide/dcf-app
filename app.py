from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
import pandas as pd
import numpy as np
import json
import os

app = Flask(__name__, template_folder='templates', static_folder='static')
CORS(app)

# Load data
try:
    data = pd.read_csv('Data.csv', thousands=',')
except Exception as e:
    print(f"Error loading Data.csv: {e}")
    data = None

def read_stockdata(stock_name):
    Revenue_name = stock_name+'_Revenue'
    EBIT_name = stock_name+'_EBIT'
    DA_name = stock_name+'_DA'
    CapEx_name = stock_name+'_CapEx'
    Assets_name = stock_name+'_Assets'
    Liabilities_name = stock_name+'_Liabilities'
    Cash_name = stock_name+'_Cash'
    Debt_name = stock_name+'_Debt'
    Shares_name = stock_name+'_Shares'

    try:
        Reported_Revenue = data[Revenue_name]
        Reported_EBIT = data[EBIT_name]
        Reported_DA = data[DA_name]
        Reported_CapEx = data[CapEx_name]
        Reported_Assets = data[Assets_name]
        Reported_Liabilities = data[Liabilities_name]
        Reported_Cash = data[Cash_name]
        Reported_Debt = data[Debt_name]
        Reported_Shares = data[Shares_name]

        return {
            'revenue': Reported_Revenue,
            'ebit': Reported_EBIT,
            'da': Reported_DA,
            'capex': Reported_CapEx,
            'assets': Reported_Assets,
            'liabilities': Reported_Liabilities,
            'cash': Reported_Cash,
            'debt': Reported_Debt,
            'shares': Reported_Shares
        }
    except KeyError:
        return None

def calculate_growth(data_series):
    growth_rates = []
    i = 0
    while i < len(data_series) - 1 and pd.notna(data_series[i+1]):
        growth = (data_series[i+1] - data_series[i]) / data_series[i]
        growth_rates.append(growth)
        i = i + 1
    if len(growth_rates) == 0:
        return 0
    average_growth = sum(growth_rates) / len(growth_rates)
    return average_growth

def calculate_percentage(data_series, base_series):
    percentages = []
    i = 0
    while i < len(data_series) and pd.notna(data_series[i]) and pd.notna(base_series[i]):
        if base_series[i] != 0:
            percentage = data_series[i] / base_series[i]
            percentages.append(percentage)
        i = i + 1
    if len(percentages) == 0:
        return 0
    average_percentage = sum(percentages) / len(percentages)
    return average_percentage

def projecting_values(last_value, growth_rate, years):
    projections = []
    for year in range(1, years + 1):
        projected_value = last_value * ((1 + growth_rate) ** year)
        projections.append(float(projected_value))
    return projections

def calculate_nopat(ebit, tax_rate):
    nopat = ebit * (1 - tax_rate)
    return nopat

def calculate_nwc(assets, liabilities, cash, debt):
    nwc = assets - liabilities - cash + debt
    return nwc

def calculate_dcf(stock, tax_rate=0.27, wacc=0.069, terminal_growth=0.025, projection_years=5):
    if data is None:
        return {'error': 'Data file not loaded'}
    
    stock_data = read_stockdata(stock)
    
    if stock_data is None:
        return {'error': f'Stock ticker {stock} not found in database'}
    
    # Extract data
    Revenue = stock_data['revenue']
    EBIT = stock_data['ebit']
    DA = stock_data['da']
    CapEx = stock_data['capex']
    Assets = stock_data['assets']
    Liabilities = stock_data['liabilities']
    Cash = stock_data['cash']
    Debt = stock_data['debt']
    Shares = stock_data['shares']
    
    # Calculate growth rates
    revenue_growth = calculate_growth(Revenue)
    ebit_growth = calculate_growth(EBIT)
    da_growth = calculate_growth(DA)
    capex_growth = calculate_growth(CapEx)
    
    # Project future values
    last_revenue = Revenue.dropna().values[-1]
    last_ebit = EBIT.dropna().values[-1]
    last_da = DA.dropna().values[-1]
    last_capex = CapEx.dropna().values[-1]
    
    stock_revenue_projections = projecting_values(last_revenue, revenue_growth, projection_years)
    stock_ebit_projections = projecting_values(last_ebit, ebit_growth, projection_years)
    stock_da_projections = projecting_values(last_da, da_growth, projection_years)
    stock_capex_projections = projecting_values(last_capex, capex_growth, projection_years)
    
    # Calculate NOPAT
    NOPAT_projections = [calculate_nopat(ebit, tax_rate) for ebit in stock_ebit_projections]
    
    # Calculate NWC
    Avg_NWC_Percent = calculate_percentage(
        calculate_nwc(Assets, Liabilities, Cash, Debt),
        Revenue
    )
    
    NWC_Projections = []
    for i in range(projection_years):
        NWC_Projections.append(stock_revenue_projections[i] * (Avg_NWC_Percent))
    
    # Change in NWC
    last_nwc = calculate_nwc(
        Assets.dropna().values[-1],
        Liabilities.dropna().values[-1],
        Cash.dropna().values[-1],
        Debt.dropna().values[-1]
    )
    
    Change_in_NWC = [NWC_Projections[0] - last_nwc]
    for i in range(1, projection_years):
        Change_in_NWC.append(NWC_Projections[i] - NWC_Projections[i-1])
    
    # Calculate FCFF
    FCFF_Projections = []
    for i in range(projection_years):
        fcff = NOPAT_projections[i] + stock_da_projections[i] - stock_capex_projections[i] - Change_in_NWC[i]
        FCFF_Projections.append(float(fcff))
    
    # Discount FCFF to present value
    PV_FCFF = []
    for i in range(projection_years):
        pv_fcff = FCFF_Projections[i] / ((1 + wacc) ** (i + 1))
        PV_FCFF.append(float(pv_fcff))
    
    # Calculate terminal value
    FCFF_year_after_projection = FCFF_Projections[-1] * (1 + terminal_growth)
    Terminal_Value = FCFF_year_after_projection / (wacc - terminal_growth)
    PV_Terminal_Value = Terminal_Value / ((1 + wacc) ** projection_years)
    
    # Calculate valuations
    Enterprise_Value = sum(PV_FCFF) + PV_Terminal_Value
    Equity_Value = Enterprise_Value - Debt.dropna().values[-1] + Cash.dropna().values[-1]
    Intrinsic_Value = Equity_Value / Shares.dropna().values[-1]
    
    return {
        'stock': stock,
        'intrinsic_value': float(Intrinsic_Value),
        'enterprise_value': float(Enterprise_Value),
        'equity_value': float(Equity_Value),
        'pv_fcff': PV_FCFF,
        'pv_terminal_value': float(PV_Terminal_Value),
        'fcff_projections': FCFF_Projections,
        'revenue_projections': stock_revenue_projections,
        'growth_rates': {
            'revenue': revenue_growth * 100,
            'ebit': ebit_growth * 100,
            'da': da_growth * 100,
            'capex': capex_growth * 100
        },
        'assumptions': {
            'tax_rate': tax_rate * 100,
            'wacc': wacc * 100,
            'terminal_growth': terminal_growth * 100
        }
    }

@app.route('/')
def index():
    try:
        return render_template('index.html')
    except Exception as e:
        return f"Error rendering template: {e}", 500

@app.route('/api/stocks', methods=['GET'])
def get_available_stocks():
    if data is None:
        return jsonify({'error': 'Data not available'}), 500
    
    # Get all stock tickers from the data
    stocks = set()
    for col in data.columns:
        if '_Revenue' in col:
            ticker = col.replace('_Revenue', '')
            stocks.add(ticker)
    return jsonify(sorted(list(stocks)))

@app.route('/api/calculate', methods=['POST'])
def calculate():
    try:
        request_data = request.json
        stock = request_data.get('stock', '').upper()
        tax_rate = request_data.get('tax_rate', 27) / 100
        wacc = request_data.get('wacc', 6.9) / 100
        terminal_growth = request_data.get('terminal_growth', 2.5) / 100
        
        result = calculate_dcf(stock, tax_rate, wacc, terminal_growth)
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=False, host='0.0.0.0', port=port)
