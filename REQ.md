# Requirements

## Fetch the required data

### Game data

Fetched from an url like this: https://stats.swehockey.se/Game/Events/1004840

File: src/shl/game.py

Function name:  <code>fetchGame</code>.

API end point: *tbd*

### Table/Standings

Either fetch from https://stats.swehockey.se/ScheduleAndResults/Overview/18263  or calcutae from all played games


File: src/shl/standings.py

Function name:  <code>fetchTable</code>.

API end point: *tbd*

### Schdeule

Fetch from https://stats.swehockey.se/ScheduleAndResults/Schedule/18263

Function name:  <code>fetchSchedule</code>.

API end point: *tbd*


### Todays games (from schedule?)

Fetch the games for a specific date, e.g. today.

Function name:  <code>fetchGamesForDate</code>.

API end point: *tbd*



### Get all played games from schedule

Fetch from https://stats.swehockey.se/ScheduleAndResults/Schedule/18263, likely using the <code>fetchSchedule</code> and then filter


