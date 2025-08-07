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
app.title = "PSF TOOL V216"

app.index_string = '''
<!DOCTYPE html>
<html>
    <head>
        {%metas%}
        <title>{%title%}</title>
        <link rel="icon" href="/static/volvo.ico" type="image/x-icon" />
        {%favicon%}
        {%css%}
    </head>
    <body>
        {%app_entry%}
        <footer>
            {%config%}
            {%scripts%}
            {%renderer%}
        </footer>
    </body>
</html>
'''




global_df = pd.DataFrame()

app.layout = html.Div([
    html.Div([
        html.Img(src='/static/logo.png', style={"maxWidth": "150px", "display": "block", "margin": "0 auto"}),
        html.H1(" PSF TOOL V216 ", style={"color": "black", "textAlign": "center"}),
    ]),

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
            'margin': '10px 0',
            'fontWeight': 'bold',
            'color': 'blue',
        },
        multiple=False
    ),

    html.Div(id='file-info'),

    html.Div([
        html.Label('Filter op TimerName:', style={"fontWeight": "bold"}),
        dcc.Dropdown(id='timer-dropdown', placeholder='Selecteer TimerName'),

        html.Label('Filter op NPTName:', style={"marginTop": 10, "fontWeight": "bold"}),
        dcc.Dropdown(id='npt-dropdown', placeholder='Selecteer NPTName'),

        dcc.Checklist(
            id='nok-only',
            options=[{'label': ' ❌ Toon alleen NOK SPOTS ❌ ', 'value': 'nok'}],
            value=[]
        ),

        dcc.Checklist(
            id='adaptief-checkbox',
            options=[{'label': '✅ SPOTS IN ADAPTIEF ✅', 'value': 'adaptief'}],
            value=['adaptief']
        ),

        html.Label(' 💥 Aantal lassen per spot (min & max) 💥:', style={"marginTop": 10}),
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

        html.Label('  Gemiddelde PSF (min & max) :', style={"marginTop": 10}),
        html.Div([
            dcc.Input(
                id='min-psf-input',
                type='number',
                placeholder='Min PSF',
                value=0,
                style={'width': '100px', 'marginRight': '10px'}
            ),
            dcc.Input(
                id='max-psf-input',
                type='number',
                placeholder='Max PSF',
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

        df['Tol=OK'] = df['Tol=OK'].astype(str).str.strip().str.lower()

        global_df = df.copy()

        timers = [{'label': t, 'value': t} for t in sorted(df['TimerName'].dropna().unique())]
        npts = [{'label': n, 'value': n} for n in sorted(df['NPTName'].dropna().unique())]

        return html.Div(f"✅ Bestand geladen: {filename}", style={"fontWeight": "bold", "color": "blue"}), timers, npts, None, None


    except Exception as e:
        return html.Div(f"❌ Fout bij laden: {str(e)}"), [], [], None, None


@app.callback(
    Output('bar-chart', 'figure'),
    Input('timer-dropdown', 'value'),
    Input('npt-dropdown', 'value'),
    Input('nok-only', 'value'),
    Input('adaptief-checkbox', 'value'),
    Input('min-welds-input', 'value'),
    Input('max-welds-input', 'value'),
    Input('min-psf-input', 'value'),
    Input('max-psf-input', 'value'),
    Input('sigma-button', 'n_clicks')
)
def update_chart(selected_timer, selected_npt, nok_only, adaptief_value, min_welds, max_welds, min_psf, max_psf, sigma_click):
    df = global_df.copy()

    if df.empty or 'Tol=OK' not in df.columns:
        return px.bar(title="⚠️ Geen geldige data geladen")

    # Zet Tol=OK om naar int en map naar 'kwaliteit'
    df['Tol=OK'] = df['Tol=OK'].astype(int)
    df['kwaliteit'] = df['Tol=OK'].map({1: 'ok', 0: 'nok'})

    if selected_timer:
        df = df[df['TimerName'] == selected_timer]
    if selected_npt:
        df = df[df['NPTName'] == selected_npt]

    if 'nok' in nok_only:
        df = df[df['kwaliteit'] == 'nok']

    if 'adaptief' in adaptief_value:
        df = df[df['uirRegulationActive'] == 1]
    else:
        df = df[df['uirRegulationActive'] == 0]

    df['SpotName'] = df['SpotName'].astype(str)

    grouped = df.groupby(['SpotName', 'kwaliteit']).agg(
        count=('cnt_welds_lastShift', 'sum'),
        avg_psf=('AVG_PSF_last_shift', 'mean'),
        stdev_psf=('STDEV_stabilisationFactor', 'mean'),
        cond_tol=('uirPsfCondTol', 'first'),
        lower_tol=('uirPsfLowerTol', 'first')
    ).reset_index()

    min_val = min_welds if min_welds is not None else 0
    max_val = max_welds if max_welds is not None else float('inf')
    grouped = grouped[(grouped['count'] >= min_val) & (grouped['count'] <= max_val)]

    min_psf_val = min_psf if min_psf is not None else 0
    max_psf_val = max_psf if max_psf is not None else float('inf')
    grouped = grouped[(grouped['avg_psf'] >= min_psf_val) & (grouped['avg_psf'] <= max_psf_val)]

    # Bereken de aangepaste PSF voor sigma-button filter
    grouped['adjusted_psf'] = grouped['avg_psf'] - 6 * grouped['stdev_psf']

    # Aanpassen data voor TOL optimalisatie
    trigger = dash.callback_context.triggered[0]['prop_id'].split('.')[0]
    if trigger == 'sigma-button':
        grouped = grouped[
            (grouped['adjusted_psf'] > 80) & # aangepaste PSF filter
            (grouped['count'] >= 20) &      # minimum aantal lassen
          #  (grouped['count'] <= 80) &      # maximum aantal lassen
            (grouped['kwaliteit'] == 'nok') # kwaliteit
        ]

    fig = px.bar(
        grouped,
        x='SpotName',
        y='count',
        color='kwaliteit',
        barmode='stack',
        text='count',
        title='Aantal lassen per SpotName (OK/NOK)',
        labels={'kwaliteit': 'Tol. Band geoptimaliseerd', 'count': 'Aantal lassen'},
        category_orders={'kwaliteit': ['ok', 'nok']},
        color_discrete_map={'ok': 'green', 'nok': 'red'},
        hover_data={
            'SpotName': True,
            'count': True,
            'avg_psf': ':.2f',
            'stdev_psf': ':.2f',
            'cond_tol': True,
            'lower_tol': True,
            'kwaliteit': True
        }
    )

    fig.update_traces(
        textposition='outside',
        textfont_size=14,
        cliponaxis=False
    )

    fig.update_layout(
        font=dict(family="Arial, sans-serif", size=12, color="black"),
        xaxis_tickangle=45,
        xaxis_tickfont=dict(size=11),
        yaxis_title='Aantal lassen',
        height=900,
        width=1400,
        margin=dict(l=40, r=40, t=60, b=200),
        legend_title_text='Tol. Band geoptimaliseerd'
    )

    return fig


if __name__ == '__main__':
    app.run_server(debug=False, host='0.0.0.0', port=8080)









