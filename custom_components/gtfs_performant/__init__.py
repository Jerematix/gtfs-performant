"""GTFS Performant integration for Home Assistant."""
import asyncio
from datetime import timedelta
import logging
import json
from pathlib import Path

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .database import GTFSDatabase
from .gtfs_loader import GTFSLoader
from .realtime import GTFSRealtimeHandler

_LOGGER = logging.getLogger(__name__)

DOMAIN = "gtfs_performant"
PLATFORMS = ["sensor"]

SCAN_INTERVAL = timedelta(seconds=30)


async def _create_dashboard(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Create a Lovelace dashboard for GTFS departures."""
    try:
        # Get stop groups and stops info
        stop_groups = entry.data.get("stop_groups", [])
        selected_stops = entry.data.get("selected_stops", [])
        entry_name = entry.data.get("name", "GTFS Transit")

        # Build cards for each sensor
        cards = []

        # Header card
        cards.append({
            "type": "markdown",
            "content": f"# 🚌 {entry_name} Departures\nReal-time transit departures updated every 30 seconds."
        })

        # Create cards for stop groups
        grouped_stop_ids = set()
        for group in stop_groups:
            group_name = group.get("name", "Unknown")
            group_stops = group.get("stops", [])
            grouped_stop_ids.update(group_stops)

            # Sensor entity_id format - sanitize name
            safe_name = group_name.lower()
            for char in [' ', '.', '-', '/', '(', ')', 'ä', 'ö', 'ü', 'ß']:
                safe_name = safe_name.replace(char, '_')
            entity_id = f"sensor.{safe_name}"

            cards.append({
                "type": "markdown",
                "title": f"🚏 {group_name}",
                "content": f"{{{{{{ state_attr('{entity_id}', 'departures_markdown') }}}}}}"
            })

        # Create cards for ungrouped stops
        for stop_id in selected_stops:
            if stop_id not in grouped_stop_ids:
                entity_id = f"sensor.stop_{stop_id}"
                cards.append({
                    "type": "markdown",
                    "title": f"🚏 Stop {stop_id}",
                    "content": f"{{{{{{ state_attr('{entity_id}', 'departures_markdown') }}}}}}"
                })

        # Create the dashboard configuration
        dashboard_config = {
            "title": "Transit Departures",
            "views": [{
                "title": "Departures",
                "path": "departures",
                "icon": "mdi:bus-clock",
                "cards": cards
            }]
        }

        # Save to .storage for Lovelace
        storage_path = Path(hass.config.path(".storage"))
        storage_path.mkdir(parents=True, exist_ok=True)

        # 1. Save the dashboard config
        dashboard_file = storage_path / "lovelace.gtfs_departures"
        dashboard_data = {
            "version": 1,
            "minor_version": 1,
            "key": "lovelace.gtfs_departures",
            "data": {"config": dashboard_config}
        }
        with open(dashboard_file, "w") as f:
            json.dump(dashboard_data, f, indent=2)

        # 2. Register the dashboard in lovelace_dashboards
        dashboards_file = storage_path / "lovelace_dashboards"
        dashboards_data = {"version": 1, "minor_version": 1, "key": "lovelace_dashboards", "data": {"items": []}}

        if dashboards_file.exists():
            with open(dashboards_file, "r") as f:
                dashboards_data = json.load(f)

        # Check if our dashboard already exists
        items = dashboards_data.get("data", {}).get("items", [])
        dashboard_exists = any(d.get("url_path") == "gtfs-departures" for d in items)

        if not dashboard_exists:
            items.append({
                "id": "gtfs_departures",
                "url_path": "gtfs-departures",
                "mode": "storage",
                "require_admin": False,
                "show_in_sidebar": True,
                "icon": "mdi:bus-clock",
                "title": "Transit"
            })
            dashboards_data["data"]["items"] = items

            with open(dashboards_file, "w") as f:
                json.dump(dashboards_data, f, indent=2)

        _LOGGER.info("Created GTFS departures dashboard - restart HA to see it in sidebar")

    except Exception as err:
        _LOGGER.warning("Could not create dashboard: %s", err)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up GTFS Performant from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    
    # Initialize database
    db_path = hass.config.path(f"gtfs_{entry.entry_id}.db")
    database = GTFSDatabase(db_path)
    await database.async_init()
    
    # Initialize GTFS loader with selected stops/routes
    static_url = entry.data.get("static_url")
    realtime_url = entry.data.get("realtime_url")
    selected_stops = entry.data.get("selected_stops", [])
    selected_routes = entry.data.get("selected_routes", [])
    
    loader = GTFSLoader(database, static_url, selected_stops, selected_routes)
    realtime_handler = GTFSRealtimeHandler(database, realtime_url)
    
    # Load static GTFS data
    try:
        await loader.async_load_gtfs_data()
        _LOGGER.info("Successfully loaded static GTFS data")
    except Exception as err:
        _LOGGER.error("Failed to load static GTFS data: %s", err)
        return False
    
    # Create coordinator
    coordinator = GTFSDataUpdateCoordinator(
        hass,
        entry=entry,
        database=database,
        realtime_handler=realtime_handler,
    )
    
    await coordinator.async_config_entry_first_refresh()
    
    hass.data[DOMAIN][entry.entry_id] = {
        "coordinator": coordinator,
        "database": database,
        "realtime_handler": realtime_handler,
    }
    
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Create dashboard for easy access
    await _create_dashboard(hass, entry)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    
    if unload_ok:
        data = hass.data[DOMAIN].pop(entry.entry_id)
        await data["database"].async_close()
    
    return unload_ok


class GTFSDataUpdateCoordinator(DataUpdateCoordinator):
    """Coordinator to manage GTFS realtime data updates."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        database: GTFSDatabase,
        realtime_handler: GTFSRealtimeHandler,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=SCAN_INTERVAL,
        )
        self.entry = entry
        self.database = database
        self.realtime_handler = realtime_handler
        self.selected_stops = entry.data.get("selected_stops", [])

    async def _async_update_data(self) -> dict:
        """Fetch latest scheduled + realtime data."""
        try:
            # Try to update realtime feed (non-blocking if fails)
            try:
                await self.realtime_handler.async_update_realtime_data()
            except Exception as rt_err:
                _LOGGER.debug("Realtime update skipped: %s", rt_err)

            # Fetch scheduled departures for all selected stops
            departures = {}
            for stop_id in self.selected_stops:
                # Get scheduled departures (this always works)
                stop_departures = await self.database.get_scheduled_departures(stop_id, limit=15)
                departures[stop_id] = stop_departures

            return {
                "status": "success",
                "departures": departures,
            }
        except Exception as err:
            _LOGGER.error("Error updating departure data: %s", err)
            return {"status": "error", "error": str(err), "departures": {}}