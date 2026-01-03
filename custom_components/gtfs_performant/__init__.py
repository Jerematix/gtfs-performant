"""GTFS Performant integration for Home Assistant."""
import asyncio
from datetime import timedelta
import logging

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


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up GTFS Performant from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    
    # Initialize database
    db_path = hass.config.path(f"gtfs_{entry.entry_id}.db")
    database = GTFSDatabase(db_path)
    await database.async_init()
    
    # Initialize GTFS loader
    static_url = entry.data.get("static_url")
    realtime_url = entry.data.get("realtime_url")
    
    loader = GTFSLoader(database, static_url)
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
    
    async def _async_update_data(self) -> dict:
        """Fetch latest realtime data."""
        try:
            await self.realtime_handler.async_update_realtime_data()
            return {"status": "success"}
        except Exception as err:
            _LOGGER.error("Error updating realtime data: %s", err)
            return {"status": "error", "error": str(err)}