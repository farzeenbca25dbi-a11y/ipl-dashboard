"""IPL Intelligence - Teams & Venues dashboard.  Run: streamlit run app.py"""
import glob
import sqlite3
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

st.set_page_config(page_title="IPL Intelligence", layout="wide")

DATA = Path(__file__).parent / "data"
MIN_V, MIN_T = 10, 30            # min matches to judge a venue / a team
VIOLET, BLUE, GOLD, GREY = "#8B5CF6", "#3B82F6", "#F5C451", "#8B93A7"

# ---------------------------------------------------------------- data layer
ALIAS = {  # raw base name -> canonical ground (spelling variants and renamed grounds)
    "M.Chinnaswamy Stadium": "M Chinnaswamy Stadium",
    "Punjab Cricket Association Stadium": "Punjab Cricket Association IS Bindra Stadium",
    "Zayed Cricket Stadium": "Sheikh Zayed Stadium",
    "Feroz Shah Kotla": "Arun Jaitley Stadium",
    "Sardar Patel Stadium": "Narendra Modi Stadium",
    "Subrata Roy Sahara Stadium": "Maharashtra Cricket Association Stadium",
}


def clean_venue(v):
    base = str(v).split(",")[0].strip()          # drop ", City" suffixes
    return ALIAS.get(base, base)


def find(name):
    hits = glob.glob(str(DATA / f"*{name}.csv")) + glob.glob(str(DATA / f"*{name}.csv.gz"))
    if not hits:
        st.error(f"Missing data file: put *{name}.csv in the data/ folder.")
        st.stop()
    return hits[0]


@st.cache_resource(show_spinner="Building database...")
def get_db():
    m = pd.read_csv(find("matches")).drop_duplicates("match_id")
    m["venue_clean"] = m["venue"].map(clean_venue)
    vn = pd.read_csv(find("venues"))
    vn["venue_clean"] = vn["venue"].map(clean_venue)
    c = pd.concat([m[["venue_clean", "city"]], vn[["venue_clean", "city"]]]).dropna()
    c["city"] = c["city"].replace({"Bangalore": "Bengaluru"})
    m["city"] = m["venue_clean"].map(c.groupby("venue_clean")["city"].agg(lambda s: s.mode().iat[0]))
    d = pd.read_csv(find("deliveries"), usecols=["match_id", "innings", "batting_team",
                                                  "total_runs", "batter_runs", "is_super_over"])
    d = d[(d.is_super_over == 0) & d.innings.isin([1, 2])]
    con = sqlite3.connect(":memory:", check_same_thread=False)
    m[["match_id", "season", "match_date", "venue_clean", "city", "team1", "team2",
       "toss_winner", "toss_decision", "match_winner", "result"]].to_sql("matches", con, index=False)
    d.to_sql("deliveries", con, index=False)
    con.executescript("""
    CREATE VIEW inn AS SELECT match_id, innings, batting_team, SUM(total_runs) runs
        FROM deliveries GROUP BY match_id, innings, batting_team;
    CREATE VIEW mv AS SELECT m.*, a.batting_team AS bat1, a.runs AS r1, b.runs AS r2
        FROM matches m LEFT JOIN inn a ON a.match_id=m.match_id AND a.innings=1
                       LEFT JOIN inn b ON b.match_id=m.match_id AND b.innings=2;
    CREATE VIEW tm AS
        SELECT match_id, season, match_date, venue_clean, city, team1 AS team, team2 AS opp,
               (result!='no result') AS played,
               (result IN ('win','tie') AND match_winner=team1) AS won FROM mv
        UNION ALL
        SELECT match_id, season, match_date, venue_clean, city, team2, team1,
               (result!='no result'),
               (result IN ('win','tie') AND match_winner=team2) FROM mv;
    """)
    return con


@st.cache_data(show_spinner=False)
def _run(sql, params):
    return pd.read_sql_query(sql, get_db(), params=params)


def q(sql, params=()):
    """Run SQL and return a DataFrame (every displayed number goes through here)."""
    return _run(sql, tuple(params))


def W(kind, skip_team=False):
    """Build a WHERE clause from the applied sidebar filters. kind: 'm' (mv) or 't' (tm)."""
    c, p = [], []
    for col, key in (("season", "f_seasons"), ("venue_clean", "f_venues"), ("city", "f_cities")):
        v = st.session_state.get(key) or []
        if v:
            c.append(f"{col} IN ({','.join('?' * len(v))})")
            p += v
    t = [] if skip_team else (st.session_state.get("f_teams") or [])
    if t:
        ph = ",".join("?" * len(t))
        if kind == "m":
            c.append(f"(team1 IN ({ph}) OR team2 IN ({ph}))")
            p += t + t
        else:
            c.append(f"team IN ({ph})")
            p += t
    return "WHERE 1=1" + "".join(f" AND {x}" for x in c), tuple(p)


# ---------------------------------------------------------------- UI helpers
CSS = """<style>
.stApp{background:radial-gradient(1200px 600px at 85% -10%,rgba(139,92,246,.18),transparent 60%),
 radial-gradient(900px 500px at -10% 10%,rgba(59,130,246,.12),transparent 60%),#070A18}
section[data-testid=stSidebar]{background:#0A0E20;border-right:1px solid rgba(255,255,255,.06)}
.block-container{padding-top:3.5rem;max-width:1500px}
.hero{display:flex;align-items:center;gap:22px;padding:18px 26px;margin-bottom:18px;border-radius:18px;
 background:linear-gradient(120deg,rgba(139,92,246,.20),rgba(59,130,246,.07));
 border:1px solid rgba(255,255,255,.08);box-shadow:0 10px 40px rgba(0,0,0,.35)}
.hero h1{margin:0;font-size:2rem;letter-spacing:.22em;font-weight:800;color:#fff}
.hero p{margin:2px 0 0;color:#8B93A7;letter-spacing:.14em;font-size:.82rem;text-transform:uppercase}
.kpi{padding:16px 18px;border-radius:16px;background:rgba(255,255,255,.045);backdrop-filter:blur(8px);
 border:1px solid rgba(255,255,255,.09);box-shadow:0 8px 26px rgba(0,0,0,.3);min-height:116px;transition:.2s}
.kpi:hover{border-color:rgba(139,92,246,.6);transform:translateY(-2px)}
.kl{color:#8B93A7;font-size:.72rem;letter-spacing:.14em;text-transform:uppercase}
.kv{color:#fff;font-size:2rem;font-weight:700;line-height:1.25;margin-top:4px}
.kv.sm{font-size:1.1rem;line-height:1.5;padding-top:6px}
.ks{color:#F5C451;font-size:.78rem;margin-top:2px}
.sec{color:#fff;font-size:1.15rem;font-weight:600;margin:22px 0 4px;padding-left:10px;border-left:3px solid #8B5CF6}
.note{color:#8B93A7;font-size:.82rem}
.obs{padding:10px 14px;margin:6px 0;border-radius:10px;background:rgba(255,255,255,.04);
 border-left:3px solid #F5C451;color:#D5DAEA;font-size:.93rem}
</style>"""

LOGO = """<svg width="92" height="64" viewBox="0 0 92 64"><defs><linearGradient id="g" x1="0" x2="1">
<stop offset="0" stop-color="#8B5CF6"/><stop offset="1" stop-color="#3B82F6"/></linearGradient></defs>
<ellipse cx="46" cy="40" rx="42" ry="20" fill="none" stroke="url(#g)" stroke-width="2"/>
<ellipse cx="46" cy="40" rx="26" ry="11" fill="none" stroke="#ffffff22"/>
<rect x="42" y="30" width="8" height="20" rx="2" fill="#F5C451" opacity=".85"/>
<path d="M8 22 L20 6 M84 22 L72 6 M46 18 L46 2" stroke="#F5C451" stroke-width="1.5" opacity=".7"/></svg>"""


ANIM = """<style>
.hero{position:relative;overflow:hidden;border:1px solid rgba(52,211,153,.55);box-shadow:0 0 26px rgba(52,211,153,.18)}
.hero:before{content:"";position:absolute;right:92px;top:34px;width:16px;height:16px;border-radius:50%;
 background:radial-gradient(circle at 35% 30%,#ff8a8a,#d0212a 60%,#7a0d12);box-shadow:0 0 12px rgba(255,70,70,.8);
 animation:floaty 3.6s ease-in-out infinite reverse}
.hero:after{content:"";position:absolute;right:46px;top:16px;width:11px;height:62px;border-radius:5px 5px 2px 2px;
 background:linear-gradient(#f5d38a,#c9974a);transform:rotate(35deg);box-shadow:0 0 12px rgba(245,196,81,.5);
 animation:floaty 3.6s ease-in-out infinite}
@keyframes floaty{0%,100%{transform:translateY(0) rotate(35deg)}50%{transform:translateY(-8px) rotate(28deg)}}
.strip{position:relative;height:34px;margin:6px 0 2px;border-radius:12px;overflow:hidden;
 background:linear-gradient(90deg,rgba(16,185,129,.20),rgba(59,130,246,.10));border:1px solid rgba(52,211,153,.25)}
.strip:before{content:"";position:absolute;left:5%;right:5%;top:50%;height:1px;
 background:repeating-linear-gradient(90deg,rgba(255,255,255,.28) 0 6px,transparent 6px 14px)}
.ball{position:absolute;top:50%;left:4%;width:14px;height:14px;margin-top:-7px;border-radius:50%;
 background:radial-gradient(circle at 35% 30%,#ff8a8a,#d0212a 60%,#7a0d12);box-shadow:0 0 10px rgba(255,70,70,.85);
 animation:bowl 3.4s ease-in infinite}
.bat{position:absolute;top:50%;right:5%;width:7px;height:26px;margin-top:-13px;border-radius:3px 3px 1px 1px;
 background:linear-gradient(#f5d38a,#c9974a);transform-origin:50% 100%;box-shadow:0 0 8px rgba(245,196,81,.55);
 animation:swing 3.4s ease-in-out infinite}
@keyframes bowl{0%{left:4%;opacity:0}6%{opacity:1}55%{left:calc(95% - 34px);opacity:1}100%{left:108%;opacity:0}}
@keyframes swing{0%,48%{transform:rotate(20deg)}58%{transform:rotate(-60deg)}85%,100%{transform:rotate(20deg)}}
</style>"""
STRIP = '<div class="strip"><div class="ball"></div><div class="bat"></div></div>'


def kpi(label, value, sub="", small=False):
    return (f'<div class="kpi"><div class="kl">{label}</div>'
            f'<div class="kv{" sm" if small else ""}">{value}</div><div class="ks">{sub}</div></div>')


def sec(t):
    st.markdown(f'<div class="sec">{t}</div>', unsafe_allow_html=True)


def show(fig, h=380, title=None, side_legend=False):
    legend = (dict(orientation="v", x=1.02, y=0.5, title_text="") if side_legend
              else dict(orientation="h", x=0, y=1.0, yanchor="bottom", title_text=""))
    fig.update_layout(
        template="plotly_dark", height=h, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#C9D1E4"), legend=legend, hoverlabel=dict(bgcolor="#14172B", bordercolor=VIOLET),
        margin=dict(l=10, r=190 if side_legend else 20, t=95 if title else 40, b=10),
        title=dict(text=title, font=dict(size=16, color="#fff"), x=0.01, y=0.96, yanchor="top") if title else None)
    fig.update_xaxes(gridcolor="rgba(255,255,255,.06)", zeroline=False)
    st.markdown(STRIP, unsafe_allow_html=True)
    st.plotly_chart(fig)


def empty(df):
    if df.empty:
        st.info("No data for the current filters.")
    return df.empty


def pick(label, options, key):
    """Filter box above one chart. Leave it empty to show everything."""
    chosen = st.multiselect(label, options, key=key, placeholder="All")
    return chosen or options


def hbar(df, x, y, **kw):
    fig = px.bar(df, x=x, y=y, orientation="h", **kw)
    fig.update_yaxes(autorange="reversed", title=None)
    return fig


# ---------------------------------------------------------------- sidebar
def sidebar():
    st.sidebar.markdown("### IPL INTELLIGENCE")
    page = st.sidebar.radio("Navigate", ["Overview", "Teams", "Venues", "Insights"], label_visibility="collapsed")
    seasons = q("SELECT season FROM matches GROUP BY season ORDER BY MIN(match_date)").season.tolist()
    teams = q("SELECT team1 AS t FROM matches UNION SELECT team2 FROM matches ORDER BY 1").t.tolist()
    vdf = q("SELECT venue_clean v, COUNT(*) n FROM matches GROUP BY v ORDER BY n DESC")
    cities = q("SELECT DISTINCT city FROM matches WHERE city IS NOT NULL ORDER BY 1").city.tolist()
    counts = dict(zip(vdf.v, vdf.n))
    with st.sidebar.form("filters"):
        st.multiselect("Season", seasons, key="f_seasons", placeholder="All seasons")
        st.multiselect("Team", teams, key="f_teams", placeholder="All teams")
        st.multiselect("Venue", vdf.v.tolist(), key="f_venues", placeholder="All venues",
                       format_func=lambda v: f"{v} ({counts[v]})")
        st.multiselect("City", cities, key="f_cities", placeholder="All cities")
        st.form_submit_button("Apply Filters")

    def reset():
        for k in ("f_seasons", "f_teams", "f_venues", "f_cities"):
            st.session_state[k] = []
    st.sidebar.button("Reset Filters", on_click=reset)

    act = [f"{n}: {', '.join(st.session_state.get(k) or [])}" for n, k in
           (("Season", "f_seasons"), ("Team", "f_teams"), ("Venue", "f_venues"), ("City", "f_cities"))
           if st.session_state.get(k)]
    st.sidebar.markdown('<div class="note"><b>Active filters</b><br>' + ("<br>".join(act) or "None - full dataset")
                        + "</div>", unsafe_allow_html=True)
    s = q("SELECT COUNT(*) n, MIN(match_date) a, MAX(match_date) b FROM matches").iloc[0]
    st.sidebar.markdown(f'<div class="note" style="margin-top:14px"><span style="color:#34D399">&#9679;</span> '
                        f'Dataset loaded - {s.n:,} matches, {s.a[:4]}-{s.b[:4]}</div>', unsafe_allow_html=True)
    return page


# ---------------------------------------------------------------- pages
def page_overview():
    wm, pm = W("m")
    wt, pt = W("t")
    k = q(f"""SELECT COUNT(*) n, COUNT(DISTINCT venue_clean) v,
              ROUND(1.0*COUNT(*)/COUNT(DISTINCT venue_clean),1) apv FROM mv {wm}""", pm).iloc[0]
    nt = q(f"SELECT COUNT(DISTINCT team) n FROM tm {wt}", pt).n[0]
    best = q(f"SELECT team, SUM(won) w FROM tm {wt} GROUP BY team ORDER BY w DESC LIMIT 1", pt)
    busy = q(f"SELECT venue_clean v, COUNT(*) n FROM mv {wm} GROUP BY v ORDER BY n DESC LIMIT 1", pm)
    c = st.columns(6)
    cards = [("Total Teams", f"{nt}", ""), ("Total Venues", f"{int(k.v)}", "cleaned grounds"),
             ("Total Matches", f"{int(k.n):,}", ""),
             ("Most Successful Team", best.team[0], f"{best.w[0]} wins", True),
             ("Busiest Venue", busy.v[0], f"{busy.n[0]} matches", True),
             ("Avg Matches / Venue", f"{k.apv}", "")]
    for col, cd in zip(c, cards):
        col.markdown(kpi(*cd), unsafe_allow_html=True)
    if k.n == 0:
        st.warning("No matches for the current filters.")
        return

    sec("Team record")
    t = q(f"""SELECT team, SUM(played) played, SUM(won) wins FROM tm {wt}
              GROUP BY team ORDER BY wins DESC""", pt)
    sel = pick("Filter teams in this chart", t.team.tolist(), "ov_teams")
    t = t[t.team.isin(sel)]
    fig = go.Figure([go.Bar(y=t.team, x=t.played, orientation="h", name="Matches played", marker_color="#2A3358"),
                     go.Bar(y=t.team, x=t.wins, orientation="h", name="Wins", marker_color=VIOLET,
                            text=t.wins, textposition="outside")])
    fig.update_layout(barmode="group")
    fig.update_yaxes(autorange="reversed")
    show(fig, 560, "Who wins the most? Wins against matches played")

    a, b = st.columns(2)
    v = q(f"SELECT venue_clean venue, COUNT(*) matches FROM mv {wm} GROUP BY venue_clean ORDER BY matches DESC LIMIT 15", pm)
    with a:
        sel = pick("Filter grounds in this chart", v.venue.tolist(), "ov_venues")
        v = v[v.venue.isin(sel)].copy()
        v["Sample"] = v.matches.map(lambda n: "Enough to judge" if n >= MIN_V else "Small sample")
        f = hbar(v, "matches", "venue", color="Sample", text="matches",
                 color_discrete_map={"Enough to judge": VIOLET, "Small sample": "#4B5575"})
        f.add_vline(x=MIN_V, line_dash="dash", line_color=GOLD, annotation_text=f"cut-off {MIN_V}")
        show(f, 440, "Matches hosted by ground (top 15)")
    lg = q(f"""SELECT ROUND(100.0*SUM(match_winner=bat1)/COUNT(*),1) p FROM mv {wm} AND result='win'""".replace(
        "WHERE 1=1", "WHERE 1=1", 1), pm).p[0]
    bf = q(f"""SELECT venue_clean venue, COUNT(*) decided,
               ROUND(100.0*SUM(match_winner=bat1)/COUNT(*),1) bat_first_win_pct FROM mv
               {wm} AND result='win' GROUP BY venue_clean HAVING decided>={MIN_V}
               ORDER BY bat_first_win_pct DESC""", pm)
    with b:
        sel = pick("Filter grounds in this chart", bf.venue.tolist(), "ov_bf")
        bf = bf[bf.venue.isin(sel)]
        if not empty(bf):
            f = hbar(bf, "bat_first_win_pct", "venue", text="decided", color_discrete_sequence=[BLUE],
                     hover_data=["decided"])
            f.update_traces(texttemplate="n=%{text}")
            f.add_vline(x=lg, line_dash="dash", line_color=GOLD, annotation_text=f"league {lg}%")
            show(f, 440, f"Does batting first win? Grounds with {MIN_V}+ decided matches")

    sec("Ground usage over time")
    s = q(f"""SELECT season, COUNT(DISTINCT venue_clean) grounds, COUNT(*) matches FROM mv {wm}
              GROUP BY season ORDER BY MIN(match_date)""", pm)
    sel = pick("Filter seasons in this chart", s.season.tolist(), "ov_seasons")
    s = s[s.season.isin(sel)]
    f = px.bar(s, x="season", y="grounds", hover_data=["matches"], color_discrete_sequence=[VIOLET])
    show(f, 320, "Number of grounds used per season")


def page_teams():
    wt, pt = W("t")
    wc, pc = W("t", skip_team=True)
    sec("Team ranking")
    r = q(f"""SELECT ROW_NUMBER() OVER (ORDER BY 1.0*SUM(won)/NULLIF(SUM(played),0) DESC, SUM(played) DESC) AS "#",
              team AS Team, SUM(played) AS Matches, SUM(won) AS Wins, SUM(played)-SUM(won) AS Losses,
              ROUND(100.0*SUM(won)/NULLIF(SUM(played),0),1) AS "Win %",
              CASE WHEN SUM(played)>={MIN_T} THEN 'OK' ELSE 'Small sample' END AS Sample
              FROM tm {wt} GROUP BY team HAVING SUM(played)>0 ORDER BY "#" """, pt)
    if empty(r):
        return
    st.dataframe(r, hide_index=True, height=min(620, 36 * (len(r) + 1) + 3), column_config={"Win %": st.column_config.ProgressColumn(
        "Win %", min_value=0, max_value=100, format="%.1f")})
    a, b = st.columns([3, 2])
    with a:
        sel = pick("Filter teams in this chart", r.Team.tolist(), "tm_wl")
        m = r[r.Team.isin(sel)].melt(id_vars="Team", value_vars=["Wins", "Losses"], var_name="Outcome", value_name="Count")
        f = hbar(m, "Count", "Team", color="Outcome", barmode="stack",
                 color_discrete_map={"Wins": VIOLET, "Losses": "#2A3358"})
        show(f, 480, "Wins and losses by team (sorted by win %)")
    with b:
        sel2 = pick("Filter teams in this chart", r.Team.tolist(), "tm_pie")
        f = px.pie(r[r.Team.isin(sel2)], names="Team", values="Wins", hole=.58, color_discrete_sequence=px.colors.sequential.Purples_r +
                   px.colors.sequential.Blues_r)
        f.update_traces(textinfo="none")
        show(f, 480, "Share of all wins", side_legend=True)

    sec("Compare two teams")
    all_t = q("SELECT team1 AS t FROM matches UNION SELECT team2 FROM matches ORDER BY 1").t.tolist()
    names = [t for t in r.Team.tolist() if t in all_t] + all_t   # ranked teams first
    c1, c2 = st.columns(2)
    A = c1.selectbox("Team A", all_t, index=all_t.index(names[0]))
    B = c2.selectbox("Team B", all_t, index=all_t.index(next(t for t in names if t != names[0])))
    if A == B:
        st.info("Pick two different teams.")
        return
    cols = st.columns(3)
    for col, T in ((cols[0], A), (cols[2], B)):
        x = q(f"""SELECT SUM(played) p, SUM(won) w, ROUND(100.0*SUM(won)/NULLIF(SUM(played),0),1) wp
                  FROM tm {wc} AND team=?""", pc + (T,)).iloc[0]
        col.markdown(kpi(T, f"{x.wp if pd.notna(x.wp) else '-'}%", f"{x.w or 0} wins / {x.p or 0} matches", True),
                     unsafe_allow_html=True)
    h = q(f"""SELECT COALESCE(SUM(won),0) w, COALESCE(SUM(played),0) p, COALESCE(SUM(played)-SUM(won),0) l
              FROM tm {wc} AND team=? AND opp=?""", pc + (A, B)).iloc[0]
    cols[1].markdown(kpi("Head to head", f"{h.w} - {h.l}", f"{h.p} matches", True), unsafe_allow_html=True)
    s = q(f"""SELECT team, season, SUM(played) matches, ROUND(100.0*SUM(won)/NULLIF(SUM(played),0),1) win_pct
              FROM tm {wc} AND team IN (?,?) GROUP BY team, season HAVING matches>0 ORDER BY season""", pc + (A, B))
    if not empty(s):
        f = px.line(s, x="season", y="win_pct", color="team", markers=True, hover_data=["matches"],
                    color_discrete_sequence=[VIOLET, GOLD])
        f.add_hline(y=50, line_dash="dash", line_color=GREY, annotation_text="50%")
        show(f, 380, "Win rate by season")


def page_venues():
    wm, pm = W("m")
    v = q(f"""SELECT ROW_NUMBER() OVER (ORDER BY COUNT(*) DESC) AS "#", venue_clean AS Venue, city AS City,
              COUNT(*) AS Matches, ROUND(AVG(r1),1) AS "Avg 1st inns", ROUND(AVG(r2),1) AS "Avg 2nd inns",
              ROUND(100.0*SUM(result='win' AND match_winner=bat1)/NULLIF(SUM(result='win'),0),1) AS "Bat-first win %",
              ROUND(100.0*SUM(toss_decision='field')/COUNT(*),1) AS "Toss: field %"
              FROM mv {wm} GROUP BY venue_clean, city ORDER BY Matches DESC""", pm)
    if empty(v):
        return
    sec("Matches hosted")
    n = st.slider("Venues to show", 5, max(6, min(30, len(v))), min(15, len(v)))
    f = hbar(v.head(n), "Matches", "Venue", text="Matches", color_discrete_sequence=[VIOLET], hover_data=["City"])
    show(f, 30 * n + 80, "Matches hosted by ground")
    st.dataframe(v, hide_index=True)
    st.markdown('<div class="note">Venue map not shown: the dataset has no venue coordinates.</div>',
                unsafe_allow_html=True)

    sec("Scoring by ground")
    mn = st.slider("Minimum matches per venue", 1, 40, MIN_V)
    lg = q(f"SELECT ROUND(AVG(r1),1) a1, ROUND(AVG(r2),1) a2 FROM mv {wm}", pm).iloc[0]
    sc = v[v.Matches >= mn].sort_values("Avg 1st inns", ascending=False).head(20)
    sel = pick("Filter grounds in this chart", sc.Venue.tolist(), "vn_sc")
    sc = sc[sc.Venue.isin(sel)]
    if not empty(sc):
        m = sc.melt(id_vars=["Venue", "Matches"], value_vars=["Avg 1st inns", "Avg 2nd inns"],
                    var_name="Innings", value_name="Avg runs")
        f = hbar(m, "Avg runs", "Venue", color="Innings", barmode="group", hover_data=["Matches"],
                 color_discrete_map={"Avg 1st inns": VIOLET, "Avg 2nd inns": BLUE})
        f.add_vline(x=lg.a1, line_dash="dash", line_color=GOLD, annotation_text=f"league 1st: {lg.a1}")
        show(f, 36 * len(sc) + 100, "Average first vs second innings score")

    sec("Compare venues")
    top = v.Venue.head(2).tolist()
    sel = st.multiselect("Choose up to two venues", v.Venue.tolist(), default=top, max_selections=2)
    cmp_ = v[v.Venue.isin(sel)]
    if cmp_.empty:
        return
    cols = st.columns(len(cmp_))
    for col, (_, r) in zip(cols, cmp_.iterrows()):
        col.markdown(kpi(r.Venue, f"{r.Matches} matches",
                         f"1st: {r['Avg 1st inns']} | 2nd: {r['Avg 2nd inns']} | league 1st: {lg.a1}", True),
                     unsafe_allow_html=True)
        if r.Matches < MIN_V:
            col.caption("Small sample - treat patterns as indicative only.")
    a, b = st.columns(2)
    d = cmp_.assign(**{"Chasing win %": (100 - cmp_["Bat-first win %"]).round(1)})
    m = d.melt(id_vars=["Venue", "Matches"], value_vars=["Bat-first win %", "Chasing win %"], var_name="Strategy",
               value_name="Win %")
    f = px.bar(m, x="Venue", y="Win %", color="Strategy", barmode="group", hover_data=["Matches"],
               color_discrete_map={"Bat-first win %": VIOLET, "Chasing win %": GOLD})
    f.add_hline(y=50, line_dash="dash", line_color=GREY)
    with a:
        show(f, 340, "Batting first vs chasing (decided matches)")
    t = cmp_.assign(**{"Bat first": (100 - cmp_["Toss: field %"]).round(1)}).rename(columns={"Toss: field %": "Field first"})
    m = t.melt(id_vars="Venue", value_vars=["Bat first", "Field first"], var_name="Toss decision", value_name="Share %")
    with b:
        show(px.bar(m, x="Venue", y="Share %", color="Toss decision", barmode="stack",
                    color_discrete_map={"Bat first": BLUE, "Field first": VIOLET}), 340, "What toss winners choose")


def page_insights():
    wm, pm = W("m")
    wt, pt = W("t")
    sec("Key findings")
    obs = []
    t = q(f"""SELECT team, SUM(played) p, SUM(won) w, ROUND(100.0*SUM(won)/SUM(played),1) wp FROM tm {wt}
              GROUP BY team HAVING p>={MIN_T} ORDER BY wp DESC, p DESC LIMIT 1""", pt)
    if len(t):
        obs.append(f"Highest win rate (min {MIN_T} matches): <b>{t.team[0]}</b> at {t.wp[0]}% ({t.w[0]} of {t.p[0]}).")
    b = q(f"SELECT venue_clean v, COUNT(*) n FROM mv {wm} GROUP BY v ORDER BY n DESC LIMIT 1", pm)
    if len(b):
        obs.append(f"Busiest venue: <b>{b.v[0]}</b> with {b.n[0]} matches.")
    s = q(f"""SELECT venue_clean v, COUNT(*) n, ROUND(AVG(r1),1) a FROM mv {wm} GROUP BY v
              HAVING n>={MIN_V} ORDER BY a DESC""", pm)
    if len(s):
        obs.append(f"Highest average first-innings score (min {MIN_V} matches): <b>{s.v[0]}</b> ({s.a[0]}, n={s.n[0]}); "
                   f"lowest: <b>{s.v.iloc[-1]}</b> ({s.a.iloc[-1]}, n={s.n.iloc[-1]}).")
    c = q(f"""SELECT venue_clean v, COUNT(*) n, ROUND(100.0*SUM(match_winner=bat1)/COUNT(*),1) p FROM mv
              {wm} AND result='win' GROUP BY v HAVING n>={MIN_V} ORDER BY p DESC""", pm)
    if len(c):
        obs.append(f"Batting first has won most often at <b>{c.v[0]}</b> ({c.p[0]}%, n={c.n[0]}) and least often at "
                   f"<b>{c.v.iloc[-1]}</b> ({c.p.iloc[-1]}%, n={c.n.iloc[-1]}).")
    tw = q(f"""SELECT COUNT(*) n, ROUND(100.0*SUM(toss_winner=match_winner)/COUNT(*),1) p FROM mv {wm} AND result='win'""", pm)
    if tw.n[0]:
        obs.append(f"Toss winners won {tw.p[0]}% of {tw.n[0]} decided matches - an association, not proof the toss causes wins.")
    for o in obs:
        st.markdown(f'<div class="obs">{o}</div>', unsafe_allow_html=True)
    if not obs:
        st.info("No data for the current filters.")
        return
    st.markdown('<div class="note">Home-ground advantage is not assessed: the data has no home-team field. '
                'Findings describe patterns in these matches and do not establish causes.</div>', unsafe_allow_html=True)

    sec("Team performance by ground (minimum 6 matches)")
    base = f"""SELECT team AS Team, venue_clean AS Venue, SUM(played) AS Matches, SUM(won) AS Wins,
               ROUND(100.0*SUM(won)/SUM(played),1) AS "Win %" FROM tm {wt}
               GROUP BY team, venue_clean HAVING Matches>=6 ORDER BY "Win %" {{o}}, Matches DESC LIMIT 8"""
    a, b2 = st.columns(2)
    with a:
        st.markdown("**Strongest records**")
        st.dataframe(q(base.format(o="DESC"), pt), hide_index=True)
    with b2:
        st.markdown("**Weakest records**")
        st.dataframe(q(base.format(o="ASC"), pt), hide_index=True)


# ---------------------------------------------------------------- main
st.markdown(CSS + ANIM, unsafe_allow_html=True)
st.markdown(f'<div class="hero">{LOGO}<div><h1>IPL INTELLIGENCE</h1>'
            '<p>Teams &bull; Venues &bull; Match Insights</p></div></div>', unsafe_allow_html=True)
page = sidebar()
{"Overview": page_overview, "Teams": page_teams, "Venues": page_venues, "Insights": page_insights}[page]()
