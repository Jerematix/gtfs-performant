# GTFS Performant

A high-performance GTFS (General Transit Feed Specification) integration for Home Assistant, optimized for Raspberry Pi and large transit datasets like German nationwide GTFS feeds.

![HACS](https://img.shields.io/badge/HACS-Default-orange)
![License](https://img.shields.io/badge/License-MIT-blue)
![HA Version](https://img.shields.io/badge/HA-2025.7%2B-green)

## 🚀 Features

- **Performance Optimized**: Designed specifically for resource-constrained devices like Raspberry Pi
- **Intelligent Duplicate Detection**: Automatically identifies and groups duplicate stops
- **Real-time Updates**: Efficient GTFS-RT protobuf processing with memory optimization
- **User-Friendly Setup**: Modern config flow with step-by-step wizard
- **Flexible Configuration**: Select specific stops, routes, and create custom stop groups
- **Live Departure Information**: Real-time sensor updates with delay information

## 🏗️ Architecture

### Performance Optimizations
1. **SQLite Database**: Uses optimized database with strategic indexes for fast queries
2. **Batch Processing**: Processes large GTFS files in memory-efficient batches
3. **Incremental Updates**: Only processes changed realtime data
4. **Lazy Loading**: Loads data on-demand to minimize memory usage
5. **Background Updates**: Non-blocking data refresh

### Data Processing
- **Static GTFS**: Efficiently processes large ZIP files with streaming
- **Realtime GTFS**: Memory-optimized protobuf parsing with zero-copy techniques
- **Duplicate Detection**: Intelligent grouping of stops based on location and name similarity

## 📦 Installation

### Using HACS (Recommended)
1. Install [HACS](https://hacs.xyz/) if you haven't already
2. Add this repository as a custom repository:
   - URL: `https://github.com/jerematix/gtfs-performant`
   - Category: Integration
3. Install "GTFS Performant" from HACS
4. Restart Home Assistant

### Manual Installation
1. Download the latest release
2. Copy the `custom_components/gtfs_performant` directory to your Home Assistant `custom_components` directory
3. Restart Home Assistant

## ⚙️ Configuration

### Initial Setup
1. Go to **Settings → Devices & Services → Add Integration**
2. Search for "GTFS Performant"
3. Enter your GTFS data sources:
   - **Static GTFS URL**: URL to the static GTFS ZIP file
   - **Realtime GTFS URL**: URL to the GTFS realtime protobuf feed
   - **Integration Name**: Friendly name for this integration

### Example Configuration

For German nationwide GTFS:
```yaml
Static URL: https://download.gtfs.de/germany/rv_free/latest.zip
Realtime URL: https://realtime.gtfs.de/realtime-free.pb
```

### Selecting Stops
After setup, you can:
- Browse all available stops grouped by location
- Select specific stops you want to monitor
- Group duplicate stops (e.g., opposite sides of a street)
- Filter by specific routes

## 📊 Sensor Attributes

Each departure sensor provides:
- **departure_N_route**: Route name/number
- **departure_N_destination**: Final destination
- **departure_N_scheduled**: Scheduled departure time
- **departure_N_expected**: Expected departure time (with delays)
- **departure_N_delay_minutes**: Delay in minutes
- **departure_N_vehicle_id**: Vehicle identifier

## 🖥️ Performance on Raspberry Pi

This integration is specifically optimized for Raspberry Pi hardware:
- **Memory Efficient**: Processes large datasets in batches
- **CPU Optimized**: Minimal blocking operations
- **Storage Efficient**: Compressed data storage
- **Background Processing**: Doesn't block Home Assistant core

## 🔧 Services

### `gtfs_performant.reload_gtfs_data`
Reload static GTFS data (optionally force complete refresh)

### `gtfs_performant.refresh_realtime`
Force immediate refresh of realtime data

### `gtfs_performant.manage_stops`
Add, remove, or group stops dynamically

## 🐛 Troubleshooting

### Large Dataset Performance
If you experience performance issues with very large datasets:
1. Reduce the update interval in options
2. Select only specific stops you need
3. Use stop grouping to reduce duplicate processing

### Memory Issues on Raspberry Pi
- Ensure sufficient swap space
- Close unnecessary Home Assistant integrations
- Consider using a Raspberry Pi 4 or 5 for best performance

## 🛠️ Development

### Requirements
- Python 3.12+
- Home Assistant 2025.7+
- `uv` package manager

### Setup
```bash
# Install dependencies
uv pip install -r requirements.txt

# Run tests
pytest custom_components/gtfs_performant/tests/
```

## 📄 License

MIT License - see [LICENSE](LICENSE) file for details

## 🙏 Credits

- Inspired by [ha-gtfs-rt-v2](https://github.com/mark1foley/ha-gtfs-rt-v2)
- Uses official [gtfs-realtime-bindings](https://github.com/MobilityData/gtfs-realtime-bindings)
- Built specifically for German GTFS data and other large datasets

## ⭐ Support

If you find this integration helpful, please consider giving it a star on GitHub!

- **Issues**: [GitHub Issues](https://github.com/jerematix/gtfs-performant/issues)
- **Discussions**: [GitHub Discussions](https://github.com/jerematix/gtfs-performant/discussions)