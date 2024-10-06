import socket
from typing import Optional
import time
import requests
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import threading
from typing import Any


class SSDPSearch:
    def retrieve_device_descriptions(self) -> Any:
        """
        Get location URL using SSDP M-Search.
        """
        print("Fetching camera infos...")
        # SSDP M-SEARCH request to discover the camera
        M_SEARCH = (
            b"M-SEARCH * HTTP/1.1\r\n"
            b"HOST: 239.255.255.250:1900\r\n"
            b'MAN: "ssdp:discover"\r\n'
            b"MX: 1\r\n"
            b"ST: urn:schemas-sony-com:service:ScalarWebAPI:1\r\n"
            b"USER-AGENT: Django/5.0 Python/3.x\r\n\r\n"
        )

        # Create socket for sending and receiving UDP packets over IPv4, necessary for SSDP
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)

        # Allow socket to reuse the address and set socket options
        sock.setsockopt(
            socket.SOL_SOCKET, socket.SO_REUSEADDR, 1
        )  # Allows multiple sockets to bind to the same address and port -> in case OS hasnt closed the socket zb. from previous run
        sock.setsockopt(
            socket.SOL_SOCKET, socket.SO_BROADCAST, 1
        )  # Extend to Broadcast
        sock.setsockopt(
            socket.SOL_SOCKET, socket.SO_RCVBUF, 4096
        )  # Incease buffer size

        # Best to bind device IP directly ensures SSDP sends request through correct inteface
        local_ip = "192.168.122.177"
        sock.bind((local_ip, 0))

        # Send M-SEARCH requests multiple times to increase probability that camera reponses
        for i in range(5):
            sock.sendto(M_SEARCH, ("239.255.255.250", 1900))
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
                    data, addr = sock.recvfrom(1024)
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
            print("Error: Location URL not found in SSDP response.")
            return None

        response = requests.get(location_url)
        if response.status_code == 200:
            xml_content = response.content
            print("XML content fetched successfully!")
            return xml_content


class RequestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/discover":
            # Perform SSDP discovery
            searcher = SSDPSearch()
            device_description = searcher.retrieve_device_descriptions()
            print(device_description)
            if device_description is None:
                response = {"error": "Divice discripton fetching failed."}
            else:
                device_description_str = device_description.decode("utf-8")
                response = {"device_description": device_description_str}

            # Send device discription as JSON response
            self.send_response(200)
            self.send_header("Content-type", "application/json")

            # CORS header to allow cross-origin requests
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(response).encode("utf-8"))
        else:
            self.send_error(404, "Local Service not found.")


def run_server():
    server_address = ("", 8001)  # Listen on all interfaces on port 8001
    httpd = HTTPServer(server_address, RequestHandler)
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
