"""Sensor entities for GTFS Performant departure display."""
import logging
from datetime import datetime, timedelta
from typing import Optional

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
import homeassistant.util.dt as dt_util

from . import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up GTFS Performant sensor entities."""
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    database = hass.data[DOMAIN][entry.entry_id]["database"]

    # Get agency timezone for accurate time calculations
    import asyncio
    import aiosqlite

    agency_timezone = None
    try:
        db_path = hass.config.path(f"gtfs_{entry.entry_id}.db")
        async with aiosqlite.connect(db_path) as db:
            cursor = await db.execute("SELECT agency_timezone FROM agency LIMIT 1")
            result = await cursor.fetchone()
            if result:
                agency_timezone = result[0]
                _LOGGER.info("Using agency timezone: %s", agency_timezone)
    except Exception as e:
        _LOGGER.warning("Could not get agency timezone: %s", e)

    entities = []

    # Get stop groups and individual stops
    selected_stops = entry.data.get("selected_stops", [])
    stop_groups = entry.data.get("stop_groups", [])

    # Get stop names from database
    stop_names = await database.get_stop_names(selected_stops) if selected_stops else {}

    if not selected_stops:
        _LOGGER.warning("No stops selected, creating default sensor")
        entities.append(GTFSDepartureSensor(
            coordinator, database, entry, "default", None, None, agency_timezone
        ))
    else:
        # Create sensors for stop groups (multiple stops combined)
        grouped_stop_ids = set()
        for group in stop_groups:
            group_name = group.get("name", "Unknown Group")
            group_stops = group.get("stops", [])
            if group_stops:
                grouped_stop_ids.update(group_stops)
                _LOGGER.info("Creating grouped sensor: %s with stops %s", group_name, group_stops)
                entities.append(GTFSDepartureSensor(
                    coordinator, database, entry, group_stops[0], group_name, group_stops, agency_timezone
                ))

        # Create sensors for ungrouped stops
        for stop_id in selected_stops:
            if stop_id not in grouped_stop_ids:
                stop_name = stop_names.get(stop_id, f"Stop {stop_id}")
                _LOGGER.info("Creating individual sensor for stop: %s (%s)", stop_name, stop_id)
                entities.append(GTFSDepartureSensor(
                    coordinator, database, entry, stop_id, stop_name, None, agency_timezone
                ))

    _LOGGER.info("Created %d GTFS departure sensors", len(entities))
    async_add_entities(entities)


class GTFSDepartureSensor(CoordinatorEntity, SensorEntity):
    """Sensor for displaying GTFS departure information."""

    def __init__(
        self,
        coordinator,
        database,
        entry: ConfigEntry,
        stop_id: Optional[str],
        stop_name: Optional[str],
        grouped_stop_ids: Optional[list] = None,
        agency_timezone: Optional[str] = None,
    ) -> None:
        """Initialize the departure sensor."""
        super().__init__(coordinator)
        self.database = database
        self.entry = entry
        self.stop_id = stop_id
        self.stop_name = stop_name or "GTFS Departures"
        self.agency_timezone = agency_timezone
        # For grouped sensors, monitor multiple stop IDs
        self.grouped_stop_ids = grouped_stop_ids or ([stop_id] if stop_id else [])
    
    @property
    def unique_id(self) -> str:
        """Return unique ID."""
        return f"{DOMAIN}_{self.entry.entry_id}_sensor_{self.stop_id or 'default'}"
    
    @property
    def name(self) -> str:
        """Return sensor name."""
        return self.stop_name
    
    def _get_all_departures(self) -> list:
        """Get departures from all monitored stops, sorted by time."""
        all_departures = []
        departures_data = self.coordinator.data.get("departures", {}) if self.coordinator.data else {}

        for stop_id in self.grouped_stop_ids:
            stop_departures = departures_data.get(stop_id, [])
            all_departures.extend(stop_departures)

        # Sort by scheduled arrival time
        all_departures.sort(key=lambda x: x.get("scheduled_arrival", "99:99:99"))
        return all_departures

    @property
    def native_value(self) -> str:
        """Return current departures count."""
        if self.stop_id is None:
            return "Not Configured"

        departures = self._get_all_departures()
        return str(len(departures)) if departures else "No departures"

    def _format_departure(self, departure: dict) -> dict:
        """Format a single departure with calculated times - timezone aware."""
        scheduled_time = departure.get("scheduled_arrival")
        delay = departure.get("arrival_delay", 0) or 0

        expected_time_str = "--:--"
        minutes_until = None
        delay_minutes = int(delay / 60) if delay else 0

        if scheduled_time:
            try:
                hours, mins, secs = map(int, scheduled_time.split(':'))

                # Get current time in agency timezone
                if self.agency_timezone:
                    try:
                        import zoneinfo
                        tz = zoneinfo.ZoneInfo(self.agency_timezone)
                        now = datetime.now(tz)
                    except Exception:
                        now = dt_util.now()
                else:
                    now = dt_util.now()

                scheduled = now.replace(hour=hours % 24, minute=mins, second=secs, microsecond=0)

                # Handle times after midnight (GTFS times can go to 28:00:00)
                if hours >= 24:
                    from datetime import timedelta
                    scheduled = scheduled.replace(day=scheduled.day) + timedelta(days=1)
                    scheduled = scheduled.replace(hour=hours - 24)

                expected = scheduled + timedelta(seconds=delay)
                expected_time_str = expected.strftime("%H:%M")

                # Calculate minutes until departure
                diff = (expected - now).total_seconds() / 60
                minutes_until = max(0, int(diff))
            except Exception as e:
                _LOGGER.warning("Error formatting departure time: %s", e)

        return {
            "route": departure.get("route_short_name") or departure.get("route_id", "?"),
            "destination": departure.get("trip_headsign", "Unknown"),
            "scheduled": scheduled_time[:5] if scheduled_time else "--:--",
            "expected": expected_time_str,
            "delay_minutes": delay_minutes,
            "minutes_until": minutes_until,
            "vehicle_id": departure.get("vehicle_id"),
        }

    @property
    def extra_state_attributes(self) -> dict:
        """Return additional attributes."""
        if self.stop_id is None:
            return {}

        departures = self._get_all_departures()
        formatted_departures = [self._format_departure(d) for d in departures[:10]]

        attributes = {
            "stop_id": self.stop_id,
            "stop_name": self.stop_name,
            "monitored_stops": self.grouped_stop_ids,
            "last_update": datetime.now().isoformat(),
            "departures_count": len(formatted_departures),
            "departures": formatted_departures,
        }

        # Build markdown table for easy display
        if formatted_departures:
            md_lines = ["| Route | Destination | Time | Delay |", "|:---:|:---|:---:|:---:|"]
            for dep in formatted_departures:
                delay_str = f"+{dep['delay_minutes']}m" if dep['delay_minutes'] > 0 else "on time"
                minutes = f"in {dep['minutes_until']}m" if dep['minutes_until'] is not None else dep['expected']
                md_lines.append(f"| **{dep['route']}** | {dep['destination']} | {minutes} | {delay_str} |")
            attributes["departures_markdown"] = "\n".join(md_lines)
        else:
            attributes["departures_markdown"] = "*No upcoming departures*"

        # Also add individual departure attributes for templates
        for i, dep in enumerate(formatted_departures, 1):
            attributes[f"departure_{i}_route"] = dep["route"]
            attributes[f"departure_{i}_destination"] = dep["destination"]
            attributes[f"departure_{i}_expected"] = dep["expected"]
            attributes[f"departure_{i}_delay"] = dep["delay_minutes"]
            attributes[f"departure_{i}_minutes"] = dep["minutes_until"]

        return attributes
    
    @property
    def icon(self) -> str:
        """Return sensor icon."""
        return "mdi:bus-stop"
    
    @property
    def device_class(self) -> str:
        """Return device class."""
        return None  # Return None instead of timestamp to avoid datetime validation
    
    @property
    def available(self) -> bool:
        """Return if sensor is available."""
        return self.coordinator.last_update_success and self.stop_id is not None