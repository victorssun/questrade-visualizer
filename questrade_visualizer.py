"""
Dashboard to summarily visualize questrade data
- execute commandline iva `streamlit run <script>.py
- use with st.echo() and st.experimental_show() for debugging
"""
import sqlite3
import streamlit as st
import altair as alt
import os
import pandas as pd
import datetime as dt
import plotly.express as px


def fetch_from_db(sql_statement):
    cursor.execute(sql_statement)
    return cursor.fetchall()


def calculate_metrics(date):
    """ calculate book_value, init_value, net_profit given a date """
    metrics = dict()
    metrics['book_value'] = fetch_from_db("SELECT sum(value) FROM positions JOIN dates ON positions.date_id = dates.date_id "
                                          "WHERE dates.date <= '{}' GROUP BY positions.date_id "
                                          "ORDER BY positions.date_id DESC".format(date))[0][0]
    metrics['init_value'] = fetch_from_db("SELECT sum(deposit) FROM transfers JOIN dates ON transfers.date_id = dates.date_id "
                                          "WHERE dates.date <= '{}'".format(date))[0][0]
    metrics['net_profit'] = metrics['book_value'] - metrics['init_value']
    return metrics


def calculate_days_diff(days_input):
    days_diff = (date_dt - dt.datetime.strptime('2018-05-02', '%Y-%m-%d').date())
    if days_diff < pd.Timedelta(days=days_input):
        return days_diff
    return pd.Timedelta(days=days_input)


### MAIN ###
investment_directory = ''

# set up
path_db = '{}questrade.db'.format(investment_directory)
conn = sqlite3.connect(path_db)
cursor = conn.cursor()

### sidebar ###
st.set_page_config('Investment Portfolio Visualization', 'random', initial_sidebar_state='auto',
                   menu_items={"Get help": None, "Report a bug": None, "About": None})

st.sidebar.write('<br>', unsafe_allow_html=True)
st.sidebar.write('#### Select')

# account
accounts = fetch_from_db("SELECT account_id, number, name, type FROM accounts")

account_name = st.sidebar.selectbox('Account: ', [acc[2] for acc in accounts])
account_id = accounts[0][0]
for acc in accounts:
    if account_name == acc[2]:
        account_id = acc[0]
        break

# date
date_dt = st.sidebar.date_input("Date: ", value=pd.to_datetime('today'),
                       min_value=pd.to_datetime('2018-05-02'), max_value=pd.to_datetime('today'))
date = date_dt.strftime('%Y-%m-%d')
st.sidebar.write("<hr>Dashboard visualization for historical, portfolio investments. "
                 "Made by <a style='color:LightSkyBlue; text-decoration: none;' href=https://www.victorssun.com/>Victor Sun</a>.", unsafe_allow_html=True)


### main page ####
st.markdown("""<style>footer {visibility: hidden;}</style>""", unsafe_allow_html=True)
st.write('# Investment Portfolio Visualizer')
st.write('## {} - {} '.format(account_name, pd.to_datetime(date).strftime('%b %d, %Y')))

# db to df
positions = fetch_from_db("SELECT dates.date, symbols.symbol, positions.value FROM positions \
    JOIN dates ON positions.date_id = dates.date_id \
    JOIN symbols ON positions.symbol_id = symbols.symbol_id \
    WHERE positions.account_id = {} \
    AND dates.date <= '{}' \
    ORDER BY positions.date_id".format(account_id, date))
positions = pd.DataFrame(positions, columns=['date', 'symbol', 'value'])

trades = fetch_from_db("SELECT dates.date, symbols.symbol, trades.quantity, trades.value FROM trades \
    JOIN dates ON trades.date_id = dates.date_id \
    JOIN symbols ON trades.symbol_id = symbols.symbol_id \
    WHERE trades.account_id = {} \
    AND dates.date <= '{}' \
    ORDER BY trades.date_id".format(account_id, date))
trades = pd.DataFrame(trades, columns=['date', 'symbol', 'quantity', 'value'])

transfers = fetch_from_db("SELECT dates.date, transfers.deposit FROM transfers \
    JOIN dates ON transfers.date_id = dates.date_id \
    WHERE transfers.account_id = {} \
    AND dates.date <= '{}' \
    ORDER BY transfers.date_id".format(account_id, date))
transfers = pd.DataFrame(transfers, columns=['date', 'deposit'])
transfers['date'] = pd.to_datetime(transfers['date'], format='%Y-%m-%d')
transfers['cum_deposit'] = transfers['deposit'].cumsum()

balances = fetch_from_db("SELECT dates.date, sum(value) FROM positions "
                         "JOIN dates ON positions.date_id = dates.date_id "
                         "WHERE dates.date <= '{}' GROUP BY positions.date_id "
                         "ORDER BY positions.date_id".format(date))
balances = pd.DataFrame(balances, columns=['date', 'book_value'])
balances['date'] = pd.to_datetime(balances['date'], format='%Y-%m-%d')
balances = balances.merge(transfers[['date', 'cum_deposit']], on='date', how='outer')
balances.sort_values('date', inplace=True)
balances['cum_deposit'].fillna(method='ffill', inplace=True)
balances['net_profit'] = balances['book_value'] - balances['cum_deposit']

# metrics
metrics = dict()
metrics['current'] = calculate_metrics(date)
metrics['past_year'] = calculate_metrics(date_dt - calculate_days_diff(365))
metrics['past_month'] = calculate_metrics(date_dt - calculate_days_diff(30))

col1, col2 = st.columns(2)
col1.metric('Account balance', '{:.2f}'.format(metrics['current']['book_value']), delta='{:.2f} (past 1 year)'.format(
    metrics['current']['net_profit'] - metrics['past_year']['net_profit']))
col2.metric('Net profit', '{:.2f}'.format(metrics['current']['net_profit']), delta='{:.2f} (past 1 month)'.format(
    metrics['current']['net_profit'] - metrics['past_month']['net_profit']))

st.write('### Current Portfolio')
recent_positions = positions[positions['date'] == max(positions['date'])][['symbol', 'value']]
fig = px.pie(recent_positions, values='value', names='symbol', color_discrete_sequence=px.colors.sequential.RdBu)
fig.update_traces(textinfo='value')
st.plotly_chart(fig, use_container_width=True)

st.write('### Profit by Position')
past_positions = fetch_from_db("SELECT symbols.symbol, value FROM "
                           "(SELECT trades.symbol_id AS symb, sum(value) AS value FROM trades "
                           "JOIN dates ON trades.date_id = dates.date_id "
                           "WHERE dates.date <= '{}' "
                           "GROUP BY symbol_id )"
                           "JOIN symbols ON symb = symbols.symbol_id "
                           .format(date))
past_positions = pd.DataFrame(past_positions, columns=['symbol', 'value'])
positions_profits = pd.concat([past_positions, recent_positions]).groupby('symbol').sum().sort_values('value', ascending=False)
positions_profits = positions_profits.drop(index='cash')
positions_profits = positions_profits.reset_index(level=0)
fig = alt.Chart(positions_profits).mark_bar().encode(x=alt.X('symbol', sort='-y', title='Position'), y=alt.Y('value', title='Profit'),
                                                     tooltip=['symbol', 'value']).properties(height=400)
st.altair_chart(fig, use_container_width=True)

# net profit graph
st.write('### Profit by Date')
balances = balances.dropna()
fig = alt.Chart(balances).mark_line().encode(x=alt.X('date', title='Date'), y=alt.Y('net_profit', title='Profit'),
                                                     tooltip=['date', 'net_profit']).properties(height=400)
st.altair_chart(fig, use_container_width=True)
