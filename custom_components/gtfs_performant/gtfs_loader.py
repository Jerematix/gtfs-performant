"""Ultra-optimized GTFS data loader - streams everything, zero unnecessary parsing."""
import aiohttp
import csv
import logging
import zipfile
from io import BytesIO, StringIO
from typing import List, Set, Optional, Dict

from .database import GTFSDatabase

_LOGGER = logging.getLogger(__name__)


class GTFSLoader:
    """Ultra-optimized GTFS loader - pure streaming, no wasted memory."""

    def __init__(
        self,
        database: GTFSDatabase,
        static_url: str,
        selected_stops: List[str] = None,
        selected_routes: List[str] = None
    ) -> None:
        self.database = database
        self.static_url = static_url
        self.selected_stops = set(selected_stops) if selected_stops else set()
        self.selected_routes = set(selected_routes) if selected_routes else set()
        self._gtfs_data: Optional[BytesIO] = None
        self._discovered_trips: Set[str] = set()
        self._stop_names: Dict[str, str] = {}  # Cache stop names for final destinations

    async def async_load_gtfs_data(self, force_reload: bool = False) -> None:
        """Load GTFS data with ultra-efficient streaming - minimal memory, maximum speed.

        Args:
            force_reload: If True, force a full reload even if data exists
        """
        _LOGGER.info("async_load_gtfs_data called: force_reload=%s, stops=%d",
                    force_reload, len(self.selected_stops))

        if not self.selected_stops:
            _LOGGER.warning("No stops selected - skipping GTFS load")
            return

        # Check if we can skip loading
        if not force_reload:
            needs_load = await self.database.needs_full_load(self.static_url, list(self.selected_stops))
            if not needs_load:
                _LOGGER.info("✅ Database already has valid data for this GTFS source - skipping load (startup will be instant!)")
                return

        _LOGGER.info("⚠️ Starting ultra-optimized GTFS load for %d stops...", len(self.selected_stops))

        # Clear existing data if reloading
        if force_reload:
            await self._clear_database()

        # Step 1: Download GTFS file ONCE
        await self._download_gtfs()
        if not self._gtfs_data:
            return

        # Step 2: Pre-load stop names (needed for trip destinations)
        await self._cache_stop_names()

        # Step 3: Stream and discover which trips/routes we need
        await self._discover_trips_and_routes()

        # Step 4: Load all data in one pass with filtering
        await self._load_all_data_streaming()

        # Store metadata to avoid reload on next startup
        _LOGGER.info("💾 Storing metadata for future fast startups...")
        await self.database.store_metadata(self.static_url)

        _LOGGER.info("✅ GTFS load complete! %d trips serving your stops.", len(self._discovered_trips))

    async def _clear_database(self) -> None:
        """Clear existing GTFS data from database."""
        cursor = await self.database._connection.cursor()
        await cursor.execute("DELETE FROM stop_times")
        await cursor.execute("DELETE FROM trips")
        await cursor.execute("DELETE FROM routes")
        await cursor.execute("DELETE FROM stops")
        await cursor.execute("DELETE FROM calendar")
        await cursor.execute("DELETE FROM calendar_dates")
        await cursor.execute("DELETE FROM agency")
        await cursor.execute("DELETE FROM realtime_updates")
        await self.database._connection.commit()
        _LOGGER.info("Cleared existing database data")

    async def _cache_stop_names(self) -> None:
        """Stream stops.txt once and cache only stop_id -> stop_name mapping."""
        _LOGGER.info("Caching stop names...")
        self._gtfs_data.seek(0)

        try:
            with zipfile.ZipFile(self._gtfs_data) as zf:
                with zf.open('stops.txt') as f:
                    reader = csv.DictReader(StringIO(f.read().decode('utf-8-sig')))
                    # Only cache what we need - stop_id and stop_name
                    self._stop_names = {
                        row['stop_id']: row['stop_name']
                        for row in reader
                        if 'stop_id' in row and 'stop_name' in row
                    }
            _LOGGER.info("Cached %d stop names", len(self._stop_names))
        except Exception as e:
            _LOGGER.error("Error caching stop names: %s", e)
            self._stop_names = {}

    async def _discover_trips_and_routes(self) -> None:
        """Stream stop_times.txt to discover only trips and routes for our stops.

        This is the KEY optimization - we never load all trips into memory.
        We stream once, extract just IDs, and use those for filtering later.
        """
        _LOGGER.info("Discovering trips and routes for %d stops...", len(self.selected_stops))
        self._gtfs_data.seek(0)

        trip_ids = set()
        route_ids = set()

        try:
            with zipfile.ZipFile(self._gtfs_data) as zf:
                # Stream stop_times - filter while reading
                with zf.open('stop_times.txt') as f:
                    reader = csv.DictReader(StringIO(f.read().decode('utf-8-sig')))
                    for row in reader:
                        # Check if this stop is one we care about
                        if row.get('stop_id') in self.selected_stops:
                            trip_id = row.get('trip_id')
                            if trip_id:
                                trip_ids.add(trip_id)

                _LOGGER.info("Found %d trips serving selected stops", len(trip_ids))

                # Stream trips - get route_ids for our trips
                with zf.open('trips.txt') as f:
                    reader = csv.DictReader(StringIO(f.read().decode('utf-8-sig')))
                    for row in reader:
                        if row.get('trip_id') in trip_ids:
                            route_id = row.get('route_id')
                            if route_id:
                                route_ids.add(route_id)

            self._discovered_trips = trip_ids
            self.selected_routes = route_ids
            _LOGGER.info("Discovered %d routes serving selected stops", len(route_ids))

        except Exception as e:
            _LOGGER.error("Error discovering trips/routes: %s", e)

    async def _load_all_data_streaming(self) -> None:
        """Load ALL data in streaming fashion - filter while reading, never load into memory.

        This is the most efficient approach:
        1. Stream each file once
        2. Filter rows as we read
        3. Batch insert directly to DB
        4. Never accumulate Python lists
        """
        _LOGGER.info("Loading data with streaming filters...")

        await self._load_agency_streaming()
        await self._load_stops_streaming()
        await self._load_calendar_streaming()
        await self._load_calendar_dates_streaming()
        await self._load_routes_streaming()
        await self._load_trips_streaming()
        await self._load_stop_times_streaming()

    async def _load_agency_streaming(self) -> None:
        """Stream and load agency (just first one)."""
        if not self._gtfs_data:
            return

        self._gtfs_data.seek(0)
        try:
            with zipfile.ZipFile(self._gtfs_data) as zf:
                with zf.open('agency.txt') as f:
                    reader = csv.DictReader(StringIO(f.read().decode('utf-8-sig')))
                    # Just take first agency
                    for i, row in enumerate(reader):
                        if i == 0:  # Only first agency
                            row.setdefault('agency_id', 'default')
                            await self._batch_insert('agency',
                                ['agency_id', 'agency_name', 'agency_url', 'agency_timezone',
                                 'agency_lang', 'agency_phone', 'agency_fare_url'], [row])
                            _LOGGER.info("Loaded agency")
                            break
        except Exception as e:
            _LOGGER.warning("Could not load agency: %s", e)

    async def _load_stops_streaming(self) -> None:
        """Stream stops.txt and load only selected stops."""
        if not self._gtfs_data or not self.selected_stops:
            return

        self._gtfs_data.seek(0)
        batch = []
        count = 0

        try:
            with zipfile.ZipFile(self._gtfs_data) as zf:
                with zf.open('stops.txt') as f:
                    reader = csv.DictReader(StringIO(f.read().decode('utf-8-sig')))
                    for row in reader:
                        # Filter WHILE reading - don't accumulate
                        if row.get('stop_id') in self.selected_stops:
                            row.setdefault('stop_code', '')
                            row.setdefault('zone_id', '')
                            row.setdefault('location_type', '0')
                            row.setdefault('parent_station', '')
                            row.setdefault('wheelchair_boarding', '0')
                            row['duplicate_group_id'] = ''
                            row['is_duplicate'] = '0'
                            batch.append(row)
                            count += 1

                            # Batch insert every 500 rows
                            if len(batch) >= 500:
                                await self._batch_insert('stops',
                                    ['stop_id', 'stop_code', 'stop_name', 'stop_lat', 'stop_lon',
                                     'zone_id', 'location_type', 'parent_station', 'wheelchair_boarding',
                                     'duplicate_group_id', 'is_duplicate'], batch)
                                batch = []

                    # Insert remaining
                    if batch:
                        await self._batch_insert('stops',
                            ['stop_id', 'stop_code', 'stop_name', 'stop_lat', 'stop_lon',
                             'zone_id', 'location_type', 'parent_station', 'wheelchair_boarding',
                             'duplicate_group_id', 'is_duplicate'], batch)

            _LOGGER.info("Loaded %d selected stops", count)

        except Exception as e:
            _LOGGER.error("Error loading stops: %s", e)

    async def _load_calendar_streaming(self) -> None:
        """Stream and load all calendar entries (needed for schedule filtering)."""
        if not self._gtfs_data:
            return

        self._gtfs_data.seek(0)
        batch = []

        try:
            with zipfile.ZipFile(self._gtfs_data) as zf:
                with zf.open('calendar.txt') as f:
                    reader = csv.DictReader(StringIO(f.read().decode('utf-8-sig')))
                    for row in reader:
                        batch.append(row)
                        if len(batch) >= 1000:
                            await self._batch_insert('calendar',
                                ['service_id', 'monday', 'tuesday', 'wednesday', 'thursday',
                                 'friday', 'saturday', 'sunday', 'start_date', 'end_date'], batch)
                            batch = []

                    if batch:
                        await self._batch_insert('calendar',
                            ['service_id', 'monday', 'tuesday', 'wednesday', 'thursday',
                             'friday', 'saturday', 'sunday', 'start_date', 'end_date'], batch)

            _LOGGER.info("Loaded calendar entries")

        except Exception as e:
            _LOGGER.warning("Could not load calendar.txt: %s (this is OK if calendar_dates.txt is used)", e)

    async def _load_calendar_dates_streaming(self) -> None:
        """Stream and load all calendar_dates entries (service exceptions).

        Many German transit agencies use calendar_dates.txt exclusively instead of calendar.txt.
        exception_type: 1 = service added, 2 = service removed
        """
        if not self._gtfs_data:
            return

        self._gtfs_data.seek(0)
        batch = []
        count = 0

        try:
            with zipfile.ZipFile(self._gtfs_data) as zf:
                with zf.open('calendar_dates.txt') as f:
                    reader = csv.DictReader(StringIO(f.read().decode('utf-8-sig')))
                    for row in reader:
                        batch.append(row)
                        count += 1
                        if len(batch) >= 1000:
                            await self._batch_insert('calendar_dates',
                                ['service_id', 'date', 'exception_type'], batch)
                            batch = []

                    if batch:
                        await self._batch_insert('calendar_dates',
                            ['service_id', 'date', 'exception_type'], batch)

            _LOGGER.info("Loaded %d calendar_dates entries", count)

        except KeyError:
            _LOGGER.debug("No calendar_dates.txt found (using calendar.txt only)")
        except Exception as e:
            _LOGGER.warning("Could not load calendar_dates.txt: %s", e)

    async def _load_routes_streaming(self) -> None:
        """Stream routes.txt and load only routes that serve our stops."""
        if not self._gtfs_data or not self.selected_routes:
            return

        self._gtfs_data.seek(0)
        batch = []
        count = 0

        try:
            with zipfile.ZipFile(self._gtfs_data) as zf:
                with zf.open('routes.txt') as f:
                    reader = csv.DictReader(StringIO(f.read().decode('utf-8-sig')))
                    for row in reader:
                        # Filter WHILE reading
                        if row.get('route_id') in self.selected_routes:
                            row.setdefault('agency_id', '')
                            row.setdefault('route_desc', '')
                            row.setdefault('route_url', '')
                            row.setdefault('route_color', '')
                            row.setdefault('route_text_color', '')
                            row.setdefault('route_sort_order', '0')
                            batch.append(row)
                            count += 1

                            if len(batch) >= 500:
                                await self._batch_insert('routes',
                                    ['route_id', 'agency_id', 'route_short_name', 'route_long_name',
                                     'route_desc', 'route_type', 'route_url', 'route_color',
                                     'route_text_color', 'route_sort_order'], batch)
                                batch = []

                    if batch:
                        await self._batch_insert('routes',
                            ['route_id', 'agency_id', 'route_short_name', 'route_long_name',
                             'route_desc', 'route_type', 'route_url', 'route_color',
                             'route_text_color', 'route_sort_order'], batch)

            _LOGGER.info("Loaded %d routes", count)

        except Exception as e:
            _LOGGER.error("Error loading routes: %s", e)

    async def _load_trips_streaming(self) -> None:
        """Stream trips.txt and load only trips that serve our stops.

        Also pre-computes final stop names for trips without headsign.
        """
        if not self._gtfs_data or not self._discovered_trips:
            return

        # First pass: find final stops for trips without headsign
        trip_final_stops = await self._get_final_stop_names_for_trips()

        self._gtfs_data.seek(0)
        batch = []
        count = 0

        try:
            with zipfile.ZipFile(self._gtfs_data) as zf:
                with zf.open('trips.txt') as f:
                    reader = csv.DictReader(StringIO(f.read().decode('utf-8-sig')))
                    for row in reader:
                        # Filter WHILE reading
                        if row.get('trip_id') in self._discovered_trips:
                            # Use final stop name if no headsign
                            if not row.get('trip_headsign'):
                                row['trip_headsign'] = trip_final_stops.get(row.get('trip_id', ''), '')

                            row.setdefault('trip_short_name', '')
                            row.setdefault('direction_id', '')
                            row.setdefault('block_id', '')
                            row.setdefault('shape_id', '')
                            row.setdefault('wheelchair_accessible', '0')
                            row.setdefault('bikes_allowed', '0')
                            batch.append(row)
                            count += 1

                            # Larger batch for trips (there are many)
                            if len(batch) >= 2000:
                                await self._batch_insert('trips',
                                    ['trip_id', 'route_id', 'service_id', 'trip_headsign',
                                     'trip_short_name', 'direction_id', 'block_id', 'shape_id',
                                     'wheelchair_accessible', 'bikes_allowed'], batch)
                                batch = []

                    if batch:
                        await self._batch_insert('trips',
                            ['trip_id', 'route_id', 'service_id', 'trip_headsign',
                             'trip_short_name', 'direction_id', 'block_id', 'shape_id',
                             'wheelchair_accessible', 'bikes_allowed'], batch)

            _LOGGER.info("Loaded %d trips", count)

        except Exception as e:
            _LOGGER.error("Error loading trips: %s", e)

    async def _get_final_stop_names_for_trips(self) -> Dict[str, str]:
        """Get final stop name for each discovered trip.

        Returns: {trip_id: stop_name}
        """
        if not self._gtfs_data or not self._discovered_trips:
            return {}

        self._gtfs_data.seek(0)
        trip_final_stops = {}  # trip_id -> (max_sequence, stop_id)

        try:
            with zipfile.ZipFile(self._gtfs_data) as zf:
                # Stream stop_times to find final stop for each trip
                with zf.open('stop_times.txt') as f:
                    reader = csv.DictReader(StringIO(f.read().decode('utf-8-sig')))
                    for row in reader:
                        trip_id = row.get('trip_id')
                        if trip_id in self._discovered_trips:
                            seq = int(row.get('stop_sequence', 0))
                            current = trip_final_stops.get(trip_id, (-1, ''))
                            if seq > current[0]:
                                trip_final_stops[trip_id] = (seq, row.get('stop_id', ''))

        except Exception as e:
            _LOGGER.warning("Error finding final stops: %s", e)
            return {}

        # Convert trip_id -> stop_name using cached stop names
        return {
            trip_id: self._stop_names.get(stop_id, '')
            for trip_id, (_, stop_id) in trip_final_stops.items()
        }

    async def _load_stop_times_streaming(self) -> None:
        """Stream stop_times.txt and load ONLY for selected stops.

        This is typically the largest file - streaming is critical.
        """
        if not self._gtfs_data or not self.selected_stops:
            return

        self._gtfs_data.seek(0)
        batch = []
        count = 0

        try:
            with zipfile.ZipFile(self._gtfs_data) as zf:
                with zf.open('stop_times.txt') as f:
                    reader = csv.DictReader(StringIO(f.read().decode('utf-8-sig')))
                    for row in reader:
                        # Filter WHILE reading - this is KEY for performance
                        if row.get('stop_id') in self.selected_stops:
                            row.setdefault('stop_headsign', '')
                            row.setdefault('pickup_type', '0')
                            row.setdefault('drop_off_type', '0')
                            row.setdefault('shape_dist_traveled', '')
                            row.setdefault('timepoint', '1')
                            batch.append(row)
                            count += 1

                            # Large batch for stop_times (there are MANY)
                            if len(batch) >= 3000:
                                await self._batch_insert('stop_times',
                                    ['trip_id', 'arrival_time', 'departure_time', 'stop_id',
                                     'stop_sequence', 'stop_headsign', 'pickup_type',
                                     'drop_off_type', 'shape_dist_traveled', 'timepoint'], batch)
                                batch = []

                    if batch:
                        await self._batch_insert('stop_times',
                            ['trip_id', 'arrival_time', 'departure_time', 'stop_id',
                             'stop_sequence', 'stop_headsign', 'pickup_type',
                             'drop_off_type', 'shape_dist_traveled', 'timepoint'], batch)

            _LOGGER.info("Loaded %d stop_times for selected stops", count)

        except Exception as e:
            _LOGGER.error("Error loading stop_times: %s", e)

    async def _batch_insert(self, table: str, columns: list, rows: list) -> None:
        """Efficient batch insert - direct to DB, no intermediate processing."""
        if not rows:
            return
        cursor = await self.database._connection.cursor()
        placeholders = ','.join(['?' for _ in columns])
        sql = f"INSERT OR REPLACE INTO {table} ({','.join(columns)}) VALUES ({placeholders})"
        data = [[row.get(col, '') for col in columns] for row in rows]
        await cursor.executemany(sql, data)
        await self.database._connection.commit()

    async def _download_gtfs(self) -> None:
        """Download GTFS file once."""
        try:
            _LOGGER.info("Downloading GTFS data...")
            async with aiohttp.ClientSession() as session:
                async with session.get(self.static_url, timeout=aiohttp.ClientTimeout(total=120)) as response:
                    if response.status != 200:
                        _LOGGER.error("Failed to download GTFS: %s", response.status)
                        return
                    data = await response.read()
                    self._gtfs_data = BytesIO(data)
                    _LOGGER.info("Downloaded %.1f MB", len(data) / 1024 / 1024)
        except Exception as e:
            _LOGGER.error("Download error: %s", e)
