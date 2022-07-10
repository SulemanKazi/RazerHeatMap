import argparse
import json
import logging
import socket
import time

import matplotlib.pyplot as plt
import numpy as np
from pynput.keyboard import Key, Listener

HOST = "127.0.0.1"
# Color map names from matplotlib, this is not an exhaustive list, just ones that look good on a
#  keyboard.
COLOR_MAPS = ['jet', 'turbo', 'hot', 'bwr', 'seismic', 'Spectral', 'gnuplot', 'brg',
              'gist_rainbow', 'rainbow']


class HeatMapper:
    def __init__(self, keyboard_json_file, color_map='hot', refresh_interval_secs=3600,
                 enhance_lowkeys=False, server_port=65432, change_heatmap_on_refresh=False, debug_mode=False):
        self.debug_mode = debug_mode
        # Map of keys to locations, different for each keyboard.
        with open(keyboard_json_file) as f:
            self.key_to_location_map = json.load(f)
        # Convert the lists of locations to tuples so we can use them as dict keys further below.
        for k, locations in self.key_to_location_map.items():
            tuple_locations = []
            for location in locations:
                tuple_locations.append(tuple(location))
            self.key_to_location_map[k] = tuple_locations

        self.color_map_name = color_map
        self.color_map = plt.cm.get_cmap(self.color_map_name)
        self.color_map_index = COLOR_MAPS.index(self.color_map_name)

        self.refresh_interval = refresh_interval_secs
        self.enhance_lowkeys = enhance_lowkeys
        self.change_heatmap_on_refresh = change_heatmap_on_refresh

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.connect((HOST, server_port))

        self.start_time = time.time()
        self.elapsed_time = time.time() - self.start_time

        # Tracks keyboard coordinates to color values
        self.location_to_color = dict()
        # Tracks keyboard coordinates to key-press counts.
        self.location_to_count = dict()
        # Also tracks key press counts, but maps more human-readable key names to count.
        self.key_name_to_count = {k: 0 for k, _ in self.key_to_location_map.items()}

        self.__init_color_map()
        self.__send_colors_to_server()

    # Sets the entire keyboard to the lowest value of the colormap.
    def __init_color_map(self):
        base_color = self.color_map(0)[0:3]
        base_color = [int(color_val * 255) for color_val in base_color]

        for key, location_list in self.key_to_location_map.items():
            for location in location_list:
                self.location_to_count[location] = 0
                self.location_to_color[location] = base_color

    # Sends current color mapping to the server.
    def __send_colors_to_server(self):
        serialized_dict = json.dumps(
            {str(k): self.location_to_color[k] for k in self.location_to_color if k is not None})
        try:
            self.sock.sendall(serialized_dict.encode())
        except socket.error as exc:
            logging.error("Caught exception when sending data socket.error : %s" % exc)

    # Update color map to match current value of keypress counts.
    def __update_color_map(self):
        location_counts_np = np.fromiter(self.location_to_count.values(), dtype=float)

        if self.enhance_lowkeys:
            # Increases colormap contrast for low-count keys.
            location_counts_np = np.sqrt(location_counts_np)
        location_counts_np = (location_counts_np - np.min(location_counts_np)) / np.max(location_counts_np)

        index = 0
        for location, count in self.location_to_count.items():
            # NP array is flat, so we have to use an index here.
            normalized_count = location_counts_np[index]
            # Color map returns RGBA, we only need RGB.
            rgb = self.color_map(normalized_count)[0:3]
            rgb = [int(element * 255) for element in rgb]

            self.location_to_color[location] = rgb
            index += 1

    def __select_next_colormap(self):
        if self.color_map_index == len(COLOR_MAPS) - 1:
            self.color_map_index = 0
        else:
            self.color_map_index += 1
        self.color_map_name = COLOR_MAPS[self.color_map_index]
        self.color_map = plt.cm.get_cmap(self.color_map_name)

    def on_key_release(self, key):
        self.elapsed_time = time.time() - self.start_time
        if self.elapsed_time > self.refresh_interval:
            if self.change_heatmap_on_refresh:
                self.__select_next_colormap()
            self.__init_color_map()
            self.start_time = time.time()

        str_key = str(key)
        # Our key to location map is only required to contain non-caps alphabet characters.
        if not str_key.startswith("Key"):
            str_key = str_key.lower()
        locations = self.key_to_location_map.get(str_key)
        # Some keys might not be present in the mapping.
        if locations is None:
            return

        # Update both our count-holding dicts.
        self.key_name_to_count[str_key] += 1

        for loc in locations:
            self.location_to_count[loc] += 1

        if self.debug_mode:
            if str_key == "Key.f7":
                print("Using Colormap: ", self.color_map_name)
                print("Lowkey enhancement: ", self.enhance_lowkeys)
                print("Key names to counts: ")
                print(self.key_name_to_count)
                print("Keyboard locations to colors: ")
                print(self.location_to_color)
            if str_key == "Key.f2":
                self.__select_next_colormap()
                print("Colormap updated to : ", self.color_map_name)
            if str_key == "Key.f3":
                self.enhance_lowkeys = not self.enhance_lowkeys
                print("Lowkey enhancement switched to: ", self.enhance_lowkeys)

        self.__update_color_map()
        self.__send_colors_to_server()


def main(args):
    if args.verbose:
        logging.basicConfig(format="%(levelname)s: %(message)s", level=logging.DEBUG)

    logging.info("Received arguments: ")
    for arg, value in sorted(vars(args).items()):
        logging.info("Argument %s: %r", arg, value)
    logging.info("Key counter service is starting...")

    heat_mapper = HeatMapper(args.keymap_json_file, args.colormap, args.refresh_time_secs,
                             args.enhance_lowkeys, args.server_port, args.change_heatmap_on_refresh,
                             args.debug_mode)

    # Block until script is killed.
    with Listener(on_press=None, on_release=heat_mapper.on_key_release) as listener:
        listener.join()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--keymap_json_file", type=str, default="razer_blackwidow.json",
                        help="Map of keyboard keys to locations for your keyboard.")
    parser.add_argument("--refresh_time_secs", type=int, default=3600,
                        help="Amount of time, in seconds after which to reset the heatmap (Default is 3600).")
    parser.add_argument("--colormap", type=str, default='jet',
                        help="Colormap to use for heatmap. This has to be a valid Matplotlib heatmap name.")
    parser.add_argument("--change_heatmap_on_refresh", action='store_true',
                        help="If specified, selects a new matplotlib heatmap after every refresh .", default=False)
    parser.add_argument("--enhance_lowkeys", action="store_true", default=True,
                        help="If specified, helps boost the contrast of rarely pressed keys.")
    parser.add_argument("--server_port", type=int, default=65432,
                        help="Port to send color data to.")
    parser.add_argument("--debug_mode", action="store_true", default=False,
                        help="If specified, enables manual debugging features.")
    parser.add_argument("--verbose", action="store_true", default=False,
                        help="If specified, prints debug logs to screen.")
    args = parser.parse_args()
    main(args)
