import io
import json
import sys

from fastapi import FastAPI, Request, Query
from solarcalc import *
from fastapi.middleware.cors import CORSMiddleware

from urllib.parse import parse_qs, unquote

origins = ["http://localhost:3001"]

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


@app.get("/locationsearch")
async def search_location(location: str = Query(None),):
    print(location)
    api_key = "ftSsz1bBFYcRrjGUUl9WkmERZHc-6rpmTrxaPRIWG4Q"
    r = requests.get(
        f"https://atlas.microsoft.com/search/address/json?&subscription-key=ftSsz1bBFYcRrjGUUl9WkmERZHc"
        f"-6rpmTrxaPRIWG4Q&api-version=1.0&language=en-US&query={location}")
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

@app.get("/getUTC")
def get_utc_offset(lat: str = Query(None), lng: str = Query(None)):
    # Parse the query string

    r = requests.get(
        "https://atlas.microsoft.com/timezone/byCoordinates/json?api-version=1.0&subscription-key"
        f"=ftSsz1bBFYcRrjGUUl9WkmERZHc-6rpmTrxaPRIWG4Q&query={str(lat)},{str(lng)}")
    return int(r.json().get('TimeZones')[0].get('ReferenceTime').get('StandardOffset').split(":")[0])


#  uvicorn main:app --reload --port 8000