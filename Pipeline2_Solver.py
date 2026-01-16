import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import random
import json
from enum import IntEnum

# Debug flag - set to True to enable console output
DEBUG = True

def debug_log(msg, indent=0):
    """Print debug message if DEBUG is enabled"""
    if DEBUG:
        prefix = "  " * indent
        print(f"{prefix}[DEBUG] {msg}")

class CellType(IntEnum):
    EMPTY = 0
    ROOM = 1
    CORRIDOR = 2
    SPAWN_T = 3
    SPAWN_CT = 4
    BOMBSITE = 5
    MID_AREA = 6
    CHOKEPOINT = 7
    CONNECTOR = 8
    COVER = 9

class LevelGenerator:
    def __init__(self, width, height):
        self.width = width
        self.height = height
        self.grid = [[CellType.EMPTY for _ in range(width)] for _ in range(height)]
        self.areas = {}
        debug_log(f"LevelGenerator initialized: {width}x{height} grid")
        
    def generate_from_json(self, level_spec):
        debug_log("=" * 50)
        debug_log("STARTING LEVEL GENERATION")
        debug_log("=" * 50)
        
        self.grid = [[CellType.EMPTY for _ in range(self.width)] for _ in range(self.height)]
        self.areas = {}
        
        size_map = {"small": 4, "medium": 6, "large": 9}
        debug_log(f"Size mapping: {size_map}")
        
        # Generate spawn zones
        debug_log("\n--- GENERATING SPAWN ZONES ---")
        spawn_zones = []
        for i, spawn_spec in enumerate(level_spec.get("spawn_zones", [])):
            debug_log(f"Spawn zone {i+1}: {spawn_spec}", indent=1)
            zone = self._create_zone_with_spec(
                spawn_spec["team"],
                size_map.get(spawn_spec.get("size", "medium"), 6),
                spawn_spec.get("location"),
                spawn_spec.get("position_preference", "edge"),
                CellType.SPAWN_T if spawn_spec["team"] == "T" else CellType.SPAWN_CT,
                spawn_spec.get("shape")
            )
            if zone:
                spawn_zones.append(zone)
                self.areas[f"{spawn_spec['team']}_spawn"] = zone
                debug_log(f"SUCCESS: Created {spawn_spec['team']}_spawn at ({zone['x']}, {zone['y']}) size {zone['w']}x{zone['h']} shape={zone['shape']}", indent=2)
            else:
                debug_log(f"FAILED: Could not place {spawn_spec['team']}_spawn", indent=2)
        
        # Generate bomb sites
        debug_log("\n--- GENERATING BOMB SITES ---")
        bomb_sites = []
        for i, site_spec in enumerate(level_spec.get("bomb_sites", [])):
            debug_log(f"Bomb site {i+1}: {site_spec}", indent=1)
            site = self._create_zone_with_spec(
                site_spec["id"],
                size_map.get(site_spec.get("size", "medium"), 6),
                site_spec.get("location"),
                site_spec.get("position_preference", "any"),
                CellType.BOMBSITE,
                site_spec.get("shape")
            )
            if site:
                bomb_sites.append(site)
                self.areas[f"site_{site_spec['id']}"] = site
                debug_log(f"SUCCESS: Created site_{site_spec['id']} at ({site['x']}, {site['y']}) size {site['w']}x{site['h']} shape={site['shape']}", indent=2)
            else:
                debug_log(f"FAILED: Could not place site_{site_spec['id']}", indent=2)
        
        # Generate mid areas
        debug_log("\n--- GENERATING MID AREAS ---")
        mid_index = 0
        for i, area_spec in enumerate(level_spec.get("areas", [])):
            if area_spec["type"] == "mid":
                debug_log(f"Mid area {mid_index+1}: {area_spec}", indent=1)
                mid = self._create_zone_with_spec(
                    f"mid_{mid_index}",
                    size_map.get(area_spec.get("size", "medium"), 6),
                    area_spec.get("location", {"x": 0.5, "y": 0.5}),
                    "any",
                    CellType.MID_AREA,
                    area_spec.get("shape")
                )
                if mid:
                    self.areas[f"mid_{mid_index}"] = mid
                    debug_log(f"SUCCESS: Created mid_{mid_index} at ({mid['x']}, {mid['y']}) size {mid['w']}x{mid['h']} shape={mid['shape']}", indent=2)
                    mid_index += 1
                else:
                    debug_log(f"FAILED: Could not place mid_{mid_index}", indent=2)
        
        # Connect areas
        debug_log("\n--- CONNECTING AREAS ---")
        connectivity = level_spec.get("connectivity", {})
        sightline_control = level_spec.get("sightline_control", {})
        debug_log(f"Connectivity settings: {connectivity}", indent=1)
        debug_log(f"Sightline control: {sightline_control}", indent=1)
        self._connect_areas(connectivity, sightline_control)
        
        # Add cover objects
        debug_log("\n--- PLACING COVER OBJECTS ---")
        cover_spec = level_spec.get("cover_objects", {})
        if cover_spec.get("enabled", False):
            debug_log(f"Cover settings: {cover_spec}", indent=1)
            self._place_cover_objects(cover_spec)
        else:
            debug_log("Cover objects disabled", indent=1)
        
        # Calculate stats
        debug_log("\n--- CALCULATING SIGHTLINE STATS ---")
        stats = self._calculate_sightline_stats()
        debug_log(f"Sightline stats: {stats}", indent=1)
        
        debug_log("\n" + "=" * 50)
        debug_log("LEVEL GENERATION COMPLETE")
        debug_log(f"Total areas created: {len(self.areas)}")
        for name, area in self.areas.items():
            debug_log(f"  - {name}: pos=({area['x']}, {area['y']}) size={area['w']}x{area['h']}", indent=1)
        debug_log("=" * 50)
        
        return {
            "grid": self.grid,
            "areas": self.areas,
            "width": self.width,
            "height": self.height,
            "sightline_stats": stats
        }
    
    def _parse_location(self, location):
        """Convert location to coordinates. Accepts:
           - Dict: {"x": 0.0-1.0, "y": 0.0-1.0}
           - List: [x, y] where x,y are 0.0-1.0
           - String: "top-left", "center", etc. (legacy support)
        """
        debug_log(f"Parsing location: {location} (type: {type(location).__name__})", indent=2)
        
        # Handle numeric coordinates (dict or list)
        if isinstance(location, dict):
            fx = max(0.0, min(1.0, location.get("x", 0.5)))
            fy = max(0.0, min(1.0, location.get("y", 0.5)))
            result = int(fx * self.width), int(fy * self.height)
            debug_log(f"Dict format: ({fx}, {fy}) -> grid ({result[0]}, {result[1]})", indent=3)
            return result
        
        if isinstance(location, (list, tuple)) and len(location) >= 2:
            fx = max(0.0, min(1.0, location[0]))
            fy = max(0.0, min(1.0, location[1]))
            result = int(fx * self.width), int(fy * self.height)
            debug_log(f"List format: ({fx}, {fy}) -> grid ({result[0]}, {result[1]})", indent=3)
            return result
        
        # Legacy string support
        if isinstance(location, str):
            locations = {
                "top-left": (0.2, 0.2),
                "top-right": (0.8, 0.2),
                "bottom-left": (0.2, 0.8),
                "bottom-right": (0.8, 0.8),
                "center": (0.5, 0.5),
                "top": (0.5, 0.2),
                "bottom": (0.5, 0.8),
                "left": (0.2, 0.5),
                "right": (0.8, 0.5)
            }
            fx, fy = locations.get(location, (0.5, 0.5))
            result = int(fx * self.width), int(fy * self.height)
            debug_log(f"String format '{location}': ({fx}, {fy}) -> grid ({result[0]}, {result[1]})", indent=3)
            return result
        
        # Default to center
        debug_log(f"Unknown format, defaulting to center", indent=3)
        return self.width // 2, self.height // 2
    
    def _create_zone_with_spec(self, name, size, location, preference, cell_type, specified_shape=None):
        debug_log(f"Creating zone '{name}': size={size}, preference={preference}, cell_type={cell_type}", indent=2)
        
        target_x, target_y = self._parse_location(location) if location else (self.width // 2, self.height // 2)
        debug_log(f"Target position: ({target_x}, {target_y})", indent=3)
        
        size_variation = random.randint(-1, 1)
        original_size = size
        size = max(3, size + size_variation)
        debug_log(f"Size with variation: {original_size} + {size_variation} = {size}", indent=3)
        
        if preference == "edge":
            old_target = (target_x, target_y)
            # Only push to edge on axes that are already near an edge (within 30% of edge)
            edge_threshold = 0.3
            
            # Check if x is near left or right edge
            x_ratio = target_x / self.width
            if x_ratio < edge_threshold:
                target_x = size // 2 + 2  # push to left edge
                debug_log(f"X near left edge ({x_ratio:.2f}), pushing to left", indent=4)
            elif x_ratio > (1 - edge_threshold):
                target_x = self.width - size // 2 - 2  # push to right edge
                debug_log(f"X near right edge ({x_ratio:.2f}), pushing to right", indent=4)
            else:
                debug_log(f"X in center zone ({x_ratio:.2f}), keeping position", indent=4)
            
            # Check if y is near top or bottom edge
            y_ratio = target_y / self.height
            if y_ratio < edge_threshold:
                target_y = size // 2 + 2  # push to top edge
                debug_log(f"Y near top edge ({y_ratio:.2f}), pushing to top", indent=4)
            elif y_ratio > (1 - edge_threshold):
                target_y = self.height - size // 2 - 2  # push to bottom edge
                debug_log(f"Y near bottom edge ({y_ratio:.2f}), pushing to bottom", indent=4)
            else:
                debug_log(f"Y in center zone ({y_ratio:.2f}), keeping position", indent=4)
            
            debug_log(f"Edge preference adjusted: ({old_target[0]}, {old_target[1]}) -> ({target_x}, {target_y})", indent=3)
        
        if specified_shape and specified_shape in ["square", "rectangle", "L_shape", "T_shape", "plus", "organic"]:
            shape = specified_shape
            debug_log(f"Using specified shape: {shape}", indent=3)
        else:
            shapes = ["square", "rectangle", "L_shape", "T_shape", "plus", "organic"]
            shape = random.choice(shapes)
            debug_log(f"Random shape selected: {shape}", indent=3)
        
        for attempt in range(50):
            offset_x = random.randint(-5, 5) if attempt > 0 else random.randint(-2, 2)
            offset_y = random.randint(-5, 5) if attempt > 0 else random.randint(-2, 2)
            x = max(2, min(self.width - size - 2, target_x + offset_x - size // 2))
            y = max(2, min(self.height - size - 2, target_y + offset_y - size // 2))
            
            if attempt < 5 or attempt % 10 == 0:
                debug_log(f"Attempt {attempt+1}: trying position ({x}, {y}) with offset ({offset_x}, {offset_y})", indent=4)
            
            if self._can_place_shaped_zone(x, y, size, shape):
                cells = self._place_shaped_zone(x, y, size, shape, cell_type)
                if cells:
                    min_x = min(cx for cx, cy in cells)
                    max_x = max(cx for cx, cy in cells)
                    min_y = min(cy for cx, cy in cells)
                    max_y = max(cy for cx, cy in cells)
                    debug_log(f"Placed successfully on attempt {attempt+1}: bounds=({min_x},{min_y}) to ({max_x},{max_y}), {len(cells)} cells", indent=4)
                    return {
                        "x": min_x, "y": min_y, 
                        "w": max_x - min_x + 1, "h": max_y - min_y + 1, 
                        "name": name, "type": cell_type, "shape": shape
                    }
        
        debug_log(f"FAILED after 50 attempts", indent=4)
        return None
    
    def _get_shape_cells(self, x, y, size, shape):
        cells = []
        if shape == "square":
            for dy in range(size):
                for dx in range(size):
                    cells.append((x + dx, y + dy))
        elif shape == "rectangle":
            if random.choice([True, False]):
                w, h = size + random.randint(1, 3), max(3, size - 1)
            else:
                w, h = max(3, size - 1), size + random.randint(1, 3)
            for dy in range(h):
                for dx in range(w):
                    cells.append((x + dx, y + dy))
        elif shape == "L_shape":
            for dy in range(size):
                for dx in range(size // 2 + 1):
                    cells.append((x + dx, y + dy))
            for dx in range(size):
                for dy in range(size // 2 + 1):
                    cells.append((x + dx, y + dy))
        elif shape == "T_shape":
            for dx in range(size):
                for dy in range(size // 3 + 1):
                    cells.append((x + dx, y + dy))
            stem_start = size // 3
            for dy in range(stem_start, size):
                for dx in range(size // 3, size // 3 + size // 2 + 1):
                    cells.append((x + dx, y + dy))
        elif shape == "plus":
            mid = size // 2
            for dx in range(size):
                for dy in range(mid - 1, mid + 2):
                    cells.append((x + dx, y + dy))
            for dy in range(size):
                for dx in range(mid - 1, mid + 2):
                    cells.append((x + dx, y + dy))
        elif shape == "organic":
            added_cells = set()
            for dy in range(size):
                for dx in range(size):
                    added_cells.add((x + dx, y + dy))
            for _ in range(random.randint(2, 5)):
                mod_x, mod_y = x + random.randint(-2, size), y + random.randint(-2, size)
                block_size = random.choice([2, 2, 3])
                if random.random() < 0.5:
                    for dy in range(block_size):
                        for dx in range(block_size):
                            added_cells.add((mod_x + dx, mod_y + dy))
                else:
                    for dy in range(block_size):
                        for dx in range(block_size):
                            added_cells.discard((mod_x + dx, mod_y + dy))
            cells = list(added_cells)
        return list(set(cells))
    
    def _can_place_shaped_zone(self, x, y, size, shape):
        cells = self._get_shape_cells(x, y, size, shape)
        for cx, cy in cells:
            for dy in range(-1, 2):
                for dx in range(-1, 2):
                    nx, ny = cx + dx, cy + dy
                    if 0 <= nx < self.width and 0 <= ny < self.height:
                        if self.grid[ny][nx] != CellType.EMPTY:
                            return False
        return True
    
    def _place_shaped_zone(self, x, y, size, shape, cell_type):
        cells = self._get_shape_cells(x, y, size, shape)
        for cx, cy in cells:
            if 0 <= cx < self.width and 0 <= cy < self.height:
                self.grid[cy][cx] = cell_type
        return cells
    
    def _connect_areas(self, connectivity, sightline_control):
        style = connectivity.get("style", "3-lane")
        corridor_width = connectivity.get("max_chokepoint_width", 2)
        max_segment = sightline_control.get("max_consecutive_open", 8) if sightline_control.get("enabled", False) else 999
        
        debug_log(f"Connection style: {style}, corridor_width: {corridor_width}, max_segment: {max_segment}", indent=2)
        
        t_spawn, ct_spawn = self.areas.get("T_spawn"), self.areas.get("CT_spawn")
        sites = [v for k, v in self.areas.items() if k.startswith("site_")]
        mids = [v for k, v in self.areas.items() if k.startswith("mid")]
        
        debug_log(f"Areas to connect: T_spawn={t_spawn is not None}, CT_spawn={ct_spawn is not None}, sites={len(sites)}, mids={len(mids)}", indent=2)
        
        num_lanes = 3
        if "lane" in style.lower():
            try: num_lanes = int(style.split("-")[0])
            except: pass
        debug_log(f"Number of lanes: {num_lanes}", indent=2)
        
        if len(mids) > 1:
            debug_log(f"Connecting {len(mids)} mid areas to each other", indent=2)
            self._connect_mid_network(mids, corridor_width, max_segment)
        
        connection_count = 0
        
        if num_lanes == 2:
            if t_spawn and ct_spawn:
                for site in sites:
                    debug_log(f"2-lane: Connecting T_spawn -> site_{site['name']}", indent=3)
                    self._create_path_with_corners(t_spawn, site, corridor_width, max_segment)
                    connection_count += 1
                    debug_log(f"2-lane: Connecting site_{site['name']} -> CT_spawn", indent=3)
                    self._create_path_with_corners(site, ct_spawn, corridor_width, max_segment)
                    connection_count += 1
        elif num_lanes == 3:
            if t_spawn and ct_spawn:
                for site in sites:
                    debug_log(f"3-lane: Connecting T_spawn -> site_{site['name']}", indent=3)
                    self._create_path_with_corners(t_spawn, site, corridor_width, max_segment)
                    connection_count += 1
                    debug_log(f"3-lane: Connecting CT_spawn -> site_{site['name']}", indent=3)
                    self._create_path_with_corners(ct_spawn, site, corridor_width, max_segment)
                    connection_count += 1
            if mids:
                if t_spawn:
                    closest = self._find_closest_area(t_spawn, mids)
                    debug_log(f"3-lane: Connecting T_spawn -> closest mid ({closest['name']})", indent=3)
                    self._create_path_with_corners(t_spawn, closest, corridor_width, max_segment)
                    connection_count += 1
                if ct_spawn:
                    closest = self._find_closest_area(ct_spawn, mids)
                    debug_log(f"3-lane: Connecting CT_spawn -> closest mid ({closest['name']})", indent=3)
                    self._create_path_with_corners(ct_spawn, closest, corridor_width, max_segment)
                    connection_count += 1
                for site in sites:
                    closest_mids = self._find_n_closest_areas(site, mids, n=min(2, len(mids)))
                    for mid in closest_mids:
                        debug_log(f"3-lane: Connecting site_{site['name']} -> mid ({mid['name']})", indent=3)
                        self._create_path_with_corners(site, mid, corridor_width, max_segment)
                        connection_count += 1
            if len(sites) >= 2 and random.random() < 0.3:
                debug_log(f"3-lane: Random extra connection between sites", indent=3)
                self._create_path_with_corners(sites[0], sites[1], corridor_width, max_segment)
                connection_count += 1
        elif num_lanes >= 4:
            if t_spawn:
                for site in sites:
                    debug_log(f"4-lane: Connecting T_spawn -> site_{site['name']}", indent=3)
                    self._create_path_with_corners(t_spawn, site, corridor_width, max_segment)
                    connection_count += 1
                if mids:
                    for mid in self._find_n_closest_areas(t_spawn, mids, n=min(2, len(mids))):
                        debug_log(f"4-lane: Connecting T_spawn -> mid ({mid['name']})", indent=3)
                        self._create_path_with_corners(t_spawn, mid, corridor_width, max_segment)
                        connection_count += 1
            if ct_spawn:
                for site in sites:
                    debug_log(f"4-lane: Connecting CT_spawn -> site_{site['name']}", indent=3)
                    self._create_path_with_corners(ct_spawn, site, corridor_width, max_segment)
                    connection_count += 1
                if mids:
                    for mid in self._find_n_closest_areas(ct_spawn, mids, n=min(2, len(mids))):
                        debug_log(f"4-lane: Connecting CT_spawn -> mid ({mid['name']})", indent=3)
                        self._create_path_with_corners(ct_spawn, mid, corridor_width, max_segment)
                        connection_count += 1
            for i in range(len(sites)):
                for j in range(i + 1, len(sites)):
                    debug_log(f"4-lane: Connecting site_{sites[i]['name']} -> site_{sites[j]['name']}", indent=3)
                    self._create_path_with_corners(sites[i], sites[j], corridor_width, max_segment)
                    connection_count += 1
            if mids:
                for site in sites:
                    for mid in self._find_n_closest_areas(site, mids, n=min(2, len(mids))):
                        debug_log(f"4-lane: Connecting site_{site['name']} -> mid ({mid['name']})", indent=3)
                        self._create_path_with_corners(site, mid, corridor_width, max_segment)
                        connection_count += 1
        
        debug_log(f"Total connections created: {connection_count}", indent=2)
    
    def _connect_mid_network(self, mids, width, max_segment):
        if len(mids) <= 1: return
        connection_count = 0
        for i, mid in enumerate(mids):
            other_mids = [m for j, m in enumerate(mids) if j != i]
            for close_mid in self._find_n_closest_areas(mid, other_mids, n=min(2, len(other_mids))):
                if mids.index(mid) < mids.index(close_mid):
                    debug_log(f"Mid network: Connecting {mid['name']} -> {close_mid['name']}", indent=3)
                    self._create_path_with_corners(mid, close_mid, width, max_segment)
                    connection_count += 1
        debug_log(f"Mid network connections: {connection_count}", indent=3)
    
    def _find_closest_area(self, from_area, target_areas):
        if not target_areas: return None
        from_x, from_y = from_area["x"] + from_area["w"] // 2, from_area["y"] + from_area["h"] // 2
        closest = min(target_areas, key=lambda a: abs(a["x"] + a["w"]//2 - from_x) + abs(a["y"] + a["h"]//2 - from_y))
        return closest
    
    def _find_n_closest_areas(self, from_area, target_areas, n=2):
        if not target_areas: return []
        from_x, from_y = from_area["x"] + from_area["w"] // 2, from_area["y"] + from_area["h"] // 2
        distances = [(abs(a["x"] + a["w"]//2 - from_x) + abs(a["y"] + a["h"]//2 - from_y), a) for a in target_areas]
        distances.sort(key=lambda x: x[0])
        return [a for _, a in distances[:n]]
        
    def _create_path_with_corners(self, area1, area2, width, max_segment_length):
        x1 = max(1, min(self.width - 2, area1["x"] + area1["w"] // 2 + random.randint(-1, 1)))
        y1 = max(1, min(self.height - 2, area1["y"] + area1["h"] // 2 + random.randint(-1, 1)))
        x2 = max(1, min(self.width - 2, area2["x"] + area2["w"] // 2 + random.randint(-1, 1)))
        y2 = max(1, min(self.height - 2, area2["y"] + area2["h"] // 2 + random.randint(-1, 1)))
        
        path_length = abs(x2 - x1) + abs(y2 - y1)
        debug_log(f"Path: ({x1},{y1}) -> ({x2},{y2}), length={path_length}", indent=4)
        
        if path_length > 15: varied_width = max(2, width + random.randint(-1, 1))
        elif path_length > 8: varied_width = max(2 if width == 1 else 1, width + random.randint(-1, 1))
        else: varied_width = max(1, width + random.randint(-1, 1))
        
        debug_log(f"Corridor width: {varied_width} (base: {width})", indent=4)
        
        if max_segment_length >= 999:
            self._draw_segment(x1, y1, x2, y2, varied_width)
        else:
            self._draw_path_with_turns(x1, y1, x2, y2, varied_width, max_segment_length)
    
    def _draw_path_with_turns(self, x1, y1, x2, y2, width, max_segment):
        current_x, current_y, target_x, target_y = x1, y1, x2, y2
        is_mainly_horizontal = abs(target_x - current_x) > abs(target_y - current_y)
        detour_amount = max(2, max_segment // 3 + random.randint(-1, 2))
        going_right = random.choice([True, False])
        
        debug_log(f"Path with turns: horizontal={is_mainly_horizontal}, detour={detour_amount}", indent=5)
        
        for _ in range(20):
            if abs(current_x - target_x) <= 1 and abs(current_y - target_y) <= 1: break
            segment_length = max_segment + random.randint(-2, 2)
            
            if is_mainly_horizontal:
                for _ in range(min(segment_length, abs(target_x - current_x))):
                    if current_x == target_x: break
                    next_x = current_x + (1 if current_x < target_x else -1)
                    eff_w = self._get_safe_width(next_x, current_y, width, True)
                    for w in range(eff_w):
                        ny = current_y + w - eff_w // 2
                        if 0 <= ny < self.height and 0 <= next_x < self.width and self.grid[ny][next_x] == CellType.EMPTY:
                            self.grid[ny][next_x] = CellType.CORRIDOR
                    current_x = next_x
                
                if abs(current_x - target_x) > 1:
                    detour_y = max(1, min(self.height - 2, current_y + (detour_amount if going_right else -detour_amount) + random.randint(-1, 1)))
                    while current_y != detour_y:
                        next_y = current_y + (1 if current_y < detour_y else -1)
                        eff_w = self._get_safe_width(current_x, next_y, width, False)
                        for w in range(eff_w):
                            nx = current_x + w - eff_w // 2
                            if 0 <= next_y < self.height and 0 <= nx < self.width and self.grid[next_y][nx] == CellType.EMPTY:
                                self.grid[next_y][nx] = CellType.CORRIDOR
                        current_y = next_y
                    if random.random() > 0.2: going_right = not going_right
            else:
                for _ in range(min(segment_length, abs(target_y - current_y))):
                    if current_y == target_y: break
                    next_y = current_y + (1 if current_y < target_y else -1)
                    eff_w = self._get_safe_width(current_x, next_y, width, False)
                    for w in range(eff_w):
                        nx = current_x + w - eff_w // 2
                        if 0 <= next_y < self.height and 0 <= nx < self.width and self.grid[next_y][nx] == CellType.EMPTY:
                            self.grid[next_y][nx] = CellType.CORRIDOR
                    current_y = next_y
                
                if abs(current_y - target_y) > 1:
                    detour_x = max(1, min(self.width - 2, current_x + (detour_amount if going_right else -detour_amount) + random.randint(-1, 1)))
                    while current_x != detour_x:
                        next_x = current_x + (1 if current_x < detour_x else -1)
                        eff_w = self._get_safe_width(next_x, current_y, width, True)
                        for w in range(eff_w):
                            ny = current_y + w - eff_w // 2
                            if 0 <= ny < self.height and 0 <= next_x < self.width and self.grid[ny][next_x] == CellType.EMPTY:
                                self.grid[ny][next_x] = CellType.CORRIDOR
                        current_x = next_x
                    if random.random() > 0.2: going_right = not going_right
        
        while current_x != target_x:
            current_x += 1 if current_x < target_x else -1
            eff_w = self._get_safe_width(current_x, current_y, width, True)
            for w in range(eff_w):
                ny = current_y + w - eff_w // 2
                if 0 <= ny < self.height and 0 <= current_x < self.width and self.grid[ny][current_x] == CellType.EMPTY:
                    self.grid[ny][current_x] = CellType.CORRIDOR
        while current_y != target_y:
            current_y += 1 if current_y < target_y else -1
            eff_w = self._get_safe_width(current_x, current_y, width, False)
            for w in range(eff_w):
                nx = current_x + w - eff_w // 2
                if 0 <= current_y < self.height and 0 <= nx < self.width and self.grid[current_y][nx] == CellType.EMPTY:
                    self.grid[current_y][nx] = CellType.CORRIDOR
    
    def _get_safe_width(self, x, y, desired_width, is_horizontal):
        open_count = 0
        for d in range(-3, 4):
            if is_horizontal:
                ny = y + d
                if 0 <= ny < self.height and 0 <= x < self.width and self._is_open_cell(self.grid[ny][x]):
                    open_count += 1
            else:
                nx = x + d
                if 0 <= y < self.height and 0 <= nx < self.width and self._is_open_cell(self.grid[y][nx]):
                    open_count += 1
        if open_count > 4: return 1
        elif open_count > 2: return max(1, desired_width - 1)
        return desired_width
    
    def _draw_segment(self, x1, y1, x2, y2, width):
        for x in range(min(x1, x2), max(x1, x2) + 1):
            for w in range(width):
                ny = y1 + w - width // 2
                if 0 <= ny < self.height and 0 <= x < self.width and self.grid[ny][x] == CellType.EMPTY:
                    self.grid[ny][x] = CellType.CORRIDOR
        for y in range(min(y1, y2), max(y1, y2) + 1):
            for w in range(width):
                nx = x2 + w - width // 2
                if 0 <= y < self.height and 0 <= nx < self.width and self.grid[y][nx] == CellType.EMPTY:
                    self.grid[y][nx] = CellType.CORRIDOR
    
    def _is_open_cell(self, cell_type):
        return cell_type in [CellType.CORRIDOR, CellType.BOMBSITE, CellType.MID_AREA, CellType.SPAWN_T, CellType.SPAWN_CT, CellType.CONNECTOR]
    
    def _calculate_sightline_stats(self):
        max_h = max_v = 0
        for y in range(self.height):
            c = 0
            for x in range(self.width):
                if self._is_open_cell(self.grid[y][x]): c += 1; max_h = max(max_h, c)
                else: c = 0
        for x in range(self.width):
            c = 0
            for y in range(self.height):
                if self._is_open_cell(self.grid[y][x]): c += 1; max_v = max(max_v, c)
                else: c = 0
        return {"max_horizontal_sightline": max_h, "max_vertical_sightline": max_v, "estimated_max_diagonal": int(max(max_h, max_v) * 1.4)}
    
    def _place_cover_objects(self, cover_spec):
        density_name = cover_spec.get("density", "medium")
        chance = {"low": 0.08, "medium": 0.12, "high": 0.18}.get(density_name, 0.12)
        debug_log(f"Cover density: {density_name} ({chance*100:.0f}% chance per corridor cell)", indent=2)
        
        cover_count = 0
        corridor_count = 0
        for y in range(self.height):
            for x in range(self.width):
                if self.grid[y][x] == CellType.CORRIDOR:
                    corridor_count += 1
                    if random.random() < chance and self._can_place_cover(x, y):
                        self.grid[y][x] = CellType.COVER
                        cover_count += 1
        
        debug_log(f"Cover objects placed: {cover_count} / {corridor_count} corridor cells", indent=2)
    
    def _can_place_cover(self, x, y):
        wall_neighbors = [(x+dx, y+dy) for dy in [-1,0,1] for dx in [-1,0,1] if not (dx==0 and dy==0) and 0<=x+dx<self.width and 0<=y+dy<self.height and not self._is_open_cell(self.grid[y+dy][x+dx])]
        return len(wall_neighbors) <= 1 or self._walls_are_connected(wall_neighbors)
    
    def _walls_are_connected(self, wall_cells):
        if len(wall_cells) <= 1: return True
        visited = {wall_cells[0]}
        queue = [wall_cells[0]]
        while queue:
            cx, cy = queue.pop(0)
            for dy in [-1,0,1]:
                for dx in [-1,0,1]:
                    if (dx or dy) and (cx+dx, cy+dy) in wall_cells and (cx+dx, cy+dy) not in visited:
                        visited.add((cx+dx, cy+dy)); queue.append((cx+dx, cy+dy))
        return len(visited) == len(wall_cells)

class SolverGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("CS2 Level Generator - Numeric Coordinates (DEBUG)")
        self.root.geometry("1400x850")
        self.grid_width = self.grid_height = 40
        self.generator = LevelGenerator(self.grid_width, self.grid_height)
        self.current_result = self.current_spec = None
        self.auto_export = tk.BooleanVar(value=False)
        self.export_folder = tk.StringVar(value=r"D:\_School\BUAS\Level builders\CS2\JSON to VMAP\JSON layouts")
        self.create_widgets()
        self.load_example_spec()
        
    def create_widgets(self):
        main_container = tk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        main_container.pack(fill=tk.BOTH, expand=True)
        
        left_panel = tk.Frame(main_container, width=500)
        main_container.add(left_panel)
        
        tk.Label(left_panel, text="CS2 Level Generator (DEBUG)", font=("Arial", 16, "bold")).pack(pady=10)
        
        # Debug toggle
        self.debug_var = tk.BooleanVar(value=DEBUG)
        debug_frame = tk.Frame(left_panel)
        debug_frame.pack(pady=5)
        tk.Checkbutton(debug_frame, text="Enable Debug Output (console)", variable=self.debug_var, command=self.toggle_debug).pack()
        
        json_frame = tk.LabelFrame(left_panel, text="Level Specification (JSON)", padx=10, pady=10)
        json_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        text_container = tk.Frame(json_frame)
        text_container.pack(fill=tk.BOTH, expand=True)
        scrollbar = tk.Scrollbar(text_container)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.json_text = tk.Text(text_container, height=22, width=50, font=("Courier", 9), yscrollcommand=scrollbar.set)
        self.json_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.json_text.yview)
        
        button_frame = tk.Frame(left_panel)
        button_frame.pack(pady=10)
        tk.Button(button_frame, text="🎲 Generate Level", command=self.generate_from_json, bg="#4CAF50", fg="white", font=("Arial", 11, "bold"), padx=15, pady=8).grid(row=0, column=0, padx=5, pady=3)
        tk.Button(button_frame, text="📂 Load JSON", command=self.load_json_file, bg="#2196F3", fg="white", font=("Arial", 11, "bold"), padx=15, pady=8).grid(row=0, column=1, padx=5, pady=3)
        tk.Button(button_frame, text="💾 Save JSON", command=self.save_json_file, bg="#FF9800", fg="white", font=("Arial", 11, "bold"), padx=15, pady=8).grid(row=1, column=0, padx=5, pady=3)
        tk.Button(button_frame, text="📤 Export for VMAP", command=self.export_for_vmap, bg="#9C27B0", fg="white", font=("Arial", 11, "bold"), padx=15, pady=8).grid(row=1, column=1, padx=5, pady=3)
        tk.Button(button_frame, text="📋 Load Example", command=self.load_example_spec, bg="#607D8B", fg="white", font=("Arial", 11, "bold"), padx=15, pady=8).grid(row=2, column=0, columnspan=2, padx=5, pady=3)
        
        export_frame = tk.LabelFrame(left_panel, text="Auto-Export Settings", padx=10, pady=5)
        export_frame.pack(fill=tk.X, padx=10, pady=5)
        tk.Checkbutton(export_frame, text="Auto-export for VMAP after generation", variable=self.auto_export).pack(anchor=tk.W)
        folder_frame = tk.Frame(export_frame)
        folder_frame.pack(fill=tk.X, pady=5)
        tk.Label(folder_frame, text="Export folder:").pack(side=tk.LEFT)
        tk.Entry(folder_frame, textvariable=self.export_folder, width=35).pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        tk.Button(folder_frame, text="Browse", command=self.browse_export_folder).pack(side=tk.LEFT)
        tk.Button(export_frame, text="⚡ Quick Export to Folder", command=self.quick_export, bg="#E91E63", fg="white", font=("Arial", 10, "bold"), padx=10, pady=5).pack(pady=5)
        
        self.status_var = tk.StringVar(value="Ready - Debug output enabled in console")
        tk.Label(left_panel, textvariable=self.status_var, font=("Arial", 9), fg="blue", wraplength=450).pack(pady=5)
        
        right_panel = tk.Frame(main_container)
        main_container.add(right_panel)
        tk.Label(right_panel, text="Generated Level Preview", font=("Arial", 14, "bold")).pack(pady=10)
        self.viz_canvas = tk.Canvas(right_panel, bg="white", width=700, height=700)
        self.viz_canvas.pack(padx=10, pady=10)
        
        legend_frame = tk.Frame(right_panel)
        legend_frame.pack(pady=10)
        for i, (name, color) in enumerate([("T Spawn", "#FF6B6B"), ("CT Spawn", "#4ECDC4"), ("Bomb Sites", "#FFD93D"), ("Mid", "#A8DADC"), ("Corridor", "#C0C0C0"), ("Cover", "#8B4513")]):
            tk.Label(legend_frame, text="■ ", fg=color, font=("Arial", 14)).grid(row=i//3, column=(i%3)*2, padx=2)
            tk.Label(legend_frame, text=name, font=("Arial", 9)).grid(row=i//3, column=(i%3)*2+1, padx=5)
        
        stats_frame = tk.LabelFrame(right_panel, text="Sightline Statistics", padx=10, pady=5)
        stats_frame.pack(pady=10, fill=tk.X, padx=10)
        self.stats_text = tk.Label(stats_frame, text="Generate a level to see stats", font=("Courier", 9), justify=tk.LEFT, fg="gray")
        self.stats_text.pack()
    
    def toggle_debug(self):
        global DEBUG
        DEBUG = self.debug_var.get()
        status = "enabled" if DEBUG else "disabled"
        self.status_var.set(f"Debug output {status}")
        print(f"[DEBUG] Debug mode {status}")
    
    def load_example_spec(self):
        example = {
            "map_size": {"width": 40, "height": 40},
            "description": "Map using numeric x,y coordinates (0-1 range)",
            "spawn_zones": [
                {"team": "T", "size": "medium", "location": {"x": 0.15, "y": 0.85}, "position_preference": "edge", "shape": "L_shape"},
                {"team": "CT", "size": "medium", "location": {"x": 0.85, "y": 0.15}, "position_preference": "edge", "shape": "T_shape"}
            ],
            "bomb_sites": [
                {"id": "A", "size": "large", "location": {"x": 0.2, "y": 0.2}, "shape": "organic"},
                {"id": "B", "size": "medium", "location": {"x": 0.8, "y": 0.8}, "shape": "plus"}
            ],
            "areas": [
                {"type": "mid", "size": "medium", "location": {"x": 0.5, "y": 0.5}},
                {"type": "mid", "size": "small", "location": {"x": 0.25, "y": 0.5}},
                {"type": "mid", "size": "small", "location": {"x": 0.75, "y": 0.5}}
            ],
            "connectivity": {"style": "3-lane", "max_chokepoint_width": 2},
            "sightline_control": {"enabled": True, "max_consecutive_open": 6},
            "cover_objects": {"enabled": True, "density": "medium"}
        }
        self.json_text.delete("1.0", tk.END)
        self.json_text.insert("1.0", json.dumps(example, indent=2))
        self.status_var.set("Example loaded - locations use {\"x\": 0-1, \"y\": 0-1} format")
    
    def generate_from_json(self):
        try:
            print("\n" + "=" * 60)
            print("GENERATE BUTTON PRESSED")
            print("=" * 60)
            
            level_spec = json.loads(self.json_text.get("1.0", tk.END))
            self.current_spec = level_spec
            
            debug_log(f"Loaded JSON specification:")
            debug_log(f"  Description: {level_spec.get('description', 'N/A')}")
            debug_log(f"  Map size: {level_spec.get('map_size', {})}")
            
            if "map_size" in level_spec:
                self.grid_width = level_spec["map_size"].get("width", 40)
                self.grid_height = level_spec["map_size"].get("height", 40)
            
            self.generator = LevelGenerator(self.grid_width, self.grid_height)
            self.status_var.set("Generating level... (check console for debug output)")
            self.root.update()
            
            self.current_result = self.generator.generate_from_json(level_spec)
            self.visualize_grid(self.current_result["grid"])
            
            if self.current_result.get("sightline_stats"):
                s = self.current_result["sightline_stats"]
                self.stats_text.config(text=f"Max Horizontal: {s['max_horizontal_sightline']} cells\nMax Vertical: {s['max_vertical_sightline']} cells\nEst. Max Diagonal: {s['estimated_max_diagonal']} cells", fg="black")
            
            self.status_var.set(f"✓ Generated: {level_spec.get('description', 'No description')}")
            if self.auto_export.get(): self.export_for_vmap(silent=True)
            
        except json.JSONDecodeError as e:
            print(f"[ERROR] JSON parsing failed: {e}")
            messagebox.showerror("JSON Error", f"Invalid JSON:\n{str(e)}")
        except Exception as e:
            print(f"[ERROR] Generation failed: {e}")
            import traceback
            traceback.print_exc()
            messagebox.showerror("Generation Error", f"Failed:\n{str(e)}")
    
    def visualize_grid(self, grid):
        self.viz_canvas.delete("all")
        cell_size = min(700 / self.grid_width, 700 / self.grid_height)
        colors = {CellType.EMPTY: "#FFFFFF", CellType.ROOM: "#808080", CellType.CORRIDOR: "#C0C0C0", CellType.SPAWN_T: "#FF6B6B", CellType.SPAWN_CT: "#4ECDC4", CellType.BOMBSITE: "#FFD93D", CellType.MID_AREA: "#A8DADC", CellType.CHOKEPOINT: "#F97316", CellType.CONNECTOR: "#D0D0D0", CellType.COVER: "#8B4513"}
        site_colors = {"site_A": "#FFD93D", "site_B": "#6BCF7F", "site_C": "#A78BFA"}
        
        for y in range(self.grid_height):
            for x in range(self.grid_width):
                color = colors.get(grid[y][x], "#FFFFFF")
                if grid[y][x] == CellType.BOMBSITE:
                    for sn, area in self.current_result.get("areas", {}).items():
                        if sn.startswith("site_") and area["x"] <= x < area["x"]+area["w"] and area["y"] <= y < area["y"]+area["h"]:
                            color = site_colors.get(sn, color); break
                self.viz_canvas.create_rectangle(x*cell_size, y*cell_size, (x+1)*cell_size, (y+1)*cell_size, fill=color, outline="#EEEEEE")
        
        for name, area in self.current_result.get("areas", {}).items():
            cx, cy = (area["x"] + area["w"]/2) * cell_size, (area["y"] + area["h"]/2) * cell_size
            if name.startswith("site_"): label = f"SITE {name.split('_')[1].upper()}"
            elif name.startswith("mid_"): label = f"MID {int(name.split('_')[1])+1}"
            else: label = name.upper().replace("_", " ")
            self.viz_canvas.create_text(cx, cy, text=label, font=("Arial", 10, "bold"), fill="black")
    
    def load_json_file(self):
        fn = filedialog.askopenfilename(title="Select JSON", filetypes=[("JSON", "*.json"), ("All", "*.*")])
        if fn:
            try:
                with open(fn) as f: self.json_text.delete("1.0", tk.END); self.json_text.insert("1.0", f.read())
                self.status_var.set(f"Loaded: {fn}")
                debug_log(f"Loaded file: {fn}")
            except Exception as e: messagebox.showerror("Error", str(e))
    
    def save_json_file(self):
        fn = filedialog.asksaveasfilename(title="Save JSON", defaultextension=".json", filetypes=[("JSON", "*.json")])
        if fn:
            try:
                with open(fn, 'w') as f: f.write(self.json_text.get("1.0", tk.END))
                self.status_var.set(f"Saved: {fn}")
                debug_log(f"Saved file: {fn}")
            except Exception as e: messagebox.showerror("Error", str(e))
    
    def browse_export_folder(self):
        folder = filedialog.askdirectory(title="Select Export Folder", initialdir=self.export_folder.get())
        if folder: self.export_folder.set(folder)
    
    def quick_export(self):
        """Quick export to configured folder without file dialog"""
        if not self.current_result:
            messagebox.showwarning("Warning", "Generate a level first!")
            return
        
        import os
        from datetime import datetime
        
        # Build output in correct format (same as export_for_vmap)
        output = {
            "grid": [[int(c) for c in row] for row in self.current_result["grid"]],
            "areas": {n: {k:v for k,v in a.items() if k != "type"} for n,a in self.current_result["areas"].items()},
            "width": self.current_result["width"],
            "height": self.current_result["height"],
            "sightline_stats": self.current_result.get("sightline_stats"),
            "metadata": {
                "specification": self.current_spec,
                "cell_types": {
                    "0": "EMPTY", "1": "ROOM", "2": "CORRIDOR",
                    "3": "SPAWN_T", "4": "SPAWN_CT", "5": "BOMBSITE",
                    "6": "MID_AREA", "7": "CHOKEPOINT", "8": "CONNECTOR", "9": "COVER"
                }
            }
        }
        
        folder = self.export_folder.get()
        if not os.path.exists(folder):
            try:
                os.makedirs(folder)
                debug_log(f"Created export folder: {folder}")
            except Exception as e:
                messagebox.showerror("Error", f"Could not create folder: {e}")
                return
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = os.path.join(folder, f"level_{timestamp}.json")
        
        try:
            with open(filename, 'w') as f:
                json.dump(output, f, indent=2)
            self.status_var.set(f"✓ Quick exported to {filename}")
            debug_log(f"Quick export completed: {filename}")
            debug_log(f"  Grid size: {len(output['grid'])}x{len(output['grid'][0])}")
            debug_log(f"  Areas: {list(output['areas'].keys())}")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to export: {e}")
            debug_log(f"Quick export FAILED: {e}")
    
    def export_for_vmap(self, silent=False):
        if not self.current_result:
            if not silent: messagebox.showwarning("Warning", "Generate a level first!")
            return
        output = {
            "grid": [[int(c) for c in row] for row in self.current_result["grid"]],
            "areas": {n: {k:v for k,v in a.items() if k != "type"} for n,a in self.current_result["areas"].items()},
            "width": self.current_result["width"], "height": self.current_result["height"],
            "sightline_stats": self.current_result.get("sightline_stats"),
            "metadata": {"specification": self.current_spec, "cell_types": {"0":"EMPTY","1":"ROOM","2":"CORRIDOR","3":"SPAWN_T","4":"SPAWN_CT","5":"BOMBSITE","6":"MID_AREA","7":"CHOKEPOINT","8":"CONNECTOR","9":"COVER"}}
        }
        if silent:
            import os; from datetime import datetime
            folder = self.export_folder.get()
            if not os.path.exists(folder):
                try: os.makedirs(folder)
                except: self.status_var.set("Error: Could not create export folder"); return
            fn = os.path.join(folder, f"level_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
            try:
                with open(fn, 'w') as f: json.dump(output, f, indent=2)
                self.status_var.set(f"✓ Generated and auto-exported to {fn}")
                debug_log(f"Auto-exported to: {fn}")
            except Exception as e: self.status_var.set(f"Error: {e}")
        else:
            fn = filedialog.asksaveasfilename(title="Export for VMAP", defaultextension=".json", initialdir=self.export_folder.get(), initialfile="level_layout.json", filetypes=[("JSON", "*.json")])
            if fn:
                try:
                    with open(fn, 'w') as f: json.dump(output, f, indent=2)
                    messagebox.showinfo("Success", f"Exported to {fn}")
                    debug_log(f"Exported to: {fn}")
                except Exception as e: messagebox.showerror("Error", str(e))

if __name__ == "__main__":
    print("=" * 60)
    print("CS2 LEVEL GENERATOR - DEBUG MODE")
    print("=" * 60)
    print("Debug output will appear in this console window.")
    print("Toggle debug with the checkbox in the GUI.")
    print("=" * 60 + "\n")
    
    root = tk.Tk()
    app = SolverGUI(root)
    root.mainloop()