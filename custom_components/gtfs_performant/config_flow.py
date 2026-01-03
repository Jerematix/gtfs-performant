"""Config flow for GTFS Performant integration."""
import asyncio
import logging

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult

from . import DOMAIN
from .database import GTFSDatabase

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema({
    vol.Required("static_url"): str,
    vol.Required("realtime_url"): str,
    vol.Optional("name", default="GTFS Transit"): str,
})


async def validate_input(hass: HomeAssistant, data: dict) -> dict:
    """Validate the user input allows us to connect."""
    # Basic validation - check URLs are accessible
    # More detailed validation happens during actual setup
    return {"title": data.get("name", "GTFS Transit")}


class GTFSPerformantConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for GTFS Performant."""
    
    VERSION = 1
    
    async def async_step_user(
        self, user_input: dict[str, str] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors = {}
        if user_input is not None:
            try:
                info = await validate_input(self.hass, user_input)
                
                # Set unique ID based on URLs to avoid duplicates
                await self.async_set_unique_id(f"{user_input['static_url']}")
                self._abort_if_unique_id_configured()
                
                return self.async_create_entry(title=info["title"], data=user_input)
            except Exception as err:
                _LOGGER.exception("Unexpected exception: %s", err)
                errors["base"] = "unknown"
        
        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )
    
    async def async_step_select_stops(
        self, user_input: dict[str, str] | None = None
    ) -> FlowResult:
        """Handle stop selection step."""
        errors = {}
        stops_data = []
        
        # Get current entry data
        if self.current_entry:
            current_data = self.current_entry.data
        else:
            errors["base"] = "no_config"
            return self.async_show_form(step_id="select_stops", errors=errors)
        
        try:
            # Load database and get stops
            db_path = self.hass.config.path(f"gtfs_{self.current_entry.entry_id}.db")
            database = GTFSDatabase(db_path)
            await database.async_init()
            
            stops = await database.get_all_stops()
            
            # Group stops by duplicate groups
            grouped_stops = {}
            for stop in stops:
                group_id = stop['duplicate_group_id']
                if group_id not in grouped_stops:
                    grouped_stops[group_id] = {
                        'group_id': group_id,
                        'stops': [],
                        'is_duplicate_group': stop['is_duplicate'] == 1
                    }
                grouped_stops[group_id]['stops'].append(stop)
            
            stops_data = list(grouped_stops.values())
            
        except Exception as err:
            _LOGGER.error("Error loading stops: %s", err)
            errors["base"] = "cannot_load_stops"
        
        if user_input is not None:
            # Save selected stops
            selected_stops = user_input.get("selected_stops", [])
            user_input["selected_stops"] = selected_stops
            
            return self.async_create_entry(
                title=current_data.get("name", "GTFS Transit"),
                data={**current_data, **user_input}
            )
        
        # Show form with stop selection
        return self.async_show_form(
            step_id="select_stops",
            data_schema=vol.Schema({
                vol.Required("selected_stops"): str,
            }),
            description_placeholders={"stops_count": len(stops_data)},
            errors=errors,
        )
    
    async def async_step_select_routes(
        self, user_input: dict[str, str] | None = None
    ) -> FlowResult:
        """Handle route selection step."""
        errors = {}
        
        # Similar to select_stops, but for routes
        # This would be called after select_stops
        
        if user_input is not None:
            # Save selected routes and continue
            return self.async_create_entry(
                title="GTFS Transit",
                data=user_input
            )
        
        return self.async_show_form(
            step_id="select_routes",
            data_schema=vol.Schema({
                vol.Required("selected_routes"): str,
            }),
            errors=errors,
        )


class GTFSPerformantOptionsFlow(config_entries.OptionsFlow):
    """Handle options flow for GTFS Performant."""
    
    async def async_step_init(
        self, user_input: dict[str, str] | None = None
    ) -> FlowResult:
        """Manage options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)
        
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Required("update_interval", default=30): vol.All(vol.Coerce(int), vol.Range(min=10, max=300)),
            }),
        )