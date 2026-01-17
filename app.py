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
st.set_page_config(page_title="魔釣 - 明石タイラバ予報", page_icon="🎣")

# --- 定数 ---
AKASHI_LAT = 34.60
AKASHI_LON = 135.00
HISTORICAL_TEMPS = {
    1: 10.5, 2: 9.8, 3: 10.5, 4: 13.0, 5: 17.5, 6: 21.0,
    7: 25.5, 8: 27.0, 9: 25.5, 10: 22.0, 11: 18.0, 12: 14.0
}

# --- 関数群 (キャッシュ化して高速化) ---
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

def get_tide_type(moon_age):
    age_norm = moon_age % 15
    if age_norm <= 2 or age_norm >= 13: return "大潮(激)", "100-120g"
    elif 3 <= age_norm <= 5 or 10 <= age_norm <= 12: return "中潮(速)", "80-100g"
    else: return "小潮(緩)", "45-60g"

def estimate_akashi_tide(moon_age, hour):
    base_high = 8.5; delay = 0.8
    high_tide = (base_high + (moon_age % 15) * delay) % 12
    diff = abs(hour - high_tide)
    if diff > 6: diff = 12 - diff
    level = math.cos(diff * (math.pi / 6))
    is_slack = (diff < 1.0 or abs(diff - 6.0) < 1.0)
    return level, is_slack

def suggest_strategy(h, sun_h, sc, t_diff):
    c = "赤オレ"; s = "極細"
    if h <= sun_h: c = "チャート"
    elif h <= sun_h + 1: c = "オレ金"
    elif t_diff <= -0.1: c = "黒/海苔"
    
    if sc >= 50: s = "強波動"
    elif sc >= 30: s = "ショート"
    return f"{c} × {s}"

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
    st.title("🌊 魔釣 - 明石タイラバ予報")
    st.markdown("明石海峡の潮流・水温・月齢から**「攻め時」**と**「ネクタイ」**を解析します。")

    # 日付選択（カレンダー）
    target_date = st.date_input("釣行日を選択してください", datetime.date.today() + datetime.timedelta(days=1))
    
    if st.button("予報を開始する"):
        with st.spinner('明石の海況データを解析中...'):
            # 解析ロジック
            mage = get_moon_age(target_date)
            tname, sinker = get_tide_type(mage)
            
            sd, wd = get_weather_data(target_date)
            sun_h = int(wd["daily"]["sunrise"][0].split('T')[1].split(':')[0]) if wd else 7
            
            # データ検証
            r_temps = sd["hourly"]["sea_surface_temperature"] if sd else []
            OFF = 15
            use_historical = False
            valid_data = [t for t in r_temps if t is not None and t > 0]
            
            if not valid_data:
                use_historical = True
                avg_temp = HISTORICAL_TEMPS.get(target_date.month, 15.0)
                r_temps = [avg_temp] * 48

            # 水温範囲
            day_temps = []
            for h in range(5, 16):
                idx = OFF + h
                if idx < len(r_temps): day_temps.append(r_temps[idx])
            min_t = min(day_temps) if day_temps else 0
            max_t = max(day_temps) if day_temps else 0

            # 結果表示エリア
            st.success("解析完了！")
            
            # 概要カラム
            col1, col2 = st.columns(2)
            with col1:
                st.metric(label="月齢", value=f"{mage:.1f}", delta=tname)
            with col2:
                st.metric(label="推奨シンカー", value=sinker)
            
            if use_historical:
                st.info(f"⚠️ 長期予報のため、平年値（約{min_t}℃）を使用しています。")
            else:
                st.info(f"🌡️ 水温範囲: {min_t:.1f}℃ 〜 {max_t:.1f}℃")

            # データ構築
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
                
                tie = suggest_strategy(h, sun_h, sc, tdiff)
                ext = "★転流" if slack else ""
                
                hl.append(h); sl.append(sc); tl.append(ct); tll.append(tlev)
                
                # テーブル用データ
                t_pct = int((tlev+1)*50)
                data_rows.append({
                    "時間": f"{h}:00",
                    "水温(℃)": f"{ct:.1f}",
                    "潮位目安": f"{t_pct}%",
                    "推奨ネクタイ": tie,
                    "備考": ext
                })

            # --- グラフ描画 (英語ラベルで安定化) ---
            title_txt = f"{target_date} Akashi Forecast (Moon:{mage:.1f})"
            fig, ax1 = plt.subplots(figsize=(10, 5))
            
            # 1. Expectation
            color = 'tab:blue'
            ax1.set_xlabel('Time')
            ax1.set_ylabel('Score', color=color)
            ax1.bar(hl, sl, color=color, alpha=0.4)
            ax1.set_ylim(0, 100)
            
            # 2. Temp
            ax2 = ax1.twinx()
            color = 'tab:red'
            ax2.set_ylabel('Temp (C)', color=color)
            ax2.plot(hl, tl, color=color, marker='o')
            vt = [t for t in tl if t > 0]
            if vt:
                 margin = 1.0 if max(vt) == min(vt) else 0.5
                 ax2.set_ylim(min(vt)-margin, max(vt)+margin)
            
            # 3. Tide
            ax3 = ax1.twinx()
            ax3.spines["right"].set_position(("axes", 1.15))
            color = 'tab:green'
            ax3.set_ylabel('Tide (Est)', color=color)
            ax3.plot(hl, tll, color=color, linestyle='--', marker='x')
            ax3.set_ylim(-1.5, 1.5)
            ax3.set_yticks([])
            
            plt.title(title_txt)
            plt.grid(axis='x', linestyle='--', alpha=0.5)
            st.pyplot(fig)

            # --- テーブル表示 ---
            st.subheader("📝 時間別 戦略リスト")
            df = pd.DataFrame(data_rows)
            st.dataframe(df, use_container_width=True)

            st.caption("※潮位は月齢に基づく推定値です。天候等によりズレが生じる場合があります。")

if __name__ == "__main__":
    main()
