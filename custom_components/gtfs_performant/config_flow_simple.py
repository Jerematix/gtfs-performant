"""Simplified config flow for testing dropdown selector only."""
import logging
import aiohttp
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.selector import (
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    SelectOptionDict,
)

from . import DOMAIN

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema({
    vol.Required("static_url"): str,
    vol.Required("realtime_url"): str,
    vol.Optional("name", default="GTFS Transit"): str,
})


class GTFSPerformantConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a simplified config flow for GTFS Performant with dropdown."""
    
    VERSION = 1
    
    def __init__(self):
        """Initialize the config flow."""
        self.gtfs_data = {}
        self.available_stops = []
        self.selected_stops = []
    
    async def async_step_user(
        self, user_input: dict[str, str] | None = None
    ) -> FlowResult:
        """Step 1: Basic GTFS source configuration."""
        errors = {}
        if user_input is not None:
            try:
                # Validate URLs work
                async with aiohttp.ClientSession() as session:
                    async with session.get(user_input["static_url"]) as response:
                        if response.status != 200:
                            errors["base"] = "cannot_connect"
                        else:
                            # Store URLs and proceed to dropdown selection
                            self.gtfs_data = {
                                "static_url": user_input["static_url"],
                                "realtime_url": user_input["realtime_url"],
                                "name": user_input.get("name", "GTFS Transit")
                            }
                            return await self.async_step_select_stops()
            except Exception as err:
                _LOGGER.error("Error connecting to GTFS source: %s", err)
                errors["base"] = "cannot_connect"
        
        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )
    
    async def async_step_select_stops(
        self, user_input: dict[str, str] | None = None
    ) -> FlowResult:
        """Step 2: Select stops with dropdown - simplified version."""
        if user_input is not None:
            # Parse selected stops from dropdown
            selected_stops_input = user_input.get("selected_stops", [])
            if isinstance(selected_stops_input, list):
                self.selected_stops = selected_stops_input
            
            # Create the config entry immediately for this test
            config_data = {
                "static_url": self.gtfs_data["static_url"],
                "realtime_url": self.gtfs_data["realtime_url"],
                "name": self.gtfs_data["name"],
                "selected_stops": self.selected_stops,
            }
            
            return self.async_create_entry(
                title=self.gtfs_data["name"],
                data=config_data
            )
        
        # Download and parse GTFS to get stops
        if not self.available_stops:
            await self._load_test_stops()
        
        # Create dropdown selector using exact bcpearce pattern
        stop_options = [
            SelectOptionDict(
                value=stop['stop_id'],
                label=f"{stop['stop_name']} ({stop['stop_id']})"
            )
            for stop in self.available_stops
        ]
        
        # Sort by label for better UX
        stop_options.sort(key=lambda x: x.label)
        
        _LOGGER.info("🔍 Creating dropdown with %d stops options", len(stop_options))
        
        return self.async_show_form(
            step_id="select_stops",
            data_schema=vol.Schema({
                vol.Required("selected_stops"): SelectSelector(
                    SelectSelectorConfig(
                        options=stop_options,
                        mode=SelectSelectorMode.DROPDOWN,
                        multiple=True,
                    )
                )
            }),
            description_placeholders={
                "stops_count": len(self.available_stops)
            }
        )
    
    async def _load_test_stops(self):
        """Load test stops - either from real GTFS or create test data."""
        try:
            import zipfile
            import csv
            from io import BytesIO, StringIO
            
            _LOGGER.info("🔍 Downloading GTFS data for dropdown test...")
            
            async with aiohttp.ClientSession() as session:
                async with session.get(self.gtfs_data["static_url"]) as response:
                    if response.status != 200:
                        _LOGGER.error("Failed to download GTFS: %s", response.status)
                        # Create test data instead
                        self._create_test_stops()
                        return
                    
                    data = await response.read()
            
            _LOGGER.info("📦 Downloaded GTFS data, parsing stops...")
            
            gtfs_zip = BytesIO(data)
            
            # Extract stops
            with zipfile.ZipFile(gtfs_zip) as zf:
                self.available_stops = []
                try:
                    with zf.open('stops.txt') as f:
                        reader = csv.DictReader(StringIO(f.read().decode('utf-8')))
                        for row in reader:
                            location_type = row.get('location_type', '0')
                            if location_type == '0' or location_type == '':
                                stop_id = row.get('stop_id', '')
                                if stop_id:
                                    self.available_stops.append({
                                        'stop_id': stop_id,
                                        'stop_name': row.get('stop_name', 'Unknown'),
                                    })
                                    if len(self.available_stops) >= 100:  # Limit for testing
                                        break
                    
                    self.available_stops.sort(key=lambda x: x['stop_name'])
                    _LOGGER.info("✅ Loaded %d test stops", len(self.available_stops))
                    
                except Exception as e:
                    _LOGGER.error("Error parsing stops: %s", e)
                    self._create_test_stops()
        
        except Exception as e:
            _LOGGER.error("Error loading GTFS data: %s", e)
            self._create_test_stops()
    
    def _create_test_stops(self):
        """Create test stops if GTFS download fails."""
        _LOGGER.info("Creating test stops for dropdown...")
        self.available_stops = [
            {'stop_id': 'stop1', 'stop_name': 'Main Street'},
            {'stop_id': 'stop2', 'stop_name': 'Central Station'},
            {'stop_id': 'stop3', 'stop_name': 'Park Avenue'},
            {'stop_id': 'stop4', 'stop_name': 'Market Square'},
            {'stop_id': 'stop5', 'stop_name': 'University Campus'},
        ]
        _LOGGER.info("✅ Created %d test stops", len(self.available_stops))