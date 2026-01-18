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
st.set_page_config(page_title="魔釣 - 明石タイラバ予報 v2.7", page_icon="🎣")

# --- 定数 ---
AKASHI_LAT = 34.60
AKASHI_LON = 135.00
BASE_DEPTH = 40
HISTORICAL_TEMPS = {
    1: 10.5, 2: 9.8, 3: 10.5, 4: 13.0, 5: 17.5, 6: 21.0,
    7: 25.5, 8: 27.0, 9: 25.5, 10: 22.0, 11: 18.0, 12: 14.0
}
KAIHO_URL = "https://www1.kaiho.mlit.go.jp/KAN5/tyouryuu/stream_akashi.html"
# 釣り座チェッカーのURL (以前のURLを設定しています)
SEAT_CHECKER_URL = "https://matsuri-akashi-checker-4qw73q6qju7ppzztkyagpu.streamlit.app/"

# --- 関数群 (キャッシュ化) ---
@st.cache_data
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
    age_norm = moon_age % 15
    if age_norm <= 2 or age_norm >= 13:
        tide_name = "大潮(激)"
        min_w = int(depth * 2.0)
        max_w = int(depth * 2.5)
    elif 3 <= age_norm <= 5 or 10 <= age_norm <= 12:
        tide_name = "中潮(速)"
        min_w = int(depth * 1.5)
        max_w = int(depth * 2.0)
    else:
        tide_name = "小潮(緩)"
        min_w = int(depth * 1.1)
        max_w = int(depth * 1.5)
    return tide_name, f"{min_w}g〜{max_w}g"

def estimate_akashi_tide(moon_age, hour):
    base_high = 8.5; delay = 0.8
    high_tide = (base_high + (moon_age % 15) * delay) % 12
    diff = abs(hour - high_tide)
    if diff > 6: diff = 12 - diff
    level = math.cos(diff * (math.pi / 6))
    is_slack = (diff < 1.0 or abs(diff - 6.0) < 1.0)
    return level, is_slack

def suggest_strategy(h, sun_h, sc, t_diff):
    # --- 1. 本命パターン (Best) ---
    c1 = "赤オレ"
    s1 = "極細"

    if h <= sun_h:
        # 朝マズメ
        c1 = "チャート" if h % 2 == 0 else "オレンジゼブラ"
    elif h <= sun_h + 2:
        # 日の出〜9時頃: マジョーラ投入
        c1 = "オレ金" if h % 2 == 0 else "マジョーラゼブラ"
    elif t_diff <= -0.1:
        # 水温低下
        c1 = "コーラ" if h % 2 == 0 else "黒/海苔"
    
    # 活性が高いときは強波動
    if sc >= 50: s1 = "強波動"
    elif sc >= 30: s1 = "ショート"
    
    # --- 2. 抑えパターン (Rotation) ---
    c2 = "グリーン"; s2 = "ショート" # デフォルト

    # ローテーションロジック
    if c1 == "チャート": c2 = "オレ金"
    elif c1 == "オレンジゼブラ": c2 = "マジョーラゼブラ"
    elif c1 == "オレ金": c2 = "赤オレ"
    elif c1 == "マジョーラゼブラ": c2 = "赤オレ"
    elif c1 == "コーラ": c2 = "赤オレ"
    elif c1 == "黒/海苔": c2 = "コーラ"
    elif c1 == "赤オレ": c2 = "マジョーラゼブラ"
    
    # 形状ローテ
    if s1 == "強波動": s2 = "ショート"
    elif s1 == "ショート": s2 = "極細"
    else: s2 = "カーリー"
    
    return f"{c1}×{s1}", f"{c2}×{s2}"

@st.cache_data
def get_weather_data(target_date):
    bm = "https://marine-api.open-meteo.com/v1/marine"
    bw = "https://api.open-meteo.com/v1/forecast"
    d_str = target_date.strftime("%Y-%m-%d")
    y_str = (target_date - datetime.timedelta(days=1)).strftime("%Y-%m-%d")
    
    p_temp = {"latitude": AKASHI_LAT, "longitude": AKASHI_LON, "hourly": "sea_surface_temperature", "start_date": y_str, "end_date": d_str}
    p_sun = {"latitude": AKASHI_LAT, "longitude": AKASHI_LON, "daily": "sunrise", "start_date": d_str, "end_date": d_str, "timezone": "Asia/Tokyo"}
    
    return make_request(f"{bm}?{urllib.parse.urlencode(p_temp)}"), make_request(f"{bw}?{urllib.parse.urlencode(p_sun)}")

# --- メイン画面 ---
def main():
    st.markdown("""
        <h1 style='text-align: center; font-size: 28px; margin-bottom: 5px;'>
            🌊 魔釣<br>
            <span style='font-size: 22px;'>明石タイラバ予報</span>
        </h1>
        <p style='text-align: center; font-size: 13px; color: gray; margin-bottom: 20px;'>
            明石海峡の潮流・水温・月齢から<br>
            <b>「攻め時」</b>と<b>「ネクタイ」</b>を解析します。
        </p>
    """, unsafe_allow_html=True)

    target_date = st.date_input("釣行日を選択してください", datetime.date.today() + datetime.timedelta(days=1))
    
    if st.button("魔釣予報を開始する"):
        with st.spinner('明石の海況データを解析中...'):
            mage = get_moon_age(target_date)
            tname, sinker = get_sinker_weight(mage, BASE_DEPTH)
            
            sd, wd = get_weather_data(target_date)
            sun_h = int(wd["daily"]["sunrise"][0].split('T')[1].split(':')[0]) if wd else 7
            
            r_temps = sd["hourly"]["sea_surface_temperature"] if sd else []
            OFF = 15
            use_historical = False
            valid_data = [t for t in r_temps if t is not None and t > 0]
            
            if not valid_data:
                use_historical = True
                avg_temp = HISTORICAL_TEMPS.get(target_date.month, 15.0)
                r_temps = [avg_temp] * 48

            day_temps = []
            for h in range(5, 16):
                idx = OFF + h
                if idx < len(r_temps): day_temps.append(r_temps[idx])
            min_t = min(day_temps) if day_temps else 0
            max_t = max(day_temps) if day_temps else 0

            st.success("解析完了！")
            
            col1, col2 = st.columns(2)
            with col1:
                st.metric(label="月齢・潮回り", value=f"{mage:.1f}", delta=tname)
            with col2:
                st.metric(label=f"推奨シンカー ({BASE_DEPTH}m基準)", value=sinker)
            
            if use_historical:
                st.info(f"⚠️ 長期予報のため、平年値（約{min_t}℃）を使用しています。")
            else:
                st.info(f"🌡️ 水温範囲: {min_t:.1f}℃ 〜 {max_t:.1f}℃")

            hl, sl, tl, tll, data_rows = [], [], [], [], []
            
            for h in range(5, 16):
                idx = OFF + h
                ct = r_temps[idx] if idx < len(r_temps) else 0
                pt = r_temps[idx-1] if idx>0 else ct
                tdiff = ct - pt
                if use_historical: tdiff = 0
                
                tlev, slack = estimate_akashi_tide(mage, h)
                
                sc = 0
                if h == sun_h: sc += 40
                elif abs(h - sun_h) == 1: sc += 20
                if slack: sc += 50
                elif h>5 and abs(tlev - tll[-1]) > 0.3: sc += 30
                
                if not use_historical:
                    if tdiff >= 0.1: sc += 20
                    elif tdiff <= -0.1: sc -= 20
                if sc < 0: sc = 0
                
                tie1, tie2 = suggest_strategy(h, sun_h, sc, tdiff)
                
                time_str = f"{h}:00"
                if slack: time_str += " ★"
                
                hl.append(h); sl.append(sc); tl.append(ct); tll.append(tlev)
                
                t_pct = int((tlev+1)*50)
                
                data_rows.append({
                    "時間": time_str,
                    "水温": f"{ct:.1f}",
                    "潮位": f"{t_pct}%",
                    "本命": tie1,
                    "抑え": tie2
                })

            # --- グラフ描画 ---
            TITLE_SIZE = 18; LABEL_SIZE = 14; TICK_SIZE = 12; LINE_WIDTH = 2.5; MARKER_SIZE = 8

            title_txt = f"{target_date} Akashi Forecast (Moon:{mage:.1f})"
            fig, ax1 = plt.subplots(figsize=(10, 6))
            
            color = 'tab:blue'
            ax1.set_xlabel('Time', fontsize=LABEL_SIZE)
            ax1.set_ylabel('Score', color=color, fontsize=LABEL_SIZE)
            ax1.bar(hl, sl, color=color, alpha=0.4)
            ax1.set_ylim(0, 100)
            ax1.tick_params(axis='x', labelsize=TICK_SIZE)
            ax1.tick_params(axis='y', labelcolor=color, labelsize=TICK_SIZE)
            
            ax2 = ax1.twinx()
            color = 'tab:red'
            ax2.set_ylabel('Temp (C)', color=color, fontsize=LABEL_SIZE)
            ax2.plot(hl, tl, color=color, marker='o', linewidth=LINE_WIDTH, markersize=MARKER_SIZE)
            vt = [t for t in tl if t > 0]
            if vt:
                 margin = 1.0 if max(vt) == min(vt) else 0.5
                 ax2.set_ylim(min(vt)-margin, max(vt)+margin)
            ax2.tick_params(axis='y', labelcolor=color, labelsize=TICK_SIZE)
            
            ax3 = ax1.twinx()
            ax3.spines["right"].set_position(("axes", 1.15))
            color = 'tab:green'
            ax3.set_ylabel('Tide (Est)', color=color, fontsize=LABEL_SIZE)
            ax3.plot(hl, tll, color=color, linestyle='--', marker='x', linewidth=LINE_WIDTH, markersize=MARKER_SIZE)
            ax3.set_ylim(-1.5, 1.5)
            ax3.set_yticks([])
            
            plt.title(title_txt, fontsize=TITLE_SIZE)
            plt.grid(axis='x', linestyle='--', alpha=0.5)
            st.pyplot(fig)

            st.subheader("📝 戦略ネクタイ (本命 / 抑え)")
            df = pd.DataFrame(data_rows)
            st.dataframe(df, use_container_width=True, hide_index=True)
            st.caption("※時間の「★」は転流（潮止まり）の目安です。")

            # --- 関連リンクエリア (更新) ---
            st.markdown("---")
            st.subheader("🔗 関連ツール")
            
            # 2つのボタンを横並びに配置
            col_link1, col_link2 = st.columns(2)
            
            with col_link1:
                st.markdown("##### 🌊 公式データ")
                st.link_button("海上保安庁の潮流情報", KAIHO_URL)
                
            with col_link2:
                st.markdown("##### 🚤 釣り座(潮先)")
                st.link_button("どこの釣り座が釣れる？", SEAT_CHECKER_URL)

if __name__ == "__main__":
    main()
