`next-train`
------------

`next-train` is a script that finds the next train (bus, ferry, etc.) between two stops. To use it you will need a [GTFS][GTFS] feed. Many transit agencies publish feeds. You can find feeds [here][TransitFeed] or [here][PublicFeeds] (or just by searching).

[GTFS]: https://developers.google.com/transit/gtfs/
[TransitFeed]: http://transitfeeds.com/feeds
[PublicFeeds]: https://code.google.com/archive/p/googletransitdatafeed/wikis/PublicFeeds.wiki

Usage
-----

`next-train` requires Python 3.6 or later. To use it, follow these steps:

  1. Run `python3.6 setup.py --install` to install the script.
  2. Find and download a GTFS feed.
  3. The script contains a wizard to help you pick a route. To use it, run `next-train [feed]`.
  4. After you have run the wizard, you can run `next-train` to find the next train.

See the output of `next-train --help` for more options.

Acknowledgments
----------------

`next_train/route_types.csv` is reproduced from [work][CSV source] created and [shared by Google][Google readme] and used according to terms described in the [Creative Commons 3.0 Attribution License][CC BY 3.0].

[CSV source]: https://developers.google.com/transit/gtfs/reference/routes-file
[Google readme]: https://developers.google.com/readme/policies/
[CC BY 3.0]: http://creativecommons.org/licenses/by/3.0/
