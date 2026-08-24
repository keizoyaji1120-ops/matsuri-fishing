import streamlit as st
import pandas as pd
import json
import urllib.request
import urllib.parse
import datetime
import math
import ssl
import matplotlib.pyplot as plt
import warnings

# --- 設定 ---
warnings.filterwarnings("ignore")
st.set_page_config(page_title="魔釣 - 瀬戸内タイラバ予報 v8.1", page_icon="🎣", layout="wide")

# --- CSS ---
st.markdown("""
    <style>
    div[data-testid="stDataFrame"] div[role="columnheader"],
    div[data-testid="stDataFrame"] th {
        pointer-events: none !important;
        cursor: default !important;
    }
    table.matsuri-table {
        width: 100%;
        border-collapse: collapse;
        font-family: "Hiragino Kaku Gothic ProN", "Hiragino Sans", Meiryo, sans-serif;
        font-size: 14px;
        color: #2c3e50;
        margin-bottom: 20px;
        box-shadow: 0 4px 10px rgba(0,0,0,0.05);
        border-radius: 8px;
        overflow: hidden;
    }
    table.matsuri-table th {
        background-color: #1a252f;
        color: #ffffff;
        font-weight: bold;
        padding: 12px 6px;
        text-align: center;
        white-space: nowrap;
    }
    table.matsuri-table td {
        padding: 10px 6px;
        text-align: center;
        border-bottom: 1px solid #ecf0f1;
        vertical-align: middle;
        line-height: 1.5;
    }
    table.matsuri-table tr:nth-child(even) { background-color: #fbfbfc; }
    table.matsuri-table tr:hover { background-color: #e8f4f8; }
    .col-time { width: 16%; font-weight: bold; font-size: 13px; white-space: nowrap; background-color: #f8f9fa;}
    .col-honmei { width: 22%; color: #c0392b; font-weight: bold; }
    .col-osae { width: 22%; color: #2980b9; }
    .col-tac { width: 18%; font-size: 12px; font-weight: bold;}
    .col-note { width: 22%; font-size: 11px; text-align: left; color: #7f8c8d; }
    
    @media (max-width: 640px) {
        table.matsuri-table { font-size: 11px; }
        .col-time { font-size: 11px; }
        .col-tac { font-size: 10px; }
    }
    </style>
""", unsafe_allow_html=True)

# --- 海域データ設定 ---
AREA_DATA = {
    "明石": {
        "lat": 34.60, "lon": 135.00, 
        "base_slack": 5.5, # 明石の転流基準(大潮時: 約5:30)
        "depths": [30, 45, 60],
        "name_en": "Akashi",
        "kaiho_url": "https://www1.kaiho.mlit.go.jp/KAN5/tyouryuu/stream_akashi.html",
        "checker_url": "https://matsuri-akashi-checker-4qw73q6qju7ppzztkyagpu.streamlit.app/"
    },
    "鳴門": {
        "lat": 34.22, "lon": 134.64, 
        "base_slack": 4.5, # 鳴門の転流基準(大潮時: 約4:30)
        "depths": [40, 60, 80],
        "name_en": "Naruto",
        "kaiho_url": "https://www1.kaiho.mlit.go.jp/KAN5/tyouryuu/stream_naruto.html",
        "checker_url": None
    },
    "小豆島": {
        "lat": 34.46, "lon": 134.29, 
        "base_slack": 7.0, # 小豆島の転流基準(大潮時: 約7:00)
        "depths": [30, 40, 50],
        "name_en": "Shodoshima",
        "kaiho_url": "https://www1.kaiho.mlit.go.jp/KAN6/kyou/bisan/bisan_info.html",
        "checker_url": None
    },
    "瀬戸大橋": {
        "lat": 34.39, "lon": 133.82, 
        "base_slack": 8.5, # 備讃瀬戸の転流基準(大潮時: 約8:30)
        "depths": [30, 45, 60],
        "name_en": "Seto-Ohashi",
        "kaiho_url": "https://www1.kaiho.mlit.go.jp/KAN6/kyou/bisan/bisan_info.html",
        "checker_url": None
    }
}

HISTORICAL_TEMPS = {
    1: 10.5, 2: 9.8, 3: 10.5, 4: 13.0, 5: 17.5, 6: 21.0,
    7: 25.5, 8: 27.0, 9: 25.5, 10: 22.0, 11: 18.0, 12: 14.0
}

# --- 関数群 ---
@st.cache_data(ttl=3600)
def make_request(url):
    req = urllib.request.Request(url)
    req.add_header('User-Agent', 'Mozilla/5.0 (App; CPU iPhone OS 15_0)')
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=10) as res:
            return json.loads(res.read().decode())
    except Exception:
        return None

def get_moon_age(date):
    year, month, day = date.year, date.month, date.day
    age = (((year - 2009) % 19) * 11 + month + day) % 30
    if month <= 2: age += 2
    return age % 30

def get_sinker_weight(moon_age, depth):
    STANDARD_SINKERS = [30, 45, 60, 80, 100, 120, 150, 180, 200, 250, 300]
    age_norm = moon_age % 15
    if age_norm <= 2 or age_norm >= 13:
        tide_name = "大潮(激)"
        mult_min, mult_max = 2.0, 2.5
    elif 3 <= age_norm <= 5 or 10 <= age_norm <= 12:
        tide_name = "中潮(速)"
        mult_min, mult_max = 1.5, 2.0
    else:
        tide_name = "小潮(緩)"
        mult_min, mult_max = 1.0, 1.5

    raw_min = depth * mult_min
    raw_max = depth * mult_max

    def get_closest_sinker(val):
        return min(STANDARD_SINKERS, key=lambda x: abs(x - val))

    w_min = get_closest_sinker(raw_min)
    w_max = get_closest_sinker(raw_max)
    if w_min > w_max: w_min = w_max
    return tide_name, f"{w_min}g" if w_min == w_max else f"{w_min}g〜{w_max}g"

# 【修正】転流(潮止まり)時間を基準にし、潮流の速さを正確に計算するロジック
def estimate_current_speed(moon_age, hour, base_slack):
    delay = 0.8 # 月の出の遅れによる時差(約48分/日)
    slack_time = (base_slack + (moon_age % 15) * delay) % 12
    diff = abs(hour - slack_time)
    if diff > 6: diff = 12 - diff
    
    # 潮流の速さ(0.0:完全に止まる 〜 1.0:最速)
    speed = math.sin(diff * (math.pi / 6))
    
    # スピードが0.25未満(転流前後約45分)を「潮止まり」と判定
    is_slack = speed < 0.25 
    return speed, is_slack

def get_seasonal_bait(month):
    if month in [12, 1, 2]: return "海苔(ノリ)", "黒・緑・濃い茶"
    elif month in [3, 4, 5]: return "イカナゴ", "ミドキン・緑・オレ金"
    elif month in [6, 7]: return "イカ・タコ", "グロー・ゼブラ・金"
    elif month in [8, 9, 10, 11]: return "イワシ・エビ", "オレンジ・赤・金"
    else: return "混合", "赤オレ"

def suggest_strategy(h, sun_h, sc, t_diff, month, temp, cloud_cover, rain):
    c1 = "赤オレ" if h % 2 == 0 else "オレンジ"
    s1 = "極細"
    speed = "普通"
    hook = "M"

    is_nori_season = month in [12, 1, 2, 3, 4]

    if rain >= 0.5: c1 = "チャート" if h % 2 == 0 else "ソリッドレッド"
    elif h <= sun_h: c1 = "チャート" if h % 2 == 0 else "赤ゼブラ"
    elif t_diff <= -0.1: c1 = "コーラ" if h % 2 == 0 else "赤黒"
    elif month in [3, 4, 5]: c1 = "ミドキン" if h % 2 == 0 else "グリーン"
    elif is_nori_season and (temp < 13.0 or sc < 45): c1 = "黒/海苔" if h % 2 == 0 else "コーラ"
    elif cloud_cover > 70: c1 = "チャート" if h % 2 == 0 else "赤ゼブラ"
    elif h <= sun_h + 2: c1 = "オレ金" if h % 2 == 0 else "マジョーラゼブラ"
    
    if rain >= 0.5: s1 = "ワイドカーリー"
    elif month in [6, 7, 8] and sc >= 40: s1 = "ロングカーリー"
    elif sc >= 50: s1 = "強波動"
    elif sc >= 30: s1 = "ショート"
    elif sc >= 20: s1 = "ストレート"
    else: s1 = "極細"
    
    if temp >= 18.0 and sc >= 40: speed = "早巻"
    elif temp <= 12.0 or sc <= 20: speed = "激遅"
    elif sc >= 30: speed = "普通"
    else: speed = "遅め"

    if month in [12, 1, 2] and (temp < 10.0 or sc < 30): hook = "3S"
    elif month in [3, 4]: hook = "SS"
    elif speed == "激遅" or sc < 40: hook = "S"
    elif temp >= 22.0 and sc >= 50: hook = "L"
    else: hook = "M"

    worm_option = "+ワーム" if sc <= 10 else ""

    c2 = "グリーン"; s2 = "ショート"
    if c1 == "チャート": c2 = "オレ金"
    elif c1 == "ソリッドレッド": c2 = "チャート"
    elif c1 == "赤ゼブラ": c2 = "オレンジ"
    elif c1 == "ミドキン": c2 = "オレ金"
    elif c1 == "オレ金": c2 = "ピンク"
    elif c1 == "マジョーラゼブラ": c2 = "ピンク"
    elif c1 == "ピンク": c2 = "赤オレ"
    elif c1 == "コーラ": c2 = "赤黒"
    elif c1 == "赤黒": c2 = "コーラ"
    elif c1 == "黒/海苔": c2 = "コーラ"
    elif c1 == "赤オレ": c2 = "マジョーラゼブラ"
    elif c1 == "オレンジ": c2 = "赤オレ"
    elif c1 == "グリーン": c2 = "ミドキン"
    
    if s1 == "ロングカーリー": s2 = "ショート"
    elif s1 == "ワイドカーリー": s2 = "カーリー"
    elif s1 == "強波動": s2 = "ショート"
    elif s1 == "ショート": s2 = "極細"
    elif s1 == "ストレート": s2 = "ショート"
    else: s2 = "カーリー"
    
    return f"{c1}×{s1}", f"{c2}×{s2}", speed, hook, worm_option

@st.cache_data(ttl=3600)
def get_weather_data(target_date, lat, lon):
    bm = "https://marine-api.open-meteo.com/v1/marine"
    bw = "https://api.open-meteo.com/v1/forecast"
    d_str = target_date.strftime("%Y-%m-%d")
    y_str = (target_date - datetime.timedelta(days=1)).strftime("%Y-%m-%d")
    
    p_temp = {
        "latitude": lat, "longitude": lon, 
        "hourly": "sea_surface_temperature", 
        "start_date": y_str, "end_date": d_str, "timezone": "Asia/Tokyo"
    }
    p_weather = {
        "latitude": lat, "longitude": lon, 
        "daily": "sunrise", "hourly": "cloud_cover,wind_speed_10m,rain",
        "start_date": d_str, "end_date": d_str, "timezone": "Asia/Tokyo"
    }
    return make_request(f"{bm}?{urllib.parse.urlencode(p_temp)}"), make_request(f"{bw}?{urllib.parse.urlencode(p_weather)}")

# --- メイン画面 ---
def main():
    st.markdown("""
        <h1 style='text-align: center; font-size: 38px; margin-bottom: 5px; font-weight: 800;'>
            <span style='margin-right: 0.5em;'>🌊 魔釣</span><br>
            <span style='font-size: 24px; font-weight: normal; color: #555;'>瀬戸内タイラバ予報</span>
        </h1>
        <p style='text-align: center; font-size: 13px; color: gray; margin-bottom: 20px;'>
            瀬戸内海の各海域の潮流・水温・天気から「攻め時」と「戦略」を解析します。
        </p>
    """, unsafe_allow_html=True)

    # 【修正】日本時間(JST)を基準にして日付のズレを防止
    JST = datetime.timezone(datetime.timedelta(hours=9), 'JST')
    today_jst = datetime.datetime.now(JST).date()

    sel_col1, sel_col2 = st.columns(2)
    with sel_col1:
        selected_area = st.selectbox("🌍 海域を選択してください", list(AREA_DATA.keys()))
    with sel_col2:
        target_date = st.date_input("📅 釣行日を選択してください", today_jst + datetime.timedelta(days=1))
    
    area_info = AREA_DATA[selected_area]
    d_str = target_date.strftime("%Y-%m-%d")
    y_str = (target_date - datetime.timedelta(days=1)).strftime("%Y-%m-%d")
    
    bait_name, bait_colors = get_seasonal_bait(target_date.month)
    st.info(f"🐟 **{selected_area}のシーズナルパターン: {bait_name}** （有効カラー目安: {bait_colors}）")

    if st.button(f"🎯 {selected_area}の魔釣予報を開始する", use_container_width=True):
        try:
            with st.spinner(f'{selected_area}の海況・気象データを解析中...'):
                mage = get_moon_age(target_date)
                
                d1, d2, d3 = area_info["depths"]
                tname, s_d1 = get_sinker_weight(mage, d1)
                _, s_d2 = get_sinker_weight(mage, d2)
                _, s_d3 = get_sinker_weight(mage, d3)
                
                sd, wd = get_weather_data(target_date, area_info["lat"], area_info["lon"])
                
                sun_h = 6
                if wd and "daily" in wd and "sunrise" in wd["daily"] and wd["daily"]["sunrise"]:
                    sun_h = int(wd["daily"]["sunrise"][0].split('T')[1].split(':')[0])
                
                # 【修正】文字列完全一致でデータを取得する関数（時間ズレ絶対防止）
                def get_val_at_time(data, key, target_time):
                    if not data or "hourly" not in data or "time" not in data["hourly"] or key not in data["hourly"]: return None
                    times = data["hourly"]["time"]
                    if target_time in times:
                        return data["hourly"][key][times.index(target_time)]
                    return None

                # 前日・当日の平均水温の計算
                temps_yesterday = []
                temps_today = []
                if sd and "hourly" in sd and "time" in sd["hourly"]:
                    for i, t_str in enumerate(sd["hourly"]["time"]):
                        val = sd["hourly"]["sea_surface_temperature"][i]
                        if val is not None:
                            if t_str.startswith(y_str): temps_yesterday.append(val)
                            elif t_str.startswith(d_str): temps_today.append(val)

                use_historical = False
                day_trend_score = 0
                diff_day = 0
                temps_today_avg = 0

                if not temps_today:
                    use_historical = True
                    avg_temp = HISTORICAL_TEMPS.get(target_date.month, 15.0)
                    temps_today_avg = avg_temp
                else:
                    temps_today_avg = sum(temps_today) / len(temps_today)
                    if temps_yesterday:
                        avg_yesterday = sum(temps_yesterday) / len(temps_yesterday)
                        diff_day = temps_today_avg - avg_yesterday
                        if diff_day <= -0.5: day_trend_score = -20
                        elif diff_day >= 0.5: day_trend_score = 10
                
                min_t = min(temps_today) if temps_today else temps_today_avg
                max_t = max(temps_today) if temps_today else temps_today_avg

                st.success("解析完了！")
                
                st.markdown(f"### 📊 本日のコンディション ({selected_area})")
                m_col1, m_col2, m_col3 = st.columns(3)
                
                with m_col1:
                    st.metric(label="月齢・潮回り", value=f"{mage:.1f}", delta=tname, delta_color="off")
                with m_col2:
                    if use_historical:
                        st.metric(label="予想水温 (平年値)", value=f"{temps_today_avg:.1f}℃", delta="長期予報", delta_color="off")
                    else:
                        st.metric(label="予想平均水温 (前日比)", value=f"{temps_today_avg:.1f}℃", delta=f"{diff_day:+.1f}℃")
                with m_col3:
                    st.metric(label="日の出時刻", value=f"{sun_h}:00頃", delta="朝マズメの目安", delta_color="off")
                
                st.markdown("##### ⚓ 推奨シンカー (目安)")
                s_col1, s_col2, s_col3 = st.columns(3)
                s_col1.info(f"**水深{d1}m**: {s_d1}")
                s_col2.info(f"**水深{d2}m**: {s_d2}")
                s_col3.info(f"**水深{d3}m**: {s_d3}")
                
                st.markdown("---")

                hl, sl, tl, current_list = [], [], [], []
                table_html_rows = ""
                
                for h in range(5, 16):
                    target_time_str = f"{d_str}T{h:02d}:00"
                    prev_time_str = f"{d_str}T{h-1:02d}:00" if h > 0 else f"{y_str}T23:00"
                    
                    ct = get_val_at_time(sd, "sea_surface_temperature", target_time_str)
                    if ct is None: ct = temps_today_avg
                    pt = get_val_at_time(sd, "sea_surface_temperature", prev_time_str)
                    if pt is None: pt = ct
                    
                    cloud = get_val_at_time(wd, "cloud_cover", target_time_str) or 0
                    wind = get_val_at_time(wd, "wind_speed_10m", target_time_str) or 0
                    rain = get_val_at_time(wd, "rain", target_time_str) or 0
                    
                    # 潮流スピードと転流判定
                    c_speed, slack = estimate_current_speed(mage, h, area_info["base_slack"])
                    
                    sc = 0
                    if h == sun_h: sc += 40
                    elif abs(h - sun_h) == 1: sc += 20
                    
                    # 転流時は食いが立つチャンス、潮が早い時もチャンス
                    if slack: sc += 50
                    elif c_speed > 0.5: sc += 30
                    
                    tdiff = 0 if use_historical else (ct - pt)
                    if tdiff >= 0.1: sc += 20
                    elif tdiff <= -0.1: sc -= 20
                    
                    sc += day_trend_score
                    
                    w_icon = ""
                    if rain >= 0.5: sc += 10; w_icon = "☔"
                    elif cloud >= 60: sc += 10; w_icon = "☁️"
                    elif cloud <= 20: sc -= 5; w_icon = "☀️"
                    else: w_icon = "⛅"
                    
                    wind_text = ""
                    if wind >= 10.0: sc = 0; wind_text = "爆風"
                    elif wind >= 7.0: sc -= 10; wind_text = "強風"
                    elif wind >= 5.0: sc += 5; wind_text = "やや強"
                    elif wind >= 2.0: sc += 20; wind_text = "最適"
                    else: sc -= 20; wind_text = "静穏"
                    
                    low_temp_alert = ""
                    if ct <= 10.0: sc = int(sc * 0.2); low_temp_alert = "激渋"
                    elif ct <= 12.0: sc = int(sc * 0.5); low_temp_alert = "低水温"
                    
                    if sc < 0: sc = 0
                    if sc > 100: sc = 100
                    
                    tie1, tie2, spd, hk, worm = suggest_strategy(h, sun_h, sc, tdiff, target_date.month, ct, cloud, rain)
                    
                    time_display = f"{h}:00<br>{w_icon} {wind_text}"
                    tac_display = f"{spd}・{hk}"
                    if worm: tac_display += f"<br><span style='color:#e67e22;'>{worm}</span>"

                    notes = []
                    if slack: notes.append("★転流")
                    if low_temp_alert: notes.append(f"⚠️{low_temp_alert}")
                    if rain >= 0.5: notes.append("濁り")
                    
                    if not use_historical and abs(diff_day) >= 0.5:
                        if diff_day <= -0.5: notes.append(f"⚠️前日比{diff_day:+.1f}℃")
                        else: notes.append(f"前日比{diff_day:+.1f}℃")
                        
                    note_str = " ".join(notes)
                    
                    hl.append(h); sl.append(sc); tl.append(ct); current_list.append(c_speed)
                    
                    row_html = f"<tr><td class='col-time'>{time_display}</td><td class='col-honmei'>{tie1}</td><td class='col-osae'>{tie2}</td><td class='col-tac'>{tac_display}</td><td class='col-note'>{note_str}</td></tr>"
                    table_html_rows += row_html

                # --- グラフ描画 ---
                TITLE_SIZE = 16; LABEL_SIZE = 12; TICK_SIZE = 10; LINE_WIDTH = 2.5; MARKER_SIZE = 8

                fig, ax1 = plt.subplots(figsize=(10, 5))
                fig.patch.set_facecolor('#f8f9fa')
                ax1.set_facecolor('#ffffff')
                
                color = '#3498db'
                ax1.set_xlabel('Time', fontsize=LABEL_SIZE)
                ax1.set_ylabel('Score', color=color, fontsize=LABEL_SIZE)
                ax1.bar(hl, sl, color=color, alpha=0.5, edgecolor=color)
                ax1.set_ylim(0, 100)
                ax1.tick_params(axis='x', labelsize=TICK_SIZE)
                ax1.tick_params(axis='y', labelcolor=color, labelsize=TICK_SIZE)
                
                ax2 = ax1.twinx()
                color = '#e74c3c'
                ax2.set_ylabel('Temp (C)', color=color, fontsize=LABEL_SIZE)
                ax2.plot(hl, tl, color=color, marker='o', linewidth=LINE_WIDTH, markersize=MARKER_SIZE)
                vt = [t for t in tl if t > 0]
                if vt:
                     margin = 1.0 if max(vt) == min(vt) else 0.5
                     ax2.set_ylim(min(vt)-margin, max(vt)+margin)
                ax2.tick_params(axis='y', labelcolor=color, labelsize=TICK_SIZE)
                
                ax3 = ax1.twinx()
                ax3.spines["right"].set_position(("axes", 1.12))
                color = '#2ecc71'
                # 【変更】緑の線を潮流の速さ（Current Speed）に変更
                ax3.set_ylabel('Current Speed', color=color, fontsize=LABEL_SIZE)
                ax3.plot(hl, current_list, color=color, linestyle='--', marker='x', linewidth=LINE_WIDTH, markersize=MARKER_SIZE)
                ax3.set_ylim(0, 1.2) # 0(潮止まり) 〜 1(最速)
                ax3.set_yticks([])
                
                plt.title(f"{target_date} {area_info['name_en']} Forecast", fontsize=TITLE_SIZE, fontweight='bold', color='#2c3e50')
                plt.grid(axis='x', linestyle=':', alpha=0.7)
                st.pyplot(fig)

                st.markdown("### 📝 戦略ネクタイ<br><span style='font-size:14px; color:gray;'>(本命 / 抑え / 戦術)</span>", unsafe_allow_html=True)
                
                full_table_html = f"""
                <table class="matsuri-table">
                    <thead>
                        <tr>
                            <th>時間<br>(天気/風)</th>
                            <th>本命</th>
                            <th>抑え</th>
                            <th>戦術<br>(速/針)</th>
                            <th>備考</th>
                        </tr>
                    </thead>
                    <tbody>
                        {table_html_rows}
                    </tbody>
                </table>
                """
                st.markdown(full_table_html, unsafe_allow_html=True)
                
                st.markdown("""
                <div style="font-size: 12px; color: #7f8c8d; margin-bottom: 20px; padding: 10px; background-color: #f8f9fa; border-radius: 5px;">
                <strong>【ガイド】</strong><br>
                ⭐ <strong>時間の「★」</strong>：転流（潮止まり）の目安です。<br>
                🌪️ <strong>爆風</strong>：出船できない危険な風 (10m以上) / 🌬️ <strong>強風</strong>：底取りが難しく釣りづらい (7m〜)<br>
                🍃 <strong>最適</strong>：程よく船が流れ釣れやすい (2m〜) / 🌊 <strong>静穏</strong>：船が流れず見切られやすい (2m未満)
                </div>
                """, unsafe_allow_html=True)
                
                st.markdown("---")
                st.subheader("🔗 関連ツール")
                
                col_link1, col_link2 = st.columns(2)
                
                with col_link1:
                    st.link_button(f"🌊 海上保安庁の潮流情報 ({selected_area})", area_info["kaiho_url"], use_container_width=True)
                    
                with col_link2:
                    if area_info["checker_url"]:
                        st.link_button("🚤 どこの釣り座が釣れる？", area_info["checker_url"], use_container_width=True)
                    else:
                        st.info("この海域の釣り座チェッカーは現在準備中です。")

                st.markdown("---")
                st.markdown("""
                <div style='background-color: #f0f2f6; padding: 15px; border-radius: 5px; color: #555; font-size: 12px;'>
                    <strong>【⚠️ 免責事項・利用規約】</strong><br>
                    本アプリの予報は推測値であり、実際の気象・海況とは異なる場合があります。出船判断や安全確保は必ず船長の指示に従ってください。
                </div>
                """, unsafe_allow_html=True)
                
        except Exception as e:
            st.error("⚠️ 気象データの取得、または解析中にエラーが発生しました。")
            st.info("APIの提供範囲外の日付（1週間以上先など）を選択している可能性があります。数日以内の日付を選んで再度お試しください。")

if __name__ == "__main__":
    main()
