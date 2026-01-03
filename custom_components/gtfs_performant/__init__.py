"""GTFS Performant integration for Home Assistant."""
import asyncio
from datetime import timedelta
import logging
import json
import re
import shutil
import unicodedata
from pathlib import Path

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
import homeassistant.helpers.config_validation as cv
import voluptuous as vol

from .database import GTFSDatabase
from .gtfs_loader import GTFSLoader
from .realtime import GTFSRealtimeHandler

_LOGGER = logging.getLogger(__name__)

DOMAIN = "gtfs_performant"
PLATFORMS = ["sensor"]

DEFAULT_SCAN_INTERVAL = 120  # seconds (2 minutes)
CARD_JS = "gtfs-departures-card.js"

SERVICE_RELOAD_GTFS = "reload_gtfs_data"
SERVICE_REFRESH_REALTIME = "refresh_realtime"


def _slugify(text: str) -> str:
    """Convert text to a slug matching Home Assistant's entity_id format."""
    # Normalize unicode and remove accents
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    # Convert to lowercase
    text = text.lower()
    # Replace non-alphanumeric with underscores
    text = re.sub(r"[^a-z0-9]+", "_", text)
    # Remove leading/trailing underscores
    text = text.strip("_")
    return text


async def _register_card(hass: HomeAssistant) -> None:
    """Register the custom GTFS departures card."""
    try:
        # Source path (in custom_components)
        src = Path(__file__).parent / "www" / CARD_JS
        if not src.exists():
            _LOGGER.warning("Card JS not found at %s", src)
            return

        # Destination path (HA www folder)
        www_dir = Path(hass.config.path("www"))
        www_dir.mkdir(parents=True, exist_ok=True)
        dst = www_dir / CARD_JS

        # Copy the card file
        shutil.copy2(src, dst)
        _LOGGER.info("Copied GTFS card to %s", dst)

        # Register as Lovelace resource
        url = f"/local/{CARD_JS}"

        # Check if already registered via storage
        storage_path = Path(hass.config.path(".storage/lovelace_resources"))
        resources_data = {"version": 1, "minor_version": 1, "key": "lovelace_resources", "data": {"items": []}}

        if storage_path.exists():
            with open(storage_path, "r") as f:
                resources_data = json.load(f)

        items = resources_data.get("data", {}).get("items", [])
        already_registered = any(r.get("url") == url for r in items)

        if not already_registered:
            items.append({
                "id": "gtfs_departures_card",
                "type": "module",
                "url": url
            })
            resources_data["data"]["items"] = items

            with open(storage_path, "w") as f:
                json.dump(resources_data, f, indent=2)

            _LOGGER.info("Registered GTFS card as Lovelace resource")

    except Exception as err:
        _LOGGER.warning("Could not register card: %s", err)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up GTFS Performant from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    # Initialize database
    db_path = hass.config.path(f"gtfs_{entry.entry_id}.db")
    _LOGGER.info("🗄️ Database path: %s", db_path)
    database = GTFSDatabase(db_path)
    await database.async_init()

    # Initialize GTFS loader with selected stops/routes
    static_url = entry.data.get("static_url")
    realtime_url = entry.data.get("realtime_url")
    selected_stops = entry.data.get("selected_stops", [])
    selected_routes = entry.data.get("selected_routes", [])

    _LOGGER.info("🚀 Setting up GTFS Performant for %d stops", len(selected_stops))

    loader = GTFSLoader(database, static_url, selected_stops, selected_routes)
    realtime_handler = GTFSRealtimeHandler(database, realtime_url)

    # Load static GTFS data (will skip if already loaded)
    try:
        await loader.async_load_gtfs_data()
        _LOGGER.info("✅ GTFS data ready")
    except Exception as err:
        _LOGGER.error("Failed to load static GTFS data: %s", err)
        return False

    # Create coordinator
    coordinator = GTFSDataUpdateCoordinator(
        hass,
        entry=entry,
        database=database,
        realtime_handler=realtime_handler,
        loader=loader,
    )

    await coordinator.async_config_entry_first_refresh()

    hass.data[DOMAIN][entry.entry_id] = {
        "coordinator": coordinator,
        "database": database,
        "realtime_handler": realtime_handler,
        "loader": loader,
        "entry": entry,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Register custom card
    await _register_card(hass)

    # Register services
    async def handle_reload_gtfs(call):
        """Handle reload GTFS data service call."""
        force_refresh = call.data.get("force_refresh", False)
        _LOGGER.info("Reloading GTFS data (force=%s)", force_refresh)
        try:
            await loader.async_load_gtfs_data(force_reload=force_refresh)
            await coordinator.async_refresh()
            _LOGGER.info("GTFS data reloaded successfully")
        except Exception as err:
            _LOGGER.error("Failed to reload GTFS data: %s", err)

    async def handle_refresh_realtime(call):
        """Handle refresh realtime service call."""
        _LOGGER.info("Force refreshing realtime data")
        try:
            await realtime_handler.async_update_realtime_data()
            await coordinator.async_refresh()
            _LOGGER.info("Realtime data refreshed successfully")
        except Exception as err:
            _LOGGER.error("Failed to refresh realtime data: %s", err)

    hass.services.async_register(DOMAIN, SERVICE_RELOAD_GTFS, handle_reload_gtfs)
    hass.services.async_register(DOMAIN, SERVICE_REFRESH_REALTIME, handle_refresh_realtime)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        # Unregister services
        hass.services.async_remove(DOMAIN, SERVICE_RELOAD_GTFS)
        hass.services.async_remove(DOMAIN, SERVICE_REFRESH_REALTIME)

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
        loader: GTFSLoader,
    ) -> None:
        """Initialize the coordinator."""
        # Get update interval from config or use default
        update_interval_seconds = entry.data.get("update_interval", DEFAULT_SCAN_INTERVAL)
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=update_interval_seconds),
        )
        self.entry = entry
        self.database = database
        self.realtime_handler = realtime_handler
        self.loader = loader
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