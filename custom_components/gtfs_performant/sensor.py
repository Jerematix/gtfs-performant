"""Sensor entities for GTFS Performant departure display."""
import logging
from datetime import datetime, timedelta
from typing import Optional

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

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
    
    entities = []
    
    # Create sensors for user-selected stops and routes
    selected_stops = entry.data.get("selected_stops", [])
    
    if not selected_stops:
        _LOGGER.warning("No stops selected, creating default sensor")
        # Create a sensor that will be configured later
        entities.append(GTFSDepartureSensor(
            coordinator, database, entry, "default", None
        ))
    else:
        # Create sensors for each selected stop/route combination
        for stop_config in selected_stops:
            stop_id = stop_config.get("stop_id")
            stop_name = stop_config.get("stop_name", "Unknown Stop")
            
            # Create sensor for this stop
            entities.append(GTFSDepartureSensor(
                coordinator, database, entry, stop_id, stop_name
            ))
    
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
    ) -> None:
        """Initialize the departure sensor."""
        super().__init__(coordinator)
        self.database = database
        self.entry = entry
        self.stop_id = stop_id
        self.stop_name = stop_name or "GTFS Departures"
    
    @property
    def unique_id(self) -> str:
        """Return unique ID."""
        return f"{DOMAIN}_{self.entry.entry_id}_sensor_{self.stop_id or 'default'}"
    
    @property
    def name(self) -> str:
        """Return sensor name."""
        return self.stop_name
    
    @property
    def native_value(self) -> str:
        """Return current departures count."""
        if self.stop_id is None:
            return "Not Configured"
        
        departures = self.coordinator.data.get("departures", {}).get(self.stop_id, [])
        return str(len(departures))
    
    @property
    def extra_state_attributes(self) -> dict:
        """Return additional attributes."""
        if self.stop_id is None:
            return {}
        
        departures = self.coordinator.data.get("departures", {}).get(self.stop_id, [])
        
        attributes = {
            "stop_id": self.stop_id,
            "stop_name": self.stop_name,
            "last_update": datetime.now().isoformat(),
        }
        
        # Add departure details
        for i, departure in enumerate(departures[:10], 1):
            prefix = f"departure_{i}"
            
            # Calculate expected time with delay
            scheduled_time = departure.get("scheduled_arrival")
            delay = departure.get("arrival_delay", 0)
            
            expected_time_str = "Unknown"
            if scheduled_time and delay is not None:
                try:
                    # Parse GTFS time format (HH:MM:SS)
                    hours, mins, secs = map(int, scheduled_time.split(':'))
                    scheduled = datetime.now().replace(
                        hour=hours % 24, minute=mins, second=secs, microsecond=0
                    )
                    
                    # Add delay in seconds
                    expected = scheduled + timedelta(seconds=delay)
                    expected_time_str = expected.strftime("%H:%M")
                    
                except Exception as e:
                    _LOGGER.warning("Error parsing time: %s", e)
            
            attributes[f"{prefix}_route"] = departure.get("route_short_name", "Unknown")
            attributes[f"{prefix}_destination"] = departure.get("trip_headsign", "Unknown")
            attributes[f"{prefix}_scheduled"] = scheduled_time or "Unknown"
            attributes[f"{prefix}_expected"] = expected_time_str
            attributes[f"{prefix}_delay_minutes"] = int(delay / 60) if delay else 0
            attributes[f"{prefix}_vehicle_id"] = departure.get("vehicle_id") or "Unknown"
        
        return attributes
    
    @property
    def icon(self) -> str:
        """Return sensor icon."""
        return "mdi:bus-stop"
    
    @property
    def device_class(self) -> str:
        """Return device class."""
        return "timestamp"
    
    @property
    def available(self) -> bool:
        """Return if sensor is available."""
        return self.coordinator.last_update_success and self.stop_id is not None