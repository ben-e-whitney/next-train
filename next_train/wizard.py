"""
Trim GTFS feeds according to user input.
"""

import csv
import curses
import functools
import logging
import operator
import sys
import typing
import zipfile

from . import chooser
from . import gtfs

logger = logging.getLogger(__name__)

def _get_choice(
        window,
        name: str,
        rows: typing.Collection[gtfs.CSV_Row],
        id_field: str,
        display_fields: typing.Sequence[str],
) -> str:

    def display(row: gtfs.CSV_Row) -> str:
        for display_field in display_fields:
            if display_field in row and row[display_field]:
                return row[display_field]
        raise KeyError((
            'Row {row} has no value for any of display fields {dfs}.'
        ).format(row=row, dfs=display_fields))

    curses.curs_set(False)
    question: str = 'Please choose a{vow} {nam}.'.format(
        nam=name, vow='n' if name and name[0] in 'aeiou' else ''
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

def stop_sequences(
        rows: typing.Iterable[gtfs.CSV_Row]
) -> typing.Iterable[int]:
    return map(int, map(operator.itemgetter('stop_sequence'), rows))

def trips_through_stop(
        rows: typing.Iterable[gtfs.CSV_Row],
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
) -> gtfs.CSV_Row:
    config: gtfs.CSV_Row = {}
    logger.info('Reading original feed from %s.', filename_original)
    with zipfile.ZipFile(filename_original, 'r') as original:
        route_restrictions: gtfs.CSV_Restrictions = {}

        agency: gtfs.FilteredCSV = gtfs.FilteredCSV(original, 'agency.txt', {})
        agency_id: str = get_choice(
            'agency',
            agency.rows,
            'agency_id',
            ('agency_name',),
        )
        logger.debug('Agency ID %s selected.', agency_id)
        agency.update_restrictions(agency_id={agency_id})
        route_restrictions.update(agency_id={agency_id})

        with open('route_types.csv', 'r') as f:
            reader: csv.DictReader = csv.DictReader(
                f, fieldnames=('route_type_id', 'description'), dialect='unix'
            )
            #Skip header. Could also leave `fieldnames` unspecified above.
            next(reader)
            ROUTE_TYPES: typing.Tuple[gtfs.CSV_Row, ...] = tuple(reader)

        route_type: str = get_choice(
            'route type',
            ROUTE_TYPES,
            'route_type_id',
            ('description',),
        )
        config.update({'route_type_id': route_type})
        logger.debug('Route type %s selected.', route_type)
        route_restrictions.update(route_type={route_type})

        routes: gtfs.FilteredCSV = gtfs.FilteredCSV(
            original, 'routes.txt', route_restrictions
        )
        route_id: str = get_choice(
            'route',
            routes.rows,
            'route_id',
            ('route_long_name', 'route_short_name',),
        )
        logger.debug('Route ID %s selected.', route_id)
        routes.update_restrictions(route_id={route_id})

        trips: gtfs.FilteredCSV = gtfs.FilteredCSV(
            original, 'trips.txt', {'route_id': routes.values('route_id')},
        )
        stop_times: gtfs.FilteredCSV = gtfs.FilteredCSV(
            original, 'stop_times.txt', {'trip_id': trips.values('trip_id')}
        )
        stops: gtfs.FilteredCSV = gtfs.FilteredCSV(
            original, 'stops.txt', {'stop_id': stop_times.values('stop_id')}
        )
        departure_stop_id: str = get_choice(
            'departure stop',
            stops.rows,
            'stop_id',
            ('stop_name', 'stop_code', 'stop_desc')
        )
        logger.debug('Departure stop ID %s selected.', departure_stop_id)
        config.update({'stop_id_departure': departure_stop_id})
        trip_ids_through_departure: typing.Set[str] = trips_through_stop(
            stop_times.rows, departure_stop_id
        )
        stop_times.update_restrictions(trip_id=trip_ids_through_departure)

        arrival_stop_ids: set = set()
        for trip_stop_times in gtfs.binned_by_field(
                stop_times.rows, 'trip_id'
        ).values():
            #`trip_stop_times` is a list of the stops ('StopTimes') that a
            #particular trip going through stop `departure_stop_id` makes
            binned_stop_times: typing.Dict[str, typing.List[gtfs.CSV_Row]] = (
                gtfs.binned_by_field(trip_stop_times, 'stop_id')
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
        logging.debug('Arrival stop ID %s selected.', arrival_stop_id)
        config.update({'stop_id_arrival': arrival_stop_id})
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
        calendar: gtfs.FilteredCSV = gtfs.FilteredCSV(
            original, 'calendar.txt', {'service_id': service_ids}
        )
        filtereds: typing.List[gtfs.FilteredCSV] = [
            agency, stops, routes, trips, stop_times, calendar
        ]
        if 'calendar_dates.txt' in original.namelist():
            calendar_dates: gtfs.FilteredCSV = gtfs.FilteredCSV(
                original, 'calendar_dates.txt', {'service_id': service_ids}
            )
            filtereds.append(calendar_dates)
        logger.info('Writing filtered feed to %s.', filename_trimmed)
        with zipfile.ZipFile(filename_trimmed, 'w') as trimmed:
            for filtered in filtereds:
                filtered.write(trimmed)
    return config
