"""
Interact with CSV files in GTFS feeds.
"""

import collections
import csv
import io
import operator
import sys
import typing
import zipfile

CSV_Row = typing.Dict[str, str]
CSV_Restrictions = typing.Dict[str, typing.Collection[str]]

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

