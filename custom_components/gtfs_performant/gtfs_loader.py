"""Static GTFS data loader with duplicate detection and efficient processing."""
import aiohttp
import asyncio
import csv
import logging
import math
import zipfile
from io import BytesIO
from pathlib import Path
from typing import Optional

from .database import GTFSDatabase

_LOGGER = logging.getLogger(__name__)


class GTFSLoader:
    """Efficient GTFS data loader with duplicate detection and optimized processing."""
    
    def __init__(self, database: GTFSDatabase, static_url: str) -> None:
        """Initialize the GTFS loader."""
        self.database = database
        self.static_url = static_url
    
    async def async_load_gtfs_data(self) -> None:
        """Load and process static GTFS data efficiently."""
        async with aiohttp.ClientSession() as session:
            async with session.get(self.static_url) as response:
                if response.status != 200:
                    raise RuntimeError(f"Failed to download GTFS data: {response.status}")
                
                gtfs_zip = BytesIO(await response.read())
                
        # Process files in optimal order for dependencies
        await self._process_agency(gtfs_zip)
        await self._process_stops_with_duplicate_detection(gtfs_zip)
        await self._process_routes(gtfs_zip)
        await self._process_calendar(gtfs_zip)
        await self._process_trips(gtfs_zip)
        await self._process_stop_times(gtfs_zip)
        
        _LOGGER.info("GTFS data loaded successfully")
    
    async def _read_csv_from_zip(self, zip_file: BytesIO, filename: str) -> list[dict]:
        """Read CSV file from ZIP with error handling."""
        try:
            with zipfile.ZipFile(zip_file) as zf:
                with zf.open(filename) as f:
                    reader = csv.DictReader(f.read().decode('utf-8').splitlines())
                    return list(reader)
        except KeyError:
            _LOGGER.warning("File %s not found in GTFS archive", filename)
            return []
    
    async def _agro_insert_batch(self, table: str, columns: list[str], rows: list[dict]) -> None:
        """Efficiently insert batch of rows into database."""
        if not rows:
            return
        
        cursor = await self.database._connection.cursor()
        placeholders = ','.join(['?' for _ in columns])
        sql = f"INSERT OR REPLACE INTO {table} ({','.join(columns)}) VALUES ({placeholders})"
        
        await cursor.executemany(sql, [[row[col] for col in columns] for row in rows])
        await self.database._connection.commit()
    
    async def _process_agency(self, zip_file: BytesIO) -> None:
        """Process agency data."""
        rows = await self._read_csv_from_zip(zip_file, 'agency.txt')
        if not rows:
            return
        
        columns = ['agency_id', 'agency_name', 'agency_url', 'agency_timezone', 
                  'agency_lang', 'agency_phone', 'agency_fare_url']
        await self._agro_insert_batch('agency', columns, rows)
        _LOGGER.info("Loaded %d agencies", len(rows))
    
    async def _process_stops_with_duplicate_detection(self, zip_file: BytesIO) -> None:
        """Process stops with intelligent duplicate detection."""
        rows = await self._read_csv_from_zip(zip_file, 'stops.txt')
        if not rows:
            return
        
        # Process and detect duplicates
        stops_map = {}
        for row in rows:
            # Only process stops, not stations or entrances
            if row.get('location_type', '0') != '0':
                continue
            
            stop_id = row['stop_id']
            lat = float(row.get('stop_lat', 0))
            lon = float(row.get('stop_lon', 0))
            name = row.get('stop_name', '').strip().lower()
            
            # Create duplicate group ID based on location proximity and name similarity
            duplicate_key = self._create_duplicate_key(lat, lon, name)
            
            if duplicate_key not in stops_map:
                stops_map[duplicate_key] = []
            stops_map[duplicate_key].append({**row, 'duplicate_key': duplicate_key})
        
        # Assign group IDs and mark duplicates
        group_id = 0
        processed_stops = []
        for duplicate_key, stops in stops_map.items():
            if len(stops) > 1:
                # Multiple stops in this group
                for i, stop in enumerate(stops):
                    stop['duplicate_group_id'] = f"group_{group_id}"
                    stop['is_duplicate'] = 1 if i > 0 else 0
                    processed_stops.append(stop)
            else:
                # Single stop, no duplicate
                stops[0]['duplicate_group_id'] = f"single_{group_id}"
                stops[0]['is_duplicate'] = 0
                processed_stops.append(stops[0])
            group_id += 1
        
        # Insert into database
        columns = ['stop_id', 'stop_code', 'stop_name', 'stop_lat', 'stop_lon',
                  'zone_id', 'location_type', 'parent_station', 'wheelchair_boarding',
                  'duplicate_group_id', 'is_duplicate']
        
        await self._agro_insert_batch('stops', columns, processed_stops)
        _LOGGER.info("Loaded %d stops with %d duplicate groups", len(processed_stops), group_id)
    
    def _create_duplicate_key(self, lat: float, lon: float, name: str) -> str:
        """Create a key for duplicate detection based on location and name."""
        # Round coordinates to 5 decimal places (~1 meter precision)
        lat_rounded = round(lat, 5)
        lon_rounded = round(lon, 5)
        
        # Simplify name by removing common suffixes and extra spaces
        name_parts = name.split()
        if len(name_parts) > 2:
            # Use first two significant words
            name_key = ' '.join(name_parts[:2])
        else:
            name_key = name
        
        return f"{lat_rounded}_{lon_rounded}_{name_key}"
    
    async def _process_routes(self, zip_file: BytesIO) -> None:
        """Process route data."""
        rows = await self._read_csv_from_zip(zip_file, 'routes.txt')
        if not rows:
            return
        
        # Add sort order for better UI display
        for i, row in enumerate(rows):
            row['route_sort_order'] = str(i)
        
        columns = ['route_id', 'agency_id', 'route_short_name', 'route_long_name',
                  'route_desc', 'route_type', 'route_url', 'route_color', 'route_text_color',
                  'route_sort_order']
        await self._agro_insert_batch('routes', columns, rows)
        _LOGGER.info("Loaded %d routes", len(rows))
    
    async def _process_calendar(self, zip_file: BytesIO) -> None:
        """Process calendar data."""
        rows = await self._read_csv_from_zip(zip_file, 'calendar.txt')
        if not rows:
            return
        
        columns = ['service_id', 'monday', 'tuesday', 'wednesday', 'thursday',
                  'friday', 'saturday', 'sunday', 'start_date', 'end_date']
        await self._agro_insert_batch('calendar', columns, rows)
        _LOGGER.info("Loaded %d service calendars", len(rows))
    
    async def _process_trips(self, zip_file: BytesIO) -> None:
        """Process trip data in batches for memory efficiency."""
        rows = await self._read_csv_from_zip(zip_file, 'trips.txt')
        if not rows:
            return
        
        # Process in batches to avoid memory issues on Raspberry Pi
        batch_size = 1000
        for i in range(0, len(rows), batch_size):
            batch = rows[i:i + batch_size]
            columns = ['trip_id', 'route_id', 'service_id', 'trip_headsign',
                      'trip_short_name', 'direction_id', 'block_id', 'shape_id',
                      'wheelchair_accessible', 'bikes_allowed']
            await self._agro_insert_batch('trips', columns, batch)
        
        _LOGGER.info("Loaded %d trips", len(rows))
    
    async def _process_stop_times(self, zip_file: BytesIO) -> None:
        """Process stop times with optimized memory usage."""
        # This is typically the largest file, process very carefully
        try:
            with zipfile.ZipFile(zip_file) as zf:
                with zf.open('stop_times.txt') as f:
                    # Read in chunks to avoid memory issues
                    reader = csv.DictReader(f.read().decode('utf-8').splitlines())
                    
                    batch_size = 5000
                    batch = []
                    count = 0
                    
                    for row in reader:
                        batch.append(row)
                        count += 1
                        
                        if len(batch) >= batch_size:
                            await self._insert_stop_times_batch(batch)
                            batch = []
                            _LOGGER.debug("Processed %d stop times", count)
                    
                    # Insert remaining rows
                    if batch:
                        await self._insert_stop_times_batch(batch)
        
        except KeyError:
            _LOGGER.warning("stop_times.txt not found in GTFS archive")
            return
        
        _LOGGER.info("Loaded stop times data")
    
    async def _insert_stop_times_batch(self, batch: list[dict]) -> None:
        """Insert batch of stop times efficiently."""
        cursor = await self.database._connection.cursor()
        
        columns = ['trip_id', 'arrival_time', 'departure_time', 'stop_id',
                  'stop_sequence', 'stop_headsign', 'pickup_type', 'drop_off_type',
                  'shape_dist_traveled', 'timepoint']
        
        placeholders = ','.join(['?' for _ in columns])
        sql = f"INSERT OR REPLACE INTO stop_times ({','.join(columns)}) VALUES ({placeholders})"
        
        await cursor.executemany(sql, [[row.get(col) for col in columns] for row in batch])
        await self.database._connection.commit()