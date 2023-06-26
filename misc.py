import datetime
from pydantic import BaseModel
from mysql import connector
import requests

from solarcalc import pv_output, pv

API_TOKEN = "8f0830ca7113e6565417609a26f7850e"

# Connect to the MySQL database
db = connector.connect(
    host="solarity-db.mysql.database.azure.com",
    user="db_admin",
    password="Db12345678",
    database="dwt"
)


def datetime_to_list(dt):
    return [dt.year, dt.month, dt.day, dt.hour]


def date_to_unix_time(year, month, day, hour):
    dt = datetime.datetime(year, month, day, hour)
    unix_time = int(dt.timestamp())
    return unix_time


def unix_to_normal_time(timestamp):
    dt = datetime.datetime.fromtimestamp(timestamp)
    year = dt.year
    month = dt.month
    day = dt.day
    hour = dt.hour

    return [year, month, day, hour]


def unix_to_normal_date(timestamp):
    dt = datetime.datetime.fromtimestamp(timestamp)
    year = dt.year
    month = dt.month
    day = dt.day
    hour = dt.hour

    return [year, month, day, hour]


def get_dates_between(start_date, end_date):
    dates = []
    current_date = start_date

    while current_date < end_date:
        dates.append(current_date)
        current_date += datetime.timedelta(days=1)

    return dates


def get_products(pid):
    cursor = db.cursor()
    sub_query = f'SELECT field_product_id, lat,lon,utc_offset,tilt,orientation,company_product_id FROM field_product WHERE project_id="{pid}"'
    cursor.execute(sub_query)
    products = list(cursor.fetchall())
    cursor.close()
    if len(products) == 0:
        return []
    return [[elem for elem in row] for row in products]


def get_open_projects():
    cursor = db.cursor()
    query = "SELECT idProject,duration,start_date FROM projects WHERE STATUS= 0"
    cursor.execute(query)
    rows = cursor.fetchall()
    cursor.close()
    if len(rows) == 0:
        return []
    return rows


def get_open_projects_by_id(uID):
    cursor = db.cursor()
    query = f"SELECT idProject,duration,start_date FROM projects WHERE status=0 AND assigned_user_id='{uID}'"
    cursor.execute(query)
    rows = cursor.fetchall()
    cursor.close()
    if len(rows) == 0:
        return []
    return [list(row) for row in rows] if cursor.rowcount > 1 else [[elem for elem in row] for row in rows]


def get_dates_from_weather_data(pid):
    cursor = db.cursor()
    query = f"SELECT date_time FROM weather_data WHERE project_id = '{pid}'"
    cursor.execute(query)
    rows = cursor.fetchall()
    cursor.close()

    unique_dates = set()

    for dt in rows:
        date = dt[0].date()
        unique_dates.add(date)

    return unique_dates


def get_already_existent_weather_data(prodId, projId, startDate):
    cursor = db.cursor()
    formatted_date = startDate.strftime("%Y-%m-%d")
    query = f"SELECT date_time, temp, clouds FROM weather_data WHERE project_id = '{projId}' AND product_id= '{prodId}' AND date_time >= '{formatted_date}' ORDER BY date_time ASC;"
    cursor.execute(query)
    rows = cursor.fetchall()
    cursor.close()

    res = []

    for w in rows:
        weather_data = {
            "time": datetime_to_list(w[0]),
            "temp": w[1],
            "clouds": w[2],
        }
        res.append(weather_data)

    return res


# get weather data based for one day given a location from API
def get_weather_data_one_day(lat, lon, date):
    path = f"https://history.openweathermap.org/data/2.5/history/city?lat={lat}&lon={lon}&type=hour&start={date_to_unix_time(date.year, date.month, date.day, 0)}&end={date_to_unix_time(date.year, date.month, date.day, 23)}&appid={API_TOKEN}&units=metric"
    r = requests.get(path)
    # Return a response
    response = r.json()['list']
    return response


# get weather data based on range given from api
def get_weather_data(lat, lon, d):
    path = f"https://history.openweathermap.org/data/2.5/history/city?lat={lat}&lon={lon}&type=hour&start={date_to_unix_time(d.year, d.month, d.day, 0)}&end={date_to_unix_time(d.year, d.month, d.day, 23)}&appid={API_TOKEN}&units=metric"
    r = requests.get(path)
    # Return a response
    response = r.json()['list']
    result = []
    for weather in response:
        time = weather['dt']

        weather_data = {
            "time": unix_to_normal_date(time),
            "temp": weather['main']['temp'],
            "clouds": weather['clouds']['all'],
        }

        result.append(weather_data)

    return result


def start_cal_naturally(project, company_details):
    cursor = db.cursor()

    today = datetime.datetime.now().date()
    # Calculate the date of yesterday
    daybefore = today - datetime.timedelta(days=2)

    dates_between = get_dates_between(project['start'].date(), daybefore)

    dates_already = get_dates_from_weather_data(project['project_id'])

    dates_to_retrieve = []

    found = 0
    firstdate = None
    for i in dates_between:
        if i not in dates_already:
            dates_to_retrieve.append(i)
        elif i in dates_already:
            if (found == 0):
                firstdate = i
                found = found + 1
            else:
                if i < firstdate:
                    firstdate = i

    fill_weather_gap(project['products'], dates_to_retrieve, project['project_id'])

    for product in project['products']:
        wdta = get_already_existent_weather_data(product['field_product_id'], project['project_id'], firstdate)
        results = []
        for weather in wdta:
            irr = pv(product['lat'], product['lon'], weather['time'][0], weather['time'][1],
                     weather['time'][2], weather['time'][3], product['orientation'], product['tilt'], product['utc'])

            cprod = company_details[str(product['company_product_id'])]

            energy_out = pv_output(cprod['peakpower'], cprod['area'], irr, cprod['temp_coff'], weather['temp'],
                                   cprod['nominal_temp'], weather['clouds'], cprod['system_loss'])

            if energy_out <= 0:
                results.append([datetime.datetime(weather['time'][0], weather['time'][1],
                                                  weather['time'][2], weather['time'][3], second=0), 0])
                continue

            results.append([datetime.datetime(weather['time'][0], weather['time'][1],
                                              weather['time'][2], weather['time'][3], second=0), energy_out / 1000.0])

        results = group_final_data(results)
        print(results)
        query = f'INSERT INTO pv_energy (product_id,project_id,date,pvoutput ) VALUES (%s,%s,%s,%s)'
        for i in results:
            cursor.execute(query, (
                product['field_product_id'],
                project['project_id'], i[0], i[1]))
            db.commit()

    cursor.close()


def start_cal_force(products, company_details, projId):
    cursor = db.cursor()
    for product in products:
        results = []
        for weather in product['weather_data']:
            irr = pv(product['lat'], product['lon'], weather['time'][0], weather['time'][1],
                     weather['time'][2], weather['time'][3], product['orientation'], product['tilt'], product['utc'])

            print("irradiance: ", irr)
            cprod = company_details[str(product['company_product_id'])]
            energy_out = pv_output(cprod['peakpower'], cprod['area'], irr, cprod['temp_coff'], weather['temp'],
                                   cprod['nominal_temp'], weather['clouds'], cprod['system_loss'])

            if energy_out <= 0:
                results.append([datetime.datetime(weather['time'][0], weather['time'][1],
                                                  weather['time'][2], weather['time'][3], second=0), 0])
                continue

            results.append([datetime.datetime(weather['time'][0], weather['time'][1],
                                              weather['time'][2], weather['time'][3], second=0), energy_out / 1000])

        results = group_final_data(results)
        print(results)
        query = f'INSERT INTO pv_energy (product_id,project_id,date,pvoutput) VALUES (%s,%s,%s,%s)'
        for i in results:
            cursor.execute(query, (
                product['field_product_id'],
                projId, i[0], i[1]))
            db.commit()

    cursor.close()


def fill_weather_gap(parray, darray, projId):
    cursor = db.cursor()
    for product in parray:
        for d in darray:
            weather = get_weather_data_one_day(product['lat'], product['lon'], d)

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
                    datetime.datetime(d.year, d.month, d.day, weather_data['time'][3], microsecond=5), projId,
                    product['field_product_id'], weather_data['temp'], weather_data['clouds']))
                db.commit()
                # Commit the changes to the database

        db.commit()
        cursor.close()


def group_final_data(input):
    # Create an empty dictionary to store the grouped values
    grouped_data = {}

    for item in input:
        date = item[0].date()
        value = item[1]

        # Check if the date is already a key in the dictionary
        if date in grouped_data:
            grouped_data[date] += value
        else:
            grouped_data[date] = value

    # Convert the dictionary to a list of [date, sum of values] pairs
    result = [[date, total] for date, total in grouped_data.items()]
    return result


def update_proj_status(projId):
    cursor = db.cursor()

    query = f"UPDATE projects SET status = 2 WHERE idProject = '{projId}'"

    cursor.execute(query)
    db.commit()
    cursor.close()


def get_projects_id(uID):
    projects = []
    calc_projects = []

    rows = get_open_projects_by_id(uID)

    # Process the rows
    print(rows)
    for project in rows:

        print(project)

        obj = {
            "project_id": project[0],
            "duration": project[1],
            "start": project[2],
            "products": []
        }

        yesterday = datetime.datetime.now() - datetime.timedelta(days=1)

        given_datetime = project[2]

        time_difference = (yesterday - given_datetime).days
        print(time_difference)

        # check if yesterday already exists - forced sync by the user
        dates_already = get_dates_from_weather_data(obj['project_id'])

        print(yesterday.date())

        products = get_products(obj['project_id'])

        for item in products:
            obj['products'].append({
                "field_product_id": item[0],
                "lat": item[1],
                "lon": item[2],
                "utc": item[3],
                "tilt": item[4],
                "orientation": item[5],
                "company_product_id": item[6]
            })

        if yesterday not in dates_already:
            projects.append(obj)

        if abs(time_difference) >= project[1]:
            calc_projects.append(obj)

        return [projects, calc_projects]


class Date(BaseModel):
    year: int
    month: int
    day: int
    hour: int


class Loc(BaseModel):
    lat: float
    lon: float
    start: Date
    end: Date
    # utc: int


class QueData(BaseModel):
    idProj: int
    duration: int


class user(BaseModel):
    userID: int
