# psf_dashboard.py

import pandas as pd
import plotly.express as px
import base64
import io

def parse_excel(contents):
    content_type, content_string = contents.split(',')
    decoded = base64.b64decode(content_string)
    df = pd.read_excel(io.BytesIO(decoded), sheet_name="Query1")

    df.columns = df.columns.astype(str).str.strip().str.replace(r"\s+", " ", regex=True).str.replace('\n', '', regex=True)

    df['cnt_welds_lastShift'] = pd.to_numeric(df['cnt_welds_lastShift'], errors='coerce')
    df['AVG_PSF_last_shift'] = pd.to_numeric(df['AVG_PSF_last_shift'], errors='coerce')
    df['STDEV_stabilisationFactor'] = pd.to_numeric(df['STDEV_stabilisationFactor'], errors='coerce')

    return df


def generate_plot(df, timer=None, npt=None, min_welds=0, max_welds=9999, nok_only=False, sigma_filter=False):
    if df.empty or 'Tol=OK' not in df.columns:
        return px.bar(title="⚠️ Geen geldige data geladen")

    if timer:
        df = df[df['TimerName'] == timer]
    if npt:
        df = df[df['NPTName'] == npt]
    if nok_only:
        df = df[df['Tol=OK'].str.lower() == 'nok']

    df['SpotName'] = df['SpotName'].astype(str)

    grouped = df.groupby(['SpotName', 'Tol=OK']).agg(
        count=('cnt_welds_lastShift', 'sum'),
        avg_psf=('AVG_PSF_last_shift', 'mean'),
        stdev_psf=('STDEV_stabilisationFactor', 'mean')
    ).reset_index()

    grouped = grouped[(grouped['count'] >= min_welds) & (grouped['count'] <= max_welds)]

    if sigma_filter:
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

    fig.update_traces(textposition='outside', textfont_size=12, cliponaxis=False)

    fig.update_layout(
        xaxis_tickangle=0,
        xaxis_tickfont=dict(size=10),
        yaxis_title='Aantal lassen',
        height=900,
        margin=dict(l=40, r=40, t=60, b=200),
        legend_title_text='Kwaliteit'
    )

    return fig
