# GTFS Performant

A high-performance GTFS (General Transit Feed Specification) integration for Home Assistant, optimized for large transit datasets like German nationwide GTFS feeds.

[![HACS Badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
[![License](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![HA Version](https://img.shields.io/badge/HA-2024.1%2B-green.svg)](https://www.home-assistant.io/)
[![Validate HACS](https://github.com/jerematix/gtfs-performant/actions/workflows/hacs.yaml/badge.svg)](https://github.com/jerematix/gtfs-performant/actions/workflows/hacs.yaml)
[![Hassfest](https://github.com/jerematix/gtfs-performant/actions/workflows/hassfest.yaml/badge.svg)](https://github.com/jerematix/gtfs-performant/actions/workflows/hassfest.yaml)

## Features

- **High Performance**: Optimized for large GTFS datasets with streaming processing
- **SQLite Database**: Persistent storage with fast indexed queries
- **GTFS-RT Support**: Real-time updates with delay information
- **Smart Stop Selection**: Browse and select specific stops during setup
- **Stop Grouping**: Group related stops (e.g., both sides of a street)
- **Custom Lovelace Card**: Beautiful departure board with visual configuration
- **Past-Midnight Service**: Properly handles night services that cross midnight
- **Calendar Dates Support**: Full support for service exceptions

## Installation

### HACS (Recommended)

1. Open HACS in Home Assistant
2. Click the three dots menu → **Custom repositories**
3. Add `https://github.com/jerematix/gtfs-performant` with category **Integration**
4. Click **Install**
5. Restart Home Assistant

### Manual Installation

1. Download the latest release
2. Copy `custom_components/gtfs_performant` to your `custom_components` directory
3. Restart Home Assistant

## Configuration

1. Go to **Settings → Devices & Services → Add Integration**
2. Search for **GTFS Performant**
3. Enter your GTFS data sources:
   - **Static GTFS URL**: URL to the static GTFS ZIP file
   - **Realtime GTFS URL**: URL to the GTFS-RT protobuf feed (optional)
4. Select the stops you want to monitor
5. Optionally group stops and configure update intervals

### Example GTFS Sources

**Germany (nationwide free feed):**
```
Static: https://download.gtfs.de/germany/nv_free/latest.zip
Realtime: https://realtime.gtfs.de/realtime-free.pb
```

## Lovelace Card

The integration includes a custom departure card that can be configured via the UI.

### Adding the Card

1. Edit your dashboard
2. Click **Add Card**
3. Search for **GTFS Departures**
4. Select your transit sensor from the dropdown
5. Configure options (title, max departures, colors)

### Card Options

| Option | Description |
|--------|-------------|
| Entity | The transit stop sensor to display |
| Title | Custom card title (optional) |
| Max Departures | Number of departures to show (1-20) |
| Route Color | Color for the route badges |
| Show Header | Show/hide the card header |

### Manual YAML Configuration

```yaml
type: custom:gtfs-departures-card
entity: sensor.koln_sulz_weisshausstr
title: My Stop
max_items: 8
route_color: "#03a9f4"
show_header: true
```

## Services

### `gtfs_performant.reload_gtfs_data`
Force reload of static GTFS data.

```yaml
service: gtfs_performant.reload_gtfs_data
data:
  force_refresh: true
```

## Troubleshooting

### No departures showing
- Verify stops were selected during setup
- Check that current date is within the GTFS feed's valid date range
- Check Home Assistant logs for errors

### Wrong departure times
- Ensure the GTFS feed has correct timezone information
- Check that `calendar_dates.txt` is being loaded (for German feeds)

### Card not showing in picker
- Clear browser cache (Ctrl+Shift+R)
- Check **Settings → Dashboards → Resources** for the card registration

## Development

```bash
# Clone the repository
git clone https://github.com/jerematix/gtfs-performant.git

# Install dependencies
pip install -r requirements.txt

# Run validation
python -m py_compile custom_components/gtfs_performant/*.py
```

## License

MIT License - see [LICENSE](LICENSE) for details.

## Credits

Built for the German GTFS ecosystem and other large transit datasets.
