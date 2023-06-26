import datetime
from misc import *
import schedule


def get_open_products_list():
    projects = []
    calc_projects = []
    rows = get_open_projects()

    # Process the rows
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

        print(projects)
        return [projects, calc_projects]


def cronwork():
    stat = get_open_products_list()
    projects = stat[0]
    calc_projects = stat[1]

    if len(projects) == 0:
        return

    yesterday = datetime.datetime.now() - datetime.timedelta(days=1)
    # TODO check if yesterday exists from sync job
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
                    datetime.datetime(yesterday.year, yesterday.month, yesterday.day, weather_data['time'][3], seconds=0, microsecond=5), project['project_id'],
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

    # clean weather data

    return


def run_schedule():
    # Schedule the insert_row function to run every night at 10 PM
    schedule.every().day.at("23:00:00").do(cronwork)
    # TODO change the time of the cron job
    while True:
        schedule.run_pending()


def get_company_products():
    cursor = db.cursor()
    query = f"SELECT product_id, peakpower, temp_coff, system_loss, area, nominal_temp FROM company_product"
    cursor.execute(query)
    rows = cursor.fetchall()
    cursor.close()

    res = dict()

    for cp in rows:
        company_product = {
            "peakpower": cp[1],
            "temp_coff": cp[2],
            "system_loss": cp[3],
            "area": cp[4],
            "nominal_temp": cp[5]
        }

        res[str(cp[0])] = company_product

    return res