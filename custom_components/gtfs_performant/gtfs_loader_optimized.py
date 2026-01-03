    async def _process_minimal_agency(self, zip_file: BytesIO) -> None:
        """Process minimal agency data."""
        rows = await self._read_csv_from_zip(zip_file, 'agency.txt')
        if not rows:
            return
        
        # Only process first agency
        if rows:
            row = rows[0]
            row.setdefault('agency_id', 'default')
            row.setdefault('agency_lang', '')
            row.setdefault('agency_phone', '')
            row.setdefault('agency_fare_url', '')
            
            await self._agro_insert_batch('agency', 
                ['agency_id', 'agency_name', 'agency_url', 'agency_timezone', 
                 'agency_lang', 'agency_phone', 'agency_fare_url'], [row])
            _LOGGER.info("Loaded minimal agency data")
    
    async def _process_selected_stops(self, zip_file: BytesIO, relevant_stops: Set[str]) -> None:
        """Process ONLY selected stops."""
        if not relevant_stops:
            _LOGGER.info("No specific stops selected, skipping stops processing")
            return
        
        rows = await self._read_csv_from_zip(zip_file, 'stops.txt')
        if not rows:
            return
        
        # Filter to only selected stops
        selected_rows = [row for row in rows if row.get('stop_id') in relevant_stops]
        
        # Process with duplicate detection
        processed_stops = []
        for row in selected_rows:
            if row.get('location_type', '0') != '0':  # Only process stops
                continue
            
            # Add duplicate detection fields
            lat = float(row.get('stop_lat', 0))
            lon = float(row.get('stop_lon', 0))
            name = row.get('stop_name', '').strip().lower() if row.get('stop_name') else ''
            
            duplicate_key = self._create_duplicate_key(lat, lon, name)
            
            row['duplicate_group_id'] = f"single_{duplicate_key}"
            row['is_duplicate'] = 0
            processed_stops.append(row)
        
        columns = ['stop_id', 'stop_code', 'stop_name', 'stop_lat', 'stop_lon',
                  'zone_id', 'location_type', 'parent_station', 'wheelchair_boarding',
                  'duplicate_group_id', 'is_duplicate']
        
        await self._agro_insert_batch('stops', columns, processed_stops)
        _LOGGER.info("Loaded %d selected stops (from %d total)", len(processed_stops), len(rows))
    
    async def _process_selected_routes(self, zip_file: BytesIO, relevant_routes: Set[str]) -> None:
        """Process ONLY selected routes."""
        if not relevant_routes:
            _LOGGER.info("No specific routes selected, skipping routes processing")
            return
        
        rows = await self._read_csv_from_zip(zip_file, 'routes.txt')
        if not rows:
            return
        
        # Filter to only selected routes
        selected_rows = [row for row in rows if row.get('route_id') in relevant_routes]
        
        # Add missing fields
        for i, row in enumerate(selected_rows):
            row.setdefault('agency_id', '')
            row.setdefault('route_desc', '')
            row.setdefault('route_url', '')
            row.setdefault('route_color', '')
            row.setdefault('route_text_color', '')
            row['route_sort_order'] = str(i)
        
        columns = ['route_id', 'agency_id', 'route_short_name', 'route_long_name',
                  'route_desc', 'route_type', 'route_url', 'route_color', 'route_text_color',
                  'route_sort_order']
        
        await self._agro_insert_batch('routes', columns, selected_rows)
        _LOGGER.info("Loaded %d selected routes (from %d total)", len(selected_rows), len(rows))
    
    async def _process_selected_calendar(self, zip_file: BytesIO) -> None:
        """Process minimal calendar data."""
        rows = await self._read_csv_from_zip(zip_file, 'calendar.txt')
        if not rows:
            return
        
        # Only process first calendar (usually enough)
        if rows:
            await self._agro_insert_batch('calendar', 
                ['service_id', 'monday', 'tuesday', 'wednesday', 'thursday',
                 'friday', 'saturday', 'sunday', 'start_date', 'end_date'], 
                [rows[0]])
            _LOGGER.info("Loaded minimal calendar data")
    
    async def _process_selected_trips(self, zip_file: BytesIO, relevant_routes: Set[str]) -> None:
        """Process ONLY trips for selected routes."""
        if not relevant_routes:
            return
        
        rows = await self._read_csv_from_zip(zip_file, 'trips.txt')
        if not rows:
            return
        
        # Filter to only selected routes and handle missing fields
        selected_rows = []
        for row in rows:
            if row.get('route_id') in relevant_routes:
                row.setdefault('trip_headsign', '')
                row.setdefault('trip_short_name', '')
                row.setdefault('direction_id', '')
                row.setdefault('block_id', '')
                row.setdefault('shape_id', '')
                row.setdefault('wheelchair_accessible', '0')
                row.setdefault('bikes_allowed', '0')
                selected_rows.append(row)
        
        # Process in batches
        batch_size = 1000
        for i in range(0, len(selected_rows), batch_size):
            batch = selected_rows[i:i + batch_size]
            columns = ['trip_id', 'route_id', 'service_id', 'trip_headsign',
                      'trip_short_name', 'direction_id', 'block_id', 'shape_id',
                      'wheelchair_accessible', 'bikes_allowed']
            await self._agro_insert_batch('trips', columns, batch)
        
        _LOGGER.info("Loaded %d trips for selected routes (from %d total)", len(selected_rows), len(rows))
    
    async def _process_selected_stop_times(self, zip_file: BytesIO, relevant_stops: Set[str], relevant_routes: Set[str]) -> None:
        """Process ONLY stop times for selected stops and routes."""
        if not relevant_stops or not relevant_routes:
            _LOGGER.info("No stops or routes selected, skipping stop_times processing")
            return
        
        _LOGGER.info("Processing stop_times selectively (this may take a moment)...")
        
        try:
            with zipfile.ZipFile(zip_file) as zf:
                with zf.open('stop_times.txt') as f:
                    reader = csv.DictReader(StringIO(f.read().decode('utf-8')))
                    
                    batch = []
                    batch_size = 5000
                    processed_count = 0
                    total_count = 0
                    
                    for row in reader:
                        total_count += 1
                        
                        # Only process stop_times for our selected stops
                        if row.get('stop_id') in relevant_stops:
                            # Handle missing optional columns
                            row.setdefault('stop_headsign', '')
                            row.setdefault('pickup_type', '0')
                            row.setdefault('drop_off_type', '0')
                            row.setdefault('shape_dist_traveled', '')
                            row.setdefault('timepoint', '1')
                            
                            batch.append(row)
                            processed_count += 1
                            
                            if len(batch) >= batch_size:
                                await self._insert_stop_times_batch(batch)
                                batch = []
                                _LOGGER.debug("Processed %d/%d stop_times", processed_count, total_count)
                    
                    # Insert remaining
                    if batch:
                        await self._insert_stop_times_batch(batch)
            
            _LOGGER.info("Loaded %d stop_times for selected stops (from %d total)", processed_count, total_count)
        
        except KeyError:
            _LOGGER.warning("stop_times.txt not found in GTFS archive")
            return