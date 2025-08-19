from flask import Flask, send_from_directory
import dash
from dash import html, dcc, Input, Output, State
import pandas as pd
import plotly.express as px
from dash.exceptions import PreventUpdate
from xml.sax.saxutils import quoteattr
from datetime import datetime
import os
import pyodbc
from io import StringIO
import numpy as np

# ==============================
# Config / constants
# ==============================
APP_TITLE = "PSF TOOL V216"

# Sigma drempels (UI-overridable)
DEFAULT_SIGMA_THRESHOLD = 72   # adjusted PSF drempel (user input)
MIN_SIGMA_THRESHOLD = 60       # minimum toelaatbare drempel in UI
PSF_THRESH_HI = 85             # grens voor keuze van export-banden

# Monitoring band-parameters (lage band en hoge band)
LOW_BAND  = dict(v3=7, v4=1, v9=60, v10=100, v11=30)  # thr < psf < 85
HIGH_BAND = dict(v3=7, v4=1, v9=40, v10=100, v11=20)  # 85 <= psf <= 100

REQUIRED_COLUMNS = {
    'TimerName','NPTName','SpotName',
    'cnt_welds_lastShift','AVG_PSF_last_shift','STDEV_stabilisationFactor',
    'uirRegulationActive','Tol=OK','CondTol<40','LowerTol<60','TolBands_switched'
}

# ==============================
# Flask server & static
# ==============================
server = Flask(__name__)
@server.get("/healthz")
def healthz():
    return {"status": "ok"}, 200

@server.get("/odbc")
def odbc():
    import pyodbc
    return {"drivers": list(pyodbc.drivers())}, 200


@server.route('/static/<path:path>')
def send_static(path):
    return send_from_directory('static', path)

# ==============================
# Dash app
# ==============================
app = dash.Dash(__name__, server=server)
app.title = APP_TITLE

app.layout = html.Div([
    dcc.Store(id="df-store"),

    html.Div([
        html.Img(src='/static/logo.png',
                 style={"maxWidth": "150px", "display": "block", "margin": "0 auto"}),
        html.H1(f" {APP_TITLE} ", style={"color": "black", "textAlign": "center"}),
    ]),

    html.Button(
        "🔄 Ververs data uit database",
        id="refresh-db",
        n_clicks=0,
        style={"marginTop": 10, "backgroundColor": "#66b3ff", "fontWeight": "bold",
               "display": "block", "marginLeft": "auto", "marginRight": "auto"}
    ),
    dcc.Interval(id="auto-refresh", interval=10*60*1000, n_intervals=0),

    html.Div(id='file-info'),

    html.Div([
        html.Label('Filter op TimerName:', style={"fontWeight": "bold"}),
        dcc.Dropdown(id='timer-dropdown', placeholder='Selecteer TimerName',
                     style={'margin':'0 auto','width':'50%'}),

        html.Label('Filter op NPTName:', style={"marginTop": 10, "fontWeight": "bold"}),
        dcc.Dropdown(id='npt-dropdown', placeholder='Selecteer NPTName',
                     style={'margin':'0 auto','width':'50%'}),

        dcc.Checklist(
            id='nok-only',
            options=[{'label': ' ❌ Toon alleen NOK SPOTS ❌ ', 'value': 'nok'}],
            value=[],
            inputStyle={"marginRight": "10px"},
            style={'textAlign': 'center', 'marginTop': '10px'}
        ),

        dcc.Checklist(
            id='adaptief-checkbox',
            options=[{'label': '✅ Alleen ADAPTIEF ✅', 'value': 'adaptief'}],
            value=['adaptief'],
            inputStyle={"marginRight": "10px"},
            style={'textAlign': 'center', 'marginTop': '10px'}
        ),

        html.Label('Tolerantieband status:', style={"marginTop": 10, "fontWeight": "bold"}),
        dcc.Dropdown(
            id='tolband-filter',
            options=[
                {'label': 'Toon alles',                 'value': 'all'},
                {'label': '❌ Enkel nog niet aangepast', 'value': 'not_switched'},
                {'label': '✅ Enkel al aangepast',       'value': 'switched'},
            ],
            value='all',
            clearable=False,
            style={'margin':'0 auto','width':'50%'}
        ),

        html.Label(' 💥 Aantal lassen per spot (min & max) 💥:', style={"marginTop": 10}),
        html.Div([
            dcc.Input(id='min-welds-input', type='number', placeholder='Min', value=0,
                      style={'width':'100px','marginRight':'10px'}),
            dcc.Input(id='max-welds-input', type='number', placeholder='Max', value=9999,
                      style={'width':'100px'})
        ], style={'display':'flex','justifyContent':'center','gap':'10px','marginTop':'5px'}),

        html.Label('  Gemiddelde PSF (min & max) :', style={"marginTop": 10}),
        html.Div([
            dcc.Input(id='min-psf-input', type='number', placeholder='Min PSF', value=0,
                      style={'width':'100px','marginRight':'10px'}),
            dcc.Input(id='max-psf-input', type='number', placeholder='Max PSF', value=9999,
                      style={'width':'100px'})
        ], style={'display':'flex','justifyContent':'center','gap':'10px','marginTop':'5px'}),

        html.Label(' Sigma-drempel (adjusted PSF = AVG - 6×STDEV):', style={"marginTop": 10, "fontWeight": "bold"}),
        html.Div([
            dcc.Input(
                id='sigma-threshold',
                type='number',
                min=MIN_SIGMA_THRESHOLD, max=100, step=1,
                value=DEFAULT_SIGMA_THRESHOLD,
                style={'width': '140px'}
            ),
            html.Span("  (min 60, default 72)", style={"marginLeft":"8px", "color":"#555"})
        ], style={'display':'flex','justifyContent':'center','gap':'10px','marginTop':'5px'}),

        html.Button(
            "🔁 Toggle: sigma (alleen ADAPTIEF + NOK + 6σ > drempel) 🔁",
            id="sigma-button", n_clicks=0,
            style={"marginTop": 20, "backgroundColor": "#ffcc54", "fontWeight": "bold",
                   "display": "block", "marginLeft": "auto", "marginRight": "auto"}
        ),

        html.Button(
            "📥 Export tolerantie banden (XML)",
            id="export-xml-button",
            n_clicks=0,
            style={"marginTop": 10, "backgroundColor": "#00cc99", "fontWeight": "bold",
                   "display": "block", "marginLeft": "auto", "marginRight": "auto"}
        ),

        dcc.Download(id="download-xml")
    ], style={'textAlign': 'center', 'marginBottom': 30}),

    html.Div(
        dcc.Graph(id='bar-chart', style={'width': '100%', 'height': '900px'}),
        style={'display': 'flex', 'justifyContent': 'center', 'width': '100%'}
    )
])

# ============ Helpers ============
def normalize_tol_ok(value):
    m = str(value).strip().lower()
    if m in {'1','true','ok','yes','ja'}: return 1
    if m in {'0','false','nok','nee','no'}: return 0
    try:
        return int(float(m))
    except Exception:
        return pd.NA

def get_sql_connection():
    server   = os.getenv("DB_SERVER", r"EQUI_DB_PROD.gen.volvocars.net\DBSQLEQVCGP")
    database = os.getenv("DB_DATABASE", "GADATA")
    user     = os.getenv("DB_USERNAME")  # zet deze env vars correct
    pwd      = os.getenv("DB_PASSWORD")

    candidates = ["ODBC Driver 18 for SQL Server", "ODBC Driver 17 for SQL Server", "SQL Server"]
    installed  = set(pyodbc.drivers())
    driver = next((d for d in candidates if d in installed), None)
    if not driver:
        raise RuntimeError(f"Geen geschikte SQL Server ODBC driver gevonden. Geïnstalleerde drivers: {sorted(installed)}.")

    base = f"DRIVER={{{driver}}};DATABASE={database};Encrypt=yes;TrustServerCertificate=yes;Connection Timeout=30;"
    auth = f"UID={user};PWD={pwd};" if user and pwd else "Trusted_Connection=yes;"

    try:
        conn_str = base + f"SERVER={server};" + auth
        return pyodbc.connect(conn_str)
    except pyodbc.Error:
        host = server.split("\\")[0]
        port = os.getenv("DB_PORT", "1433")
        conn_str = base + f"SERVER={host},{port};" + auth
        return pyodbc.connect(conn_str)

SQL_TEXT = """
SELECT
  t.Name AS TimerName,
  t.ResponsibleWeldMaster,
  LEFT(n.Name, 5) AS NPTName,
  s.SpotName,
  w.AVG_stabilisationFactor AS AVG_PSF_last_shift,
  w.STDEV_stabilisationFactor,
  w.[count] AS cnt_welds_lastShift,
  a.uirPsfCondTol,
  a.uirPsfLowerTol,
  a.rt_spot_id,
  a.Lastweld,
  a.uirRegulationActive,

  -- Excel-kolommen 1-op-1:
  CASE WHEN a.uirPsfCondTol  <= 40 THEN 1 ELSE 0 END AS [CondTol<40],
  CASE WHEN a.uirPsfLowerTol <= 60 THEN 1 ELSE 0 END AS [LowerTol<60],
  CASE WHEN (a.uirPsfCondTol <= 40 AND a.uirPsfLowerTol <= 60) THEN 1 ELSE 0 END AS [Tol=OK],
  CASE WHEN a.uirPsfCondTol > a.uirPsfLowerTol THEN CAST(1 AS int) ELSE CAST(0 AS int) END AS [TolBands_switched]

FROM WELDING2.h_weldmeasure AS w
LEFT JOIN (
  SELECT
    T1.uirPsfCondTol,
    T1.uirPsfLowerTol,
    T1.rt_spot_id,
    T1._timestamp AS Lastweld,
    T1.uirRegulationActive
  FROM WELDING2.rt_weldmeasureprotddw AS T1
  INNER JOIN (
    SELECT rt_spot_id, MAX(_timestamp) AS MaxTimestamp
    FROM WELDING2.rt_weldmeasureprotddw
    GROUP BY rt_spot_id
  ) AS T2
  ON T1.rt_spot_id = T2.rt_spot_id AND T1._timestamp = T2.MaxTimestamp
) AS a ON w.spotId = a.rt_spot_id
LEFT JOIN WELDING2.c_timer AS t ON w.timerId = t.ID
LEFT JOIN WELDING2.c_NPT  AS n ON t.NptId = n.ID
LEFT JOIN WELDING2.rt_spottable AS s ON w.spotId = s.ID
WHERE t.Name LIKE ?
  AND t.Name NOT LIKE ?
  AND t.Name NOT LIKE ?
  AND w.L_timeline_starttime > DATEADD(hour, ?, GETDATE())
  AND s.SpotName NOT LIKE ?
ORDER BY t.Name ASC;
"""

def fetch_df_from_db(timer_like='%GA-5%', not_like1='%WB%', not_like2='%WN%',
                      hours_back=17, spot_not_like='253'):
    params = (timer_like, not_like1, not_like2, -int(hours_back), spot_not_like)
    with get_sql_connection() as conn:
        df = pd.read_sql(SQL_TEXT, conn, params=params)
    df.columns = (
        df.columns.astype(str)
        .str.strip()
        .str.replace(r"\s+", " ", regex=True)
        .str.replace('\n', '', regex=True)
    )
    return df

# ==============================
# Callbacks
# ==============================
@app.callback(
    Output('file-info', 'children'),
    Output('timer-dropdown', 'options'),
    Output('npt-dropdown', 'options'),
    Output('timer-dropdown', 'value'),
    Output('npt-dropdown', 'value'),
    Output('df-store', 'data'),
    Input('refresh-db', 'n_clicks'),
    Input('auto-refresh', 'n_intervals'),
)
def load_from_db(n_clicks, n_intervals):
    try:
        df = fetch_df_from_db(
            timer_like='%GA-5%',
            not_like1='%WB%',
            not_like2='%WN%',
            hours_back=17,
            spot_not_like='253'
        )

        missing = REQUIRED_COLUMNS - set(df.columns)
        if missing:
            return (html.Div(f"❌ Ontbrekende kolommen in DB-resultaat: {', '.join(sorted(missing))}"),
                    [], [], None, None, None)

        # Numeriek maken
        numeric_cols = [
            'cnt_welds_lastShift','AVG_PSF_last_shift','STDEV_stabilisationFactor',
            'uirRegulationActive','Tol=OK','CondTol<40','LowerTol<60','TolBands_switched'
        ]
        for c in numeric_cols:
            if c in df.columns:
                df[c] = pd.to_numeric(df[c], errors='coerce')

        # Kwaliteit label zoals in de app
        df['Tol=OK'] = df['Tol=OK'].map(normalize_tol_ok).astype('Int64')
        df = df.dropna(subset=['Tol=OK']).astype({'Tol=OK':'int'})

        timers = [{'label': t, 'value': t} for t in sorted(df['TimerName'].dropna().unique())]
        npts   = [{'label': n, 'value': n} for n in sorted(df['NPTName'].dropna().unique())]

        df_json = df.to_json(date_format='iso', orient='split')

        return (
            html.Div("✅ Data geladen uit database",
                     style={"fontWeight":"bold","color":"green","textAlign":"Center"}),
            timers, npts, None, None, df_json
        )

    except Exception as e:
        return (html.Div(f"❌ DB-fout: {e}"), [], [], None, None, None)

@app.callback(
    Output('bar-chart', 'figure'),
    Input('df-store', 'data'),
    Input('timer-dropdown', 'value'),
    Input('npt-dropdown', 'value'),
    Input('nok-only', 'value'),
    Input('adaptief-checkbox', 'value'),
    Input('tolband-filter', 'value'),
    Input('min-welds-input', 'value'),
    Input('max-welds-input', 'value'),
    Input('min-psf-input', 'value'),
    Input('max-psf-input', 'value'),
    Input('sigma-threshold', 'value'),
    Input('sigma-button', 'n_clicks')
)
def update_chart(df_json, selected_timer, selected_npt, nok_only, adaptief_value, tolband_filter,
                 min_welds, max_welds, min_psf, max_psf, sigma_threshold, sigma_click):
    if not df_json:
        return px.bar(title="⚠️ Geen geldige data geladen")

    df = pd.read_json(StringIO(df_json), orient='split')
    if df.empty:
        return px.bar(title="⚠️ Geen data gevonden")

    df['kwaliteit'] = df['Tol=OK'].map({1: 'ok', 0: 'nok'})

    # UI-filters (Timer/NPT)
    if selected_timer:
        df = df[df['TimerName'] == selected_timer]
    if selected_npt:
        df = df[df['NPTName'] == selected_npt]

    # Alleen NOK?
    if 'nok' in (nok_only or []):
        df = df[df['kwaliteit'] == 'nok']

    # Sigma toggle
    apply_sigma = (sigma_click or 0) % 2 == 1
    thr = sigma_threshold if (sigma_threshold is not None and sigma_threshold >= MIN_SIGMA_THRESHOLD) else DEFAULT_SIGMA_THRESHOLD

    # Adaptief: in sigma altijd ADAPTIEF; buiten sigma: volg checkbox
    adaptief = 'adaptief' in (adaptief_value or [])
    if apply_sigma:
        df = df[df['uirRegulationActive'] == 1]
    else:
        df = df[df['uirRegulationActive'] == (1 if adaptief else 0)]

    # Tolerantieband status filter
    if tolband_filter == 'not_switched':
        df = df[df['TolBands_switched'] == 0]
    elif tolband_filter == 'switched':
        df = df[df['TolBands_switched'] == 1]

    if df.empty:
        return px.bar(title="⚠️ Geen data na filters")

    df['SpotName'] = df['SpotName'].astype(str)

    grouped = df.groupby(['SpotName', 'kwaliteit'], as_index=False).agg(
        count=('cnt_welds_lastShift', 'sum'),
        avg_psf=('AVG_PSF_last_shift', 'mean'),
        stdev_psf=('STDEV_stabilisationFactor', 'mean'),
        cond_tol=('uirPsfCondTol', 'first'),
        lower_tol=('uirPsfLowerTol', 'first')
    )

    grouped['stdev_psf'] = grouped['stdev_psf'].fillna(0.0)
    grouped['avg_psf']   = grouped['avg_psf'].fillna(0.0)
    grouped['adjusted_psf'] = grouped['avg_psf'] - 6 * grouped['stdev_psf']

    # Numerieke UI-filters
    min_val = min_welds if min_welds is not None else 0
    max_val = max_welds if max_welds is not None else float('inf')
    grouped = grouped[(grouped['count'] >= min_val) & (grouped['count'] <= max_val)]

    min_psf_val = min_psf if min_psf is not None else 0
    max_psf_val = max_psf if max_psf is not None else float('inf')
    grouped = grouped[(grouped['avg_psf'] >= min_psf_val) & (grouped['avg_psf'] <= max_psf_val)]

    # Sigma: ENKEL NOK + adjusted_psf > drempel
    if apply_sigma:
        grouped = grouped[(grouped['adjusted_psf'] > thr) & (grouped['kwaliteit'] == 'nok')]

    if grouped.empty:
        return px.bar(title="ℹ️ Geen rijen na (extra) filters")

    # === Aanbevolen tolerantieband (zelfde logica als XML) ===
    def _aanbevolen_vals(psf):
        if thr < psf < PSF_THRESH_HI:
            return LOW_BAND
        elif PSF_THRESH_HI <= psf <= 100:
            return HIGH_BAND
        else:
            return None

    def _aanbevolen_row(psf):
        vals = _aanbevolen_vals(psf)
        if not vals:
            return pd.Series({
                'aanbevolen_lower':  pd.NA,
                'aanbevolen_cond':   pd.NA,
                'aanbevolen_label':  '—'
            })
        return pd.Series({
            'aanbevolen_lower':  vals['v9'],   # 60 of 40
            'aanbevolen_cond':   vals['v11'],  # 30 of 20
            'aanbevolen_label':  f"{vals['v9']}/{vals['v11']}"
        })

    grouped = pd.concat([grouped, grouped['adjusted_psf'].apply(_aanbevolen_row)], axis=1)

    # match/mismatch vs huidige tol-banden (NA veilig vergelijken)
    match_mask = (
        (grouped['lower_tol'].fillna(-9999) == grouped['aanbevolen_lower'].fillna(-9999)) &
        (grouped['cond_tol'].fillna(-9999)  == grouped['aanbevolen_cond'].fillna(-9999))
    )
    grouped['band_match'] = match_mask.map({True: 'match', False: 'mismatch'})

    # === Plot ===
    fig = px.bar(
        grouped,
        x='SpotName',
        y='count',
        color='kwaliteit',
        barmode='stack',
        text='count',
        title=('Aantal lassen per SpotName (OK/NOK)' + (f' — Sigma (NOK) actief, drempel {thr}' if apply_sigma else '')),
        labels={'kwaliteit': 'Kwaliteit', 'count': 'Aantal lassen'},
        category_orders={'kwaliteit': ['ok', 'nok']},
        color_discrete_map={'ok': 'green', 'nok': 'red'},
        hover_data={
            'SpotName': True,
            'count': True,
            'avg_psf': ':.2f',
            'stdev_psf': ':.2f',
            'adjusted_psf': ':.2f',
            'cond_tol': True,          # huidige cond (XML: v11)
            'lower_tol': True,         # huidige lower (XML: v9)
            'aanbevolen_label': True,  # nieuw: "60/30" of "40/20"
            'band_match': True,
            'kwaliteit': True
        }
    )

    fig.update_traces(textposition='outside', textfont_size=14, cliponaxis=False)
    fig.update_layout(
        font=dict(family="Arial, sans-serif", size=15, color="black"),
        xaxis_tickangle=45,
        xaxis_tickfont=dict(size=12),
        yaxis_title='Aantal lassen',
        margin=dict(l=40, r=40, t=60, b=160),
        legend_title_text='Kwaliteit',
        autosize=True
    )

    return fig



# ===== XML export =====
@app.callback(
    Output("download-xml", "data"),
    Input("export-xml-button", "n_clicks"),
    State('df-store', 'data'),
    State('timer-dropdown', 'value'),
    State('npt-dropdown', 'value'),
    State('nok-only', 'value'),
    State('adaptief-checkbox', 'value'),
    State('tolband-filter', 'value'),
    State('sigma-button', 'n_clicks'),
    # Numerieke UI-filters en sigma-drempel
    State('min-welds-input', 'value'),
    State('max-welds-input', 'value'),
    State('min-psf-input', 'value'),
    State('max-psf-input', 'value'),
    State('sigma-threshold', 'value'),
    prevent_initial_call=True
)
def export_xml(n_clicks, df_json, selected_timer, selected_npt, nok_only, adaptief_value, tolband_filter,
               sigma_click, min_welds, max_welds, min_psf, max_psf, sigma_threshold):
    if not n_clicks or not df_json:
        raise PreventUpdate

    df = pd.read_json(StringIO(df_json), orient='split')
    if df.empty:
        raise PreventUpdate

    df['kwaliteit'] = df['Tol=OK'].map({1: 'ok', 0: 'nok'})

    # Zelfde filters als in grafiek
    if selected_timer:
        df = df[df['TimerName'] == selected_timer]
    if selected_npt:
        df = df[df['NPTName'] == selected_npt]
    if 'nok' in (nok_only or []):
        df = df[df['kwaliteit'] == 'nok']

    apply_sigma = (sigma_click or 0) % 2 == 1
    thr = sigma_threshold if (sigma_threshold is not None and sigma_threshold >= MIN_SIGMA_THRESHOLD) else DEFAULT_SIGMA_THRESHOLD

    adaptief = 'adaptief' in (adaptief_value or [])
    if apply_sigma:
        df = df[df['uirRegulationActive'] == 1]  # in sigma altijd adaptief
    else:
        df = df[df['uirRegulationActive'] == (1 if adaptief else 0)]

    if tolband_filter == 'not_switched':
        df = df[df['TolBands_switched'] == 0]
    elif tolband_filter == 'switched':
        df = df[df['TolBands_switched'] == 1]

    if df.empty:
        raise PreventUpdate

    df['SpotName'] = df['SpotName'].astype(str)

    grouped = df.groupby(['NPTName', 'TimerName', 'SpotName', 'kwaliteit'], as_index=False).agg(
        count=('cnt_welds_lastShift', 'sum'),
        avg_psf=('AVG_PSF_last_shift', 'mean'),
        stdev_psf=('STDEV_stabilisationFactor', 'mean'),
    )
    grouped['stdev_psf'] = grouped['stdev_psf'].fillna(0.0)
    grouped['avg_psf']   = grouped['avg_psf'].fillna(0.0)
    grouped['adjusted_psf'] = grouped['avg_psf'] - 6 * grouped['stdev_psf']

    # Numerieke UI-filters
    min_val = min_welds if min_welds is not None else 0
    max_val = max_welds if max_welds is not None else float('inf')
    grouped = grouped[(grouped['count'] >= min_val) & (grouped['count'] <= max_val)]
    min_psf_val = min_psf if min_psf is not None else 0
    max_psf_val = max_psf if max_psf is not None else float('inf')
    grouped = grouped[(grouped['avg_psf'] >= min_psf_val) & (grouped['avg_psf'] <= max_psf_val)]

    # Sigma: ENKEL NOK + adjusted_psf > drempel
    if apply_sigma:
        grouped = grouped[(grouped['adjusted_psf'] > thr) & (grouped['kwaliteit'] == 'nok')]

    if grouped.empty:
        raise PreventUpdate

    creation = datetime.now().strftime("%Y-%m-%d--%H:%M:%S.%f")[:-3]

    xml_lines = [
        '<?xml version="1.0" encoding="utf-8" standalone="yes"?>',
        '<nwsXml:InternalTimerWeldingData xmlns:nwsXml="nwsXML">'
    ]

    for (npt, timer), group_df in grouped.groupby(['NPTName', 'TimerName']):
        timer_q = quoteattr(str(timer))
        npt_q   = quoteattr(str(npt))
        creation_q = quoteattr(creation)

        xml_lines.append(
            f'  <Header CreatorName="PSF_TOOL" CreationDate={creation_q} '
            f'TimerName={timer_q} TimerIP="" LinePC={npt_q} '
            f'SchemaVersion="12" BaseFirmwareVersion="1.11.11.2" ApplicationVersion="1000_1.2.0" '
            f'ConfigurationVersion="Cfg_1000_1.0.8" ApplicationIdentifier="1000" DataManagerVersion="1.11.11.0" />'
        )
        xml_lines.append('  <WeldJobs>')

        for _, row in group_df.iterrows():
            spot = str(row['SpotName'])
            psf  = float(row['adjusted_psf'])

            if thr < psf < PSF_THRESH_HI:
                vals = LOW_BAND
            elif PSF_THRESH_HI <= psf <= 100:
                vals = HIGH_BAND
            else:
                continue

            spot_name = f"WJ_{spot}"
            spot_q = quoteattr(spot_name)

            xml_lines.append(f'    <WeldJob Name={spot_q}>')
            xml_lines.append(f'      <Param No="100001" Name="WJ_WeldJobName" Value={spot_q} Unit="" />')
            xml_lines.append('      <SequenceBlocks>')
            xml_lines.append('        <SequenceBlock Name="">')
            xml_lines.append('          <WeldBlocks>')
            xml_lines.append('            <WeldBlock Name="1">')
            xml_lines.append('            </WeldBlock>')
            xml_lines.append('          </WeldBlocks>')
            xml_lines.append('          <MonitoringBlocks>')
            xml_lines.append('            <MonitoringBlock Name="1">')
            xml_lines.append(f'              <Param No="130003" Name="MB_MonitorValue" Value="{vals["v3"]}" Unit="" />')
            xml_lines.append(f'              <Param No="130004" Name="MB_MonitorMode" Value="{vals["v4"]}" Unit="" />')
            xml_lines.append('              <Param No="130005" Name="MB_MonitorReferenceValue" Value="10000" Unit="depends on MonitorValue:0=A1=mV2=(%*100)3=ms4=uOhm5=17=N6=7=8=13=(%*100)9=11=14=15=16=18=20(mm*10000)10=(kNm*1000)12=Ws" />')
            xml_lines.append('              <Param No="130008" Name="MB_UpperToleranceBandPerc" Value="100.00" Unit="%" />')
            xml_lines.append(f'              <Param No="130009" Name="MB_LowerToleranceBandPerc" Value="{vals["v9"]}" Unit="%" />')
            xml_lines.append(f'              <Param No="130010" Name="MB_CondUpperToleranceBandPerc" Value="{vals["v10"]}" Unit="%" />')
            xml_lines.append(f'              <Param No="130011" Name="MB_CondLowerToleranceBandPerc" Value="{vals["v11"]}" Unit="%" />')
            xml_lines.append('            </MonitoringBlock>')
            xml_lines.append('            <MonitoringBlock Name="2">')
            xml_lines.append('            </MonitoringBlock>')
            xml_lines.append('          </MonitoringBlocks>')
            xml_lines.append('          <ReferenceCurves>')
            xml_lines.append('            <ReferenceCurve Name="1">')
            xml_lines.append('            </ReferenceCurve>')
            xml_lines.append('          </ReferenceCurves>')
            xml_lines.append('        </SequenceBlock>')
            xml_lines.append('      </SequenceBlocks>')
            xml_lines.append('    </WeldJob>')

        xml_lines.append('  </WeldJobs>')

    xml_lines.append('</nwsXml:InternalTimerWeldingData>')

    xml_content = "\n".join(xml_lines)
    fname_base = selected_npt or 'all'
    filename = f"{fname_base}.xml"

    return dict(content=xml_content, filename=filename)


if __name__ == '__main__':
    port = int(os.environ.get("PORT", "8080"))
    app.run(debug=False, host='0.0.0.0', port=port)


