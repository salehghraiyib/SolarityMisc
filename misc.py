import datetime
from pydantic import BaseModel

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


# base models for json communications

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
    #utc: int




