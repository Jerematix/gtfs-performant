"""Multi-step config flow for GTFS Performant with intelligent stop/route discovery."""
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


async def validate_input(hass: HomeAssistant, data: dict) -> dict:
    """Validate the user input allows us to connect."""
    return {"title": data.get("name", "GTFS Transit")}


class GTFSPerformantConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a multi-step config flow for GTFS Performant."""
    
    VERSION = 1
    
    def __init__(self):
        """Initialize the config flow."""
        self.gtfs_data = {}
        self.available_stops = []
        self.available_routes = []
        self.selected_stops = []
        self.selected_routes = []
    
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
                            # Store URLs and proceed to discovery
                            self.gtfs_data = {
                                "static_url": user_input["static_url"],
                                "realtime_url": user_input["realtime_url"],
                                "name": user_input.get("name", "GTFS Transit")
                            }
                            return await self.async_step_discover_stops()
            except Exception as err:
                _LOGGER.error("Error connecting to GTFS source: %s", err)
                errors["base"] = "cannot_connect"
        
        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )
    
    async def async_step_discover_stops(
        self, user_input: dict[str, str] | None = None
    ) -> FlowResult:
        """Step 2: Download GTFS and discover available stops."""
        if user_input is not None:
            # User confirmed to proceed
            return await self.async_step_select_stops()
        
        # Download and parse GTFS to get stops
        info = await self._discover_gtfs_stops()
        
        if not info or not self.available_stops:
            return self.async_abort(reason="cannot_load_stops")
        
        return self.async_show_form(
            step_id="discover_stops",
            data_schema=vol.Schema({}),
            description_placeholders={
                "stops_count": len(self.available_stops),
                "agencies": info.get("agencies", "Unknown"),
                "size_mb": info.get("size_mb", "Unknown")
            }
        )
    
    async def async_step_group_stops(
        self, user_input: dict[str, str] | None = None
    ) -> FlowResult:
        """Step 4: Group duplicate stops together."""
        if user_input is not None:
            # Process stop grouping
            if user_input.get("create_groups", "no") == "yes":
                return await self.async_step_create_groups()
            else:
                # Skip to route filtering
                return await self.async_step_ask_routes()
        
        # Check if there are potential duplicate stops
        has_duplicates = self._check_for_duplicate_stops()
        
        return self.async_show_form(
            step_id="group_stops",
            data_schema=vol.Schema({
                vol.Required("create_groups", default="no"): vol.In([
                    ("no", "No - treat stops separately"),
                    ("yes", "Yes - group duplicate stops together")
                ])
            }),
            description_placeholders={
                "has_duplicates": "Yes" if has_duplicates else "No",
                "selected_count": len(self.selected_stops)
            }
        )
        
    async def async_step_select_stops(
        self, user_input: dict[str, str] | None = None
    ) -> FlowResult:
        """Step 3: Select which stops to monitor with searchable dropdown."""
        if user_input is not None:
            # Parse selected stops from dropdown
            selected_stops_input = user_input.get("selected_stops", [])
            if isinstance(selected_stops_input, list):
                self.selected_stops = selected_stops_input
            
            # Ask if they want to group stops
            return await self.async_step_group_stops()
        
        # Create proper selector options for ALL stops using SelectOptionDict
        stop_options = [
            SelectOptionDict(
                value=stop['stop_id'],
                label=f"{stop['stop_name']} ({stop['stop_id']})"
            )
            for stop in self.available_stops
        ]
        
        # Sort by label for better UX
        stop_options.sort(key=lambda x: x['label'])
        
        _LOGGER.info("🔍 Creating dropdown with %d stops options", len(stop_options))
        _LOGGER.debug("🔍 First few options: %s", stop_options[:3])
        
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
                "stops_count": len(self.available_stops),
                "total_stops": len(self.available_stops)
            }
        )
    
    async def async_step_ask_routes(
        self, user_input: dict[str, str] | None = None
    ) -> FlowResult:
        """Step 4: Ask if user wants to filter by routes too."""
        if user_input is not None:
            if user_input.get("filter_routes", "no") == "yes":
                return await self.async_step_select_routes()
            else:
                # Skip to final processing
                return await self.async_step_final_processing()
        
        return self.async_show_form(
            step_id="ask_routes",
            data_schema=vol.Schema({
                vol.Required("filter_routes", default="no"): vol.In([
                    ("no", "No - monitor all routes at my stops"),
                    ("yes", "Yes - only specific routes")
                ])
            })
        )
    
    async def async_step_select_routes(
        self, user_input: dict[str, str] | None = None
    ) -> FlowResult:
        """Step 5: Select specific routes with dropdown."""
        if user_input is not None:
            # Parse selected routes from dropdown
            selected_routes_input = user_input.get("selected_routes", [])
            if isinstance(selected_routes_input, list):
                self.selected_routes = selected_routes_input
            
            return await self.async_step_final_processing()
        
        # Discover which routes serve the selected stops
        await self._discover_relevant_routes()
        
        # Create proper selector options for routes using SelectOptionDict
        route_options = [
            SelectOptionDict(
                value=route['route_id'],
                label=f"{route.get('route_short_name', route['route_id'])} - {route.get('route_long_name', '')}"
            )
            for route in self.available_routes
        ]
        
        # Sort by label for better UX
        route_options.sort(key=lambda x: x['label'])
        
        _LOGGER.info("🔍 Creating dropdown with %d route options", len(route_options))
        
        return self.async_show_form(
            step_id="select_routes",
            data_schema=vol.Schema({
                vol.Optional("selected_routes", default=[]): SelectSelector(
                    SelectSelectorConfig(
                        options=route_options,
                        mode=SelectSelectorMode.DROPDOWN,
                        multiple=True,
                    )
                )
            }),
            description_placeholders={
                "routes_count": len(self.available_routes)
            }
        )
    
    async def async_step_final_processing(
        self, user_input: dict[str, str] | None = None
    ) -> FlowResult:
        """Step 6: Show summary and create entry."""
        if user_input is not None:
            # Create the config entry
            config_data = {
                "static_url": self.gtfs_data["static_url"],
                "realtime_url": self.gtfs_data["realtime_url"],
                "name": self.gtfs_data["name"],
                "selected_stops": self.selected_stops,
                "selected_routes": list(self.selected_routes) if self.selected_routes else [],
            }
            
            return self.async_create_entry(
                title=self.gtfs_data["name"],
                data=config_data
            )
        
        # Show summary first
        return self.async_show_form(
            step_id="final_processing",
            data_schema=vol.Schema({}),
            description_placeholders={
                "selected_stops_count": len(self.selected_stops),
                "selected_routes_count": len(self.selected_routes) if self.selected_routes else 0
            }
        )
    
    async def _discover_gtfs_stops(self) -> dict:
        """Download GTFS and extract basic stop information."""
        try:
            import zipfile
            import csv
            from io import BytesIO, StringIO
            
            _LOGGER.info("🔍 Downloading GTFS data for discovery...")
            
            async with aiohttp.ClientSession() as session:
                async with session.get(self.gtfs_data["static_url"]) as response:
                    if response.status != 200:
                        _LOGGER.error("Failed to download GTFS: %s", response.status)
                        return {}
                    
                    data = await response.read()
                    size_mb = len(data) / 1024 / 1024
            
            _LOGGER.info("📦 Downloaded %.1f MB, parsing GTFS...", size_mb)
            
            gtfs_zip = BytesIO(data)
            
            # Extract stops
            with zipfile.ZipFile(gtfs_zip) as zf:
                # Get agency info
                agencies = []
                try:
                    with zf.open('agency.txt') as f:
                        reader = csv.DictReader(StringIO(f.read().decode('utf-8')))
                        agencies = [row['agency_name'] for row in reader]
                        _LOGGER.info("✅ Found agencies: %s", agencies)
                except Exception as e:
                    _LOGGER.warning("Could not read agency.txt: %s", e)
                
                # Get stops (only location_type = 0 for actual stops)
                self.available_stops = []
                try:
                    with zf.open('stops.txt') as f:
                        reader = csv.DictReader(StringIO(f.read().decode('utf-8')))
                        for row in reader:
                            # Handle different GTFS formats with flexible column access
                            location_type = row.get('location_type', '0')
                            if location_type == '0' or location_type == '':
                                stop_id = row.get('stop_id', '')
                                if stop_id:  # Only add if we have a stop_id
                                    self.available_stops.append({
                                        'stop_id': stop_id,
                                        'stop_name': row.get('stop_name', 'Unknown'),
                                        'stop_lat': float(row.get('stop_lat', 0)),
                                        'stop_lon': float(row.get('stop_lon', 0))
                                    })
                    
                    # Sort by name
                    self.available_stops.sort(key=lambda x: x['stop_name'])
                    _LOGGER.info("✅ Discovered %d stops", len(self.available_stops))
                    
                except Exception as e:
                    _LOGGER.error("Error parsing stops: %s", e, exc_info=True)
                    return {}
            
            if not self.available_stops:
                _LOGGER.error("No stops found in GTFS data after processing")
                return {}
            
            _LOGGER.info("✅ Discovery successful: found %d stops", len(self.available_stops))
            
            return {
                "agencies": agencies[0] if agencies else "Unknown",
                "size_mb": f"{size_mb:.1f}",
                "stops_count": len(self.available_stops)
            }
        
        except Exception as e:
            _LOGGER.error("Error discovering GTFS data: %s", e, exc_info=True)
            return {}
    
    async def _discover_relevant_routes(self) -> None:
        """Discover which routes serve the selected stops."""
        if not self.selected_stops:
            return
        
        try:
            import zipfile
            import csv
            from io import BytesIO, StringIO
            
            _LOGGER.info("Discovering routes for %d stops...", len(self.selected_stops))
            
            async with aiohttp.ClientSession() as session:
                async with session.get(self.gtfs_data["static_url"]) as response:
                    if response.status != 200:
                        return
                    
                    data = await response.read()
            
            gtfs_zip = BytesIO(data)
            
            with zipfile.ZipFile(gtfs_zip) as zf:
                # First, get trips for our selected stops
                stop_trips = set()
                try:
                    with zf.open('stop_times.txt') as f:
                        reader = csv.DictReader(StringIO(f.read().decode('utf-8')))
                        for row in reader:
                            if row.get('stop_id') in self.selected_stops:
                                stop_trips.add(row.get('trip_id'))
                except:
                    return
                
                # Then, get routes for those trips  
                route_ids = set()
                try:
                    with zf.open('trips.txt') as f:
                        reader = csv.DictReader(StringIO(f.read().decode('utf-8')))
                        for row in reader:
                            if row.get('trip_id') in stop_trips:
                                route_ids.add(row.get('route_id'))
                except:
                    return
                
                # Finally, get route details
                try:
                    with zf.open('routes.txt') as f:
                        reader = csv.DictReader(StringIO(f.read().decode('utf-8')))
                        self.available_routes = [
                            {
                                'route_id': row['route_id'],
                                'route_short_name': row.get('route_short_name', ''),
                                'route_long_name': row.get('route_long_name', ''),
                                'route_type': row.get('route_type', '0')
                            }
                            for row in reader
                            if row.get('route_id') in route_ids
                        ]
                    
                    # Sort by route name
                    self.available_routes.sort(key=lambda x: x.get('route_short_name', x['route_id']))
                    
                except Exception as e:
                    _LOGGER.error("Error parsing routes: %s", e)
                    return
            
            _LOGGER.info("Discovered %d routes serving selected stops", len(self.available_routes))
        
        except Exception as e:
            _LOGGER.error("Error discovering routes: %s", e)
    
    def _check_for_duplicate_stops(self) -> bool:
        """Check if selected stops have potential duplicates."""
        if len(self.selected_stops) < 2:
            return False
        
        # Simple duplicate check based on similar names
        stop_names = [stop['stop_name'].lower() for stop in self.available_stops if stop['stop_id'] in self.selected_stops]
        
        # Check for similar names (indicating duplicates)
        for i, name1 in enumerate(stop_names):
            for name2 in stop_names[i+1:]:
                if name1 in name2 or name2 in name1:
                    return True
        
        return False
    
    async def async_step_create_groups(
        self, user_input: dict[str, str] | None = None
    ) -> FlowResult:
        """Step 5: Create stop groups."""
        if user_input is not None:
            # Process stop grouping (simplified for now)
            return await self.async_step_ask_routes()
        
        # Show potential duplicates and let user group them
        return self.async_show_form(
            step_id="create_groups",
            data_schema=vol.Schema({
                vol.Required("group_name", default=""): str,
                vol.Required("group_stops", default=""): str,
            }),
            description_placeholders={
                "selected_count": len(self.selected_stops)
            }
        )