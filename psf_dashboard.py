from flask import Flask, send_from_directory
import dash
from dash import html, dcc, Input, Output, State
import pandas as pd
import plotly.express as px
import base64
import io

# Flask server aanmaken en static folder serveren
server = Flask(__name__)

@server.route('/static/<path:path>')
def send_static(path):
    return send_from_directory('static', path)

# Dash app aanmaken met de Flask server
app = dash.Dash(__name__, server=server)

global_df = pd.DataFrame()

app.layout = html.Div([
    html.Img(src='/static/logo.png', style={"maxWidth": "100px"}),
    html.H1(" PSF Dashboard - Volvo", style={"color": "#0078D4"}),

    dcc.Upload(
        id='upload-data',
        children=html.Div(['📂 Sleep je Excel bestand hierheen of ', html.A('klik om te uploaden')]),
        style={
            'width': '100%',
            'height': '60px',
            'lineHeight': '60px',
            'borderWidth': '1px',
            'borderStyle': 'dashed',
            'borderRadius': '5px',
            'textAlign': 'center',
            'margin': '10px 0'
        },
        multiple=False
    ),

    html.Div(id='file-info'),

    html.Div([
        html.Label('Filter op TimerName:'),
        dcc.Dropdown(id='timer-dropdown', placeholder='Selecteer TimerName'),

        html.Label('Filter op NPTName:', style={"marginTop": 10}),
        dcc.Dropdown(id='npt-dropdown', placeholder='Selecteer NPTName'),

        html.Label('🔘 Toon alleen NOK:', style={"marginTop": 10}),
        dcc.Checklist(
            id='nok-only',
            options=[{'label': 'Toon alleen NOK', 'value': 'nok'}],
            value=[]
        ),

        html.Label('📊 Aantal lassen per spot (min & max):', style={"marginTop": 10}),
        html.Div([
            dcc.Input(
                id='min-welds-input',
                type='number',
                placeholder='Min',
                value=0,
                style={'width': '100px', 'marginRight': '10px'}
            ),
            dcc.Input(
                id='max-welds-input',
                type='number',
                placeholder='Max',
                value=9999,
                style={'width': '100px'}
            )
        ], style={'display': 'flex', 'alignItems': 'center', 'gap': '10px'}),

        html.Button("🔍 Toon spots klaar voor tol. band aanpassing (>= 20 welds)", id="sigma-button", n_clicks=0,
                    style={"marginTop": 20, "backgroundColor": "#ffcc00", "fontWeight": "bold"})
    ], style={'marginBottom': 30}),

    dcc.Graph(id='bar-chart')
])


@app.callback(
    Output('file-info', 'children'),
    Output('timer-dropdown', 'options'),
    Output('npt-dropdown', 'options'),
    Output('timer-dropdown', 'value'),
    Output('npt-dropdown', 'value'),
    Input('upload-data', 'contents'),
    State('upload-data', 'filename')
)
def load_file(contents, filename):
    global global_df

    if contents is None:
        return dash.no_update, [], [], None, None

    content_type, content_string = contents.split(',')
    decoded = base64.b64decode(content_string)

    try:
        df = pd.read_excel(io.BytesIO(decoded), sheet_name="Query1")
        df.columns = df.columns.astype(str).str.strip().str.replace(r"\s+", " ", regex=True).str.replace('\n', '', regex=True)

        df['cnt_welds_lastShift'] = pd.to_numeric(df['cnt_welds_lastShift'], errors='coerce')
        df['AVG_PSF_last_shift'] = pd.to_numeric(df['AVG_PSF_last_shift'], errors='coerce')
        df['STDEV_stabilisationFactor'] = pd.to_numeric(df['STDEV_stabilisationFactor'], errors='coerce')

        global_df = df.copy()

        timers = [{'label': t, 'value': t} for t in sorted(df['TimerName'].dropna().unique())]
        npts = [{'label': n, 'value': n} for n in sorted(df['NPTName'].dropna().unique())]

        return html.Div(f"✅ Bestand geladen: {filename}"), timers, npts, None, None

    except Exception as e:
        return html.Div(f"❌ Fout bij laden: {str(e)}"), [], [], None, None


@app.callback(
    Output('bar-chart', 'figure'),
    Input('timer-dropdown', 'value'),
    Input('npt-dropdown', 'value'),
    Input('nok-only', 'value'),
    Input('min-welds-input', 'value'),
    Input('max-welds-input', 'value'),
    Input('sigma-button', 'n_clicks')
)
def update_chart(selected_timer, selected_npt, nok_only, min_welds, max_welds, sigma_click):
    df = global_df.copy()

    if df.empty or 'Tol=OK' not in df.columns:
        return px.bar(title="⚠️ Geen geldige data geladen")

    if selected_timer:
        df = df[df['TimerName'] == selected_timer]
    if selected_npt:
        df = df[df['NPTName'] == selected_npt]

    if 'nok' in nok_only:
        df = df[df['Tol=OK'].str.lower() == 'nok']

    df['SpotName'] = df['SpotName'].astype(str)

    grouped = df.groupby(['SpotName', 'Tol=OK']).agg(
        count=('cnt_welds_lastShift', 'sum'),
        avg_psf=('AVG_PSF_last_shift', 'mean'),
        stdev_psf=('STDEV_stabilisationFactor', 'mean')
    ).reset_index()

    # Filter op aantal lassen tussen min en max
    min_val = min_welds if min_welds is not None else 0
    max_val = max_welds if max_welds is not None else float('inf')
    grouped = grouped[(grouped['count'] >= min_val) & (grouped['count'] <= max_val)]

    trigger = dash.callback_context.triggered[0]['prop_id'].split('.')[0]
    if trigger == 'sigma-button':
        grouped = grouped[(grouped['stdev_psf'] > 2) & (grouped['count'] >= 20)]

    fig = px.bar(
        grouped,
        x='SpotName',
        y='count',
        color='Tol=OK',
        barmode='stack',
        text='count',
        title='Aantal lassen per SpotName (OK/NOK)',
        labels={'Tol=OK': 'Kwaliteit', 'count': 'Aantal lassen'},
        category_orders={'Tol=OK': ['ok', 'nok']},
        color_discrete_map={'ok': 'green', 'nok': 'red'},
        hover_data={
            'SpotName': True,
            'count': True,
            'avg_psf': ':.2f',
            'stdev_psf': ':.2f',
            'Tol=OK': True
        }
    )

    fig.update_traces(
        textposition='outside',
        textfont_size=14,
        cliponaxis=False
    )

    fig.update_layout(
        xaxis_tickangle=45,
        xaxis_tickfont=dict(size=11),
        yaxis_title='Aantal lassen',
        height=900,
        width=1400,
        margin=dict(l=40, r=40, t=60, b=200),
        legend_title_text='Kwaliteit'
    )

    return fig


if __name__ == '__main__':
    app.run_server(debug=True)

