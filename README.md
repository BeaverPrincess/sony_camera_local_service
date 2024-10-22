## Instructions

1. **Funktion des Local Services:**
  ```
  Das Local Service ist im Wesentlichen ein kleiner Server, der auf der Client-Seite ausgeführt werden muss, damit die Client-Seite eine SSDP-Suche für die Kamera durchführen kann.
  ```

2. **Warum ein seperater Server auf dem Clientseite:**
  ```
  Da SSDP UDP verwendet, und Standard-Webbrowser keine JavaScript-APIs bereitstellen, die es ermöglichen, UDP-Pakete zu senden oder zu empfangen. 
  SSDP basiert außerdem auf Multicast zur Geräteerkennung, und Browser unterstützen aus Sicherheitsgründen weder das Beitreten zu Multicast-Gruppen noch das Senden von Multicast-Paketen, um Missbrauchspotenzial zu vermeiden.

  Wenn der Client sendet eine Anfrage direkt an die Kamera, der Browser wird die Anfrage aufgrund von CORS-Einschränkungen blockieren. Das Local Server leitet Anfragen an die Kamera weiter. Der Client sendet Anfragen an den Proxy, der sie dann an die Kamera weiterleitet.
  ```