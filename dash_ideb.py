import os
import urllib3

import dash
from dash import Input, Output, State, dcc, html, dash_table
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import trino


urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


TRINO_HOST = os.getenv("TRINO_HOST", "trino.dataiesb.com")
TRINO_PORT = int(os.getenv("TRINO_PORT", "443"))
TRINO_USER = os.getenv("TRINO_USER", "admin")
TRINO_PASSWORD = os.getenv("TRINO_PASSWORD", "")
TRINO_TABLE = os.getenv("TRINO_IDEB_TABLE", "seaweedfs.raw.inep_ideb_municipios")

COLUNAS_IDEB = [
	"sg_uf", "cod_municipio", "nome_municipio", "rede", "etapa", "ano",
	"tx_aprovacao_1", "tx_aprovacao_2", "tx_aprovacao_3", "tx_aprovacao_4", "tx_aprovacao_5",
	"tx_aprovacao_1_a_5", "indicador_rendimento",
	"nota_saeb_matematica", "nota_saeb_portugues", "nota_saeb_media",
	"ideb_observado", "ideb_meta",
]

COLUNAS_NUMERICAS = [
	"tx_aprovacao_1", "tx_aprovacao_2", "tx_aprovacao_3", "tx_aprovacao_4", "tx_aprovacao_5",
	"tx_aprovacao_1_a_5", "indicador_rendimento",
	"nota_saeb_matematica", "nota_saeb_portugues", "nota_saeb_media",
	"ideb_observado", "ideb_meta",
]


def conectar_trino():
	kwargs = {"host": TRINO_HOST, "port": TRINO_PORT, "user": TRINO_USER}
	if TRINO_PORT == 443:
		kwargs.update({
			"http_scheme": "https",
			"auth": trino.auth.BasicAuthentication(TRINO_USER, TRINO_PASSWORD),
			"verify": False,
		})
	return trino.dbapi.connect(**kwargs)


def carregar_dados():
	colunas = ", ".join(COLUNAS_IDEB)
	conn = conectar_trino()
	try:
		cursor = conn.cursor()
		cursor.execute(f"SELECT {colunas} FROM {TRINO_TABLE}")
		nomes_colunas = [descricao[0] for descricao in cursor.description]
		dados = pd.DataFrame(cursor.fetchall(), columns=nomes_colunas)
	finally:
		conn.close()

	dados["ano"] = pd.to_numeric(dados["ano"], errors="coerce").astype("Int64")
	for coluna in COLUNAS_NUMERICAS:
		dados[coluna] = pd.to_numeric(dados[coluna], errors="coerce")
	for coluna in ["sg_uf", "cod_municipio", "nome_municipio", "rede", "etapa"]:
		dados[coluna] = dados[coluna].fillna("").astype(str).str.strip()
	return dados.dropna(subset=["ano"])


print("[IDEB] Carregando dados...", flush=True)
df_ideb = carregar_dados()
print(f"[IDEB] {len(df_ideb):,} registros carregados.", flush=True)


# ── Paleta / estilo ───────────────────────────────────────────────────────────
COR_HEADER = "#000000"
COR_FUNDO = "#F0F2F5"
COR_TEXTO = "#2D3748"
COR_TEXTO_FRACO = "#718096"
COR_BORDA = "#E2E8F0"

COR_AZUL = "#2B6CB0"
COR_VERDE = "#2F855A"
COR_LARANJA = "#D69E2E"
COR_ROXO = "#805AD5"
COR_VERMELHO = "#C53030"
COR_CINZA = "#5A6B7A"

CORES_CATEGORICAS = [COR_AZUL, COR_VERDE, COR_LARANJA, COR_ROXO, COR_VERMELHO, "#1D9E75", "#378ADD"]
CORES_ETAPA_FIXO = {"anos_iniciais": COR_AZUL, "anos_finais": COR_ROXO, "ensino_medio": "#DD6B20"}


# ── Helpers ───────────────────────────────────────────────────────────────────
def formatar_numero(valor, casas=1):
	if pd.isna(valor):
		return "-"
	return f"{valor:,.{casas}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def filtrar_categoricos(df, ufs, etapas, redes):
	filtrado = df
	if ufs:
		filtrado = filtrado[filtrado["sg_uf"].isin(ufs)]
	if etapas:
		filtrado = filtrado[filtrado["etapa"].isin(etapas)]
	if redes:
		filtrado = filtrado[filtrado["rede"].isin(redes)]
	return filtrado


def filtrar_periodo(df, periodo):
	if not periodo:
		return df
	ini, fim = periodo
	return df[(df["ano"] >= int(ini)) & (df["ano"] <= int(fim))]


def obter_ano_efetivo(df, ano_ref):
	anos_disponiveis = df["ano"].dropna().unique().tolist()
	if not anos_disponiveis:
		return None
	if ano_ref in anos_disponiveis:
		return int(ano_ref)
	return int(max(anos_disponiveis))


def cor_para_categoria(nome, indice):
	chave = str(nome).strip().lower().replace(" ", "_")
	return CORES_ETAPA_FIXO.get(chave, CORES_CATEGORICAS[indice % len(CORES_CATEGORICAS)])


# ── Componentes de layout ────────────────────────────────────────────────────
def _layout_base(altura=320):
	return dict(
		margin=dict(l=40, r=20, t=10, b=40),
		plot_bgcolor="#ffffff", paper_bgcolor="#ffffff",
		font=dict(family="Inter, sans-serif", size=12, color="#333"),
		xaxis=dict(showgrid=False, linecolor="#e0e0e0"),
		yaxis=dict(gridcolor="#f0f0f0", linecolor="#e0e0e0"),
		hoverlabel=dict(bgcolor="#fff", bordercolor="#ccc", font_size=12, font_color="#000000"),
		height=altura,
	)


def _figura_vazia(mensagem, altura=320):
	fig = go.Figure()
	fig.update_layout(**_layout_base(altura), annotations=[
		{"text": mensagem, "showarrow": False, "font": {"size": 13, "color": COR_TEXTO_FRACO}}
	])
	return fig


def _kpi(valor, label, cor):
	return html.Div([
		html.P(valor, style={"fontSize": 26, "fontWeight": 700, "color": "#fff", "margin": "0 0 4px 0"}),
		html.P(label, style={"fontSize": 11, "fontWeight": 600, "color": "#fff", "margin": 0, "textTransform": "uppercase", "letterSpacing": "0.05em"}),
	], style={"backgroundColor": cor, "borderRadius": 8, "padding": "18px 22px", "flex": 1, "minWidth": 170})


def _card(children, shadow=False, flex=1):
	style = {
		"backgroundColor": "#ffffff", "borderRadius": 8, "padding": "20px 24px",
		"border": f"1px solid {COR_BORDA}", "flex": flex, "minWidth": 320,
	}
	if shadow:
		style["boxShadow"] = "0 2px 8px rgba(0,0,0,0.12)"
		style["border"] = "none"
	return html.Div(children, style=style)


def _titulo(texto):
	return html.P(texto, style={"fontSize": 13, "fontWeight": 600, "color": COR_TEXTO, "margin": 0})


def _nota(texto, cor=None):
	return html.P(texto, style={"fontSize": 11, "color": cor or COR_TEXTO_FRACO, "margin": "6px 0 0 0",
								  "fontStyle": "italic", "lineHeight": "1.4"})


# ── Construtores de gráfico ───────────────────────────────────────────────────
def grafico_evolucao(df_periodo):
	base = df_periodo.dropna(subset=["ideb_observado"])
	if base.empty:
		return _figura_vazia("Sem evolução disponível no período selecionado")

	fig = go.Figure()
	for i, (etapa, dados_etapa) in enumerate(base.groupby("etapa", sort=False)):
		serie_etapa = dados_etapa.groupby("ano", as_index=False)["ideb_observado"].mean().sort_values("ano")
		fig.add_trace(go.Scatter(
			x=serie_etapa["ano"].astype(int), y=serie_etapa["ideb_observado"].round(2),
			mode="lines+markers", name=etapa.replace("_", " ").title(),
			line=dict(color=cor_para_categoria(etapa, i), width=2.5), marker=dict(size=7),
			hovertemplate="<b>%{x}</b><br>IDEB: %{y:.2f}<extra></extra>",
		))

	meta = df_periodo.dropna(subset=["ideb_meta"])
	if not meta.empty:
		serie_meta = meta.groupby("ano", as_index=False)["ideb_meta"].mean().sort_values("ano")
		fig.add_trace(go.Scatter(
			x=serie_meta["ano"].astype(int), y=serie_meta["ideb_meta"].round(2),
			mode="lines", name="Meta média", line=dict(color=COR_VERMELHO, width=2, dash="dot"),
			hovertemplate="<b>%{x}</b><br>Meta média: %{y:.2f}<extra></extra>",
		))
	fig.update_layout(**_layout_base(), yaxis_title="Nota IDEB",
					   legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0, font_size=11))
	fig.update_xaxes(tickformat="d")
	return fig


def grafico_donut_etapa(df_referencia):
	base = df_referencia.groupby("etapa", as_index=False).size().rename(columns={"size": "qtd"})
	if base.empty:
		return _figura_vazia("Sem dados por etapa", altura=320)
	cores = [cor_para_categoria(e, i) for i, e in enumerate(base["etapa"])]
	fig = go.Figure(go.Pie(
		labels=[e.replace('_', ' ').title() for e in base["etapa"]], values=base["qtd"], hole=0.55, marker=dict(colors=cores),
		textinfo="percent", hovertemplate="%{label}<br>%{value} registros (%{percent})<extra></extra>",
	))
	fig.update_layout(**_layout_base(320), showlegend=True,
					   legend=dict(orientation="h", yanchor="bottom", y=-0.15, xanchor="center", x=0.5))
	return fig


def linha_municipio(df_mun_periodo):
	serie = df_mun_periodo.groupby("ano", as_index=False)["ideb_observado"].mean().dropna().sort_values("ano")
	if serie.empty:
		return _figura_vazia("Sem evolução para este município no período", altura=320)
	fig = go.Figure(go.Scatter(
		x=serie["ano"].astype(int), y=serie["ideb_observado"].round(2), mode="lines+markers",
		line=dict(color=COR_LARANJA, width=2.5), marker=dict(size=7),
		hovertemplate="<b>%{x}</b><br>IDEB: %{y:.2f}<extra></extra>",
	))
	fig.update_layout(**_layout_base(320), yaxis_title="IDEB")
	fig.update_xaxes(tickformat="d")
	return fig


# ── Tabela de Ranking ────────────────────────────────────────────────────────
def gerar_tabela_ranking(df_referencia):
	base = df_referencia.dropna(subset=["ideb_observado"]).copy()
	if base.empty:
		return html.P("Sem dados suficientes para gerar a tabela.", style={"color": COR_TEXTO_FRACO, "padding": 10})

	resumo = base.groupby(["nome_municipio", "sg_uf"], as_index=False).agg({
		"ideb_observado": "mean",
		"nota_saeb_matematica": "mean",
		"nota_saeb_portugues": "mean",
		"tx_aprovacao_1_a_5": "mean"
	}).sort_values("ideb_observado", ascending=False).reset_index(drop=True)

	resumo["#"] = resumo.index + 1
	resumo["ideb_observado"] = resumo["ideb_observado"].round(2)
	resumo["nota_saeb_matematica"] = resumo["nota_saeb_matematica"].round(2)
	resumo["nota_saeb_portugues"] = resumo["nota_saeb_portugues"].round(2)
	resumo["tx_aprovacao_1_a_5"] = resumo["tx_aprovacao_1_a_5"].round(1)

	resumo = resumo.rename(columns={
		"nome_municipio": "MUNICÍPIO",
		"sg_uf": "UF",
		"ideb_observado": "NOTA IDEB",
		"nota_saeb_matematica": "SAEB MAT.",
		"nota_saeb_portugues": "SAEB PORT.",
		"tx_aprovacao_1_a_5": "APROVAÇÃO (%)"
	})

	colunas_ordem = ["#", "MUNICÍPIO", "UF", "NOTA IDEB", "SAEB MAT.", "SAEB PORT.", "APROVAÇÃO (%)"]
	dados_tabela = resumo[colunas_ordem].to_dict("records")

	return dash_table.DataTable(
		data=dados_tabela,
		columns=[{"name": col, "id": col} for col in colunas_ordem],
		page_size=15,
		page_action="native",
		sort_action="native",
		filter_action="native",
		style_table={"overflowX": "auto"},
		style_header={
			"backgroundColor": "#F8FAFC",
			"color": "#475569",
			"fontWeight": "700",
			"fontSize": "11px",
			"textTransform": "uppercase",
			"letterSpacing": "0.05em",
			"borderTop": "none",
			"borderBottom": "2px solid #E2E8F0",
			"borderLeft": "none",
			"borderRight": "none",
			"padding": "12px 16px",
			"textAlign": "left"
		},
		style_cell={
			"fontFamily": "'Inter', -apple-system, sans-serif",
			"fontSize": "13px",
			"padding": "14px 16px",
			"color": "#334155",
			"borderTop": "1px solid #F1F5F9",
			"borderBottom": "1px solid #F1F5F9",
			"borderLeft": "none",
			"borderRight": "none",
			"textAlign": "left"
		},
		style_data_conditional=[
			{"if": {"row_index": "odd"}, "backgroundColor": "#FAFAFA"},
			{"if": {"column_id": "#"}, "color": "#94A3B8", "fontWeight": "600", "width": "50px", "textAlign": "center"},
			{"if": {"column_id": "MUNICÍPIO"}, "fontWeight": "600", "color": "#1E293B"},
			{"if": {"column_id": "NOTA IDEB"}, "fontWeight": "700", "color": "#2B6CB0"}
		],
		style_header_conditional=[
			{"if": {"column_id": "NOTA IDEB"}, "color": "#2B6CB0"},
			{"if": {"column_id": "#"}, "textAlign": "center"}
		]
	)


# ── Conteúdo — Visão geral ────────────────────────────────────────────────────
def construir_visao_geral(df_periodo, df_referencia, ano_efetivo):
	if df_periodo.empty:
		return html.P("Nenhum registro encontrado para os filtros selecionados.",
					   style={"color": COR_VERMELHO, "padding": 20, "fontSize": 14})

	ideb_medio = df_referencia["ideb_observado"].mean()
	saeb_matematica = df_referencia["nota_saeb_matematica"].mean()
	saeb_portugues = df_referencia["nota_saeb_portugues"].mean()
	aprovacao_media = df_referencia["tx_aprovacao_1_a_5"].mean()
	municipios = df_referencia.dropna(subset=["ideb_observado"])["nome_municipio"].nunique()

	return html.Div([
		_nota(f"Indicadores de referência para o ano de {ano_efetivo}" if ano_efetivo else "Sem ano de referência disponível"),
		html.Div(style={"marginBottom": 10}),
		html.Div([
			_kpi(formatar_numero(ideb_medio, 2), "Nota IDEB média", COR_AZUL),
			_kpi(formatar_numero(saeb_matematica, 2), "SAEB Matemática", COR_ROXO),
			_kpi(formatar_numero(saeb_portugues, 2), "SAEB Português", COR_LARANJA),
			_kpi(f"{formatar_numero(aprovacao_media, 1)}%", "Aprovação média", COR_VERDE),
			_kpi(f"{municipios:,}".replace(",", "."), "Municípios no filtro", COR_CINZA),
		], style={"display": "flex", "gap": 12, "flexWrap": "wrap", "marginBottom": 20}),

		html.Div([
			_card([_titulo("Evolução da nota IDEB por etapa"),
				   _nota("Linhas: anos iniciais, anos finais e ensino médio · meta disponível de 2007 a 2021"),
				   dcc.Graph(figure=grafico_evolucao(df_periodo), config={"displayModeBar": False})], flex=2),
		], style={"display": "flex", "gap": 12, "marginBottom": 12, "flexWrap": "wrap"}),

		html.Div([
			_card([_titulo("Distribuição por Etapa"),
				   _nota("Proporção de registros no filtro"),
				   dcc.Graph(figure=grafico_donut_etapa(df_referencia), config={"displayModeBar": False})], flex=1),
			_card([
				_titulo("Entenda os indicadores"),
				html.P("SAEB é a avaliação que mede o desempenho dos estudantes em testes de aprendizagem, como Matemática e Português.", style={"fontSize": 13, "lineHeight": "1.55", "color": COR_TEXTO, "margin": "8px 0"}),
				html.P("IDEB combina o desempenho no SAEB com a taxa de aprovação escolar. Por isso, uma nota maior indica melhor resultado conjunto de aprendizagem e fluxo escolar.", style={"fontSize": 13, "lineHeight": "1.55", "color": COR_TEXTO, "margin": "8px 0"}),
				html.P("A etapa indica o segmento avaliado: anos iniciais, anos finais ou ensino médio. As médias apresentadas podem reunir redes e municípios conforme os filtros selecionados.", style={"fontSize": 13, "lineHeight": "1.55", "color": COR_TEXTO, "margin": "8px 0"}),
			], flex=1),
		], style={"display": "flex", "gap": 12, "marginBottom": 20, "flexWrap": "wrap"}),
	])


# ── Conteúdo — Visão por município ────────────────────────────────────────────
def construir_visao_municipio(df_periodo, df_referencia, cod_municipio, ano_efetivo):
	componentes = []

	if cod_municipio:
		df_mun_periodo = df_periodo[df_periodo["cod_municipio"] == cod_municipio]
		if not df_mun_periodo.empty:
			nome = df_mun_periodo["nome_municipio"].iloc[0]
			uf = df_mun_periodo["sg_uf"].iloc[0]

			df_mun_ref = df_mun_periodo[df_mun_periodo["ano"] == ano_efetivo]
			if df_mun_ref.empty:
				ano_disponivel = int(df_mun_periodo["ano"].max())
				df_mun_ref = df_mun_periodo[df_mun_periodo["ano"] == ano_disponivel]
			else:
				ano_disponivel = ano_efetivo
			linha_recente = df_mun_ref.mean(numeric_only=True)

			ranking_ref = df_referencia.dropna(subset=["ideb_observado"]).groupby("nome_municipio", as_index=False)["ideb_observado"].mean()
			ranking_ref = ranking_ref.sort_values("ideb_observado", ascending=False).reset_index(drop=True)
			posicao = ranking_ref.index[ranking_ref["nome_municipio"] == nome]
			texto_posicao = f"{posicao[0] + 1}º de {len(ranking_ref)}" if len(posicao) else "-"

			detalhes = html.Div([
				html.P(f"{nome} — {uf}", style={"fontSize": 20, "fontWeight": 700, "color": COR_TEXTO, "margin": "0 0 2px 0"}),
				_nota(f"Dados de referência: {ano_disponivel}"),
				html.Div(style={"marginBottom": 16}),

				html.Div([
					_kpi(formatar_numero(linha_recente.get("ideb_observado"), 2), "IDEB observado", COR_AZUL),
					_kpi(formatar_numero(linha_recente.get("nota_saeb_matematica"), 2), "SAEB Matemática", COR_ROXO),
					_kpi(formatar_numero(linha_recente.get("nota_saeb_portugues"), 2), "SAEB Português", COR_LARANJA),
					_kpi(f"{formatar_numero(linha_recente.get('tx_aprovacao_1_a_5'), 1)}%", "Aprovação média", COR_VERDE),
					_kpi(texto_posicao, "Posição no ranking", COR_CINZA),
				], style={"display": "flex", "gap": 12, "flexWrap": "wrap", "marginBottom": 20}),

				html.Div([
					_card([_titulo("Evolução Histórica do IDEB no Período"),
						   dcc.Graph(figure=linha_municipio(df_mun_periodo), config={"displayModeBar": False})], flex=1),
				], style={"display": "flex", "gap": 12, "flexWrap": "wrap", "marginBottom": 20}),
			])
			componentes.append(detalhes)
	else:
		componentes.append(
			_card([
				html.Div([
					html.Div("📍", style={"fontSize": 36, "marginBottom": 8}),
					html.H3("Selecione um município no campo de busca acima para ver detalhes específicos", style={"fontSize": 15, "fontWeight": 600, "color": COR_TEXTO, "margin": "0 0 4px 0"}),
					html.P("Você também pode analisar e filtrar o ranking completo dos municípios na tabela abaixo.",
						   style={"fontSize": 12, "color": COR_TEXTO_FRACO, "margin": 0}),
				], style={"textAlign": "center", "padding": "16px 20px"})
			], shadow=True)
		)
		componentes.append(html.Div(style={"marginBottom": 20}))

	tabela_ranking = _card([
		html.Div([
			_titulo(f"Ranking dos Municípios ({ano_efetivo if ano_efetivo else ''})"),
			_nota("Utilize os controles abaixo para navegar entre as páginas de resultados, filtrar ou ordenar por coluna"),
		], style={"marginBottom": 14}),
		gerar_tabela_ranking(df_referencia)
	], shadow=True)

	componentes.append(tabela_ranking)

	return html.Div(componentes)


# ── Listas para os filtros ────────────────────────────────────────────────────
ANOS_ASC = sorted(df_ideb["ano"].dropna().unique().tolist())
ANOS_DESC = list(reversed(ANOS_ASC))
UFS = sorted(df_ideb["sg_uf"].replace("", pd.NA).dropna().unique().tolist())
ETAPAS = sorted(df_ideb["etapa"].replace("", pd.NA).dropna().unique().tolist())
REDES = sorted(df_ideb["rede"].replace("", pd.NA).dropna().unique().tolist())
MUNICIPIOS = (
	df_ideb[["cod_municipio", "nome_municipio", "sg_uf"]]
	.drop_duplicates()
	.assign(rotulo=lambda d: d["nome_municipio"] + " — " + d["sg_uf"])
	.sort_values("rotulo")
)
ANO_MIN, ANO_MAX = (int(ANOS_ASC[0]), int(ANOS_ASC[-1])) if ANOS_ASC else (2005, 2023)
ANO_REF_PADRAO = ANOS_DESC[0] if ANOS_DESC else ANO_MAX
TOTAL_MUNICIPIOS = df_ideb["cod_municipio"].nunique()

ESTILO_LABEL = {"fontSize": 11, "fontWeight": 600, "color": COR_TEXTO_FRACO, "marginBottom": 4, "display": "block",
				"textTransform": "uppercase", "letterSpacing": "0.03em"}
ESTILO_DROPDOWN = {"fontFamily": "Inter, sans-serif", "fontSize": 13, "minWidth": 190}


# ── App ────────────────────────────────────────────────────────────────────────
app = dash.Dash(__name__, title="Dashboard IDEB", suppress_callback_exceptions=True,
				url_base_pathname=os.getenv("DASH_PREFIX", "/ideb/"),
				meta_tags=[{"name": "viewport", "content": "width=device-width, initial-scale=1.0"}])
server = app.server

app.index_string = app.index_string.replace(
	"</head>",
	"""<link rel="preconnect" href="https://fonts.googleapis.com">
	<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
	<style>
		body { font-family: 'Inter', sans-serif; }
		.ideb-tab {
			font-family: Inter, sans-serif !important; font-weight: 600 !important; font-size: 14px !important;
			padding: 12px 24px !important; background-color: #ffffff !important; border: 1px solid #DBE3EA !important;
			border-radius: 8px 8px 0 0 !important; color: #2d3748 !important; border-bottom: none !important;
		}
		.ideb-tab--azul { border-top: 3px solid #2B6CB0 !important; }
		.ideb-tab--verde { border-top: 3px solid #2F855A !important; }
		.ideb-tab--azul.ideb-tab--selected {
			background-color: #2B6CB0 !important; border-color: #2B6CB0 !important; border-top: 3px solid #2B6CB0 !important;
			color: #ffffff !important; box-shadow: 0 2px 4px rgba(16,24,40,0.10);
		}
		.ideb-tab--verde.ideb-tab--selected {
			background-color: #2F855A !important; border-color: #2F855A !important; border-top: 3px solid #2F855A !important;
			color: #ffffff !important; box-shadow: 0 2px 4px rgba(16,24,40,0.10);
		}
		.botao-limpar {
			background: #fff; border: 1px solid #DBE3EA; color: #2B6CB0; font-weight: 600; font-size: 12.5px;
			border-radius: 6px; padding: 8px 14px; cursor: pointer; height: 36px;
		}
		.botao-limpar:hover { background: #2B6CB0; color: #fff; border-color: #2B6CB0; }
		.botao-download {
			background: #2F855A; border: 1px solid #2F855A; color: #fff; font-weight: 600; font-size: 12.5px;
			border-radius: 6px; padding: 8px 14px; cursor: pointer; height: 36px;
		}
		.botao-download:hover { background: #276749; border-color: #276749; }

		/* Estilização dos Botões de Paginação da Tabela */
		.previous-next-container button {
			background-color: #ffffff !important;
			border: 1px solid #E2E8F0 !important;
			border-radius: 6px !important;
			color: #475569 !important;
			font-weight: 600 !important;
			font-size: 12px !important;
			padding: 6px 12px !important;
			margin: 0 4px !important;
			cursor: pointer !important;
		}
		.previous-next-container button:hover {
			background-color: #F8FAFC !important;
			border-color: #CBD5E1 !important;
			color: #1E293B !important;
		}
		.page-number {
			color: #64748B !important;
			font-size: 12px !important;
		}
	</style></head>"""
)

app.layout = html.Div(
	style={"fontFamily": "Inter, sans-serif", "backgroundColor": COR_FUNDO, "minHeight": "100vh"},
	children=[
		dcc.Download(id="download-dados-csv"),
		# Header com Fundo Preto e Logo no canto direito
		html.Div([
			html.Div([
				html.H1("Dashboard IDEB Municipal", style={"fontSize": 22, "fontWeight": 700, "color": "#fff", "margin": 0}),
				html.P("Indicadores de aprendizagem, aprovação e desempenho por município · Fonte: INEP",
					   style={"fontSize": 12, "color": "#A0AEC0", "margin": "4px 0 0 0"}),
			], style={"flex": 1}),
			html.Div([
				html.Img(
					src=dash.get_asset_url("logo_iesb.png"),
					style={"height": "38px", "display": "block"}
				)
			], style={
				"backgroundColor": "#ffffff",
				"padding": "8px 16px",
				"borderRadius": "8px",
				"display": "flex",
				"alignItems": "center",
				"justifyContent": "center"
			}),
		], style={
			"backgroundColor": COR_HEADER,
			"padding": "20px 32px",
			"display": "flex",
			"alignItems": "center",
			"justifyContent": "space-between"
		}),

		# Filtros
		_card([
			html.Div([
				html.Label("Período (gráficos de evolução)", style=ESTILO_LABEL),
				dcc.RangeSlider(id="filtro-periodo", min=ANO_MIN, max=ANO_MAX, value=[ANO_MIN, ANO_MAX],
								 marks={int(a): str(a) for a in ANOS_ASC}, step=None, allowCross=False),
			], style={"marginBottom": 18}),
			html.Div([
				html.Div([html.Label("Ano de referência", style=ESTILO_LABEL),
						  dcc.Dropdown([{"label": str(a), "value": int(a)} for a in ANOS_DESC],
									   value=ANO_REF_PADRAO, clearable=False, id="filtro-ano-ref", style=ESTILO_DROPDOWN)]),
				html.Div([html.Label("UF", style=ESTILO_LABEL),
						  dcc.Dropdown([{"label": u, "value": u} for u in UFS], value=[], multi=True,
									   placeholder="Todas", id="filtro-uf", style=ESTILO_DROPDOWN)]),
				html.Div([html.Label("Etapa", style=ESTILO_LABEL),
						  dcc.Dropdown([{"label": e, "value": e} for e in ETAPAS], value=[], multi=True,
									   placeholder="Todas", id="filtro-etapa", style=ESTILO_DROPDOWN)]),
				html.Div([html.Label("Rede", style=ESTILO_LABEL),
						  dcc.Dropdown([{"label": r, "value": r} for r in REDES], value=[], multi=True,
									   placeholder="Todas", id="filtro-rede", style=ESTILO_DROPDOWN)]),
				html.Div([html.Label(" ", style=ESTILO_LABEL),
						  html.Button("Limpar filtros", id="botao-limpar", n_clicks=0, className="botao-limpar")]),
				html.Div([html.Label(" ", style=ESTILO_LABEL),
						  html.Button("Baixar CSV", id="botao-download", n_clicks=0, className="botao-download")]),
			], style={"display": "flex", "gap": 16, "flexWrap": "wrap", "alignItems": "flex-end"}),
		], shadow=True),

		# Abas
		html.Div([
			dcc.Tabs(id="abas", value="geral", children=[
				dcc.Tab(label="Visão geral", value="geral", className="ideb-tab ideb-tab--azul",
						selected_className="ideb-tab ideb-tab--azul ideb-tab--selected"),
				dcc.Tab(label="Visão por município", value="municipio", className="ideb-tab ideb-tab--verde",
						selected_className="ideb-tab ideb-tab--verde ideb-tab--selected"),
			]),
		], style={"padding": "16px 32px 0 32px"}),

		html.Div(id="painel-municipio-wrapper", children=[
			_card([
				html.Label("Buscar município", style=ESTILO_LABEL),
				dcc.Dropdown(
					[{"label": row.rotulo, "value": row.cod_municipio} for row in MUNICIPIOS.itertuples()],
					id="filtro-municipio", placeholder="Digite o nome do município...", clearable=True,
					style={**ESTILO_DROPDOWN, "minWidth": 320},
				),
			])
		], style={"padding": "16px 32px 0 32px", "display": "none"}),

		html.Div(id="conteudo", style={"padding": "20px 32px 40px 32px"}),
	],
)


@app.callback(Output("painel-municipio-wrapper", "style"), Input("abas", "value"))
def alternar_seletor_municipio(aba):
	base = {"padding": "16px 32px 0 32px"}
	return {**base, "display": "block"} if aba == "municipio" else {**base, "display": "none"}


@app.callback(
	Output("filtro-periodo", "value"),
	Output("filtro-ano-ref", "value"),
	Output("filtro-uf", "value"),
	Output("filtro-etapa", "value"),
	Output("filtro-rede", "value"),
	Output("filtro-municipio", "value"),
	Input("botao-limpar", "n_clicks"),
	prevent_initial_call=True,
)
def limpar_filtros(n_clicks):
	return [ANO_MIN, ANO_MAX], ANO_REF_PADRAO, [], [], [], None


@app.callback(
	Output("download-dados-csv", "data"),
	Input("botao-download", "n_clicks"),
	State("filtro-periodo", "value"),
	State("filtro-uf", "value"),
	State("filtro-etapa", "value"),
	State("filtro-rede", "value"),
	prevent_initial_call=True,
)
def exportar_csv(n_clicks, periodo, ufs, etapas, redes):
	df_categ = filtrar_categoricos(df_ideb, ufs or [], etapas or [], redes or [])
	df_filtrado = filtrar_periodo(df_categ, periodo)
	return dcc.send_data_frame(df_filtrado.to_csv, "ideb_dados_filtrados.csv", index=False)


@app.callback(
	Output("conteudo", "children"),
	Input("abas", "value"),
	Input("filtro-periodo", "value"),
	Input("filtro-ano-ref", "value"),
	Input("filtro-uf", "value"),
	Input("filtro-etapa", "value"),
	Input("filtro-rede", "value"),
	Input("filtro-municipio", "value"),
)
def atualizar_dashboard(aba, periodo, ano_ref, ufs, etapas, redes, cod_municipio):
	df_categ = filtrar_categoricos(df_ideb, ufs or [], etapas or [], redes or [])
	df_periodo = filtrar_periodo(df_categ, periodo)
	ano_efetivo = obter_ano_efetivo(df_categ, ano_ref)
	df_referencia = df_categ[df_categ["ano"] == ano_efetivo] if ano_efetivo is not None else df_categ.iloc[0:0]

	if aba == "municipio":
		return construir_visao_municipio(df_periodo, df_referencia, cod_municipio, ano_efetivo)
	return construir_visao_geral(df_periodo, df_referencia, ano_efetivo)


if __name__ == "__main__":
	app.run(debug=False, host="0.0.0.0", port=int(os.getenv("PORT", "8050")))