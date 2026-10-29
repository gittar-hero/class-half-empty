"""Class Half Empty — find empty Technion classrooms in every time slot.

Data comes live from the same source CheeseFork (https://cheesefork.cf) uses:
https://github.com/michael-maltsev/technion-sap-info-fetcher (gh-pages branch).
"""
from __future__ import annotations

import datetime as dt
import html
from zoneinfo import ZoneInfo

import requests
import streamlit as st
from PIL import Image, ImageDraw

DATA_BASE = "https://raw.githubusercontent.com/michael-maltsev/technion-sap-info-fetcher/gh-pages"
TZ = ZoneInfo("Asia/Jerusalem")
DAYS_HE = ["ראשון", "שני", "שלישי", "רביעי", "חמישי", "שישי"]
DAYS_EN = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
SEM_NAMES = {200: "Winter", 201: "Spring", 202: "Summer"}
SLOT_START, SLOT_END = 8 * 60 + 30, 21 * 60 + 30
SLOTS = [(t, t + 60) for t in range(SLOT_START, SLOT_END, 60)]
CACHE_TTL = 60 * 60  # re-download at most once an hour


def fmt(m: int) -> str:
    return f"{m // 60:02d}:{m % 60:02d}"


def to_min(t: str) -> int:
    h, m = t.strip().split(":")
    return int(h) * 60 + int(m)


def sem_label(s: dict) -> str:
    name = SEM_NAMES.get(s["semester"], "Semester")
    y = s["year"]
    return f"{name} {y}–{str(y + 1)[2:]}" if s["semester"] == 200 else f"{name} {y + 1}"


# ---------------------------------------------------------------- glass
INK, WATER, WATER_LIGHT, GLASS_BG = "#1C2E3D", "#5DB0E3", "#B9E0F6", "#F2F7FB"
GLASS_PATH = "M10 6 H54 L48.5 72 Q48 76 44 76 H20 Q16 76 15.5 72 Z"


def glass_svg(fill: float, height: int = 84) -> str:
    """A glass of water, `fill` (0–1) full, with gently moving waves."""
    fill = max(0.0, min(1.0, fill))
    y = 74 - 66 * fill

    def wave(level: float) -> str:
        return f"M-64 {level:.1f} " + "q8 -3 16 0 t16 0 " * 6 + "V80 H-64 Z"

    return (
        f'<svg class="glass" width="{height * 0.8:.0f}" height="{height}" viewBox="0 0 64 80" '
        f'role="img" aria-label="glass {round(fill * 100)}% full">'
        f'<defs><clipPath id="glass-clip"><path d="{GLASS_PATH}"/></clipPath></defs>'
        f'<g clip-path="url(#glass-clip)"><rect width="64" height="80" fill="{GLASS_BG}"/>'
        f'<path class="wave back" d="{wave(y - 1.5)}" fill="{WATER_LIGHT}"/>'
        f'<path class="wave" d="{wave(y)}" fill="{WATER}"/></g>'
        f'<path d="{GLASS_PATH}" fill="none" stroke="{INK}" stroke-width="2.5" stroke-linejoin="round"/>'
        '<path d="M16 14 L20 64" stroke="#fff" stroke-width="2.5" stroke-linecap="round" opacity=".6"/>'
        "</svg>"
    )


def glass_icon() -> Image.Image:
    img = Image.new("RGBA", (64, 64))
    d = ImageDraw.Draw(img)
    pts = [(10, 6), (54, 6), (47, 58), (17, 58)]
    d.polygon([(13.5, 32), (50.5, 32), (47, 58), (17, 58)], fill=WATER)
    d.line(pts + [pts[0]], fill=INK, width=5, joint="curve")
    return img


# ---------------------------------------------------------------- data
@st.cache_data(ttl=CACHE_TTL, show_spinner="Loading semesters…")
def load_semesters() -> list[dict]:
    r = requests.get(f"{DATA_BASE}/last_semesters.json", timeout=30)
    r.raise_for_status()
    return r.json()


@st.cache_data(ttl=CACHE_TTL, show_spinner="Downloading the latest timetable…")
def load_events(year: int, semester: int) -> tuple[list[dict], str]:
    r = requests.get(f"{DATA_BASE}/courses_{year}_{semester}.json", timeout=60)
    r.raise_for_status()
    rows, seen = [], set()
    for c in r.json():
        g = c.get("general", {})
        for s in c.get("schedule", []):
            building = (s.get("בניין") or "").strip()
            room = s.get("חדר")
            day = s.get("יום")
            hours = s.get("שעה")
            if not building or not room or room in (0, 999) or day not in DAYS_HE or not hours:
                continue
            try:
                a, e = (to_min(x) for x in hours.split(" - "))
            except ValueError:
                continue
            row = {
                "building": building,
                "room": str(room),
                "day": DAYS_HE.index(day),
                "start": a,
                "end": e,
                "course_no": g.get("מספר מקצוע", ""),
                "course": g.get("שם מקצוע", ""),
                "type": (s.get("סוג") or "").strip(),
            }
            key = tuple(row.values())
            if key not in seen:
                seen.add(key)
                rows.append(row)
    fetched = dt.datetime.now(TZ).strftime("%d %b %Y, %H:%M")
    return rows, fetched


def room_sort_key(r: tuple[str, str]):
    b, n = r
    digits = "".join(ch for ch in n if ch.isdigit())
    return (b, int(digits) if digits else 0, n)


def busy_index(events: list[dict]) -> dict:
    """{(building, room): {day: [(start, end), ...]}}"""
    idx: dict = {}
    for ev in events:
        idx.setdefault((ev["building"], ev["room"]), {}).setdefault(ev["day"], []).append((ev["start"], ev["end"]))
    for days in idx.values():
        for d in days:
            days[d].sort()
    return idx


def is_free(intervals, s, e) -> bool:
    return not any(a < e and b > s for a, b in intervals)


def free_until(intervals, t):
    nxt = [a for a, b in intervals if b > t and a >= t]
    return min(nxt) if nxt else None


def dur_label(m: int) -> str:
    return f"{m // 60}h {m % 60}m".replace(" 0m", "").replace("0h ", "")


def show_rooms(free: list) -> None:
    """Render [((building, room), free_until), ...] as room tags grouped by building."""
    if not free:
        st.write("Every listed room is in use.")
        return
    groups: dict[str, list] = {}
    for (b, n), u in free:
        groups.setdefault(b, []).append((n, u))
    parts = []
    for b, rs in groups.items():
        tags = "".join(
            f'<span class="tag" title="free {"rest of day" if u is None else "until " + fmt(u)}">'
            f'{html.escape(n)}{"" if u is None else f" <small>→{fmt(u)}</small>"}</span>'
            for n, u in rs
        )
        parts.append(f'<div class="bld"><div class="bname">{html.escape(b)}</div><div class="tags">{tags}</div></div>')
    st.markdown("".join(parts), unsafe_allow_html=True)
    st.caption("→ time = when the room's next class starts. No arrow = free for the rest of the day.")


# ---------------------------------------------------------------- page
CREDITS_MD = (
    "**Class Half Empty is an independent student project.** It is not an official Technion service "
    "and is not affiliated with or endorsed by the Technion.\n\n"
    "Timetable data comes from the Technion's public course catalog, collected by "
    "[technion-sap-info-fetcher](https://github.com/michael-maltsev/technion-sap-info-fetcher) by Michael Maltsev, "
    "the data source behind [CheeseFork](https://cheesefork.cf). Huge thanks to the creators of CheeseFork: "
    "this app couldn't exist without their work. Class Half Empty is not part of CheeseFork, and its code is independent."
)

st.set_page_config(
    page_title="Class Half Empty",
    page_icon=glass_icon(),
    layout="wide",
    menu_items={"About": CREDITS_MD},
)
st.markdown(
    """
<style>
.hero{display:flex;align-items:center;gap:22px;padding:6px 0 10px}
.hero .glass{flex:none}
.hero .name{font-size:2.5rem;font-weight:750;letter-spacing:-.03em;line-height:1.05;color:#1C2E3D}
.hero .name span{color:#2F8FD0}
.hero .tagline{color:#5A7184;margin-top:4px}
.hero .note{color:#5A7184;font-size:.8rem;margin-top:8px}
.hero .note a{color:#1C5A85}
.hero .stat{display:inline-block;margin-top:10px;padding:4px 12px;border-radius:999px;
            background:#EAF4FB;color:#1C5A85;font-size:.9rem}
.glass .wave{animation:wave 3s linear infinite}
.glass .wave.back{animation-duration:5s;animation-direction:reverse}
@keyframes wave{to{transform:translateX(32px)}}
@media (prefers-reduced-motion:reduce){.glass .wave{animation:none}}
[data-testid="stExpander"] details{border-radius:14px;border-color:#E1ECF4}
.bld{display:grid;grid-template-columns:minmax(120px,220px) 1fr;gap:4px 14px;margin:8px 0;align-items:start}
.bname{direction:rtl;text-align:right;font-weight:600}
.tags{display:flex;flex-wrap:wrap;gap:6px}
.tag{font-family:ui-monospace,Menlo,monospace;font-size:.85rem;padding:2px 9px;border-radius:999px;
     background:#fff;border:1px solid #CFE3F1;color:#1C2E3D;white-space:nowrap}
.tag small{color:#2F8FD0;font-family:inherit}
.week{display:grid;grid-template-columns:3.2rem repeat(6,minmax(0,1fr));gap:2px;max-width:640px;margin:8px 0}
.week .cell{height:14px;border-radius:3px;background:#F2F7FB}
.week .busy{background:#5DB0E3}
.week .hd,.week .tm{background:none;height:auto;font-size:.75rem;color:#5A7184}
.week .hd{text-align:center;padding-bottom:2px}
.week .hd.sel{color:#1C2E3D;font-weight:700}
.week .tm{line-height:14px;font-variant-numeric:tabular-nums}
.cls{display:flex;gap:14px;align-items:baseline;padding:8px 0;border-bottom:1px solid #E1ECF4}
.cls .when{flex:none;font-variant-numeric:tabular-nums;color:#1C5A85;font-weight:600}
.cls .what{flex:1}
.cls small{display:block;color:#5A7184}
@media (max-width:640px){
  .bld{grid-template-columns:1fr}
  .bname{text-align:left}
  .hero{gap:14px}
  .hero .glass{width:52px;height:66px}
  .hero .name{font-size:1.75rem}
  .hero .tagline{font-size:.9rem}
}
.rtl{direction:rtl;text-align:right}
</style>
""",
    unsafe_allow_html=True,
)

hero = st.empty()

try:
    semesters = load_semesters()
except requests.RequestException as e:
    st.error(f"Couldn't reach the timetable source ({e}). Try again in a minute.")
    st.stop()

now = dt.datetime.now(TZ)
today_iso = now.date().isoformat()
started = [s for s in semesters if s["start"] <= today_iso] or semesters
current = max(started, key=lambda s: s["start"])
sem_options = sorted(semesters, key=lambda s: s["start"], reverse=True)

with st.sidebar:
    st.header("Settings")
    sem = st.selectbox(
        "Semester",
        sem_options,
        index=sem_options.index(current),
        format_func=sem_label,
    )
    if st.button("Refresh data now"):
        st.cache_data.clear()
        st.rerun()

try:
    events, fetched = load_events(sem["year"], sem["semester"])
except requests.RequestException as e:
    st.error(f"Couldn't download the timetable ({e}). Try again in a minute.")
    st.stop()

if not events:
    st.warning("This semester has no room assignments yet.")
    st.stop()

idx = busy_index(events)
all_rooms = sorted(idx.keys(), key=room_sort_key)
buildings = sorted({b for b, _ in all_rooms})

st.caption(
    f"{sem_label(sem)} · {len(all_rooms)} teaching rooms in {len(buildings)} buildings · "
    f"data fetched {fetched} (Israel time)"
)

today_idx = (now.weekday() + 1) % 7  # Python Mon=0 → Technion Sun=0
in_semester = sem["start"] <= today_iso <= sem["end"]
now_min = now.hour * 60 + now.minute

live = in_semester and today_idx <= 5 and SLOT_START <= now_min < SLOT_END

# The water is the rooms in use; the empty part of the glass is what you're looking for.
if live:
    busy_now = sum(not is_free(idx[r].get(today_idx, []), now_min, now_min + 1) for r in all_rooms)
    fill = busy_now / len(all_rooms)
    stat = f"Right now <b>{len(all_rooms) - busy_now}</b> of {len(all_rooms)} rooms are empty"
else:
    fill = 0.5
    stat = "No classes running right now · plan ahead below"
hero.markdown(
    f'<div class="hero">{glass_svg(fill)}<div>'
    f'<div class="name">Class <span>Half</span> Empty</div>'
    f'<div class="tagline">Find an empty classroom at the Technion, right now or any hour of the week.</div>'
    f'<div class="stat">{stat}</div>'
    '<div class="note">Independent student project, not an official Technion service. '
    'Data thanks to <a href="https://cheesefork.cf" target="_blank">CheeseFork</a>.</div></div></div>',
    unsafe_allow_html=True,
)

def day_select(key: str) -> int:
    return st.selectbox(
        "Day",
        range(6),
        index=today_idx if today_idx <= 5 else 0,
        format_func=lambda i: DAYS_EN[i] + (" (today)" if i == today_idx else ""),
        key=key,
    )


c1, c2 = st.columns(2)
with c1:
    bsel = st.multiselect("Buildings", buildings, placeholder="All buildings")
with c2:
    q = st.text_input("Search room or building", placeholder="e.g. 301 or אולמן").strip().lower()

rooms = [
    r for r in all_rooms
    if (not bsel or r[0] in bsel) and (not q or q in f"{r[1]} {r[0]}".lower())
]
if not rooms:
    st.info("No rooms match that filter.")
    st.stop()

tab_find, tab_slots, tab_room = st.tabs(["Find a room", "Every slot", "Room schedule"])

# ---- find a room: right now, or at a time you pick
with tab_find:
    mode = st.radio(
        "When",
        ["Right now", "Pick a time"],
        index=0 if live else 1,
        horizontal=True,
        label_visibility="collapsed",
    )
    if mode == "Right now":
        st.markdown(f"**{now:%A, %H:%M}** · Israel time")
        if not live:
            if not in_semester:
                why = "The semester isn't in session today"
            elif today_idx == 6:
                why = "It's Saturday, so no classes are scheduled"
            else:
                why = f"No classes are scheduled at this hour (teaching runs {fmt(SLOT_START)}–{fmt(SLOT_END)})"
            st.info(f"{why}. Every room is technically free, though buildings may be locked. "
                    "Choose **Pick a time** to plan ahead.")
        else:
            need = st.selectbox("Need it for at least", [0, 30, 60, 90, 120, 180],
                                format_func=lambda m: "Any length" if m == 0 else dur_label(m))
            hits = []
            for r in rooms:
                iv = idx[r].get(today_idx, [])
                if is_free(iv, now_min, now_min + max(need, 1)):
                    hits.append((r, free_until(iv, now_min)))
            st.write(f"**{len(hits)} of {len(rooms)} rooms** are empty right now")
            show_rooms(hits)
    else:
        f0, f1, f2 = st.columns(3)
        with f0:
            day = day_select("find_day")
        times = list(range(SLOT_START, SLOT_END - 29, 30))
        default_t = max(SLOT_START, min(SLOT_END - 30, -(-now_min // 30) * 30)) if live and day == today_idx else SLOT_START
        with f1:
            t0 = st.selectbox("From", times, index=times.index(default_t), format_func=fmt)
        with f2:
            dur = st.selectbox("For at least", [30, 60, 90, 120, 180, 240], index=1, format_func=dur_label)
        t1 = min(SLOT_END, t0 + dur)
        hits = []
        for r in rooms:
            iv = idx[r].get(day, [])
            if is_free(iv, t0, t1):
                hits.append((r, free_until(iv, t0)))
        st.write(f"**{len(hits)} of {len(rooms)} rooms** free on {DAYS_EN[day]} from {fmt(t0)} to {fmt(t1)}")
        show_rooms(hits)

# ---- every slot
with tab_slots:
    day = day_select("slots_day")
    is_today = day == today_idx and in_semester
    cur_slot = next((i for i, (s, e) in enumerate(SLOTS) if now_min < e), None) if is_today else None
    for i, (s, e) in enumerate(SLOTS):
        free = []
        for r in rooms:
            iv = idx[r].get(day, [])
            if is_free(iv, s, e):
                free.append((r, free_until(iv, e)))
        label = f"**{fmt(s)}–{fmt(e)}** · {len(free)} / {len(rooms)} free"
        if i == cur_slot:
            label += "  ← now"
        with st.expander(label, expanded=(cur_slot is not None and i in (cur_slot, cur_slot + 1)) or (cur_slot is None and i == 0)):
            show_rooms(free)

# ---- room schedule
with tab_room:
    r1, r2 = st.columns(2)
    with r1:
        pick = st.selectbox("Room", rooms, format_func=lambda r: f"{r[1]} — {r[0]}")
    with r2:
        day = day_select("room_day")
    # Weekly grid: filled (water) cells are busy half hours, empty cells are free.
    head = '<div class="cell hd"></div>' + "".join(
        f'<div class="cell hd{" sel" if d == day else ""}">{DAYS_EN[d][:3]}</div>' for d in range(6)
    )
    body = "".join(
        f'<div class="cell tm">{fmt(t) if t % 60 == 30 else ""}</div>'
        + "".join(
            f'<div class="cell{"" if is_free(idx[pick].get(d, []), t, t + 30) else " busy"}"></div>'
            for d in range(6)
        )
        for t in range(SLOT_START, SLOT_END, 30)
    )
    st.markdown(f'<div class="week">{head}{body}</div>', unsafe_allow_html=True)
    st.caption("Blue = a class is scheduled. White = free.")

    sub = sorted(
        (ev for ev in events if (ev["building"], ev["room"]) == pick and ev["day"] == day),
        key=lambda ev: ev["start"],
    )
    st.subheader(f"Classes on {DAYS_EN[day]}")
    if not sub:
        st.write("Nothing scheduled here that day.")
    else:
        st.markdown(
            "".join(
                f'<div class="cls"><div class="when">{fmt(ev["start"])}–{fmt(ev["end"])}</div>'
                f'<div class="what rtl">{html.escape(ev["course"])}'
                f'<small>{html.escape(ev["course_no"])}{" · " + html.escape(ev["type"]) if ev["type"] else ""}</small></div></div>'
                for ev in sub
            ),
            unsafe_allow_html=True,
        )

st.divider()
st.caption(
    "“Free” means no course in the Technion timetable is scheduled there at that time. "
    "Exams, events, reservations and locked rooms aren't in the data, and only rooms that host at least "
    "one course this semester are listed."
)
st.subheader("About & credits")
st.markdown(CREDITS_MD)
st.caption("Always check the official Technion timetable before relying on a room.")
