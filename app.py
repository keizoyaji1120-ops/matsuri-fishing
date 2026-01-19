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
st.set_page_config(page_title="魔釣 - 明石タイラバ予報 v5.0", page_icon="🎣")

# --- 定数 ---
AKASHI_LAT = 34.60
AKASHI_LON = 135.00
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

def get_seasonal_bait(month):
    if month in [12, 1, 2]:
        return "海苔(ノリ)", "黒・緑・濃い茶"
    elif month in [3, 4, 5]:
        return "イカナゴ", "グリーン・金・茶"
    elif month in [6, 7]:
        return "イカ・タコ", "グロー・ゼブラ・金"
    elif month in [8, 9, 10, 11]:
        return "イワシ・エビ", "オレンジ・赤・金"
    else:
        return "混合", "赤オレ"

# 【更新】戦略ロジック (巻き速度・フックサイズ追加)
def suggest_strategy(h, sun_h, sc, t_diff, month, temp, cloud_cover, rain):
    c1 = "赤オレ" if h % 2 == 0 else "オレンジ"
    s1 = "極細"
    speed = "普通" # 巻き速度
    hook = "標準" # フックサイズ

    # --- ネクタイ選定ロジック ---
    is_nori_season = month in [12, 1, 2, 3, 4]

    if rain >= 0.5:
        c1 = "チャート" if h % 2 == 0 else "ソリッドレッド"
    elif h <= sun_h:
        c1 = "チャート" if h % 2 == 0 else "オレンジゼブラ"
    elif t_diff <= -0.1:
        c1 = "コーラ" if h % 2 == 0 else "黒/海苔"
    elif month in [3, 4, 5]: # イカナゴ
        c1 = "グリーン" if h % 2 == 0 else "オレ金"
    elif is_nori_season and (temp < 13.0 or sc < 45):
        c1 = "黒/海苔" if h % 2 == 0 else "コーラ"
    elif cloud_cover > 70:
        c1 = "チャート" if h % 2 == 0 else "オレ金"
    elif h <= sun_h + 2:
        c1 = "オレ金" if h % 2 == 0 else "マジョーラゼブラ"
    
    if sc >= 50: s1 = "強波動"
    elif sc >= 30: s1 = "ショート"
    
    # --- 【新機能】巻き速度判定 ---
    # 水温が高い or 活性が高い -> 早巻き
    # 水温が低い or 活性が低い -> デッドスロー
    if temp >= 18.0 and sc >= 40:
        speed = "早巻き"
    elif temp <= 12.0 or sc <= 20:
        speed = "デッドスロー" # 超ゆっくり
    elif sc >= 30:
        speed = "普通〜早め"
    else:
        speed = "ゆっくり"

    # --- 【新機能】フックサイズ判定 ---
    # イカナゴパターン(3-5月) or 低活性時 -> 小針
    if month in [3, 4, 5] or speed == "デッドスロー":
        hook = "小針(SS)"
    elif temp >= 20.0: # 高活性期
        hook = "太軸(L)"
    else:
        hook = "標準(M)"

    # --- 抑えパターン ---
    c2 = "グリーン"; s2 = "ショート"
    if c1 == "チャート": c2 = "オレ金"
    elif c1 == "ソリッドレッド": c2 = "チャート"
    elif c1 == "オレンジゼブラ": c2 = "ピンク"
    elif c1 == "オレ金": c2 = "ピンク"
    elif c1 == "マジョーラゼブラ": c2 = "ピンク"
    elif c1 == "ピンク": c2 = "赤オレ"
    elif c1 == "コーラ": c2 = "赤オレ"
    elif c1 == "黒/海苔": c2 = "コーラ"
    elif c1 == "赤オレ": c2 = "マジョーラゼブラ"
    elif c1 == "オレンジ": c2 = "赤オレ"
    elif c1 == "グリーン": c2 = "オレ金"
    
    if s1 == "強波動": s2 = "ショート"
    elif s1 == "ショート": s2 = "極細"
    else: s2 = "カーリー"
    
    return f"{c1}×{s1}", f"{c2}×{s2}", speed, hook

@st.cache_data(ttl=3600)
def get_weather_data(target_date):
    bm = "https://marine-api.open-meteo.com/v1/marine"
    bw = "https://api.open-meteo.com/v1/forecast"
    d_str = target_date.strftime("%Y-%m-%d")
    y_str = (target_date - datetime.timedelta(days=1)).strftime("%Y-%m-%d")
    
    p_temp = {"latitude": AKASHI_LAT, "longitude": AKASHI_LON, "hourly": "sea_surface_temperature", "start_date": y_str, "end_date": d_str}
    
    p_weather = {
        "latitude": AKASHI_LAT, 
        "longitude": AKASHI_LON, 
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
        <h1 style='text-align: center; font-size: 36px; margin-bottom: 10px; font-weight: 800;'>
            <span style='margin-right: 1em;'>🌊 魔釣</span><br>
            <span style='font-size: 28px; font-weight: normal;'>明石タイラバ予報</span>
        </h1>
        <p style='text-align: center; font-size: 13px; color: gray; margin-bottom: 20px;'>
            明石海峡の潮流・水温・天気・ベイトから<br>
            <b>「攻め時」</b>と<b>「ネクタイ」</b>を解析します。
        </p>
    """, unsafe_allow_html=True)

    target_date = st.date_input("釣行日を選択してください", datetime.date.today() + datetime.timedelta(days=1))
    
    bait_name, bait_colors = get_seasonal_bait(target_date.month)
    st.info(f"🐟 **現在のシーズナルパターン: {bait_name}**\n\n有効カラー目安: {bait_colors}")

    if st.button("魔釣予報を開始する"):
        with st.spinner('明石の海況・気象・ベイトパターンを解析中...'):
            mage = get_moon_age(target_date)
            tname, s30 = get_sinker_weight(mage, 30)
            _, s45 = get_sinker_weight(mage, 45)
            _, s60 = get_sinker_weight(mage, 60)
            
            sd, wd = get_weather_data(target_date)
            sun_h = int(wd["daily"]["sunrise"][0].split('T')[1].split(':')[0]) if wd else 7
            
            r_temps = sd["hourly"]["sea_surface_temperature"] if sd else []
            r_clouds = wd["hourly"]["cloud_cover"] if (wd and "cloud_cover" in wd["hourly"]) else []
            r_winds = wd["hourly"]["wind_speed_10m"] if (wd and "wind_speed_10m" in wd["hourly"]) else []
            r_rains = wd["hourly"]["rain"] if (wd and "rain" in wd["hourly"]) else []
            
            OFF = 15
            use_historical = False
            valid_data = [t for t in r_temps if t is not None and t > 0]
            
            day_trend_score = 0
            day_trend_label = ""

            if not valid_data:
                use_historical = True
                avg_temp = HISTORICAL_TEMPS.get(target_date.month, 15.0)
                r_temps = [avg_temp] * 48
            else:
                if len(r_temps) >= 48:
                    avg_yesterday = sum(r_temps[0:24]) / 24
                    avg_today = sum(r_temps[24:48]) / 24
                    diff_day = avg_today - avg_yesterday
                    
                    if diff_day <= -0.5:
                        day_trend_score = -20
                        day_trend_label = "⚠️前日比↓"
                    elif diff_day >= 0.5:
                        day_trend_score = 10
                        day_trend_label = "前日比↑"

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
                st.markdown(f"""
                **推奨シンカー (目安)**
                - **水深30m**: {s30}
                - **水深45m**: {s45}
                - **水深60m**: {s60}
                """, unsafe_allow_html=True)
                st.caption("※船長の指示がある場合はそちらに従ってください。")
            
            if use_historical:
                st.info(f"⚠️ 長期予報のため、平年値（約{min_t}℃）を使用しています。")
            else:
                st.info(f"🌡️ 水温範囲: {min_t:.1f}℃ 〜 {max_t:.1f}℃")
                if day_trend_label == "⚠️前日比↓":
                     st.warning("⚠️ 前日より水温が平均0.5℃以上低下しています。活性が低い可能性があります。")
                elif day_trend_label == "前日比↑":
                     st.info("📈 前日より水温が上昇傾向です。活性アップに期待できます。")

            hl, sl, tl, tll, data_rows = [], [], [], [], []
            
            for h in range(5, 16):
                idx = OFF + h
                ct = r_temps[idx] if idx < len(r_temps) else 0
                pt = r_temps[idx-1] if idx>0 else ct
                tdiff = ct - pt
                if use_historical: tdiff = 0
                
                cloud = r_clouds[h] if (h < len(r_clouds)) else 0
                wind = r_winds[h] if (h < len(r_winds)) else 0
                rain = r_rains[h] if (h < len(r_rains)) else 0
                
                tlev, slack = estimate_akashi_tide(mage, h)
                
                # --- スコア計算 ---
                sc = 0
                if h == sun_h: sc += 40
                elif abs(h - sun_h) == 1: sc += 20
                if slack: sc += 50
                elif h>5 and abs(tlev - tll[-1]) > 0.3: sc += 30
                
                if not use_historical:
                    if tdiff >= 0.1: sc += 20
                    elif tdiff <= -0.1: sc -= 20
                
                sc += day_trend_score
                
                w_note = ""
                # 雨判定
                if rain >= 0.5:
                    sc += 10
                    w_note += "☔"
                elif cloud >= 60: 
                    sc += 10
                    w_note += "☁️"
                elif cloud <= 20:
                    sc -= 5
                    w_note += "☀️"
                else:
                    w_note += "⛅"

                if wind >= 10.0:
                    sc = 0
                    w_note += " 🌪️激風"
                elif wind >= 7.0:
                    sc += 5
                    w_note += f" 🌬️{wind}m"
                elif wind >= 3.0:
                    sc += 15
                    w_note += f" 🍃{wind}m"
                elif wind <= 1.5:
                    sc -= 15
                    w_note += " 凪"
                else:
                    w_note += f" {wind}m"
                
                # 水温ペナルティ
                low_temp_alert = ""
                if ct <= 10.0:
                    sc = int(sc * 0.2)
                    low_temp_alert = "⚠️低水温(激渋)"
                elif ct <= 12.0:
                    sc = int(sc * 0.5)
                    low_temp_alert = "⚠️低水温"
                
                if sc < 0: sc = 0
                if sc > 100: sc = 100
                
                # 【変更】巻き速度とフックも受け取る
                tie1, tie2, spd, hk = suggest_strategy(h, sun_h, sc, tdiff, target_date.month, ct, cloud, rain)
                
                time_str = f"{h}:00"
                
                notes = []
                if slack: notes.append("★転流")
                if low_temp_alert: notes.append(low_temp_alert)
                if rain >= 0.5: notes.append("濁り注意")
                if day_trend_label and not low_temp_alert: notes.append(day_trend_label)
                
                hl.append(h); sl.append(sc); tl.append(ct); tll.append(tlev)
                t_pct = int((tlev+1)*50)
                
                data_rows.append({
                    "時間": time_str,
                    "天気/風": w_note,
                    "潮位": f"{t_pct}%",
                    "本命": tie1,
                    "抑え": tie2,
                    "速度": spd,  # 追加
                    "針": hk,     # 追加
                    "備考": " ".join(notes)
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

            st.markdown("### 📝 戦略ネクタイ<br>(本命 / 抑え / 戦術)", unsafe_allow_html=True)
            
            df = pd.DataFrame(data_rows)
            # カラム設定で「速度」と「針」を見やすく
            st.dataframe(
                df, 
                use_container_width=True, 
                hide_index=True,
                column_config={
                    "速度": st.column_config.TextColumn("巻速度", width="small"),
                    "針": st.column_config.TextColumn("針", width="small"),
                }
            )
            
            st.caption("※時間の「★」は転流（潮止まり）の目安です。")
            st.caption("※推奨ネクタイはシミュレーションに基づく提案であり、釣果を保証するものではありません。状況に合わせて調整してください。")

            st.markdown("---")
            st.subheader("🔗 関連ツール")
            
            col_link1, col_link2 = st.columns(2)
            
            with col_link1:
                st.markdown("##### 🌊 公式データ")
                st.link_button("海上保安庁の潮流情報", KAIHO_URL)
                
            with col_link2:
                st.markdown("##### 🚤 釣り座(潮先)")
                st.link_button("どこの釣り座が釣れる？", SEAT_CHECKER_URL)

            st.markdown("---")
            st.markdown("""
            <div style='background-color: #f0f2f6; padding: 15px; border-radius: 5px; color: #555; font-size: 12px;'>
                <strong>【⚠️ 免責事項・利用規約】</strong><br><br>
                <strong>1. 情報の正確性</strong><br>
                本アプリの予報は独自の計算ロジックに基づく推測値であり、実際の気象・海況とは異なる場合があります。<br><br>
                <strong>2. 安全の確保（重要）</strong><br>
                出船の可否や現場での安全判断については、必ず<strong>海上保安庁の警報</strong>や<strong>船長の指示</strong>を最優先してください。<br>
                本アプリを航海用海図（ナビゲーション）の代わりに使用することは絶対にお止めください。<br><br>
                <strong>3. 責任の所在</strong><br>
                本アプリの利用に起因するいかなる損失・損害についても、開発者は一切の責任を負わず、補償等は行いません。<br><br>
                <strong>4. 営利利用の禁止</strong><br>
                本アプリのデータを<strong>第三者へ販売、再配布、または営利目的で利用することを固く禁じます。</strong><br>
                本アプリは個人の趣味の範囲でご利用ください。<br><br>
                <div style='text-align: right; margin-top: 10px;'>
                    <a href="https://open-meteo.com/" target="_blank" style="text-decoration: none; color: #555;">Weather data by Open-Meteo.com</a><br>
                    © 2026 魔釣 - Matsuri Fishing Forecast
                </div>
            </div>
            """, unsafe_allow_html=True)

if __name__ == "__main__":
    main()
