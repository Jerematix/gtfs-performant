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
        self.stop_groups = []
    
    async def async_step_user(
        self, user_input: dict[str, str] | None = None
    ) -> FlowResult:
        """Step 1: Basic GTFS source configuration."""
        _LOGGER.info("🔍 async_step_user called with user_input: %s", user_input)
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
                            _LOGGER.info("✅ URLs validated, proceeding to discover_stops")
                            return await self.async_step_discover_stops()
            except Exception as err:
                _LOGGER.error("Error connecting to GTFS source: %s", err)
                errors["base"] = "cannot_connect"
        
        _LOGGER.info("📝 Showing user form")
        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )
    
    async def async_step_discover_stops(
        self, user_input: dict[str, str] | None = None
    ) -> FlowResult:
        """Step 2: Download GTFS and discover available stops, then go directly to selection."""
        _LOGGER.info("🔍 async_step_discover_stops called")

        # Download and parse GTFS to get stops
        _LOGGER.info("📥 Discovering GTFS stops...")
        info = await self._discover_gtfs_stops()

        if not info or not self.available_stops:
            _LOGGER.error("❌ Failed to discover stops")
            return self.async_abort(reason="cannot_load_stops")

        _LOGGER.info("✅ Discovered %d stops, proceeding to select_stops", len(self.available_stops))
        # Go directly to stop selection (skip the empty confirmation step)
        return await self.async_step_select_stops()
    
    async def async_step_group_stops(
        self, user_input: dict[str, str] | None = None
    ) -> FlowResult:
        """Step 4: Let users manually create stop groups if desired."""
        if user_input is not None:
            # Check if user wants to create groups
            if user_input.get("create_groups", "no") == "yes":
                return await self.async_step_create_groups()
            else:
                # Skip to route filtering
                return await self.async_step_ask_routes()

        return self.async_show_form(
            step_id="group_stops",
            data_schema=vol.Schema({
                vol.Required("create_groups", default="no"): SelectSelector(
                    SelectSelectorConfig(
                        options=[
                            {"value": "no", "label": "No - treat stops separately"},
                            {"value": "yes", "label": "Yes - manually group stops together"}
                        ],
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                )
            }),
            description_placeholders={
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

            # Auto-generate groups based on same name (user can modify next)
            self._auto_group_stops_by_name()

            # Show groups for user to review/modify
            return await self.async_step_review_groups()
        
        # Create selector options for ALL stops
        stop_options = [
            {"value": stop['stop_id'], "label": f"{stop['stop_name']} ({stop['stop_id']})"}
            for stop in self.available_stops
        ]

        # Sort by label for better UX
        stop_options.sort(key=lambda x: x['label'])
        
        _LOGGER.info("🔍 Creating dropdown with %d stops options", len(stop_options))
        _LOGGER.debug("🔍 First few options: %s", stop_options[:3])
        
        return self.async_show_form(
            step_id="select_stops",
            data_schema=vol.Schema({
                vol.Optional("selected_stops", default=[]): SelectSelector(
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
    
    async def async_step_review_groups(
        self, user_input: dict[str, str] | None = None
    ) -> FlowResult:
        """Step 4: Review and modify auto-generated stop groups."""
        if user_input is not None:
            # Parse the groups from user input
            new_groups = []
            group_idx = 0
            while f"group_{group_idx}_name" in user_input:
                group_name = user_input.get(f"group_{group_idx}_name", "").strip()
                group_stops_str = user_input.get(f"group_{group_idx}_stops", "").strip()
                if group_name and group_stops_str:
                    group_stops = [s.strip() for s in group_stops_str.split(",") if s.strip()]
                    if group_stops:
                        new_groups.append({"name": group_name, "stops": group_stops})
                group_idx += 1

            self.stop_groups = new_groups
            _LOGGER.info("User confirmed %d groups", len(self.stop_groups))
            return await self.async_step_ask_routes()

        # Build the form schema with pre-populated groups
        schema_dict = {}

        # Get stop info for display
        stop_id_to_name = {
            stop['stop_id']: stop['stop_name']
            for stop in self.available_stops
            if stop['stop_id'] in self.selected_stops
        }

        # Add fields for each existing group
        for idx, group in enumerate(self.stop_groups):
            schema_dict[vol.Optional(f"group_{idx}_name", default=group["name"])] = str
            schema_dict[vol.Optional(f"group_{idx}_stops", default=",".join(group["stops"]))] = str

        # Build description showing what was auto-detected
        if self.stop_groups:
            groups_summary = "\n".join([
                f"**{g['name']}**: {len(g['stops'])} stops"
                for g in self.stop_groups
            ])
        else:
            groups_summary = "No groups auto-detected (all stops have unique names)"

        # List ungrouped stops
        grouped_stop_ids = set()
        for g in self.stop_groups:
            grouped_stop_ids.update(g["stops"])
        ungrouped = [
            f"{stop_id_to_name.get(sid, sid)} ({sid})"
            for sid in self.selected_stops
            if sid not in grouped_stop_ids
        ]
        ungrouped_summary = ", ".join(ungrouped) if ungrouped else "None"

        return self.async_show_form(
            step_id="review_groups",
            data_schema=vol.Schema(schema_dict),
            description_placeholders={
                "groups_count": len(self.stop_groups),
                "groups_summary": groups_summary,
                "ungrouped_stops": ungrouped_summary,
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
                vol.Required("filter_routes", default="no"): SelectSelector(
                    SelectSelectorConfig(
                        options=[
                            {"value": "no", "label": "No - monitor all routes at my stops"},
                            {"value": "yes", "label": "Yes - only specific routes"}
                        ],
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                )
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

        # Create selector options for routes
        route_options = [
            {"value": route['route_id'], "label": f"{route.get('route_short_name', route['route_id'])} - {route.get('route_long_name', '')}"}
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
        """Step 6: Show summary, configure update intervals, and create entry."""
        if user_input is not None:
            # Get the update intervals
            update_interval = int(user_input.get("update_interval", "120"))
            full_update_day = int(user_input.get("full_update_day", "1"))
            full_update_hour = int(user_input.get("full_update_hour", "4"))

            # Create the config entry
            config_data = {
                "static_url": self.gtfs_data["static_url"],
                "realtime_url": self.gtfs_data["realtime_url"],
                "name": self.gtfs_data["name"],
                "selected_stops": self.selected_stops,
                "selected_routes": list(self.selected_routes) if self.selected_routes else [],
                "stop_groups": self.stop_groups,
                "update_interval": update_interval,
                "full_update_day": full_update_day,
                "full_update_hour": full_update_hour,
            }

            return self.async_create_entry(
                title=self.gtfs_data["name"],
                data=config_data
            )

        # Build summary information
        stop_id_to_name = {
            stop['stop_id']: stop['stop_name']
            for stop in self.available_stops
            if stop['stop_id'] in self.selected_stops
        }

        # Build groups summary
        if self.stop_groups:
            groups_list = "\n".join([
                f"• **{g['name']}** ({len(g['stops'])} stops)"
                for g in self.stop_groups
            ])
        else:
            groups_list = "None"

        # Build ungrouped stops list
        grouped_ids = set()
        for g in self.stop_groups:
            grouped_ids.update(g.get("stops", []))
        ungrouped_stops = [sid for sid in self.selected_stops if sid not in grouped_ids]
        if ungrouped_stops:
            ungrouped_list = "\n".join([
                f"• {stop_id_to_name.get(sid, sid)}"
                for sid in ungrouped_stops
            ])
        else:
            ungrouped_list = "None (all stops are grouped)"

        # Show summary with update interval selectors
        return self.async_show_form(
            step_id="final_processing",
            data_schema=vol.Schema({
                vol.Required("update_interval", default="120"): SelectSelector(
                    SelectSelectorConfig(
                        options=[
                            {"value": "30", "label": "30 seconds"},
                            {"value": "60", "label": "1 minute"},
                            {"value": "120", "label": "2 minutes (recommended)"},
                            {"value": "300", "label": "5 minutes"},
                            {"value": "600", "label": "10 minutes"},
                        ],
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Required("full_update_day", default="1"): SelectSelector(
                    SelectSelectorConfig(
                        options=[
                            {"value": "1", "label": "1st of month"},
                            {"value": "15", "label": "15th of month"},
                        ],
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Required("full_update_hour", default="4"): SelectSelector(
                    SelectSelectorConfig(
                        options=[
                            {"value": "0", "label": "Midnight (0:00)"},
                            {"value": "1", "label": "1 AM"},
                            {"value": "2", "label": "2 AM"},
                            {"value": "3", "label": "3 AM"},
                            {"value": "4", "label": "4 AM (recommended)"},
                            {"value": "5", "label": "5 AM"},
                            {"value": "6", "label": "6 AM"},
                        ],
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                ),
            }),
            description_placeholders={
                "name": self.gtfs_data["name"],
                "selected_stops_count": len(self.selected_stops),
                "groups_count": len(self.stop_groups),
                "groups_list": groups_list,
                "ungrouped_list": ungrouped_list,
                "selected_routes_count": len(self.selected_routes) if self.selected_routes else 0,
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
    
    def _auto_group_stops_by_name(self) -> None:
        """Automatically group selected stops that have the same name."""
        if len(self.selected_stops) < 2:
            return

        # Build a map of stop_id -> stop_name for selected stops
        selected_stop_info = {
            stop['stop_id']: stop['stop_name']
            for stop in self.available_stops
            if stop['stop_id'] in self.selected_stops
        }

        # Group stops by name
        name_to_stops: dict[str, list[str]] = {}
        for stop_id, stop_name in selected_stop_info.items():
            if stop_name not in name_to_stops:
                name_to_stops[stop_name] = []
            name_to_stops[stop_name].append(stop_id)

        # Create groups for names with multiple stops
        self.stop_groups = []
        for name, stop_ids in name_to_stops.items():
            if len(stop_ids) > 1:
                self.stop_groups.append({
                    "name": name,
                    "stops": stop_ids
                })
                _LOGGER.info("Auto-grouped %d stops under '%s': %s", len(stop_ids), name, stop_ids)

        if self.stop_groups:
            _LOGGER.info("Created %d automatic stop groups", len(self.stop_groups))

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
        """Step 5: Manually create stop groups."""
        if user_input is not None:
            # Parse the group definition
            group_name = user_input.get("group_name", "").strip()
            group_stops_str = user_input.get("group_stops", "").strip()
            
            if group_name and group_stops_str:
                # Parse comma-separated stop IDs
                group_stops = [s.strip() for s in group_stops_str.split(",")]
                
                # Add to groups
                self.stop_groups.append({
                    "name": group_name,
                    "stops": group_stops
                })
                
                # Ask if they want to create more groups
                return await self.async_step_more_groups()
            else:
                # No group created, move to routes
                return await self.async_step_ask_routes()
        
        # Show form for creating a group
        selected_stop_details = "\n".join([
            f"• {stop['stop_name']} ({stop['stop_id']})"
            for stop in self.available_stops if stop['stop_id'] in self.selected_stops
        ])
        
        return self.async_show_form(
            step_id="create_groups",
            data_schema=vol.Schema({
                vol.Required("group_name", default=""): str,
                vol.Required("group_stops", default=""): str,
            }),
            description_placeholders={
                "selected_count": len(self.selected_stops),
                "selected_stops_list": selected_stop_details[:500]  # Limit length
            }
        )
    
    async def async_step_more_groups(
        self, user_input: dict[str, str] | None = None
    ) -> FlowResult:
        """Step 6: Ask if user wants to create more groups."""
        if user_input is not None:
            if user_input.get("create_more", "no") == "yes":
                return await self.async_step_create_groups()
            else:
                # Done with groups, move to routes
                return await self.async_step_ask_routes()

        return self.async_show_form(
            step_id="more_groups",
            data_schema=vol.Schema({
                vol.Required("create_more", default="no"): SelectSelector(
                    SelectSelectorConfig(
                        options=[
                            {"value": "no", "label": "No - done creating groups"},
                            {"value": "yes", "label": "Yes - create another group"}
                        ],
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                )
            }),
            description_placeholders={
                "groups_count": len(self.stop_groups)
            }
        )