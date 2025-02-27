import socket
import time
import requests
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading
from typing import Any
from urllib.parse import urlparse
import psutil


class SSDPSearch:
    """
    This class handles all the functions and logic to look for and set up initial communication with the camera.
    """

    SSDP_MULTICAST_IP = "239.255.255.250"
    SSDP_MULTICAST_PORT = 1900

    def retrieve_device_descriptions(self) -> Any:
        """
        Get location URL using SSDP M-Search.
        """
        print("Fetching camera infos...")
        # SSDP M-SEARCH request to discover the camera
        M_SEARCH = (
            f"M-SEARCH * HTTP/1.1\r\n"
            f"HOST: {self.SSDP_MULTICAST_IP}:{self.SSDP_MULTICAST_PORT}\r\n"
            'MAN: "ssdp:discover"\r\n'
            "MX: 1\r\n"
            "ST: urn:schemas-sony-com:service:ScalarWebAPI:1\r\n"
            "USER-AGENT: Django/5.0 Python/3.x\r\n\r\n"
        ).encode(
            "utf-8"
        )  # Convert to a byte string

        # Best to bind device IP directly to ensure SSDP sends request through correct inteface
        ips = self._get_assigned_ip()

        for ip in ips:
            # Create socket for sending and receiving UDP packets over IPv4, necessary for SSDP
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
            # Allow socket to reuse the address and set socket options
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            # Allows multiple sockets to bind to the same address and port -> in case OS hasnt closed the socket zb. from previous run
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            # Extend to Broadcast by inceasing buffer size
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4096)
            sock.bind((ip, 0))

            # Send M-SEARCH requests multiple times to increase probability that camera reponses
            for i in range(5):
                sock.sendto(
                    M_SEARCH, (self.SSDP_MULTICAST_IP, self.SSDP_MULTICAST_PORT)
                )
                time.sleep(1)

            location_url = None
            start_time = time.time()
            timeout = 8  # Total timeout in seconds
            # Set a dynamic socket timeout to ensure that waiting for a response only takes exactly that long
            try:
                while True:
                    # Calculate remaining time
                    elapsed = time.time() - start_time
                    remaining = timeout - elapsed
                    if remaining <= 0:
                        break
                    sock.settimeout(remaining)
                    try:
                        data, _ = sock.recvfrom(1024)
                        response_str = data.decode("utf-8")

                        # Parse the response to get the LOCATION URL
                        for line in response_str.splitlines():
                            if line.startswith("LOCATION"):
                                location_url = line.split(" ", 1)[1]
                                break
                        if location_url:
                            break  # Exit loop if LOCATION URL is found
                    except socket.timeout:
                        continue  # No data received, continue waiting
            except Exception as e:
                print(f"Error: Failed to fetch location URL.\n{str(e)}")
                return None
            finally:
                sock.close()

            if not location_url:
                continue

            response = requests.get(location_url)
            if response.status_code == 200:
                xml_content = response.content
                print("XML content fetched successfully!")
                return xml_content

        print("Could not find a valid IP to connect with the camera.")
        return None

    def _get_assigned_ip(self) -> list[str]:
        """The assigned IP adress to the computer is needed in order to communicate with the Camera using SSDP M-Search"""
        try:
            # Iterate through all network interfaces
            ips = []
            for _, addresses in psutil.net_if_addrs().items():
                for address in addresses:
                    if address.family == socket.AF_INET:  # IPv4 address
                        ip = address.address
                        # Ignore loopback addresses and self assigned IPs
                        if not ip.startswith("127.") and not ip.startswith("169.254."):
                            ips.append(ip)
            return ips
        except Exception as e:
            print(f"Error occurred at fethcing assigned IP: {e}")
            return None


class BrowserCommunicationHandler(BaseHTTPRequestHandler):
    liveview_url = None

    def _set_headers(self, status_code=200, content_type="application/json"):
        """
        Used to set headers of json responses to the browser.
        """
        self.send_response(status_code)
        self.send_header("Content-type", content_type)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

    def _send_json_response(self, response: dict, status_code=200):
        """
        Used to trigger sending of json responses to the browser.
        """
        self._set_headers(status_code)
        self.wfile.write(json.dumps(response).encode("utf-8"))

    def _handle_liveview_stream(self, live_view_url, boundary="--myboundary"):
        """
        Fetches the live view stream from the camera and relays it to the client's browser
        by converting the camera's stream into an MJPEG (Motion JPEG) stream using the
        multipart/x-mixed-replace MIME type.
        """
        try:
            camera_stream = requests.get(live_view_url, stream=True)

            if camera_stream.status_code == 200:
                content_type = f"multipart/x-mixed-replace; boundary={boundary}"
                self._set_headers(camera_stream.status_code, content_type)
                print(f"Streaming live view with Content-Type: {content_type}")

                # Initializes a byte buffer to accumulate incoming data chunks from the camera's stream
                buffer = b""

                # Iterates over the streamed response in chunks of 1024 bytes.
                for chunk in camera_stream.iter_content(chunk_size=1024):
                    if not chunk:
                        continue
                    buffer += chunk

                    while True:
                        # The find method searches for a specified substring within a string (or a sequence
                        # of bytes within a bytes object) and returns the lowest index where the substring is found.
                        # -1 if not found
                        start_jpeg = buffer.find(b"\xff\xd8")  # Start of JPEG
                        end_jpeg = buffer.find(b"\xff\xd9")  # End of JPEG

                        if (
                            start_jpeg != -1
                            and end_jpeg != -1
                            and end_jpeg > start_jpeg
                        ):
                            # Slice the image out of the buffer
                            # +2 since the start/end marker are 2 bytes long "0xFF 0xD8" and "0xFF 0xD9"
                            jpg = buffer[start_jpeg : end_jpeg + 2]
                            # Remove the extracted image from buffer
                            buffer = buffer[end_jpeg + 2 :]

                            try:
                                # Sends data to the browser over the established HTTP connection.
                                # The boundary string indicates the start of a new JPEG frame in the multipart stream.
                                self.wfile.write(f"{boundary}\r\n".encode())
                                self.wfile.write(
                                    "Content-Type: image/jpeg\r\n\r\n".encode()
                                )
                                self.wfile.write(jpg)
                                self.wfile.write("\r\n".encode())
                                self.wfile.flush()
                            except BrokenPipeError:
                                print("Error at streaming chunks or client quitted.")
                                return
                        else:
                            break
            else:
                self._set_headers(camera_stream.status_code)
                print(
                    f"Failed to connect to live view stream. Status Code: {camera_stream.status_code}"
                )
        except Exception as e:
            response = {"error": "Error streaming live view.", "details": str(e)}
            self._send_json_response(response, status_code=500)
            print(f"Exception occurred while streaming live view: {e}")

    def do_GET(self):
        """
        Handles GET requests.
        """
        path = urlparse(self.path).path

        # Prompt for camera discorvering at the beginning
        if path == "/discover":
            # Perform SSDP discovery
            searcher = SSDPSearch()
            device_description = searcher.retrieve_device_descriptions()
            if device_description is None:
                response = {"error": "Device description fetching failed."}
            else:
                device_description_str = device_description.decode("utf-8")
                response = {"device_description": device_description_str}

            self._send_json_response(response)

        # For request for liveview streaming
        elif path == "/liveview":
            if not BrowserCommunicationHandler.liveview_url:
                response = {"error": "Live view URL not set. Start live view first."}
                self._send_json_response(response, status_code=400)
                print("Live view URL not set. Cannot start streaming.")
                return

            self._handle_liveview_stream(BrowserCommunicationHandler.liveview_url)
        else:
            self.send_error(404, "Local Service not found.")

    def do_POST(self):
        """
        Handles POST requests.
        """
        if self.path == "/camera_control":
            content_length = int(self.headers["Content-Length"])
            post_data = self.rfile.read(content_length)
            try:
                # Parse the JSON data sent from the client
                data = json.loads(post_data.decode("utf-8"))
                print(f"Data from Server received in Local Service: {data}")
                action_list_url = data.get("action_list_url")
                # This is the actual json object required for the api request to the camera
                payload = data.get("payload")
                action = data.get("action")

                if not action_list_url or not payload:
                    response = {"error": "Invalid request data."}
                    self._send_json_response(response, status_code=400)
                    return

                # Forward the request to the camera
                camera_response = requests.post(action_list_url, json=payload)
                camera_response_data = camera_response.json()

                # If liveview stream is requested
                if action == "startLiveview" or action == "startLiveviewWithSize":
                    liveview_urls = camera_response_data.get("result", [])
                    if liveview_urls:
                        # Extract the liveview url from the camera response
                        BrowserCommunicationHandler.liveview_url = liveview_urls[0]
                        print(
                            f"Live view URL: {BrowserCommunicationHandler.liveview_url}"
                        )
                    else:
                        print("No live view URL found in the response.")
                # Notify the client browser with the camera status (should be success)
                self._send_json_response(
                    camera_response_data, status_code=camera_response.status_code
                )

            except Exception as e:
                response = {"error": "Internal server error.", "details": str(e)}
                self._send_json_response(response, status_code=500)
        else:
            self.send_error(404, "Local Service not found.")

    # -> handle the preflight request and return the necessary CORS headers.
    def do_OPTIONS(self):
        origin = self.headers.get("Origin")
        if origin and origin.startswith("http://127.0.0.1:8000"):
            self.send_response(200, "OK")
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS, GET")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.end_headers()
        else:
            self.send_error(403, "Forbidden Origin")


def run_server():
    server_address = ("", 8001)
    httpd = ThreadingHTTPServer(server_address, BrowserCommunicationHandler)
    print("Local service running on port 8001...")
    httpd.serve_forever()


if __name__ == "__main__":
    server_thread = threading.Thread(target=run_server)
    server_thread.daemon = True
    server_thread.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Shutting down local service.")
