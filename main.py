from fastapi import FastAPI
from solarcalc import *
from fastapi.middleware.cors import CORSMiddleware
from misc import *

API_TOKEN = "8f0830ca7113e6565417609a26f7850e"
origins = ["http://localhost:3000"]

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Open the ASHRAE Model file
with open('ASHRAE.json', 'r') as file:
    # Load the JSON data into a dictionary
    ashrae = json.load(file)


@app.get("/")
async def root():
    return {"message": "Hello World"}


@app.get("/irradiance/date={year}:{month}:{day}:{hour}&cor={lat},{lon}&or={orientation}&angle={angle}")
async def irradiance(lat: float, lon: float, year: int, month: int, day: int, hour: int, orientation: str,
                     angle: float):
    diff = get_utc_offset(30.2, -84.981)  # get_utc_offset(lat, lon)
    print("UTC Offset", diff)
    # longitude
    lon = -84.981
    # latitude
    lat = 30.2
    # input date
    date = datetime.datetime(year, month, day, hour)
    print("Date: ", date)
    # fixed date with UTC Offset
    fixed_date = datetime.datetime(year, month, day, hour, tzinfo=datetime.timezone.utc) - datetime.timedelta(
        hours=-1 * diff)
    print("Date with UTC Offset: ", fixed_date)
    # local solar time
    ltsm = get_local_standard_meridian(diff)
    print("Local Standard Meridian: ", ltsm)
    eot = equation_of_time(date.timetuple().tm_yday)
    print("Equation Of Time: ", eot)
    tc = get_time_correction(lon, ltsm, eot)
    print("Time Correction: ", tc)
    local_solar_time = get_local_solar_time(tc, date)
    print("Local Solar Time: ", local_solar_time)
    hra = get_hra(local_solar_time)
    print("hour angle: ", hra)
    declination = get_dec(date)
    print("Declination: ", declination)
    solar_altitude = sun_altitude(declination, lat, hra)
    print("Elevation: ", solar_altitude)
    zenith = solar_zenith(solar_altitude)
    print("Solar Zenith", zenith)
    azimuth = get_solar_azimuth(zenith, hra, declination, lat, local_solar_time.hour)
    print("Azimuth: ", azimuth)
    aoi = angle_oi(angle, surface_azimuth(orientation), solar_altitude, azimuth)
    print("Aoi: ", aoi)


@app.get("/locationsearch&q={query}")
async def search_location(query: str):
    api_key = "ftSsz1bBFYcRrjGUUl9WkmERZHc-6rpmTrxaPRIWG4Q"
    r = requests.get(
        f"https://atlas.microsoft.com/search/address/json?&subscription-key=ftSsz1bBFYcRrjGUUl9WkmERZHc"
        f"-6rpmTrxaPRIWG4Q&api-version=1.0&language=en-US&query={query}")
    obj = r.json()

    result = {"result": []}
    k = 1
    for i in obj['results']:
        result['result'].append({
            "address": format_address(i),
            "position": {
                "lat": i['position']['lat'],
                "long": i['position']['lon']
            },
            "score": i['score'],
            "id": k

        })
        k = k + 1

        if k == 2:
            break

    return result


def format_address(i):
    address = ""
    if 'municipality' in i['address']:
        address += i['address']['municipality']
        address += " "
    if 'streetName' in i['address']:
        address += i['address']['streetName']
        address += " "
    if 'postalCode' in i['address']:
        address += i['address']['postalCode']
        address += " "
    return address


@app.get("/getUTC&q={lat},{long}")
def get_utc_offset(lat: float, long: float):
    r = requests.get(
        "https://atlas.microsoft.com/timezone/byCoordinates/json?api-version=1.0&subscription-key"
        f"=ftSsz1bBFYcRrjGUUl9WkmERZHc-6rpmTrxaPRIWG4Q&query={str(lat)},{str(long)}")
    return int(r.json().get('TimeZones')[0].get('ReferenceTime').get('StandardOffset').split(":")[0])


@app.post("/syncweather/")
async def fetch_weather_sync(loc: Loc):

    current_datetime = datetime.datetime.now()

    target_end = datetime.datetime(loc.end.year, loc.end.month, loc.end.day,loc.end.hour)

    current_datetime = current_datetime.replace(minute=0, second=0, microsecond=0)

    if (target_end > current_datetime):
        target_end = current_datetime
        #TODO: MAKE USE OF THE DURATION TO KNOW HOW MUCH TO RETRIEVE WHEN SYNCING


    path = f"https://history.openweathermap.org/data/2.5/history/city?lat={loc.lat}&lon={loc.lon}&type=hour&start={date_to_unix_time(loc.start.year, loc.start.month, loc.start.day, loc.start.hour)}&end={date_to_unix_time(target_end.year, target_end.month, target_end.day, target_end.hour)}&appid={API_TOKEN}&units=metric"
    print(path)
    r = requests.get(path)
    # Return a response
    response = r.json()['list']

    last_retrieved = unix_to_normal_time(response[len(response) - 1]['dt'])

    while not (
            (last_retrieved[0] == loc.end.year) and
            (last_retrieved[1] == loc.end.month) and
            (last_retrieved[2] == loc.end.day) and
            (last_retrieved[3] == loc.end.hour)
    ):
        path = f"https://history.openweathermap.org/data/2.5/history/city?lat={loc.lat}&lon={loc.lon}&type=hour&start={date_to_unix_time(last_retrieved[0], last_retrieved[1], last_retrieved[2], last_retrieved[3])}&end={date_to_unix_time(loc.end.year, loc.end.month, loc.end.day, loc.end.hour)}&appid={API_TOKEN}&units=metric"
        r = requests.get(path)
        addon_res = r.json()['list']


        last_retrieved = unix_to_normal_time(addon_res[len(addon_res) - 1]['dt'])

        response = response + addon_res


    db_results = []
    for weather in response:
        time = weather['dt']

        weather_data = {
            "time": unix_to_normal_time(time),
            "lon": loc.lon,
            "lat": loc.lat,
            "temp": weather['main']['temp'],
            "clouds": weather['clouds']['all'],
            #"utc": loc.utc
        }

        db_results.append(weather_data)

    print(db_results)

    return response


#TODO RETRIEVE YESTERDAY WEATHER

# TODO FIGURE OUT CRON JOB AND HOW TO ACTIVATE THE JOB