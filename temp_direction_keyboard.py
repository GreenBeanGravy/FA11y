# This is the replacement code for DirectionConfigurator keyboard handling
# Starting from "# Handle keyboard input" and replacing the entire section

replacement = """                # Keep window responsive
                cv2.waitKey(1)

                # Handle keyboard input using pynput state
                from pynput import keyboard
                current_keys = self.keys_pressed.copy()

                # Process newly pressed keys (avoid repeats)
                new_keys = current_keys - last_keys

                # Determine step size based on Shift modifier
                if self.use_minimap:
                    step_size = 1 if self.shift_pressed else 5
                else:
                    step_size = 1 if self.shift_pressed else 10

                # Character keys (one-time actions)
                if keyboard.Key.esc in current_keys:
                    break
                elif 't' in new_keys:
                    self.use_minimap = not self.use_minimap
                    mode = "MINIMAP" if self.use_minimap else "MAIN SCREEN"
                    print(f"[Dev Mode] Mode: {mode}")
                elif '1' in new_keys:
                    self.scale_factor = min(10, self.scale_factor + 1)
                    print(f"[Dev Mode] Scale factor: {self.scale_factor}x")
                elif '2' in new_keys:
                    self.scale_factor = max(1, self.scale_factor - 1)
                    print(f"[Dev Mode] Scale factor: {self.scale_factor}x")
                elif 'h' in new_keys:
                    if self.use_minimap:
                        self.minimap_width = max(10, self.minimap_width - 5)
                        print(f"[Dev Mode] Minimap size: {self.minimap_width}x{self.minimap_height}")
                    else:
                        self.main_width = max(50, self.main_width - 10)
                        print(f"[Dev Mode] Main size: {self.main_width}x{self.main_height}")
                elif 'l' in new_keys:
                    if self.use_minimap:
                        self.minimap_width += 5
                        print(f"[Dev Mode] Minimap size: {self.minimap_width}x{self.minimap_height}")
                    else:
                        self.main_width += 10
                        print(f"[Dev Mode] Main size: {self.main_width}x{self.main_height}")
                elif 'j' in new_keys:
                    if self.use_minimap:
                        self.minimap_height = max(10, self.minimap_height - 5)
                        print(f"[Dev Mode] Minimap size: {self.minimap_width}x{self.minimap_height}")
                    else:
                        self.main_height = max(50, self.main_height - 10)
                        print(f"[Dev Mode] Main size: {self.main_width}x{self.main_height}")
                elif 'k' in new_keys:
                    if self.use_minimap:
                        self.minimap_height += 5
                        print(f"[Dev Mode] Minimap size: {self.minimap_width}x{self.minimap_height}")
                    else:
                        self.main_height += 10
                        print(f"[Dev Mode] Main size: {self.main_width}x{self.main_height}")
                elif 'w' in new_keys:
                    self.white_threshold_min = min(255, self.white_threshold_min + 1)
                    print(f"[Dev Mode] White threshold: {self.white_threshold_min}-{self.white_threshold_max}")
                elif 's' in new_keys:
                    self.white_threshold_min = max(0, self.white_threshold_min - 1)
                    print(f"[Dev Mode] White threshold: {self.white_threshold_min}-{self.white_threshold_max}")
                elif 'e' in new_keys:
                    self.white_threshold_max = min(255, self.white_threshold_max + 1)
                    print(f"[Dev Mode] White threshold: {self.white_threshold_min}-{self.white_threshold_max}")
                elif 'd' in new_keys:
                    self.white_threshold_max = max(0, self.white_threshold_max - 1)
                    print(f"[Dev Mode] White threshold: {self.white_threshold_min}-{self.white_threshold_max}")
                elif 'a' in new_keys:
                    if self.use_minimap:
                        self.min_area += 10
                        print(f"[Dev Mode] Min area: {self.min_area}")
                    else:
                        self.main_min_area += 10
                        print(f"[Dev Mode] Min area: {self.main_min_area}")
                elif 'z' in new_keys:
                    if self.use_minimap:
                        self.min_area = max(0, self.min_area - 10)
                        print(f"[Dev Mode] Min area: {self.min_area}")
                    else:
                        self.main_min_area = max(0, self.main_min_area - 10)
                        print(f"[Dev Mode] Min area: {self.main_min_area}")
                elif 'q' in new_keys:
                    if self.use_minimap:
                        self.max_area += 10
                        print(f"[Dev Mode] Max area: {self.max_area}")
                    else:
                        self.main_max_area += 10
                        print(f"[Dev Mode] Max area: {self.main_max_area}")
                elif 'x' in new_keys:
                    if self.use_minimap:
                        self.max_area = max(0, self.max_area - 10)
                        print(f"[Dev Mode] Max area: {self.max_area}")
                    else:
                        self.main_max_area = max(0, self.main_max_area - 10)
                        print(f"[Dev Mode] Max area: {self.main_max_area}")
                elif 'v' in new_keys:
                    self.view_mode = (self.view_mode + 1) % 5
                    modes = ["All", "Original", "Upscaled", "Mask", "Contours"]
                    print(f"[Dev Mode] View mode: {modes[self.view_mode]}")
                elif 'p' in new_keys:
                    self.print_current_config()

                # Arrow keys (allow continuous movement)
                if keyboard.Key.up in current_keys:
                    if self.use_minimap:
                        self.minimap_y = max(0, self.minimap_y - step_size)
                        print(f"[Dev Mode] Minimap region moved to ({self.minimap_x}, {self.minimap_y})")
                    else:
                        self.main_y = max(0, self.main_y - step_size)
                        print(f"[Dev Mode] Main region moved to ({self.main_x}, {self.main_y})")
                if keyboard.Key.down in current_keys:
                    if self.use_minimap:
                        self.minimap_y += step_size
                        print(f"[Dev Mode] Minimap region moved to ({self.minimap_x}, {self.minimap_y})")
                    else:
                        self.main_y += step_size
                        print(f"[Dev Mode] Main region moved to ({self.main_x}, {self.main_y})")
                if keyboard.Key.left in current_keys:
                    if self.use_minimap:
                        self.minimap_x = max(0, self.minimap_x - step_size)
                        print(f"[Dev Mode] Minimap region moved to ({self.minimap_x}, {self.minimap_y})")
                    else:
                        self.main_x = max(0, self.main_x - step_size)
                        print(f"[Dev Mode] Main region moved to ({self.main_x}, {self.main_y})")
                if keyboard.Key.right in current_keys:
                    if self.use_minimap:
                        self.minimap_x += step_size
                        print(f"[Dev Mode] Minimap region moved to ({self.minimap_x}, {self.minimap_y})")
                    else:
                        self.main_x += step_size
                        print(f"[Dev Mode] Main region moved to ({self.main_x}, {self.main_y})")

                last_keys = current_keys"""

print(replacement)
