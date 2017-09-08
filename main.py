import argparse
import datetime
import itertools
import json
import logging
import operator
import os
import typing
import zipfile

import xdg.BaseDirectory

import wizard

APPLICATION_NAME: str = 'next-train'
FEED_FILENAME = 'feed.zip'
CONFIG_FILENAME = 'config.json'

DATE_FORMAT = '%Y%m%d'
TIME_FORMAT = '%H:%M:%S'
TIME_FORMAT_DISPLAY = '%H:%M'

WEEKDAYS: typing.Tuple[str, ...] = tuple(map(
    '{}day'.format, ('mon', 'tues', 'wednes', 'thurs', 'fri', 'sat', 'sun')
))

def parse_time(time: str) -> datetime.time:
    h, m, s = map(int, time.split(':'))
    return datetime.time(h % 24, m, s)

def stop_names(
        filename: str,
        config: wizard.CSV_Row
) -> typing.Tuple[str, str]:
    with zipfile.ZipFile(filename, 'r') as feed:
        stops: wizard.FilteredCSV = wizard.FilteredCSV(feed, 'stops.txt', {})
        stops_by_id: typing.Dict[str, typing.List[wizard.CSV_Row]] = (
            wizard.binned_by_field(stops.rows, 'stop_id')
        )
        get_name: typing.Callable[[str], str] = (
            lambda key: stops_by_id[config[key]][0]['stop_name']
        )
        return get_name('stop_id_departure'), get_name('stop_id_arrival')

def trips(
        filename: str,
        config: wizard.CSV_Row
) -> typing.Generator[typing.Tuple[datetime.time, datetime.time], None, None]:
    now: datetime.datetime = datetime.datetime.now()
    today: datetime.date = now.date()
    date: str = today.strftime(DATE_FORMAT)
    weekday: str = WEEKDAYS[today.weekday()]
    time: datetime.time = now.time()

    def today_in_service_interval(row: wizard.CSV_Row) -> bool:
        return (
            datetime.datetime.strptime(row['start_date'], DATE_FORMAT).date()
            <= today <=
            datetime.datetime.strptime(row['end_date'], DATE_FORMAT).date()
        )

    def departure_arrival_pairs(
            stop_times: typing.List[wizard.CSV_Row]
    ) -> typing.Generator[
        typing.Tuple[datetime.time, datetime.time], None, None
    ]:
        departures_by_index = {}
        arrivals_by_index = {}
        for stop_time in stop_times:
            index = int(stop_time['stop_sequence'])
            if stop_time['stop_id'] == config['stop_id_departure']:
                departures_by_index[index] = stop_time
            elif stop_time['stop_id'] == config['stop_id_arrival']:
                arrivals_by_index[index] = stop_time
            else:
                raise ValueError(
                    'StopTime at unrecognized stop found: {stp}.'
                    .format(stp=stop_time)
                )
        last_arrival_index = max(arrivals_by_index.keys())
        for i, departure in departures_by_index.items():
            departure_time = parse_time(departure['departure_time'])
            #Possibly this is already handled in the wizard. Not checking.
            if departure_time >= time and i < last_arrival_index:
                arrival: wizard.CSV_Row = arrivals_by_index[min(
                    j for j in arrivals_by_index if i < j
                )]
                arrival_time = parse_time(arrival['arrival_time'])
                yield (departure_time, arrival_time)

    with zipfile.ZipFile(filename, 'r') as feed:
        calendar: wizard.FilteredCSV = wizard.FilteredCSV(
            feed, 'calendar.txt', {weekday: '1'}
        )
        service_ids: typing.Set[str] = set(map(
            operator.itemgetter('service_id'),
            filter(today_in_service_interval, calendar.rows)
        ))
        if 'calendar_dates.txt' in feed.namelist():
            calendar_dates: wizard.FilteredCSV = wizard.FilteredCSV(
                feed, 'calendar_dates.txt', {'date': date}
            )
            exceptions: typing.Dict[str, typing.List[wizard.CSV_Row]] = (
                wizard.binned_by_field(calendar_dates.rows, 'exception_type')
            )
            getter: typing.Callable[[wizard.CSV_Row], str] = (
                operator.itemgetter('service_id')
            )
            if '1' in exceptions:
                service_ids.update(map(getter, exceptions['1']))
            if '2' in exceptions:
                service_ids.difference_update(map(getter, exceptions['2']))
        trips: wizard.FilteredCSV = wizard.FilteredCSV(
            feed, 'trips.txt', {'service_id': service_ids}
        )
        stop_times: wizard.FilteredCSV = wizard.FilteredCSV(
            feed, 'stop_times.txt', {'trip_id': trips.values('trip_id')}
        )
        trip_stop_times: typing.Dict[str, typing.List[wizard.CSV_Row]] = (
            wizard.binned_by_field(stop_times.rows, 'trip_id')
        )
        yield from sorted(itertools.chain.from_iterable(map(
            departure_arrival_pairs,
            trip_stop_times.values()
        )))

parser: argparse.ArgumentParser = argparse.ArgumentParser(
    description='Find the next train from one stop to another.'
)
parser.add_argument(
    '--verbose',
    action='store_true',
    help='enable verbose logging',
)
parser.add_argument(
    '--n',
    type=int,
    default=3,
    help='number of trains to display',
)
parser.add_argument(
    'feed',
    nargs='?',
    default=None,
    help='GTFS feed to filter',
)
args: argparse.Namespace = parser.parse_args()

logging.basicConfig(level=logging.DEBUG if args.verbose else logging.WARNING)
logger: logging.Logger = logging.getLogger(__name__)

trimmed_feed: str
config_file: str
config: wizard.CSV_Row
if args.feed is not None:
    trimmed_feed = os.path.join(
        xdg.BaseDirectory.save_data_path(APPLICATION_NAME),
        FEED_FILENAME
    )
    logger.debug('Filtered feed location set to %s.', trimmed_feed)
    config = wizard.trim_GTFS(args.feed, trimmed_feed)
    config_file = os.path.join(
        xdg.BaseDirectory.save_config_path(APPLICATION_NAME),
        CONFIG_FILENAME
    )
    logger.debug('Configuration file location set to %s.', config_file)
    with open(config_file, 'w') as f:
        json.dump(config, f)
else:
    for directory in xdg.BaseDirectory.load_config_paths(APPLICATION_NAME):
        config_file = os.path.join(directory, CONFIG_FILENAME)
        if os.path.isfile(config_file):
            logger.info(
                'Configuration file will be read from %s.', config_file
            )
            with open(config_file, 'r') as f:
                config = json.load(f)
            break
        else:
            logger.debug('No configuration file found in %s.', directory)
    else:
        raise RuntimeError('No configuration file found.')
    for directory in xdg.BaseDirectory.load_data_paths(APPLICATION_NAME):
        trimmed_feed = os.path.join(directory, FEED_FILENAME)
        if os.path.isfile(trimmed_feed):
            logger.info('Feed will be read from %s.', trimmed_feed)
        else:
            logger.debug('No feed found in %s.', directory)
        break
    else:
        raise RuntimeError('No GTFS feed found.')

departure_name, arrival_name = stop_names(trimmed_feed, config)
for departure_time, arrival_time in itertools.islice(
        trips(trimmed_feed, config), args.n
):
    print(
        'There is a train leaving {dna} at {dtm} that will arrive at {ana} at '
        '{atm}.'.format(
            dna=departure_name,
            ana=arrival_name,
            dtm=departure_time.strftime(TIME_FORMAT_DISPLAY),
            atm=arrival_time.strftime(TIME_FORMAT_DISPLAY),
        )
    )
