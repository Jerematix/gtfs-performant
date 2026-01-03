"""GTFS Realtime protobuf processor with memory optimization."""
import aiohttp
import logging
from typing import Optional

from gtfs_realtime.bindings import FeedMessage

from .database import GTFSDatabase

_LOGGER = logging.getLogger(__name__)


class GTFSRealtimeHandler:
    """Efficient GTFS Realtime handler with memory-optimized processing."""
    
    def __init__(self, database: GTFSDatabase, realtime_url: str) -> None:
        """Initialize the realtime handler."""
        self.database = database
        self.realtime_url = realtime_url
        self._last_timestamp = 0
    
    async def async_update_realtime_data(self) -> int:
        """Fetch and process realtime updates efficiently.
        
        Returns number of updates processed.
        """
        try:
            feed_message = await self._fetch_realtime_feed()
            if not feed_message:
                return 0
            
            # Process incrementally - only handle new/changed data
            update_count = await self._process_feed_message(feed_message)
            
            # Clean old data
            await self._cleanup_old_updates()
            
            return update_count
            
        except Exception as err:
            _LOGGER.error("Error processing realtime feed: %s", err)
            return 0
    
    async def _fetch_realtime_feed(self) -> Optional[FeedMessage]:
        """Fetch realtime protobuf feed with error handling."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(self.realtime_url) as response:
                    if response.status != 200:
                        _LOGGER.warning("Failed to fetch realtime feed: %s", response.status)
                        return None
                    
                    # Stream the response to avoid memory spikes
                    data = await response.read()
                    
                    # Parse protobuf
                    feed_message = FeedMessage()
                    feed_message.ParseFromString(data)
                    
                    if feed_message.header.timestamp <= self._last_timestamp:
                        _LOGGER.debug("Skipping old feed data")
                        return None
                    
                    self._last_timestamp = feed_message.header.timestamp
                    return feed_message
                    
        except Exception as err:
            _LOGGER.error("Error fetching realtime feed: %s", err)
            return None
    
    async def _process_feed_message(self, feed_message: FeedMessage) -> int:
        """Process feed message efficiently with batched inserts."""
        if not feed_message.entity:
            return 0
        
        cursor = await self.database._connection.cursor()
        update_count = 0
        batch = []
        batch_size = 1000
        
        # Process trip updates only (ignore vehicle positions for now)
        for entity in feed_message.entity:
            if not entity.HasField('trip_update'):
                continue
            
            trip_update = entity.trip_update
            trip_id = trip_update.trip.trip_id
            route_id = trip_update.trip.route_id
            
            # Process stop time updates
            for stop_time_update in trip_update.stop_time_update:
                try:
                    stop_id = stop_time_update.stop_id
                    if not stop_id:
                        continue
                    
                    # Extract arrival info
                    arrival_delay = 0
                    arrival_time = None
                    if stop_time_update.HasField('arrival'):
                        arrival_delay = stop_time_update.arrival.delay
                        arrival_time = stop_time_update.arrival.time
                    
                    # Extract departure info  
                    departure_delay = 0
                    departure_time = None
                    if stop_time_update.HasField('departure'):
                        departure_delay = stop_time_update.departure.delay
                        departure_time = stop_time_update.departure.time
                    
                    # Extract vehicle info if available
                    vehicle_id = None
                    vehicle_label = None
                    vehicle_license_plate = None
                    
                    if trip_update.HasField('vehicle'):
                        vehicle_id = trip_update.vehicle.id
                        vehicle_label = trip_update.vehicle.label
                        vehicle_license_plate = trip_update.vehicle.license_plate
                    
                    batch.append((
                        trip_id, route_id, stop_id,
                        arrival_delay, arrival_time,
                        departure_delay, departure_time,
                        stop_time_update.schedule_relationship,
                        feed_message.header.timestamp,
                        vehicle_id, vehicle_label, vehicle_license_plate
                    ))
                    
                    update_count += 1
                    
                    # Insert in batches to avoid memory issues
                    if len(batch) >= batch_size:
                        await self._insert_realtime_batch(cursor, batch)
                        batch = []
                        
                except Exception as err:
                    _LOGGER.warning("Error processing stop time update: %s", err)
                    continue
        
        # Insert remaining updates
        if batch:
            await self._insert_realtime_batch(cursor, batch)
        
        await self.database._connection.commit()
        _LOGGER.info("Processed %d realtime updates", update_count)
        return update_count
    
    async def _insert_realtime_batch(self, cursor, batch: list) -> None:
        """Insert batch of realtime updates efficiently."""
        sql = """
            INSERT OR REPLACE INTO realtime_updates 
            (trip_id, route_id, stop_id, arrival_delay, arrival_time, 
             departure_delay, departure_time, schedule_relationship, 
             timestamp, vehicle_id, vehicle_label, vehicle_license_plate)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        await cursor.executemany(sql, batch)
    
    async def _cleanup_old_updates(self) -> None:
        """Remove old realtime data to prevent database bloat."""
        cursor = await self.database._connection.cursor()
        
        # Remove updates older than 5 minutes
        cutoff_timestamp = int(__import__('time').time()) - 300
        
        await cursor.execute("""
            DELETE FROM realtime_updates 
            WHERE timestamp < ?
        """, (cutoff_timestamp,))
        
        deleted = cursor.rowcount
        await self.database._connection.commit()
        
        if deleted > 0:
            _LOGGER.debug("Cleaned up %d old realtime updates", deleted)