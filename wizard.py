import collections
import csv
import functools
import io
import operator
import sys
import typing
import zipfile

CSV_Row = typing.Dict[str, str]
CSV_Restrictions = typing.Dict[str, typing.Collection[str]]

with open('route_types.csv', 'r') as f:
    reader = csv.DictReader(
        f, fieldnames=('route_type_id', 'description'), dialect='unix'
    )
    #Skip header. Could also leave `fieldnames` unspecified above.
    next(reader)
    ROUTE_TYPES = tuple(reader)

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
        self.filename: str = filename
        self.restrictions: CSV_Restrictions = restrictions
        self.info: zipfile.ZipInfo = archive.getinfo(self.filename)
        display_loading_message: bool = (
            self.info.file_size > self.FILE_SIZE_THRESHOLD
        )
        if display_loading_message:
            sys.stdout.write('Loading {nam} (about {siz}) ... '.format(
                nam=self.filename, siz=self._format_file_size()))
            sys.stdout.flush()
        with archive.open(self.filename) as f:
            #See <http://stackoverflow.com/q/5627954/2899277> for explanation
            #of `io.TextIOWrapper` use.
            #Defining temporary variable `rows` here so we can be more precise
            #about the type of `self.rows`. In particular, later on we will
            #want to call `len` on it, so it needs to belong to `typing.Sized`.
            rows: typing.Iterable[CSV_Row] = (
                csv.DictReader(io.TextIOWrapper(f), dialect='excel')
            )
            self.apply_restrictions(rows=rows)
        if display_loading_message:
            sys.stdout.write('done.\n')

    def match(self, row: CSV_Row) -> bool:
        return all(row[key] in values
                   for key, values in self.restrictions.items())

    def apply_restrictions(
            self, rows: typing.Optional[typing.Iterable[CSV_Row]]=None
    ) -> None:
        if rows is None:
            rows = self.rows
        self.rows: typing.Collection[CSV_Row] = tuple(filter(self.match, rows))

    def values(self, fieldname: str) -> typing.Set[str]:
        return set(map(operator.itemgetter(fieldname), self.rows))

    def _format_file_size(self, figures: int=2) -> str:
        n: int = self.info.file_size
        for prefix in self.FILE_SIZE_PREFIXES:
            if n < self.FILE_SIZE_FACTOR:
                break
            else:
                n //= self.FILE_SIZE_FACTOR
        ndigits: int = -(len(str(int(n))) - figures)
        return '{num} {pre}B'.format(num=int(round(n, ndigits)), pre=prefix)

    def write(self, archive: zipfile.ZipFile) -> None:
        fieldnames: set = set()
        for row in self.rows:
            fieldnames.update(row.keys())
        #See <http://stackoverflow.com/q/25971205/2899277> for explanation
        #of `io.StringIO` use.
        #archive is already in the context manager thing or w/e
        csv_buffer: io.StringIO = io.StringIO()
        writer: csv.DictWriter = csv.DictWriter(
            csv_buffer, tuple(fieldnames), dialect='excel'
        )
        writer.writeheader()
        for row in self.rows:
            writer.writerow(row)
        archive.writestr(self.filename, csv_buffer.getvalue())

def bin_rows_by_field(
        rows: typing.Iterable[CSV_Row],
        field: str
) -> typing.Dict[str, typing.List[CSV_Row]]:
    binned: typing.Dict[str, typing.List[CSV_Row]] = (
        collections.defaultdict(list)
    )
    for row in rows:
        binned[row[field]].append(row)
    return dict(binned)

def get_choice(
        name: str,
        rows: typing.Collection[CSV_Row],
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

    lower: int = 0
    upper: int = len(rows) - 1
    index_width: int = len(str(upper))

    any_choice_text: str = ' (ENTER for any)' if any_choice else ''
    input_message: str = 'Your choice [{low}–{upp}]{ext}: '.format(
        low=lower, upp=upper, ext=any_choice_text)
    bad_input_message: str = (
        'Please input an integer between {low} and {upp}{ext}.'
    ).format(low=lower, upp=upper, ext=any_choice_text)

    print('Please choose a{vow} {nam}.'.format(nam=name,
        vow='n' if name[0] in 'aeiou' else ''))
    row_displays: typing.List[typing.Tuple[CSV_Row, str]]  = sorted(
        ((row, display(row)) for row in rows),
        key=lambda pair: pair[1],
    )
    print('\n'.join('\t{i:{wid}}: {dis}'.format(i=i, wid=index_width,
        dis=pair[1]) for i, pair in enumerate(row_displays)))
    while True:
        choice: str = input(input_message)
        if any_choice and not choice:
            return None
        else:
            try:
                index: int = int(choice)
            except ValueError:
                print(bad_input_message)
                continue
            if not (lower <= index <= upper):
                print(bad_input_message)
            else:
                return row_displays[index][0][id_field]

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
        route_restrictions: CSV_Restrictions = {}
        agency_id: typing.Optional[str] = get_choice(
            'agency', agency.rows, 'agency_id', ('agency_name',),
            any_choice=True
        )
        if agency_id is not None:
            route_restrictions['agency_id'] = (agency_id,)
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
            route_restrictions['route_type'] = (route_type,)
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

        #We'll get an error here if `route_id is None`.
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

        stop_ids_arrival: set = set()
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
