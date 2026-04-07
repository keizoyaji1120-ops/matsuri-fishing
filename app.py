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
st.set_page_config(page_title="魔釣 - 瀬戸内タイラバ予報 v8.0", page_icon="🎣")

# --- CSS (表のデザイン) ---
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
        font-size: 13px;
        color: #333;
        margin-bottom: 20px;
    }
    table.matsuri-table th {
        background-color: #f0f2f6;
        color: #31333F;
        font-weight: bold;
        padding: 10px 4px;
        text-align: center;
        border-bottom: 2px solid #ddd;
        white-space: nowrap;
    }
    table.matsuri-table td {
        padding: 8px 4px;
        text-align: center;
        border-bottom: 1px solid #eee;
        vertical-align: middle;
        line-height: 1.5;
    }
    table.matsuri-table tr:nth-child(even) {
        background-color: #f9f9f9;
    }
    .col-time { width: 18%; font-weight: bold; font-size: 12px; white-space: nowrap; }
    .col-honmei { width: 22%; color: #d63031; font-weight: bold; }
    .col-osae { width: 22%; color: #0984e3; }
    .col-tac { width: 18%; font-size: 12px; }
    .col-note { width: 20%; font-size: 11px; text-align: left; color: #666; }
    
    @media (max-width: 640px) {
        table.matsuri-table { font-size: 11px; }
        .col-time { font-size: 10px; }
        .col-tac { font-size: 10px; }
        .col-honmei, .col-osae { font-size: 11.5px; }
    }
    </style>
""", unsafe_allow_html=True)

# --- エリア定数 ---
AREA_OPTIONS = {
    "明石海峡": {"lat": 34.60, "lon": 135.00},
    "鳴門海峡": {"lat": 34.23, "lon": 134.65},
    "小豆島周辺": {"lat": 34.48, "lon": 134.27},
    "瀬戸大橋周辺": {"lat": 34.38, "lon": 133.81},
}

HISTORICAL_TEMPS = {
    1: 10.5, 2: 9.8, 3: 10.5, 4: 13.0, 5: 17.5, 6: 21.0,
    7: 25.5, 8: 27.0, 9: 25.5, 10: 22.0, 11: 18.0, 12: 14.0
}
KAIHO_URL = "https://www1.kaiho.mlit.go.jp/KAN5/tyouryuu/stream_akashi.html"
SEAT_CHECKER_URL = "https://matsuri-akashi-checker-4qw73q6qju7ppzztkyagpu.streamlit.app/"

# --- 関数群 ---
@st.cache_data(ttl=3600)
def make_request(url):
    req = urllib.request.Request(url)
    req.add_header('User-Agent', 'Mozilla/5.0 (App; CPU iPhone OS 15_0)')
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    try:
        with urllib.request.urlopen(req, context=ctx) as res:
            return json.loads(res.read().decode())
    except:
        return None

def get_moon_age(date):
    year, month, day = date.year, date.month, date.day
    if month < 3: year -= 1; month += 12
    p = math.floor(year / 4)
    age = (year + p + month * 9 / 25 + day + 11) % 30
    return int(age)

def get_sinker_weight(moon_age, depth):
    STANDARD_SINKERS = [30, 45, 60, 80, 100, 120, 150, 180, 200]
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

    if w_min == w_max:
        return tide_name, f"{w_min}g"
    else:
        return tide_name, f"{w_min}g〜{w_max}g"

def estimate_tide(moon_age, hour):
    base_high = 8.5; delay = 0.8
    high_tide = (base_high + (moon_age % 15) * delay) % 12
    diff = abs(hour - high_tide)
    if diff > 6: diff = 12 - diff
    level = math.cos(diff * (math.pi / 6))
    is_slack = (diff < 1.0 or abs(diff - 6.0) < 1.0)
    return level, is_slack

def get_seasonal_bait(month, area):
    if area == "明石海峡":
        if month in [12, 1, 2]: return "海苔(ノリ)・底生", "黒・緑・エッジブラック"
        elif month in [3, 4, 5]: return "イカナゴ", "オレンジゴールド・ミドキン"
        elif month in [6, 7]: return "イカ・タコ", "グロー・ゼブラ・金"
        elif month in [8, 9, 10, 11]: return "イワシ・エビ", "エビオレ・マスターオレンジ"
        else: return "混合", "赤オレ"
    else:
        if month in [12, 1, 2]: return "海苔(ノリ)・底生", "黒・緑・濃い茶"
        elif month in [3, 4, 5]: return "イカナゴ", "ミドキン・緑・オレ金"
        elif month in [6, 7]: return "イカ・タコ", "グロー・ゼブラ・金"
        elif month in [8, 9, 10, 11]: return "イワシ・エビ", "オレンジ・赤・金"
        else: return "混合", "赤オレ"

def suggest_strategy(h, sun_h, sc, t_diff, month, temp, cloud_cover, rain, area):
    c1 = "赤オレ"
    s1 = "極細"
    speed = "普通"
    hook = "M"

    is_nori_season = month in [12, 1, 2, 3, 4]
    is_akashi = (area == "明石海峡")

    # --- UV理論を応用したカラー＆ネクタイ選定 ---
    if is_akashi:
        # 【明石特化】ビンソルUV理論ベース（ジャッカルネクタイ名）
        if rain >= 0.5:
            c1 = "黒金(J)" if h % 2 == 0 else "ｺﾞｰｼﾞｬｽｵﾚﾝｼﾞ(J)"
            s1 = "マスターカーリー"
        elif h <= sun_h + 1:
            c1 = "ﾌﾞﾗｲﾄｵﾚﾝｼﾞ(J)" if h % 2 == 0 else "ｼﾏｼﾏｵﾚﾝｼﾞ(J)"
            s1 = "ショート" if sc >= 30 else "極細"
        elif t_diff <= -0.1:
            c1 = "赤黒(J)" if h % 2 == 0 else "ｴｯｼﾞﾌﾞﾗｯｸ(J)"
            s1 = "極細"
        elif cloud_cover > 70:
            c1 = "ｱﾐｵﾚ(J)" if h % 2 == 0 else "黒金(J)"
            s1 = "マスターカーリー" if sc >= 40 else "ショート"
        elif month in [3, 4, 5]:
            c1 = "ｵﾚﾝｼﾞｺﾞｰﾙﾄﾞ(J)" if h % 2 == 0 else "ﾐﾄﾞｷﾝ(J)"
            s1 = "カーリー" if sc >= 30 else "ストレート"
        elif h > sun_h + 3 and cloud_cover < 30:
            c1 = "ｴﾋﾞｵﾚ(J)" if h % 2 == 0 else "ｴﾋﾞﾁﾘ(J)"
            s1 = "マスターカーリー" if sc >= 40 else "カーリー"
        else:
            c1 = "ﾘﾊﾞｰｼﾌﾞﾙ赤ｵﾚ(J)" if h % 2 == 0 else "ｷﾞﾐｯｸｵﾚﾝｼﾞ(J)"
            s1 = "ショート"
            
    else:
        # その他のエリア
        if rain >= 0.5:
            c1 = "チャート" if h % 2 == 0 else "ソリッドレッド"
            s1 = "ワイドカーリー"
        elif h <= sun_h:
            c1 = "チャート" if h % 2 == 0 else "赤ゼブラ"
            s1 = "極細"
        elif t_diff <= -0.1:
            c1 = "コーラ" if h % 2 == 0 else "赤黒"
            s1 = "極細"
        elif month in [3, 4, 5]:
            c1 = "ミドキン" if h % 2 == 0 else "グリーン"
            s1 = "カーリー"
        elif is_nori_season and (temp < 13.0 or sc < 45):
            c1 = "黒/海苔" if h % 2 == 0 else "コーラ"
            s1 = "極細"
        elif cloud_cover > 70:
            c1 = "チャート" if h % 2 == 0 else "赤ゼブラ"
            s1 = "ショート"
        elif h <= sun_h + 2:
            c1 = "オレ金" if h % 2 == 0 else "マジョーラゼブラ"
            s1 = "極細"
        else:
            c1 = "オレンジ" if h % 2 == 0 else "赤オレ"
            s1 = "カーリー"
            
        if month in [6, 7, 8] and sc >= 40:
            s1 = "ロングカーリー"
        elif sc >= 50: 
            s1 = "強波動"
    
    # 巻き速度
    if temp >= 18.0 and sc >= 40: speed = "早巻"
    elif temp <= 12.0 or sc <= 20: speed = "激遅"
    elif sc >= 30: speed = "普通"
    else: speed = "遅め"

    # フックサイズ
    if month in [12, 1, 2] and (temp < 10.0 or sc < 30): hook = "3S"
    elif month in [3, 4]: hook = "SS"
    elif speed == "激遅" or sc < 40: hook = "S"
    elif temp >= 22.0 and sc >= 50: hook = "L"
    else: hook = "M"

    # ワーム判定
    worm_option = "+ワーム" if sc <= 10 else ""

    # --- 抑えパターン ---
    if is_akashi:
        c2 = "ﾏｽﾀｰｵﾚﾝｼﾞ(J)"
        if "ｵﾚﾝｼﾞ" in c1 or "金" in c1: c2 = "ｴﾋﾞﾁﾘ(J)"
        elif "黒" in c1 or "海苔" in c1: c2 = "ｱﾐｵﾚ(J)"
        elif "ｴﾋﾞ" in c1: c2 = "ｼﾏｼﾏﾚｯﾄﾞ(J)"
        s2 = "極細" if "カーリー" in s1 else "ストレート"
    else:
        c2 = "グリーン"
        if "チャート" in c1: c2 = "オレ金"
        elif "ソリッドレッド" in c1: c2 = "チャート"
        elif "赤ゼブラ" in c1: c2 = "オレンジ"
        elif "ミドキン" in c1: c2 = "オレ金"
        elif "オレ金" in c1: c2 = "ピンク"
        elif "マジョーラゼブラ" in c1: c2 = "ピンク"
        elif "ピンク" in c1: c2 = "赤オレ"
        elif "コーラ" in c1: c2 = "赤黒"
        elif "赤黒" in c1: c2 = "コーラ"
        elif "黒/海苔" in c1: c2 = "コーラ"
        elif "赤オレ" in c1: c2 = "マジョーラゼブラ"
        elif "オレンジ" in c1: c2 = "赤オレ"
        elif "グリーン" in c1: c2 = "ミドキン"
        
        s2 = "ショート"
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
    
    p_temp = {"latitude": lat, "longitude": lon, "hourly": "sea_surface_temperature", "start_date": y_str, "end_date": d_str}
    
    p_weather = {
        "latitude": lat, 
        "longitude": lon, 
        "daily": "sunrise", 
        "hourly": "cloud_cover,wind_speed_10m,rain",
        "start_date": d_str, 
        "end_date": d_str, 
        "timezone": "Asia/Tokyo"
    }
    
    return make_request(f"{bm}?{urllib.parse.urlencode(p_temp)}"), make_request(f"{bw}?{urllib.parse.urlencode(p_weather)}")

# --- メイン画面 ---
def main():
    st.markdown("""
        <h1 style='text-align: center; font-size: 32px; margin-bottom: 5px; font-weight: 800;'>
            <span style='margin-right: 0.5em;'>🌊 魔釣</span><br>
            <span style='font-size: 24px; font-weight: normal;'>瀬戸内タイラバ予報</span>
        </h1>
        <p style='text-align: center; font-size: 13px; color: gray; margin-bottom: 20px;'>
            瀬戸内海の潮流・水温・天気・ベイトから<br>
            <b>「攻め時」</b>と<b>「ネクタイ」</b>を解析します。
        </p>
    """, unsafe_allow_html=True)

    selected_area = st.selectbox("🎣 釣行エリアを選択", list(AREA_OPTIONS.keys()))
    lat = AREA_OPTIONS[selected_area]["lat"]
    lon = AREA_OPTIONS[selected_area]["lon"]
    
    target_date = st.date_input("📅 釣行日を選択", datetime.date.today() + datetime.timedelta(days=1))
    
    bait_name, bait_colors = get_seasonal_bait(target_date.month, selected_area)
    st.info(f"🐟 **現在のシーズナルパターン: {bait_name}**\n\n有効カラー目安: {bait_colors}")

    if st.button("魔釣予報を開始する"):
        try:
            with st.spinner(f'{selected_area}の海況・気象・ベイトパターンを解析中...'):
                mage = get_moon_age(target_date)
                
                tname, s15 = get_sinker_weight(mage, 15)
                _, s30 = get_sinker_weight(mage, 30)
                _, s45 = get_sinker_weight(mage, 45)
                _, s60 = get_sinker_weight(mage, 60)
                _, s80 = get_sinker_weight(mage, 80)
                
                sd, wd = get_weather_data(target_date, lat, lon)
                sun_h = int(wd["daily"]["sunrise"][0].split('T')[1].split(':')[0]) if wd else 7
                
                r_temps = sd["hourly"]["sea_surface_temperature"] if sd else []
                r_clouds = wd["hourly"]["cloud_cover"] if (wd and "cloud_cover" in wd["hourly"]) else []
                r_winds = wd["hourly"]["wind_speed_10m"] if (wd and "wind_speed_10m" in wd["hourly"]) else []
                r_rains = wd["hourly"]["rain"] if (wd and "rain" in wd["hourly"]) else []
                
                OFF = 15
                use_historical = False
                valid_data_list = [t for t in r_temps if t is not None and t > 0]
                
                day_trend_score = 0
                day_trend_label = ""

                if not valid_data_list:
                    use_historical = True
                    avg_temp = HISTORICAL_TEMPS.get(target_date.month, 15.0)
                    r_temps = [avg_temp] * 48
                else:
                    if len(r_temps) >= 48:
                        temps_yesterday = [t for t in r_temps[0:24] if t is not None]
                        temps_today = [t for t in r_temps[24:48] if t is not None]

                        if temps_yesterday and temps_today:
                            avg_yesterday = sum(temps_yesterday) / len(temps_yesterday)
                            avg_today = sum(temps_today) / len(temps_today)
                            diff_day = avg_today - avg_yesterday
                            
                            if diff_day <= -0.5:
                                day_trend_score = -20
                                day_trend_label = f"⚠️前日比{diff_day:+.1f}℃"
                            elif diff_day >= 0.5:
                                day_trend_score = 10
                                day_trend_label = f"前日比{diff_day:+.1f}℃"

                day_temps = []
                for h in range(5, 16):
                    idx = OFF + h
                    if idx < len(r_temps) and r_temps[idx] is not None:
                         day_temps.append(r_temps[idx])
                
                min_t = min(day_temps) if day_temps else 0
                max_t = max(day_temps) if day_temps else 0

                st.success(f"{selected_area}の解析が完了しました！")
                
                col1, col2 = st.columns(2)
                with col1:
                    st.metric(label="月齢・潮回り", value=f"{mage:.1f}", delta=tname)
                with col2:
                    st.markdown(f"""
                    **推奨シンカー (目安)**
                    - **水深15m**: {s15}
                    - **水深30m**: {s30}
                    - **水深45m**: {s45}
                    - **水深60m**: {s60}
                    - **水深80m**: {s80}
                    """, unsafe_allow_html=True)
                    st.caption("※船長・エリアの指示がある場合はそちらに従ってください。")
                
                if use_historical:
                    st.info(f"⚠️ 長期予報のため、平年値（約{min_t}℃）を使用しています。")
                else:
                    st.info(f"🌡️ 水温範囲: {min_t:.1f}℃ 〜 {max_t:.1f}℃")
                    if "⚠️" in day_trend_label:
                         st.warning(f"{day_trend_label} : 前日より水温が低下しています。活性が低い可能性があります。")
                    elif "前日比" in day_trend_label:
                         st.info(f"📈 {day_trend_label} : 前日より水温が上昇傾向です。活性アップに期待できます。")

                hl, sl, tl, tll = [], [], [], []
                table_html_rows = ""
                
                for h in range(5, 16):
                    idx = OFF + h
                    ct = r_temps[idx] if (idx < len(r_temps) and r_temps[idx] is not None) else (day_temps[0] if day_temps else 15.0)
                    pt = ct
                    if idx > 0 and r_temps[idx-1] is not None:
                        pt = r_temps[idx-1]
                    
                    tdiff = ct - pt
                    if use_historical: tdiff = 0
                    
                    cloud = r_clouds[h] if (h < len(r_clouds) and r_clouds[h] is not None) else 0
                    wind = r_winds[h] if (h < len(r_winds) and r_winds[h] is not None) else 0
                    rain = r_rains[h] if (h < len(r_rains) and r_rains[h] is not None) else 0
                    
                    tlev, slack = estimate_tide(mage, h)
                    
                    sc = 0
                    if h == sun_h: sc += 40
                    elif abs(h - sun_h) == 1: sc += 20
                    if slack: sc += 50
                    elif h>5 and abs(tlev - tll[-1
