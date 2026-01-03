"""Optimized GTFS data loader - downloads once, streams data, only processes selected stops."""
import aiohttp
import csv
import logging
import zipfile
from io import BytesIO, StringIO
from typing import List, Set, Optional

from .database import GTFSDatabase

_LOGGER = logging.getLogger(__name__)


class GTFSLoader:
    """Highly optimized GTFS loader - minimal memory, fast processing."""

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

    async def async_load_gtfs_data(self) -> None:
        """Load GTFS data efficiently - single download, selective processing."""
        if not self.selected_stops:
            _LOGGER.warning("No stops selected - skipping GTFS load")
            return

        _LOGGER.info("Starting optimized GTFS load for %d stops...", len(self.selected_stops))

        # Step 1: Download GTFS file ONCE
        await self._download_gtfs()
        if not self._gtfs_data:
            return

        # Step 2: Process in optimal order (dependencies matter)
        await self._load_agency()
        await self._load_stops()
        await self._load_calendar()

        # Step 3: Find trips that serve our stops (streaming)
        await self._discover_trips_for_stops()

        # Step 4: Load routes for discovered trips
        await self._load_routes()

        # Step 5: Load trips
        await self._load_trips()

        # Step 6: Load stop_times for our stops only
        await self._load_stop_times()

        _LOGGER.info("GTFS load complete! %d trips serving your stops.", len(self._discovered_trips))

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

    def _open_csv(self, filename: str):
        """Open CSV file from ZIP, returns reader or None."""
        if not self._gtfs_data:
            return None
        try:
            self._gtfs_data.seek(0)
            with zipfile.ZipFile(self._gtfs_data) as zf:
                with zf.open(filename) as f:
                    content = f.read().decode('utf-8-sig')
                    return list(csv.DictReader(StringIO(content)))
        except KeyError:
            _LOGGER.debug("%s not found in GTFS", filename)
            return None
        except Exception as e:
            _LOGGER.warning("Error reading %s: %s", filename, e)
            return None

    async def _batch_insert(self, table: str, columns: list, rows: list) -> None:
        """Efficient batch insert."""
        if not rows:
            return
        cursor = await self.database._connection.cursor()
        placeholders = ','.join(['?' for _ in columns])
        sql = f"INSERT OR REPLACE INTO {table} ({','.join(columns)}) VALUES ({placeholders})"
        data = [[row.get(col, '') for col in columns] for row in rows]
        await cursor.executemany(sql, data)
        await self.database._connection.commit()

    async def _load_agency(self) -> None:
        """Load agency info."""
        rows = self._open_csv('agency.txt')
        if rows:
            for row in rows[:1]:  # Just first agency
                row.setdefault('agency_id', 'default')
            await self._batch_insert('agency',
                ['agency_id', 'agency_name', 'agency_url', 'agency_timezone',
                 'agency_lang', 'agency_phone', 'agency_fare_url'], rows[:1])
            _LOGGER.info("Loaded agency")

    async def _load_stops(self) -> None:
        """Load only selected stops."""
        rows = self._open_csv('stops.txt')
        if not rows:
            return

        selected = [r for r in rows if r.get('stop_id') in self.selected_stops]
        for row in selected:
            row.setdefault('stop_code', '')
            row.setdefault('zone_id', '')
            row.setdefault('location_type', '0')
            row.setdefault('parent_station', '')
            row.setdefault('wheelchair_boarding', '0')
            row['duplicate_group_id'] = ''
            row['is_duplicate'] = '0'

        await self._batch_insert('stops',
            ['stop_id', 'stop_code', 'stop_name', 'stop_lat', 'stop_lon',
             'zone_id', 'location_type', 'parent_station', 'wheelchair_boarding',
             'duplicate_group_id', 'is_duplicate'], selected)
        _LOGGER.info("Loaded %d stops", len(selected))

    async def _load_calendar(self) -> None:
        """Load all calendar entries."""
        rows = self._open_csv('calendar.txt')
        if rows:
            await self._batch_insert('calendar',
                ['service_id', 'monday', 'tuesday', 'wednesday', 'thursday',
                 'friday', 'saturday', 'sunday', 'start_date', 'end_date'], rows)
            _LOGGER.info("Loaded %d calendar entries", len(rows))

    async def _discover_trips_for_stops(self) -> None:
        """Find all trips that serve our selected stops - streaming."""
        _LOGGER.info("Finding trips for your stops...")

        if not self._gtfs_data:
            return

        self._gtfs_data.seek(0)
        trip_ids = set()
        route_ids = set()

        try:
            with zipfile.ZipFile(self._gtfs_data) as zf:
                # Stream through stop_times to find relevant trips
                with zf.open('stop_times.txt') as f:
                    reader = csv.DictReader(StringIO(f.read().decode('utf-8-sig')))
                    for row in reader:
                        if row.get('stop_id') in self.selected_stops:
                            trip_ids.add(row.get('trip_id'))

                _LOGGER.info("Found %d trips serving your stops", len(trip_ids))

                # Now get route_ids for those trips
                with zf.open('trips.txt') as f:
                    reader = csv.DictReader(StringIO(f.read().decode('utf-8-sig')))
                    for row in reader:
                        if row.get('trip_id') in trip_ids:
                            route_ids.add(row.get('route_id'))

            self._discovered_trips = trip_ids
            self.selected_routes = route_ids
            _LOGGER.info("Discovered %d routes", len(route_ids))

        except Exception as e:
            _LOGGER.error("Error discovering trips: %s", e)

    async def _load_routes(self) -> None:
        """Load only routes that serve our stops."""
        rows = self._open_csv('routes.txt')
        if not rows:
            return

        selected = [r for r in rows if r.get('route_id') in self.selected_routes]
        for row in selected:
            row.setdefault('agency_id', '')
            row.setdefault('route_desc', '')
            row.setdefault('route_url', '')
            row.setdefault('route_color', '')
            row.setdefault('route_text_color', '')
            row.setdefault('route_sort_order', '0')

        await self._batch_insert('routes',
            ['route_id', 'agency_id', 'route_short_name', 'route_long_name',
             'route_desc', 'route_type', 'route_url', 'route_color',
             'route_text_color', 'route_sort_order'], selected)
        _LOGGER.info("Loaded %d routes", len(selected))

    async def _load_trips(self) -> None:
        """Load only trips that serve our stops, with destination from final stop."""
        rows = self._open_csv('trips.txt')
        if not rows:
            return

        # Get final stop names for trips without headsign
        final_stops = self._get_final_stop_names()
        _LOGGER.info("Found %d final stop destinations", len(final_stops))

        selected = [r for r in rows if r.get('trip_id') in self._discovered_trips]
        for row in selected:
            # Use headsign if available, otherwise use final stop name
            if not row.get('trip_headsign'):
                row['trip_headsign'] = final_stops.get(row.get('trip_id'), '')
            row.setdefault('trip_short_name', '')
            row.setdefault('direction_id', '')
            row.setdefault('block_id', '')
            row.setdefault('shape_id', '')
            row.setdefault('wheelchair_accessible', '0')
            row.setdefault('bikes_allowed', '0')

        # Batch insert
        batch_size = 2000
        for i in range(0, len(selected), batch_size):
            batch = selected[i:i + batch_size]
            await self._batch_insert('trips',
                ['trip_id', 'route_id', 'service_id', 'trip_headsign',
                 'trip_short_name', 'direction_id', 'block_id', 'shape_id',
                 'wheelchair_accessible', 'bikes_allowed'], batch)

        _LOGGER.info("Loaded %d trips", len(selected))

    def _get_final_stop_names(self) -> dict:
        """Get the final stop name for each trip (used as destination)."""
        if not self._gtfs_data:
            return {}

        # First, load all stop names
        stop_names = {}
        stops_data = self._open_csv('stops.txt')
        if stops_data:
            for row in stops_data:
                stop_names[row.get('stop_id')] = row.get('stop_name', '')

        # Find the final stop for each of our discovered trips
        self._gtfs_data.seek(0)
        trip_final_stops = {}  # trip_id -> (max_sequence, stop_id)

        try:
            with zipfile.ZipFile(self._gtfs_data) as zf:
                with zf.open('stop_times.txt') as f:
                    reader = csv.DictReader(StringIO(f.read().decode('utf-8-sig')))
                    for row in reader:
                        trip_id = row.get('trip_id')
                        if trip_id in self._discovered_trips:
                            seq = int(row.get('stop_sequence', 0))
                            current = trip_final_stops.get(trip_id, (-1, ''))
                            if seq > current[0]:
                                trip_final_stops[trip_id] = (seq, row.get('stop_id'))
        except Exception as e:
            _LOGGER.warning("Error finding final stops: %s", e)

        # Convert to trip_id -> stop_name
        return {
            trip_id: stop_names.get(stop_id, '')
            for trip_id, (_, stop_id) in trip_final_stops.items()
        }

    async def _load_stop_times(self) -> None:
        """Load stop_times for selected stops only - streaming."""
        _LOGGER.info("Loading stop_times for your stops...")

        if not self._gtfs_data:
            return

        self._gtfs_data.seek(0)
        batch = []
        batch_size = 3000
        count = 0

        try:
            with zipfile.ZipFile(self._gtfs_data) as zf:
                with zf.open('stop_times.txt') as f:
                    reader = csv.DictReader(StringIO(f.read().decode('utf-8-sig')))
                    for row in reader:
                        if row.get('stop_id') in self.selected_stops:
                            row.setdefault('stop_headsign', '')
                            row.setdefault('pickup_type', '0')
                            row.setdefault('drop_off_type', '0')
                            row.setdefault('shape_dist_traveled', '')
                            row.setdefault('timepoint', '1')
                            batch.append(row)
                            count += 1

                            if len(batch) >= batch_size:
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

            _LOGGER.info("Loaded %d stop_times", count)

        except Exception as e:
            _LOGGER.error("Error loading stop_times: %s", e)
