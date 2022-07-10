import argparse
import ast
import logging
import socket
import json
import sys

from openrazer.client import DeviceManager

HOST = "127.0.0.1"


class HeatMapServer:
    def __init__(self, port):
        self.port = port

        # Create a DeviceManager. This is used to get specific devices
        self.device_manager = DeviceManager()
        logging.info("Found {} Razer devices".format(len(self.device_manager.devices)))

        self.devices = self.device_manager.devices
        for device in self.devices:
            if not device.fx.advanced:
                logging.info("Skipping device " + device.name + " (" + device.serial + ")")
                self.devices.remove(device)

        self.device = device
        # Disable daemon effect syncing.
        # Without this, the daemon will try to set the lighting effect to every device.
        self.device_manager.sync_effects = False

    def __update_device(self):
        self.device.fx.advanced.draw()

    def start_listening(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind((HOST, self.port))
            s.listen()
            conn, addr = s.accept()
            with conn:
                logging.info(f"Connected by {addr}")
                while True:
                    data = conn.recv(4096)
                    logging.info("Received data: ")
                    logging.info(sys.getsizeof(data))
                    if not data:
                        break
                    try:
                        color_map_str = json.loads(data)
                    except ValueError:
                        logging.error("Error decoding JSON...")

                    color_map = dict()
                    for k, v in color_map_str.items():
                        color_map[ast.literal_eval(k)] = v
                    for k, v in color_map.items():
                        row = k[0]
                        col = k[1]
                        self.device.fx.advanced.matrix[row, col] = tuple(v)
                    self.__update_device()


def main(args):
    if args.verbose:
        logging.basicConfig(format="%(levelname)s: %(message)s", level=logging.DEBUG)

    logging.info("Received arguments: ")
    for arg, value in sorted(vars(args).items()):
        logging.info("Argument %s: %r", arg, value)

    server = HeatMapServer(args.server_port)
    print("Listening on: ", args.server_port)
    server.start_listening()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--server_port", type=int, default=65432,
                        help="Port to send color data to.")
    parser.add_argument("--verbose", action="store_true", default=False,
                        help="If specified, prints debug logs to screen.")
    args = parser.parse_args()
    main(args)
