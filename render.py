"""Render the Mt Hood night screen for a Kindle mounted in landscape.

Usage: python render.py OUTDIR

OUTDIR may already hold last-good.jpg and state.json from the previous run;
they are the day's last good webcam frame, carried forward for the thumbnail.
Writes night.png (800x600, for viewing), night-kindle.png (rotated 90 degrees
clockwise for the Kindle's portrait panel), index.html, and the updated state.

All data comes from keyless public APIs: Open-Meteo, USNO, sunrise-sunset.org
and NOAA SWPC.
"""
import json, math, os, sys, urllib.request
from datetime import date, datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path
from zoneinfo import ZoneInfo
from PIL import Image, ImageDraw, ImageFont, ImageStat

LAT, LON, ELEV_M = 45.3311, -121.7110, 2130      # Palmer/Silcox
SUMMIT = (45.3736, -121.6960, 3429)                # lat, lon, metres (11,249 ft)
TZ = ZoneInfo("America/Los_Angeles")
CAM_URL = "https://timberlinelodge.com/snowcameras/palmerbottom.jpg"
GOOD_FRAME = 60        # mean brightness (0-255) for a frame worth keeping
W, H = 800, 600
INK, MID, LIGHT = 0, 0x77, 0xCC
FONTS = Path(__file__).parent / "fonts"

# Peak night (evening date) for 2026 and typical ZHR. IMO 2026 dates for the
# majors; peaks drift by about a day between years, so refresh this yearly.
SHOWERS = [("Quadrantids", 1, 2, 80), ("Lyrids", 4, 21, 18), ("Eta Aquariids", 5, 5, 50),
           ("S. Delta Aquariids", 7, 30, 25), ("Perseids", 8, 12, 100), ("Orionids", 10, 21, 20),
           ("Leonids", 11, 16, 15), ("Geminids", 12, 13, 150), ("Ursids", 12, 21, 10)]


def get(url, raw=False):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (kindle-night-screen)"})
    with urllib.request.urlopen(req, timeout=25) as r:
        return r.read() if raw else json.load(r)


def font(size, weight="Regular"):
    return ImageFont.truetype(str(FONTS / f"Barlow-{weight}.ttf"), size)


def local(s):
    dt = datetime.fromisoformat(s)
    return dt.astimezone(TZ) if dt.tzinfo else dt.replace(tzinfo=TZ)


def hm(dt):
    return dt.strftime("%-I:%M") + ("a" if dt.hour < 12 else "p")


def hour_label(dt):
    return f"{dt.hour % 12 or 12}{'a' if dt.hour < 12 else 'p'}"


def twilight(d):
    r = get(f"https://api.sunrise-sunset.org/json?lat={LAT}&lng={LON}&date={d}"
            "&formatted=0&tzid=America/Los_Angeles")["results"]
    return {k: local(v) for k, v in r.items() if k != "day_length"}


def usno(d):
    return get(f"https://aa.usno.navy.mil/api/rstt/oneday?date={d}"
               f"&coords={LAT},{LON}&tz=-8&dst=true")["properties"]["data"]


def moon_events(d, data):
    return [(datetime.combine(d, datetime.strptime(m["time"][:5], "%H:%M").time(), TZ), m["phen"])
            for m in data["moondata"] if m["phen"] in ("Rise", "Set")]


def update_last_good(outdir, now):
    """Keep the newest webcam frame that is bright enough to be worth showing."""
    state_path = outdir / "state.json"
    state = json.loads(state_path.read_text()) if state_path.exists() else {}
    try:
        frame = Image.open(BytesIO(get(f"{CAM_URL}?nocache={int(now.timestamp())}", raw=True)))
        if ImageStat.Stat(frame.convert("L")).mean[0] >= GOOD_FRAME:
            frame.convert("RGB").save(outdir / "last-good.jpg", quality=85)
            state["last_good_time"] = now.isoformat()
    except Exception as e:                      # the thumbnail is optional; never fail the render
        print(f"webcam fetch failed: {e}", file=sys.stderr)
    state_path.write_text(json.dumps(state))
    if (outdir / "last-good.jpg").exists() and "last_good_time" in state:
        return Image.open(outdir / "last-good.jpg"), datetime.fromisoformat(state["last_good_time"])
    return None, None


def moon_disc(img, cx, cy, r, illum, waxing):
    # The terminator is the ellipse x = k * sqrt(1 - y^2), with k = 1 - 2 * illumination.
    k = 1 - 2 * illum
    for py in range(-r, r + 1):
        for px in range(-r, r + 1):
            x, y = px / r, py / r
            if x * x + y * y > 1:
                continue
            edge = k * math.sqrt(max(0.0, 1 - y * y))
            img.putpixel((cx + px, cy + py), 255 if (x > edge if waxing else x < -edge) else 0x33)
    ImageDraw.Draw(img).ellipse((cx - r, cy - r, cx + r, cy + r), outline=INK, width=2)


def main():
    outdir = Path(sys.argv[1] if len(sys.argv) > 1 else "site")
    outdir.mkdir(parents=True, exist_ok=True)
    now = datetime.now(TZ)

    # "Tonight" is the night that began this evening; before 10am it is the one just ending.
    tonight = now.date() - timedelta(days=1 if now.hour < 10 else 0)
    tomorrow = tonight + timedelta(days=1)
    eve, morn = twilight(tonight), twilight(tomorrow)
    start = eve["sunset"].replace(minute=0, second=0, microsecond=0)
    end = (morn["sunrise"] + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)

    om = get(f"https://api.open-meteo.com/v1/forecast?latitude={LAT}&longitude={LON}&elevation={ELEV_M}"
             "&hourly=cloud_cover,temperature_2m,freezing_level_height,snowfall"
             "&temperature_unit=fahrenheit&timezone=America/Los_Angeles"
             f"&start_date={tonight}&end_date={tomorrow}")["hourly"]
    hours = [dict(t=local(t), cloud=c, temp=f, frz=z, snow=s or 0) for t, c, f, z, s in
             zip(om["time"], om["cloud_cover"], om["temperature_2m"], om["freezing_level_height"], om["snowfall"])
             if start <= local(t) <= end]

    sm = get(f"https://api.open-meteo.com/v1/forecast?latitude={SUMMIT[0]}&longitude={SUMMIT[1]}"
             "&hourly=wind_speed_700hPa,wind_speed_650hPa,geopotential_height_700hPa,geopotential_height_650hPa"
             "&wind_speed_unit=mph&timezone=America/Los_Angeles"
             f"&start_date={tonight}&end_date={tomorrow}")["hourly"]
    summit_wind = []
    for t, w7, w6, z7, z6 in zip(sm["time"], sm["wind_speed_700hPa"], sm["wind_speed_650hPa"],
                                 sm["geopotential_height_700hPa"], sm["geopotential_height_650hPa"]):
        if start <= local(t) <= end and None not in (w7, w6, z7, z6):
            f = min(1, max(0, (SUMMIT[2] - z7) / (z6 - z7)))     # interpolate to summit height
            summit_wind.append(w7 + f * (w6 - w7))

    moon_today = usno(tonight)
    events = sorted(moon_events(tonight - timedelta(days=1), usno(tonight - timedelta(days=1)))
                    + moon_events(tonight, moon_today) + moon_events(tomorrow, usno(tomorrow)))
    before = [e for e in events if e[0] <= start]
    cur = start if before and before[-1][1] == "Rise" else None
    moon_spans = []
    for t, phen in events:
        if start < t < end:
            if phen == "Rise":
                cur = t
            elif cur:
                moon_spans.append((cur, t))
                cur = None
    if cur:
        moon_spans.append((cur, end))
    illum = int(str(moon_today["fracillum"]).rstrip("%")) / 100
    phase = moon_today["curphase"]
    waxing = "Waxing" in phase or phase == "First Quarter"

    # Dark-sky window: astronomical night with the moon down.
    dark_a, dark_b = eve["astronomical_twilight_end"], morn["astronomical_twilight_begin"]
    for a, b in moon_spans:
        if a <= dark_a < b:
            dark_a = b
        if a < dark_b <= b:
            dark_b = a
    dark_mins = max(0, int((dark_b - dark_a).total_seconds() // 60))
    clouds = [h["cloud"] for h in hours if dark_a <= h["t"] <= dark_b] or [100]
    avg_cloud = sum(clouds) / len(clouds)
    verdict = ("clear" if avg_cloud < 15 else "mostly clear" if avg_cloud < 40
               else "partly cloudy" if avg_cloud < 70 else "cloudy")

    kp_rows = get("https://services.swpc.noaa.gov/products/noaa-planetary-k-index-forecast.json")
    if isinstance(kp_rows[0], list):
        kp_rows = [dict(zip(kp_rows[0], r)) for r in kp_rows[1:]]
    kp = [float(r["kp"]) for r in kp_rows
          if start - timedelta(hours=3) <= datetime.fromisoformat(r["time_tag"]).replace(tzinfo=timezone.utc) <= end]
    kp_max = max(kp) if kp else 0.0
    aurora = "aurora unlikely" if kp_max < 5 else "watch north" if kp_max < 6 else "aurora possible!"

    # Next meteor shower peak on or after tonight.
    peaks = sorted((date(y, m, d), name, zhr) for y in (tonight.year, tonight.year + 1)
                   for name, m, d, zhr in SHOWERS)
    peak_date, shower, zhr = next(p for p in peaks if p[0] >= tonight - timedelta(days=1))
    peak_moon = int(str(usno(peak_date)["fracillum"]).rstrip("%"))
    days = (peak_date - tonight).days
    when = ("peak TONIGHT" if days == 0 else "peaked last night" if days < 0
            else "peak tomorrow night" if days == 1 else f"peak {peak_date:%b %-d}")
    meteor_line = f"{shower} {when}  ·  ~{zhr}/hr  ·  moon {peak_moon}%"

    low = min(hours, key=lambda h: h["temp"])
    frz_ft = min(h["frz"] for h in hours) * 3.281
    snow_in = sum(h["snow"] for h in hours) / 2.54
    winter = os.environ.get("WINTER") == "1" or now.month in (11, 12, 1, 2, 3, 4) or snow_in > 0
    thumb, thumb_time = update_last_good(outdir, now)

    # ---------- draw ----------
    img = Image.new("L", (W, H), 255)
    d = ImageDraw.Draw(img)
    d.text((32, 20), "TONIGHT ON MT HOOD", font=font(28, "Bold"), fill=INK)
    d.text((W - 32, 24), f"{tonight:%a %b %-d}", font=font(24), fill=MID, anchor="ra")
    d.line((32, 62, W - 32, 62), fill=INK, width=2)

    d.text((32, 78), "DARK SKY WINDOW", font=font(17, "Medium"), fill=MID)
    if dark_mins:
        d.text((30, 94), f"{hm(dark_a)} – {hm(dark_b)}", font=font(60, "Bold"), fill=INK)
        d.text((33, 164), f"{dark_mins // 60}h {dark_mins % 60:02d}m  ·  {verdict}", font=font(26), fill=INK)
    else:
        d.text((30, 94), "none tonight", font=font(60, "Bold"), fill=INK)
        d.text((33, 164), "moon up through astronomical night", font=font(24), fill=INK)
    d.text((33, 206), meteor_line, font=font(20, "Medium"), fill=INK)

    if thumb:
        tw_, th_ = 176, 117
        tx0, ty0 = 470, 76
        img.paste(thumb.convert("L").resize((tw_, th_), Image.LANCZOS), (tx0, ty0))
        d.rectangle((tx0 - 1, ty0 - 1, tx0 + tw_, ty0 + th_), outline=INK, width=1)
        d.text((tx0 + tw_ / 2, ty0 + th_ + 8), f"last light {hm(thumb_time.astimezone(TZ))}",
               font=font(16), fill=MID, anchor="ma")

    cx, cy, r = 712, 126, 46
    moon_disc(img, cx, cy, r, illum, waxing)
    short = {"Waxing Crescent": "crescent", "Waning Crescent": "crescent", "Waxing Gibbous": "gibbous",
             "Waning Gibbous": "gibbous", "First Quarter": "1st quarter", "Last Quarter": "last quarter",
             "Full Moon": "full", "New Moon": "new"}.get(phase, phase.lower())
    d.text((cx, cy + r + 8), f"{short} {round(illum * 100)}%", font=font(16, "Medium"), fill=INK, anchor="ma")
    msets = [hm(t) for t, p in events if p == "Set" and start < t < end]
    mrises = [hm(t) for t, p in events if p == "Rise" and start < t < end]
    d.text((cx, cy + r + 28), f"sets {msets[0]}" if msets else f"rises {mrises[0]}" if mrises else "",
           font=font(16), fill=MID, anchor="ma")

    # timeline
    X0, X1, TY = 40, W - 40, 292
    span = (end - start).total_seconds()
    def tx(t): return X0 + (X1 - X0) * (t - start).total_seconds() / span
    phases = [(start, eve["sunset"], 255), (eve["sunset"], eve["civil_twilight_end"], 0xDD),
              (eve["civil_twilight_end"], eve["nautical_twilight_end"], 0xAA),
              (eve["nautical_twilight_end"], eve["astronomical_twilight_end"], 0x66),
              (eve["astronomical_twilight_end"], morn["astronomical_twilight_begin"], 0x11),
              (morn["astronomical_twilight_begin"], morn["nautical_twilight_begin"], 0x66),
              (morn["nautical_twilight_begin"], morn["civil_twilight_begin"], 0xAA),
              (morn["civil_twilight_begin"], morn["sunrise"], 0xDD), (morn["sunrise"], end, 255)]
    for a, b, g in phases:
        if b > a:
            d.rectangle((tx(max(a, start)), TY, tx(min(b, end)), TY + 32), fill=g)
    d.rectangle((X0, TY, X1, TY + 32), outline=INK, width=1)
    if dark_mins:
        ya = TY - 12
        d.line((tx(dark_a), ya, tx(dark_b), ya), fill=INK, width=3)
        for t in (dark_a, dark_b):
            d.line((tx(t), ya - 6, tx(t), ya + 6), fill=INK, width=3)
    if winter:
        d.text((X1, TY - 30), f"sunrise {hm(morn['sunrise'])}", font=font(15), fill=MID, anchor="ra")
    for a, b in moon_spans:
        d.rectangle((tx(a), TY + 40, tx(b), TY + 47), fill=LIGHT)
        d.text((tx(a) + 3, TY + 50), "moon up", font=font(14), fill=MID)

    CY = TY + 128
    per_hour = (X1 - X0) / (span / 3600)
    step = 2 if span / 3600 <= 13 else 3
    d.line((X0, CY - 50, X1, CY - 50), fill=LIGHT, width=1)
    d.text((X1, CY - 66), "cloud cover  100%", font=font(14), fill=MID, anchor="ra")
    if max(h["cloud"] for h in hours) < 5:
        d.text(((X0 + X1) / 2, CY - 32), "clear all night", font=font(16), fill=MID, anchor="ma")
    for h in hours:
        x = tx(h["t"])
        bw = per_hour * 0.32
        d.rectangle((x - bw, CY - max(2, h["cloud"] * 0.5), x + bw, CY), fill=INK)
        if h["t"].hour % step == start.hour % step:
            d.text((x, CY + 6), f"{round(h['temp'])}°", font=font(16, "Medium"), fill=INK, anchor="ma")
            d.text((x, CY + 25), hour_label(h["t"]), font=font(14), fill=MID, anchor="ma")

    # stat tiles
    frz = f"{round(frz_ft / 100) * 100:,}"
    frz_note = "above summit" if frz_ft > SUMMIT[2] * 3.281 else "below summit"
    kp_tile = ("KP INDEX", f"{kp_max:.1f}", aurora)
    low_tile = ("OVERNIGHT LOW", f"{round(low['temp'])}°", f"around {hm(low['t'])}")
    if winter:
        wind = max(summit_wind) if summit_wind else 0
        tiles = [low_tile, ("NEW SNOW", f'{snow_in:.1f}"', "overnight at Palmer"),
                 ("SUMMIT WIND", f"{round(wind)}", "mph peak, 11,249 ft"), kp_tile,
                 ("FREEZING (FT)", frz, frz_note)]
    else:
        tiles = [low_tile, ("SUNRISE", hm(morn["sunrise"]), f"first light {hm(morn['civil_twilight_begin'])}"),
                 kp_tile, ("FREEZING LEVEL (FT)", frz, frz_note)]
    tw = (W - 64) / len(tiles)
    big = 40 if len(tiles) == 4 else 34
    for i, (label, value, sub) in enumerate(tiles):
        x = 32 + i * tw
        if i:
            d.line((x, 490, x, 580), fill=LIGHT, width=1)
        d.text((x + 12, 490), label, font=font(14, "Medium"), fill=MID)
        d.text((x + 12, 506), value, font=font(big, "Bold"), fill=INK)
        d.text((x + 12, 556), sub, font=font(15), fill=INK)
    d.text((W - 32, H - 6), f"updated {hm(now)}", font=font(12), fill=MID, anchor="rs")

    img = img.point(lambda v: round(v / 17) * 17)     # the panel's 16 grey levels
    img.save(outdir / "night.png")
    img.rotate(-90, expand=True).save(outdir / "night-kindle.png")
    (outdir / "index.html").write_text(
        '<!doctype html><meta name="viewport" content="width=device-width">'
        '<title>Mt Hood night screen</title>'
        '<body style="margin:0;background:#fff"><img src="night.png" style="width:100%;max-width:800px">')
    print(f"{outdir}/night.png  dark {hm(dark_a)}-{hm(dark_b)} {verdict}  moon {illum:.0%}  kp {kp_max}  "
          f"low {low['temp']}F  snow {snow_in:.1f}in  wind {max(summit_wind, default=0):.0f}mph  "
          f"next shower {shower} {peak_date}  winter={winter}  thumb={'yes' if thumb else 'no'}")


if __name__ == "__main__":
    main()
