import threading
from datetime import timedelta
import io
import json
import sys
from fastapi import FastAPI, Request, Query
from urllib.parse import parse_qs, unquote
from solarcalc import *
from fastapi.middleware.cors import CORSMiddleware
from weather_cron import *

origins = ["*"]

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

thread = threading.Thread(target=run_schedule, args=())
thread.start()

# Open the ASHRAE Model file
with open('ASHRAE.json', 'r') as file:
    # Load the JSON data into a dictionary
    ashrae = json.load(file)


@app.get("/")
async def root():
    return {"message": "Hello World"}


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


@app.post("/startcalc")
async def startcalc(data: QueData):
    products = []
    # Get today's date
    today = datetime.datetime.now().date()

    # Calculate the date of yesterday
    yesterday = today - timedelta(days=1)

    days_to_add = data.duration  # Replace with the desired number of days
    # Add the specified number of days
    target_start = yesterday - timedelta(days=days_to_add)

    dates_between = get_dates_between(target_start, yesterday)

    dates_already = get_dates_from_weather_data(data.idProj)

    dates_to_retrieve = []

    for i in dates_between:
        if i not in dates_already:
            dates_to_retrieve.append(i)
    products_db = get_products(data.idProj)

    for item in products_db:
        products.append({
            "field_product_id": item[0],
            "lat": item[1],
            "lon": item[2],
            "utc": item[3],
            "tilt": item[4],
            "orientation": item[5],
            "company_product_id": item[6],
            "weather_data": []
        })

    print(dates_to_retrieve)
    print(dates_already)

    for product in products:
        if(len(dates_already) > 0):
            product['weather_data'] = get_already_existent_weather_data(product['field_product_id'], data.idProj, dates_already[0])

        for d in dates_to_retrieve:
            product['weather_data'] += get_weather_data(product['lat'], product['lon'], d)

    cprods = get_company_products()
    start_cal_force(products, cprods, data.idProj)

    return 200


@app.post("/forcesync")
async def force_sync(data: user):
    print(data.userID)
    stat = get_projects_id(data.userID)
    projects = stat[0]
    calc_projects = stat[1]

    if len(projects) == 0:
        return

    yesterday = datetime.datetime.now() - datetime.timedelta(days=1)
    cursor = db.cursor()
    for project in projects:
        for product in project['products']:
            weather = get_weather_data_one_day(product['lat'], product['lon'],
                                               datetime.datetime.now() - datetime.timedelta(days=1))

            for w in weather:
                time = w['dt']

                weather_data = {
                    "time": unix_to_normal_time(time),
                    "lon": product['lon'],
                    "lat": product['lat'],
                    "temp": w['main']['temp'],
                    "clouds": w['clouds']['all'],
                }

                query = f'INSERT INTO weather_data (date_time,project_id,product_id, temp, clouds ) VALUES (%s,%s,%s,%s,%s)'

                cursor.execute(query, (
                    yesterday.replace(hour=weather_data['time'][3], minute=0, second=0), project['project_id'],
                    product['field_product_id'], weather_data['temp'], weather_data['clouds']))
                db.commit()
                # Commit the changes to the database

    db.commit()
    cursor.close()

    if len(calc_projects) == 0:
        return

    print("Calculation is needed")

    company_products = get_company_products()

    for project in calc_projects:
        start_cal_naturally(project, company_products)
        update_proj_status(project['project_id'])

    return "Done"
