import datetime
import math
import json
import sys

from pysolar.solar import get_declination, equation_of_time

# Open the ASHRAE Model file
with open('ASHRAE.json', 'r') as file:
    # Load the JSON data into a dictionary
    ashrae = json.load(file)


def get_local_solar_time(tc, date):
    return date + datetime.timedelta(hours=tc / 60)


def get_dec(date):
    return get_declination(date.timetuple().tm_yday)


def get_time_diff_hra(local_solar_time):
    time_diff = str(datetime.datetime(year=2003, month=2, day=5, hour=local_solar_time.hour,
                                      minute=local_solar_time.minute) - datetime.datetime(year=2003, day=5, month=2,
                                                                                          hour=12, minute=00))
    if len(time_diff) > 8:
        time_diff = time_diff.split(" ")[2]
        time_diff = (24 - time_to_decimal(time_diff)) * -1
    else:
        time_diff = time_to_decimal(time_diff)

    return time_diff


def get_local_standard_meridian(diff):
    return 15 * diff


def get_hra(local_solar_time):
    diff = get_time_diff_hra(local_solar_time)
    hra = 15 * diff
    return hra


def get_time_correction(lon, ltsm, eot):
    return 4 * (lon - ltsm) + eot


def get_solar_azimuth(zenith, hra, declination, lat, lst):
    zenith = math.radians(zenith)
    hra = math.radians(hra)
    declination = math.radians(declination)
    lat = math.radians(lat)

    upper = ((math.sin(declination) * math.cos(lat)) - (math.cos(hra) * math.cos(declination) * math.sin(lat)))
    lower = math.sin(zenith)

    azimuth = math.degrees(math.acos(upper / lower))

    if lst >= 12:
        return 360 - azimuth
    else:
        return azimuth


def sun_altitude(declination, lat, hra):
    # return math.asin(
    # (math.sin(declination) * math.sin(lat)) + (math.cos(declination) * math.cos(lat) * math.cos(hra)))
    latitude_rad = math.radians(lat)
    declination_rad = math.radians(declination)
    hour_angle_rad = math.radians(hra)

    sin_elevation = math.sin(latitude_rad) * math.sin(declination_rad) + math.cos(latitude_rad) * math.cos(
        declination_rad) * math.cos(hour_angle_rad)
    elevation_rad = math.asin(sin_elevation)
    elevation_deg = math.degrees(elevation_rad)

    return elevation_deg


def solar_zenith(altitude):
    return math.degrees(math.acos(math.sin(math.radians(altitude))))


def surface_azimuth(orientation):
    if orientation == "N":
        return 0
    elif orientation == "W":
        return 270
    elif orientation == "S":
        return 180
    else:
        return 90


def altitude_module(tilt):
    return 90.0 - tilt


def angle_oi(sfc_tilt, sfc_azimuth, slr_altitude, slr_azimuth):
    sfc_tilt = math.radians(sfc_tilt)
    slr_altitude = math.radians(slr_altitude)

    first = math.sin(slr_altitude) * math.cos(sfc_tilt)
    second = math.cos(slr_altitude) * math.sin(sfc_tilt) * math.cos(math.radians((slr_azimuth - sfc_azimuth)))
    angle = math.acos(first + second)

    return math.degrees(angle)


def time_to_decimal(time_str):
    hours, minutes, sec = map(int, time_str.split(':'))
    decimal_hours = hours + minutes / 60
    return decimal_hours


def direct_beam_radiation(alpha, date):
    month = date.strftime("%B")
    x = (ashrae[month]['B']) / math.sin(math.radians(alpha))
    max_exp_arg = math.log(sys.float_info.max)  # Maximum value for safe exponential calculation
    min_exp_arg = math.log(sys.float_info.min)  # Minimum value for safe exponential calculation

    # Check if the value is within a safe range for exponential calculation
    if x > max_exp_arg:
        result = math.exp(max_exp_arg)
    elif x < min_exp_arg:
        result = math.exp(min_exp_arg)
    else:
        result = math.exp(x)
    i_bn = ashrae[month]['A'] / result
    return i_bn


def diffuse_beam_radiation(i_bn, tilt, date):
    month = date.strftime("%B")
    i_d = ashrae[month]['C'] * i_bn

    return i_d * ((1 + math.cos(math.radians(tilt))) / 2)


def direct_beam_radiation_tilted(alpha, date, aoi, tilt):
    i_bn = direct_beam_radiation(alpha, date)
    i_b = i_bn * math.cos(math.radians(aoi))
    print(i_b)

    i_d = diffuse_beam_radiation(i_bn, tilt, date)
    print(i_d)

    return i_b + i_d


print(direct_beam_radiation_tilted(
    sun_altitude(get_dec(datetime.datetime(day=21, month=3, year=1999, hour=14, minute=15)), 34, 28.785),
    datetime.datetime(day=21, month=3, year=1999, hour=14, minute=15), 28.785, 30))


def pv_output(wpeak, area, irr, tc, temp, noct, cloud_cover, system_loss):
    if(irr <= 0):
        return 0

    effc = (wpeak / (1000 * area))
    print(effc)
    temp_cell = temp + (noct - 20) * (irr / 800)
    print(temp_cell)
    temp_change = (100 + (tc * (temp_cell - 25))) / 100
    print(temp_change)
    print(noct)
    print(system_loss)
    pr = 1
    h = irr
    pv = (effc * area * h * pr * temp_change) * (1-system_loss) * cloud_effect(cloud_cover)
    print(pv)


    if pv >= wpeak:
        return wpeak
    else:
        return pv


# https://ijesc.org/upload/019a8ade10f861b75fa36c98a02d98b9.The%20Effect%20of%20Cloud%20on%20the%20Output%20Performance%20of%20a%20Solar%20Module.pdf
def cloud_effect(cloud_cover):
    if cloud_cover >= 75:
        return 1 - 0.66
    elif 50 <= cloud_cover < 75:
        return 1 - ((0.6675 + 0.2380) / 2)
    elif 25 <= cloud_cover < 50:
        return 1 - 0.2380
    else:
        return 1

def pv(lat: float, lon: float, year: int, month: int, day: int, hour: int, orientation: str,
       angle: float, utc):
    print("UTC Offset", utc)
    date = datetime.datetime(year, month, day, hour)
    print("Date: ", date)
    # local solar time
    ltsm = get_local_standard_meridian(utc)
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

    # check the twilight threshhold
    if solar_altitude <= -6:
        return 0

    zenith = solar_zenith(solar_altitude)
    print("Solar Zenith", zenith)
    azimuth = get_solar_azimuth(zenith, hra, declination, lat, local_solar_time.hour)
    print("Azimuth: ", azimuth)
    aoi = angle_oi(angle, surface_azimuth(orientation), solar_altitude, azimuth)
    print("Aoi: ", aoi)

    dbrt = direct_beam_radiation_tilted(
        solar_altitude, datetime.datetime(day=day, month=month, year=year, hour=hour, minute=15), aoi,angle)

    return dbrt



