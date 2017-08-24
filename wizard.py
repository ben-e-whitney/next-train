import collections
import csv
import curses
import functools
import io
import operator
import sys
import typing
import zipfile

import chooser

CSV_Row = typing.Dict[str, str]
CSV_Restrictions = typing.Dict[str, typing.Collection[str]]

with open('route_types.csv', 'r') as f:
    reader: csv.DictReader = csv.DictReader(
        f, fieldnames=('route_type_id', 'description'), dialect='unix'
    )
    #Skip header. Could also leave `fieldnames` unspecified above.
    next(reader)
    ROUTE_TYPES: typing.Tuple[CSV_Row, ...] = tuple(reader)

class FilteredCSV:
    FILE_SIZE_THRESHOLD: int = 1 << 20
    FILE_SIZE_PREFIXES: typing.Tuple[str, ...] = (
        '', 'Ki', 'Mi', 'Gi', 'Ti', 'Pi', 'Ei', 'Zi', 'Yi'
    )
    FILE_SIZE_FACTOR: int = 1 << 10

    def __init__(
            self,
            archive: zipfile.ZipFile,
            filename: str,
            restrictions: CSV_Restrictions,
    ) -> None:
        self.filename: str = filename
        self._restrictions: CSV_Restrictions = restrictions
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
            self._apply_restrictions(rows=rows)
        if display_loading_message:
            sys.stdout.write('done.\n')

    def match(self, row: CSV_Row) -> bool:
        return all(row[key] in values
                   for key, values in self._restrictions.items())

    def _apply_restrictions(
            self, rows: typing.Optional[typing.Iterable[CSV_Row]]=None
    ) -> None:
        if rows is None:
            rows = self.rows
        self.rows: typing.Collection[CSV_Row] = tuple(filter(self.match, rows))

    def update_restrictions(
            #`*args` could more generally be something like
            #`typing.Mapping[str, typing.Collection[str]]`. Using
            #`CSV_Restrictions` for simplicity and clarity.
            self, *args: CSV_Restrictions, **kwargs: typing.Collection[str]
    ) -> None:
        self._restrictions.update(*args, **kwargs)
        self._apply_restrictions()

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

def binned_by_field(
        rows: typing.Iterable[CSV_Row],
        field: str
) -> typing.Dict[str, typing.List[CSV_Row]]:
    binned: typing.Dict[str, typing.List[CSV_Row]] = (
        collections.defaultdict(list)
    )
    for row in rows:
        binned[row[field]].append(row)
    return dict(binned)

def _get_choice(
        window,
        name: str,
        rows: typing.Collection[CSV_Row],
        id_field: str,
        display_fields: typing.Sequence[str],
) -> str:

    def display(row: CSV_Row) -> str:
        for display_field in display_fields:
            if display_field in row and row[display_field]:
                return row[display_field]
        raise KeyError((
            'Row {row} has no value for any of display fields {dfs}.'
        ).format(row=row, dfs=display_fields))

    curses.curs_set(False)
    question: str = 'Please choose a{vow} {nam}.'.format(
        nam=name, vow='n' if name[0] in 'aeiou' else ''
    )
    #TODO: we'll get a ValueError here if `rows` is empty.
    choices, sorted_rows = zip(*sorted(
        zip(map(display, rows), rows),
        #We don't want lexicographic sorting, since we likely can't compare
        #elements of `rows` with one another.
        key=lambda pair: pair[0],
    ))
    index: int = chooser.Chooser(question, choices)(window)
    return sorted_rows[index][id_field]
get_choice = functools.partial(curses.wrapper, _get_choice)

def stop_sequences(rows: typing.Iterable[CSV_Row]) -> typing.Iterable[int]:
    return map(int, map(operator.itemgetter('stop_sequence'), rows))

def trips_through_stop(
        rows: typing.Iterable[CSV_Row],
        stop_id: str
) -> typing.Set[str]:
    """
    Get trip IDs of trips going through a given stop.

    Parameters
    ----------
    rows
        Rows of `stop_times.txt` to be filtered.
    stop_id
        ID of stop of interest.

    Returns
    -------
    set
        IDs of trips going through stop `stop_id`.
    """

    return {row['trip_id'] for row in rows if row['stop_id'] == stop_id}
def trim_gtfs(
        filename_original: str,
        filename_trimmed: str
) -> typing.Dict[str, str]:
    with zipfile.ZipFile(filename_original, 'r') as original, \
            zipfile.ZipFile(filename_trimmed, 'w') as trimmed:
        route_restrictions: CSV_Restrictions = {}

        agency: FilteredCSV = FilteredCSV(original, 'agency.txt', {})
        agency_id: str = get_choice(
            'agency',
            agency.rows,
            'agency_id',
            ('agency_name',),
        )
        agency.update_restrictions(agency_id={agency_id})
        route_restrictions.update(agency_id={agency_id})

        route_type: str = get_choice(
            'route type',
            ROUTE_TYPES,
            'route_type_id',
            ('description',),
        )
        route_restrictions.update(route_type={route_type})

        routes: FilteredCSV = FilteredCSV(
            original, 'routes.txt', route_restrictions
        )
        route_id: str = get_choice(
            'route',
            routes.rows,
            'route_id',
            ('route_long_name', 'route_short_name',),
        )
        routes.update_restrictions(route_id={route_id})

        trips: FilteredCSV = FilteredCSV(
            original, 'trips.txt', {'route_id': routes.values('route_id')},
        )
        stop_times: FilteredCSV = FilteredCSV(
            original, 'stop_times.txt', {'trip_id': trips.values('trip_id')}
        )
        stops: FilteredCSV = FilteredCSV(
            original, 'stops.txt', {'stop_id': stop_times.values('stop_id')}
        )
        departure_stop_id: str = get_choice(
            'departure stop',
            stops.rows,
            'stop_id',
            ('stop_name', 'stop_code', 'stop_desc')
        )
        trip_ids_through_departure: typing.Set[str] = trips_through_stop(
            stop_times.rows, departure_stop_id
        )
        stop_times.update_restrictions(trip_id=trip_ids_through_departure)

        arrival_stop_ids: set = set()
        for trip_stop_times in binned_by_field(
                stop_times.rows, 'trip_id'
        ).values():
            #`trip_stop_times` is a list of the stops ('StopTimes') that a
            #particular trip going through stop `departure_stop_id` makes
            binned_stop_times: typing.Dict[str, typing.List[CSV_Row]] = (
                binned_by_field(trip_stop_times, 'stop_id')
            )
            #I don't see why you'd ever have multiple visits to a single stop
            #during one trip, but I don't want to read the reference closely
            #enough to rule the possibility out. So, we'll find loop over all
            #the stop times for the departure stop and find the minimum of the
            #stop sequences values, which will correspond to the first visit.
            departure_stop_sequence = min(stop_sequences(
                binned_stop_times[departure_stop_id]
            ))
            #We can get to a stop from stop `departure_stop_id` if it stop has
            #a StopTime with stop sequence greater than
            #`departure_stop_sequence`.
            arrival_stop_ids.update(
                #For each station ('Stop'), we find last stop ('StopTime') made
                #there and decide whether it comes after the first stop at the
                #departure stop.
                stop_id for stop_id, _stop_times in binned_stop_times.items()
                if max(stop_sequences(_stop_times)) > departure_stop_sequence
            )
        arrival_stop_id: str = get_choice(
            'arrival stop',
            tuple(
                row for row in stops.rows if row['stop_id'] in arrival_stop_ids
            ),
            'stop_id',
            ('stop_name', 'stop_code', 'stop_desc')
        )
        trip_ids_through_arrival: typing.Set[str] = trips_through_stop(
            stop_times.rows, arrival_stop_id
        )

        stops.update_restrictions(stop_id={departure_stop_id, arrival_stop_id})
        #Applying the same restriction by a different name.
        stop_times.update_restrictions(stop_id=stops.values('stop_id'))
        trips.update_restrictions(trip_id=(
            trip_ids_through_departure.intersection(trip_ids_through_arrival)
        ))
        routes.update_restrictions(route_id=trips.values('route_id'))
        #`agency_id` isn't a required field for `routes.txt`, so this isn't a
        #great thing to be doing.
        agency.update_restrictions(agency_id=routes.values('agency_id'))

        service_ids: typing.Set[str] = trips.values('service_id')
        calendar: FilteredCSV = FilteredCSV(
            original, 'calendar.txt', {'service_id': service_ids}
        )
        filtereds: typing.List[FilteredCSV] = [
            agency, stops, routes, trips, stop_times, calendar
        ]
        if 'calendar_dates.txt' in original.namelist():
            calendar_dates: FilteredCSV = FilteredCSV(
                original, 'calendar_dates.txt', {'service_id': service_ids}
            )
            filtereds.append(calendar_dates)
        for filtered in filtereds:
            filtered.write(trimmed)
    return {'stop_id_departure': departure_stop_id,
            'stop_id_arrival': arrival_stop_id}
