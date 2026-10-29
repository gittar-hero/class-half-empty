# Class Half Empty

A Streamlit app that shows which Technion classrooms are empty in every hourly slot.
The glass in the header fills with water as rooms fill with classes: the empty part is what you're after.
Each time someone opens it, it downloads the latest timetable from the same source
CheeseFork uses ([technion-sap-info-fetcher](https://github.com/michael-maltsev/technion-sap-info-fetcher)),
cached for up to an hour. The sidebar has a "Refresh data now" button.

## Features
- **Find a room**, in one of two modes:
  - **Right now**: the rooms empty at this moment (Israel time), optionally only ones free for at least 30 minutes, 1 hour, and so on.
  - **Pick a time**: choose a day, a start time and how long you need; get the rooms free for the whole window.
- **Every slot**: for the chosen day, every hour 08:30–21:30 with its free rooms grouped by building, and when each room's next class starts.
- **Room schedule**: a room's weekly occupancy grid and its classes on the chosen day.
- Filter by building or search by room number. Semester picker in the sidebar.

## Run on your computer
```bash
pip install -r requirements.txt
streamlit run app.py
```

## Put it online for free (Streamlit Community Cloud)
1. Create a new GitHub repository (public is simplest) and upload `app.py`, `requirements.txt` and the `.streamlit/` folder (it holds the theme).
2. Go to https://share.streamlit.io and sign in with GitHub.
3. Click **Create app** → **Deploy a public app from GitHub**, pick your repo, branch `main`, main file `app.py`.
4. Optionally choose a custom subdomain such as `class-half-empty.streamlit.app`, then **Deploy**.

Send that link to anyone; no sign-in needed to use it. Free apps go to sleep after a few days
without visitors, and the first visitor after that waits about 30 seconds while it wakes up.

## Note
"Free" means no course is scheduled in the room at that time. Exams, events, reservations and
locked rooms aren't in the data, and only rooms that host at least one course in the semester are listed.

## Disclaimer
This is an unofficial student project. It is not affiliated with or endorsed by the Technion.
Timetable data comes from the Technion's public course catalog as collected by
[technion-sap-info-fetcher](https://github.com/michael-maltsev/technion-sap-info-fetcher) (Michael Maltsev),
the data source behind [CheeseFork](https://cheesefork.cf). This app's code is independent of those projects.
