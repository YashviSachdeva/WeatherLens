
import requests
import pandas as pd
import streamlit as st
import altair as alt
from datetime import datetime, timezone
from dateutil import tz

# ================= CONFIG =================
OPENWEATHER_API_KEY = "YOUR API KEY HERE"
UNITS = "metric"
DISPLAY_TZ = tz.gettz("Asia/Kolkata")

WEIGHT_TEMP = 0.4
WEIGHT_RAIN = 0.35
WEIGHT_AQI = 0.25

IDEAL_TEMP_LOW = 18
IDEAL_TEMP_HIGH = 28

# ================= SESSION STATE =================
if "weather_loaded" not in st.session_state:
    st.session_state.weather_loaded = False

# ================= UI =================
st.set_page_config(page_title="Smart Weather Advisor", layout="centered")

st.markdown("""
<style>
html, body, [class*="css"] {
    font-family: "Inter", "Segoe UI", sans-serif;
}

h1 { font-size: 2.1rem; font-weight: 600; }
h2 { font-size: 1.35rem; font-weight: 500; margin-top: 1.6rem; }

[data-testid="metric-container"] {
    background: #f7f8fa;
    border-radius: 10px;
    padding: 14px;
    border: 1px solid #e6e6e6;
}
</style>
""", unsafe_allow_html=True)

# ================= API HELPERS =================
def forecast_url(lat, lon):
    return f"https://api.openweathermap.org/data/2.5/forecast?lat={lat}&lon={lon}&units={UNITS}&appid={OPENWEATHER_API_KEY}"

def air_pollution_url(lat, lon):
    return f"https://api.openweathermap.org/data/2.5/air_pollution?lat={lat}&lon={lon}&appid={OPENWEATHER_API_KEY}"

def geocode_city(city):
    url = "https://api.openweathermap.org/geo/1.0/direct"
    params = {"q": city, "limit": 1, "appid": OPENWEATHER_API_KEY}
    r = requests.get(url, params=params, timeout=10)
    if r.status_code != 200 or not r.json():
        raise RuntimeError("City not found")
    j = r.json()[0]
    return j["lat"], j["lon"], j["name"]

def fetch_json(url):
    r = requests.get(url, timeout=10)
    if r.status_code >= 400:
        raise RuntimeError("API error")
    return r.json()

def to_local(ts):
    return datetime.fromtimestamp(ts, tz=timezone.utc).astimezone(DISPLAY_TZ)

# ================= SCORING =================
def temp_score(t):
    if IDEAL_TEMP_LOW <= t <= IDEAL_TEMP_HIGH:
        return 1
    if t < IDEAL_TEMP_LOW:
        return max(0, t / IDEAL_TEMP_LOW)
    return max(0, 1 - (t - IDEAL_TEMP_HIGH) / 20)

def rain_score(mm):
    return max(0, 1 - mm / 5)

def aqi_score(aqi):
    return (6 - aqi) / 5 if aqi else 1

def composite_score(temp, rain, aqi):
    return (
        WEIGHT_TEMP * temp_score(temp)
        + WEIGHT_RAIN * rain_score(rain)
        + WEIGHT_AQI * aqi_score(aqi)
    )

# ================= HEADER =================
st.title("🌤️ WeatherLens-Smart Weather & AQI Advisor")
st.caption("Weather + air quality ")

st.divider()

location = st.text_input(
    "📍 Location",
    "New Delhi",
    help="Enter city name or coordinates (lat,lon)"
)

# ================= FETCH DATA =================
if st.button("Fetch Weather"):
    try:
        try:
            lat, lon = map(float, location.split(","))
            place = location
        except:
            lat, lon, place = geocode_city(location)

        forecast = fetch_json(forecast_url(lat, lon))
        pollution = fetch_json(air_pollution_url(lat, lon))

        aqi_now = pollution["list"][0]["main"]["aqi"]

        rows = []
        rain_alert = None

        for i, block in enumerate(forecast["list"][:8]):
            dt = to_local(block["dt"])
            temp = block["main"]["temp"]
            rain_mm = block.get("rain", {}).get("3h", 0)

            if rain_mm > 0 and rain_alert is None:
                rain_alert = f"Rain likely in ~{i*3} hours"

            rows.append({
                "Time": dt,
                "Temp (°C)": temp,
                "Rain (mm)": rain_mm,
                "Score": composite_score(temp, rain_mm, aqi_now)
            })

        st.session_state.df = pd.DataFrame(rows)
        st.session_state.aqi_now = aqi_now
        st.session_state.place = place
        st.session_state.rain_alert = rain_alert
        st.session_state.weather_loaded = True

    except Exception as e:
        st.error(str(e))

# ================= MAIN DISPLAY =================
if st.session_state.weather_loaded:

    df = st.session_state.df
    aqi_now = st.session_state.aqi_now
    place = st.session_state.place
    rain_alert = st.session_state.rain_alert

    st.subheader(f"📍 {place}")

    st.write("")

    # ---- Weather overview
    st.subheader("🌡️ Weather Snapshot")
    c1, c2, c3 = st.columns(3)
    c1.metric("Now", f"{df.iloc[0]['Temp (°C)']:.1f} °C")
    c2.metric("High", f"{df['Temp (°C)'].max():.1f} °C")
    c3.metric("Low", f"{df['Temp (°C)'].min():.1f} °C")

    st.write("")

    # ---- AQI
    st.subheader("🫁 Air Quality")
    aqi_text = {
        1: "🟢 Good",
        2: "🟡 Fair",
        3: "🟠 Moderate",
        4: "🔴 Poor",
        5: "🚫 Very Poor"
    }
    st.write(f"**{aqi_text[aqi_now]}** air quality (scale 1–5)")
    if aqi_now >= 4:
        st.caption("Breathing outdoors for long durations is not advised.")

    st.write("")

    # ---- Rain
    st.subheader("🌧️ Rain Update")
    if rain_alert:
        st.warning(rain_alert)
    else:
        st.success("No rain expected — skies look clear ☀️")

    st.write("")

    # ---- Best time
    st.subheader("⏰ Best Time to Step Out")
    best = df.loc[df["Score"].idxmax()]
    st.metric(
        "Recommended window",
        best["Time"].strftime("%I:%M %p"),
        f"Comfort score {best['Score']:.2f}"
    )

    st.divider()

    # ---- Schedule check
    st.subheader("📅 Should You Go?")
    with st.form("schedule"):
        event_time = st.time_input("Event start time")
        event_type = st.radio("Event type", ["Outdoor", "Indoor"])
        check = st.form_submit_button("Check")

    if check:
        event_dt = datetime.now(DISPLAY_TZ).replace(
            hour=event_time.hour,
            minute=event_time.minute,
            second=0,
            microsecond=0
        )

        df_tmp = df.copy()
        df_tmp["diff"] = df_tmp["Time"].apply(
            lambda t: abs((t - event_dt).total_seconds())
        )
        row = df_tmp.loc[df_tmp["diff"].idxmin()]

        reasons = []
        decision = "✅ Safe to go"
        tone = st.success

        if event_type == "Outdoor" and row["Rain (mm)"] > 0.5:
            decision = "❌ Not recommended"
            reasons.append("Rain is expected around this time.")
            tone = st.error

        if event_type == "Outdoor" and aqi_now >= 4:
            decision = "❌ Not recommended"
            reasons.append("Air quality is poor and unsafe outdoors.")
            tone = st.error

        if row["Temp (°C)"] > 38:
            if decision != "❌ Not recommended":
                decision = "⚠️ Go with caution"
                tone = st.warning
            reasons.append("High temperature may cause discomfort.")

        tone(decision)

        st.markdown("**Why this decision?**")
        if reasons:
            for r in reasons:
                st.write("•", r)
        else:
            st.write("• Weather and air quality are suitable.")

        st.caption(
            f"Checked for {row['Time'].strftime('%I:%M %p')} · "
            f"Temp {row['Temp (°C)']:.1f}°C · "
            f"Rain {row['Rain (mm)']} mm · "
            f"AQI {aqi_now}"
        )

    st.divider()

    # ---- Details
    with st.expander("📊 View forecast details"):
        st.dataframe(df)

        base = alt.Chart(df).encode(x="Time:T")
        st.altair_chart(
            alt.layer(
                base.mark_line().encode(y="Temp (°C):Q"),
                base.mark_bar(opacity=0.3).encode(y="Rain (mm):Q"),
                base.mark_area(opacity=0.2).encode(y="Score:Q")
            ).resolve_scale(y="independent"),
            use_container_width=True
        )

    st.caption("Built with Python · Streamlit · OpenWeather")
