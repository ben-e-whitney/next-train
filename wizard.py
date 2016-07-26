import collections
import csv
import functools
import io
import operator
import sys
import typing
import zipfile

ROUTE_TYPES = tuple({'route_type_id': t[0], 'description': t[1]} for t in (
    ('0', ('Tram, Streetcar, Light rail. Any light rail or street level '
           'system within a metropolitan area.')),
    ('1', ('Subway, Metro. Any underground rail system within a metropolitan '
        'area.')),
    ('2', 'Rail. Used for intercity or long-distance travel.'),
    ('3', 'Bus. Used for short- and long-distance bus routes.'),
    ('4', 'Ferry. Used for short- and long-distance boat service.'),
    ('5', ('Cable car. Used for street-level cable cars where the cable runs '
        'beneath the car.')),
    ('6', ('Gondola, Suspended cable car. Typically used for aerial cable '
           'cars where the car is suspended from the cable.')),
    ('7', ('Funicular. Any rail system designed for steep inclines.')),
))

CSV_Row = typing.Mapping[str, str]
CSV_Restrictions = typing.Mapping[str, typing.AbstractSet[str]]

class FilteredCSV:
    FILE_SIZE_THRESHOLD = 2 ** 20
    FILE_SIZE_PREFIXES = ('', 'Ki', 'Mi', 'Gi', 'Ti', 'Pi', 'Ei', 'Zi', 'Yi')
    FILE_SIZE_FACTOR = 2 ** 10

    def __init__(
            self,
            archive: zipfile.ZipFile,
            filename: str,
            restrictions: CSV_Restrictions,
    ) -> None:
        self.filename = filename
        self.restrictions = restrictions
        self.info = archive.getinfo(self.filename)
        display_loading_message = (self.info.file_size >
                                   self.FILE_SIZE_THRESHOLD)
        if display_loading_message:
            sys.stdout.write('Loading {nam} (about {siz}) ... '.format(
                nam=self.filename, siz=self._format_file_size()))
            sys.stdout.flush()
        with archive.open(self.filename) as f:
            #See <http://stackoverflow.com/q/5627954/2899277> for explanation
            #of `io.TextIOWrapper` use.
            self.rows = csv.DictReader(io.TextIOWrapper(f), dialect='excel')
            self.apply_restrictions()
        if display_loading_message:
            sys.stdout.write('done.\n')

    def match(self, row: CSV_Row) -> bool:
        return all(row[key] in values
                   for key, values in self.restrictions.items())

    def apply_restrictions(self) -> None:
        self.rows = tuple(filter(self.match, self.rows))

    def values(self, fieldname: str) -> typing.Set[str]:
        return set(map(operator.itemgetter(fieldname), self.rows))

    def _format_file_size(self, figures: int=2) -> str:
        n = self.info.file_size
        for prefix in self.FILE_SIZE_PREFIXES:
            if n < self.FILE_SIZE_FACTOR:
                break
            else:
                n /= self.FILE_SIZE_FACTOR
        ndigits = -(len(str(int(n))) - figures)
        return '{num} {pre}B'.format(num=int(round(n, ndigits)), pre=prefix)

    def write(self, archive: zipfile.ZipFile) -> None:
        fieldnames = set()
        for row in self.rows:
            fieldnames.update(row.keys())
        #See <http://stackoverflow.com/q/25971205/2899277> for explanation
        #of `io.StringIO` use.
        #archive is already in the context manager thing or w/e
        csv_buffer = io.StringIO()
        writer = csv.DictWriter(csv_buffer, tuple(fieldnames), dialect='excel')
        writer.writeheader()
        for row in self.rows:
            writer.writerow(row)
        archive.writestr(self.filename, csv_buffer.getvalue())

def bin_rows_by_field(
        rows: typing.Iterable[CSV_Row],
        field: str
) -> typing.Dict[str, CSV_Row]:
    binned = collections.defaultdict(list)
    for row in rows:
        binned[row[field]].append(row)
    return dict(binned)

def get_choice(
        name: str,
        rows: typing.Iterable[CSV_Row],
        id_field: str,
        display_fields: typing.Sequence[str],
        any_choice: bool=False
) -> typing.Optional[str]:

    def display(row: CSV_Row) -> str:
        for display_field in display_fields:
            if display_field in row and row[display_field]:
                return row[display_field]
        raise KeyError((
            'Row {row} has no value for any of display fields {dfs}.'
        ).format(row=row, dfs=display_fields))

    lower = 0
    upper = len(rows) - 1
    index_width = len(str(upper))

    any_choice_text = ' (ENTER for any)' if any_choice else ''
    input_message = 'Your choice [{low}–{upp}]{ext}: '.format(
        low=lower, upp=upper, ext=any_choice_text)
    bad_input_message = (
        'Please input an integer between {low} and {upp}{ext}.'
    ).format(low=lower, upp=upper, ext=any_choice_text)

    print('Please choose a{vow} {nam}.'.format(nam=name,
        vow='n' if name[0] in 'aeiou' else ''))
    row_displays = sorted(
        ((row, display(row)) for row in rows),
        key=lambda pair: pair[1],
    )
    print('\n'.join('\t{i:{wid}}: {dis}'.format(i=i, wid=index_width,
        dis=pair[1]) for i, pair in enumerate(row_displays)))
    while True:
        choice = input(input_message)
        if any_choice and not choice:
            return None
        else:
            try:
                choice = int(choice)
            except ValueError:
                print(bad_input_message)
                continue
            if not (lower <= choice <= upper):
                print(bad_input_message)
            else:
                return row_displays[choice][0][id_field]

def get_stop_sequences(rows: typing.Iterable[CSV_Row]) -> typing.Iterable[int]:
    return map(int, map(operator.itemgetter('stop_sequence'), rows))

def get_relevant_trip_ids(
        rows: typing.Iterable[CSV_Row],
        stop_id: str
) -> typing.Set[str]:
    return set(map(
        operator.itemgetter('trip_id'),
        filter(
            lambda row: row['stop_id'] == stop_id,
            rows
        )
    ))

def trim_gtfs(
        filename_original: str,
        filename_trimmed: str
) -> typing.Dict[str, str]:
    with zipfile.ZipFile(filename_original, 'r') as original, \
            zipfile.ZipFile(filename_trimmed, 'w') as trimmed:
        agency = FilteredCSV(original, 'agency.txt', {})
        route_restrictions = {}
        agency_id = get_choice('agency', agency.rows, 'agency_id',
                      ('agency_name',), any_choice=True)
        if agency_id is not None:
            route_restrictions['agency_id'] = agency_id
            agency.restrictions.update(agency_id=(agency_id,))
            agency.apply_restrictions()
        route_type = get_choice(
            'route type',
            ROUTE_TYPES,
            'route_type_id',
            ('description',),
            any_choice=True
        )
        if route_type is not None:
            route_restrictions['route_type'] = route_type
        routes = FilteredCSV(original, 'routes.txt', route_restrictions)

        route_id = get_choice(
            'route',
            routes.rows,
            'route_id',
            ('route_long_name', 'route_short_name',),
            any_choice=True,
        )
        if route_id is not None:
            routes.restrictions.update(route_id=(route_id,))
            routes.apply_restrictions()

        trips = FilteredCSV(original, 'trips.txt', {'route_id': route_id})
        trip_ids = trips.values('trip_id')
        stop_times = FilteredCSV(original, 'stop_times.txt',
                                 {'trip_id': trip_ids})
        stop_ids = stop_times.values('stop_id')
        stops = FilteredCSV(original, 'stops.txt', {'stop_id': stop_ids})
        stop_id_departure = get_choice(
            'departure stop',
            stops.rows,
            'stop_id',
            ('stop_name', 'stop_code', 'stop_desc')
        )
        trip_ids_through_departure = get_relevant_trip_ids(stop_times.rows,
                                                  stop_id_departure)
        stop_times.restrictions.update(trip_id=trip_ids_through_departure)
        stop_times.apply_restrictions()

        stop_ids_arrival = set()
        for stop_times_for_trip in bin_rows_by_field(stop_times.rows,
                                                     'trip_id').values():
            stop_times_by_stop_id = bin_rows_by_field(stop_times_for_trip,
                                                      'stop_id')
            #I don't see why you'd ever have multiple visits to a single stop
            #during one trip, but I don't want to read the reference closely
            #enough to rule the possibility out. So, we'll find loop over all
            #the stop times for the departure stop and find the minimum of the
            #stop sequences values, which will correspond to the first visit.
            stop_sequence_departure = min(get_stop_sequences(
                stop_times_by_stop_id[stop_id_departure]))
            stop_ids_arrival.update(filter(
                lambda stop_id: (
                    max(get_stop_sequences(stop_times_by_stop_id[stop_id])) >
                    stop_sequence_departure
                ),
                stop_times_by_stop_id.keys()
            ))
        stop_id_arrival = get_choice(
            'arrival stop',
            tuple(filter(
                lambda row: row['stop_id'] in stop_ids_arrival,
                stops.rows
            )),
            'stop_id',
            ('stop_name', 'stop_code', 'stop_desc')
        )
        trip_ids_through_arrival = get_relevant_trip_ids(stop_times.rows,
                                                         stop_id_arrival)

        stops.restrictions.update(stop_id=(stop_id_departure, stop_id_arrival))
        stops.apply_restrictions()
        stop_times.restrictions.update(
            stop_id=(stop_id_departure, stop_id_arrival)
        )
        stop_times.apply_restrictions()

        trips.restrictions.update(
            trip_id=trip_ids_through_departure.intersection(
                trip_ids_through_arrival)
        )
        trips.apply_restrictions()

        routes.restrictions.update(route_id=trips.values('route_id'))
        routes.apply_restrictions()

        #`agency_id` isn't a required field for `routes.txt`, so this isn't a
        #great thing to be doing.
        agency.restrictions.update(agency_id=routes.values('agency_id'))
        agency.apply_restrictions()

        service_ids = trips.values('service_id')
        calendar = FilteredCSV(original, 'calendar.txt',
                                {'service_id': service_ids})
        if 'calendar_dates.txt' in original.namelist():
            calendar_dates = FilteredCSV(original, 'calendar_dates.txt',
                                         {'service_id': service_ids})

        filtereds = [agency, stops, routes, trips, stop_times, calendar]
        if 'calendar_dates.txt' in original.namelist():
            filtereds.append(calendar_dates)
        for filtered in filtereds:
            filtered.write(trimmed)
    return {'stop_id_departure': stop_id_departure,
            'stop_id_arrival': stop_id_arrival}
