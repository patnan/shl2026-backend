# Requirements

A server that fetch data from internat, stoes it in a DB and provides API to get that persisted data.

The server is writtn in python.

* fetch* - methocds that fetsh data and store id DB
* get* - methods that get stored data from db and provide it to the user


There will be a polling loop that fetch data and stores it in the db as well as checks if there is any change and then sends notifications.

There will also be a REST server for accessing the data over HTTP using the get methods.


## Fetch the required data

### Fetch Game data

Fetched from an url like this: https://stats.swehockey.se/Game/Events/1004840

File: src/shl/game.py

Function name:  <code>fetchGame</code>.

Parameters:
    - gameId : string

Returns: (JSON object with the data for that game. Empty JSON if nothing has changed?)
    

### Fetch Table/Standings

Either fetch from https://stats.swehockey.se/ScheduleAndResults/Overview/18263 and store in DB.

File: src/shl/standings.py

Function name:  <code>fetchTable</code>.
Parameters:
    - seasonID : string

### Fetch Schdeule

Fetch from https://stats.swehockey.se/ScheduleAndResults/Schedule/18263

Function name:  <code>fetchSchedule</code>.
Parameters:
    - seasonID : string


## Dataproviders (get-methods)

### Get Schdeule

Fetch from DB

Function name:  <code>getSchedule</code>.
Parameters:
    - seasonID : string

API end point: *tbd*


### Get Todays games (from schedule?)

Fetch the games for a specific date, e.g. today.

Function name:  <code>fetchGamesForDate</code>.

Parameters:
    - seasonID : string
    - date : string  (YYYY-MM-DD)

API end point: *tbd*



### Get all played games from schedule

Get the shcdule from the DB and then filter

Parameters:
    - seasonID : string

### Get Table/Standings

Calculate from all played games

File: ?

Function name:  ?

Parameters:
    - seasonID : string

API end point: *tbd*
