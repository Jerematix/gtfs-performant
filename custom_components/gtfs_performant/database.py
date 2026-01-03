"""SQLite database layer for GTFS data with optimized schema."""
import aiosqlite
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

_LOGGER = logging.getLogger(__name__)


class GTFSDatabase:
    """Efficient SQLite database for GTFS data with optimized indexes."""
    
    def __init__(self, db_path: str) -> None:
        """Initialize the database."""
        self.db_path = db_path
        self._connection: Optional[aiosqlite.Connection] = None
    
    async def async_init(self) -> None:
        """Initialize database connection and create schema."""
        self._connection = await aiosqlite.connect(self.db_path)
        await self._create_schema()
        await self._create_indexes()
    
    async def _create_schema(self) -> None:
        """Create database schema optimized for GTFS queries."""
        cursor = await self._connection.cursor()
        
        # Create optimized tables
        await cursor.execute("""
            CREATE TABLE IF NOT EXISTS agency (
                agency_id TEXT PRIMARY KEY,
                agency_name TEXT NOT NULL,
                agency_url TEXT,
                agency_timezone TEXT,
                agency_lang TEXT,
                agency_phone TEXT,
                agency_fare_url TEXT
            )
        """)
        
        await cursor.execute("""
            CREATE TABLE IF NOT EXISTS stops (
                stop_id TEXT PRIMARY KEY,
                stop_code TEXT,
                stop_name TEXT NOT NULL,
                stop_lat REAL,
                stop_lon REAL,
                zone_id TEXT,
                location_type INTEGER DEFAULT 0,
                parent_station TEXT,
                wheelchair_boarding INTEGER DEFAULT 0,
                -- Duplicate detection fields
                duplicate_group_id TEXT,
                is_duplicate INTEGER DEFAULT 0
            )
        """)
        
        await cursor.execute("""
            CREATE TABLE IF NOT EXISTS routes (
                route_id TEXT PRIMARY KEY,
                agency_id TEXT,
                route_short_name TEXT,
                route_long_name TEXT,
                route_desc TEXT,
                route_type INTEGER NOT NULL,
                route_url TEXT,
                route_color TEXT,
                route_text_color TEXT,
                route_sort_order INTEGER DEFAULT 0
            )
        """)
        
        await cursor.execute("""
            CREATE TABLE IF NOT EXISTS trips (
                trip_id TEXT PRIMARY KEY,
                route_id TEXT NOT NULL,
                service_id TEXT NOT NULL,
                trip_headsign TEXT,
                trip_short_name TEXT,
                direction_id INTEGER,
                block_id TEXT,
                shape_id TEXT,
                wheelchair_accessible INTEGER DEFAULT 0,
                bikes_allowed INTEGER DEFAULT 0,
                FOREIGN KEY (route_id) REFERENCES routes(route_id)
            )
        """)
        
        await cursor.execute("""
            CREATE TABLE IF NOT EXISTS stop_times (
                trip_id TEXT NOT NULL,
                arrival_time TEXT,
                departure_time TEXT,
                stop_id TEXT NOT NULL,
                stop_sequence INTEGER NOT NULL,
                stop_headsign TEXT,
                pickup_type INTEGER DEFAULT 0,
                drop_off_type INTEGER DEFAULT 0,
                shape_dist_traveled REAL,
                timepoint INTEGER DEFAULT 1,
                PRIMARY KEY (trip_id, stop_sequence),
                FOREIGN KEY (trip_id) REFERENCES trips(trip_id),
                FOREIGN KEY (stop_id) REFERENCES stops(stop_id)
            )
        """)
        
        await cursor.execute("""
            CREATE TABLE IF NOT EXISTS calendar (
                service_id TEXT PRIMARY KEY,
                monday INTEGER DEFAULT 0,
                tuesday INTEGER DEFAULT 0,
                wednesday INTEGER DEFAULT 0,
                thursday INTEGER DEFAULT 0,
                friday INTEGER DEFAULT 0,
                saturday INTEGER DEFAULT 0,
                sunday INTEGER DEFAULT 0,
                start_date TEXT,
                end_date TEXT
            )
        """)
        
        await cursor.execute("""
            CREATE TABLE IF NOT EXISTS realtime_updates (
                trip_id TEXT NOT NULL,
                route_id TEXT,
                stop_id TEXT NOT NULL,
                arrival_delay INTEGER DEFAULT 0,
                arrival_time INTEGER,
                departure_delay INTEGER DEFAULT 0,
                departure_time INTEGER,
                schedule_relationship INTEGER DEFAULT 0,
                timestamp INTEGER,
                vehicle_id TEXT,
                vehicle_label TEXT,
                vehicle_license_plate TEXT,
                PRIMARY KEY (trip_id, stop_id, timestamp),
                FOREIGN KEY (trip_id) REFERENCES trips(trip_id),
                FOREIGN KEY (stop_id) REFERENCES stops(stop_id)
            )
        """)
        
        await cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_config (
                config_key TEXT PRIMARY KEY,
                config_value TEXT NOT NULL
            )
        """)
        
        await self._connection.commit()
    
    async def _create_indexes(self) -> None:
        """Create optimized indexes for query performance."""
        cursor = await self._connection.cursor()
        
        # Performance-critical indexes
        indexes = [
            "CREATE INDEX IF NOT EXISTS idx_stops_location ON stops(stop_lat, stop_lon)",
            "CREATE INDEX IF NOT EXISTS idx_stops_duplicate ON stops(duplicate_group_id)",
            "CREATE INDEX IF NOT EXISTS idx_routes_type ON routes(route_type)",
            "CREATE INDEX IF NOT EXISTS idx_trips_route ON trips(route_id)",
            "CREATE INDEX IF NOT EXISTS idx_trips_service ON trips(service_id)",
            "CREATE INDEX IF NOT EXISTS idx_stop_times_trip ON stop_times(trip_id)",
            "CREATE INDEX IF NOT EXISTS idx_stop_times_stop ON stop_times(stop_id)",
            "CREATE INDEX IF NOT EXISTS idx_realtime_trip_stop ON realtime_updates(trip_id, stop_id)",
            "CREATE INDEX IF NOT EXISTS idx_realtime_timestamp ON realtime_updates(timestamp)",
        ]
        
        for index_sql in indexes:
            await cursor.execute(index_sql)
        
        await self._connection.commit()
    
    async def get_all_stops(self) -> list[dict]:
        """Get all stops ordered by name."""
        cursor = await self._connection.cursor()
        await cursor.execute("""
            SELECT stop_id, stop_name, stop_lat, stop_lon, duplicate_group_id, is_duplicate
            FROM stops
            WHERE location_type = 0
            ORDER BY stop_name
        """)
        rows = await cursor.fetchall()
        return [dict(zip([col[0] for col in cursor.description], row)) for row in rows]
    
    async def get_routes_for_stop(self, stop_id: str) -> list[dict]:
        """Get all routes that serve a specific stop."""
        cursor = await self._connection.cursor()
        await cursor.execute("""
            SELECT DISTINCT r.route_id, r.route_short_name, r.route_long_name, r.route_type
            FROM routes r
            JOIN trips t ON r.route_id = t.route_id
            JOIN stop_times st ON t.trip_id = st.trip_id
            WHERE st.stop_id = ?
            ORDER BY r.route_sort_order, r.route_short_name
        """, (stop_id,))
        rows = await cursor.fetchall()
        return [dict(zip([col[0] for col in cursor.description], row)) for row in rows]
    
    async def get_stops_in_group(self, group_id: str) -> list[dict]:
        """Get all stops in a duplicate group."""
        cursor = await self._connection.cursor()
        await cursor.execute("""
            SELECT stop_id, stop_name, stop_lat, stop_lon
            FROM stops
            WHERE duplicate_group_id = ?
            ORDER BY stop_name
        """, (group_id,))
        rows = await cursor.fetchall()
        return [dict(zip([col[0] for col in cursor.description], row)) for row in rows]
    
    async def get_realtime_departures(self, stop_id: str, limit: int = 10) -> list[dict]:
        """Get realtime departures for a stop with schedule info."""
        cursor = await self._connection.cursor()
        await cursor.execute("""
            SELECT 
                rt.trip_id,
                r.route_id,
                r.route_short_name,
                r.route_long_name,
                t.trip_headsign,
                rt.arrival_delay,
                rt.arrival_time,
                rt.departure_delay,
                rt.departure_time,
                rt.vehicle_id,
                rt.vehicle_label,
                st.arrival_time as scheduled_arrival,
                st.departure_time as scheduled_departure
            FROM realtime_updates rt
            JOIN trips t ON rt.trip_id = t.trip_id
            JOIN routes r ON t.route_id = r.route_id
            JOIN stop_times st ON rt.trip_id = st.trip_id AND rt.stop_id = st.stop_id
            WHERE rt.stop_id = ?
            AND rt.timestamp > strftime('%s', 'now') - 300
            ORDER BY rt.arrival_time ASC
            LIMIT ?
        """, (stop_id, limit))
        rows = await cursor.fetchall()
        return [dict(zip([col[0] for col in cursor.description], row)) for row in rows]
    
    async def close(self) -> None:
        """Close database connection."""
        if self._connection:
            await self._connection.close()