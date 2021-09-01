# **Home Assistant Configuration**

## **Security Camera Stuff**
I have the following camera related components installed in my configuration.

| Component            | Description                            | Notes                             |
| -------------------- | -------------------------------------- | --------------------------------- |
[rtsp-simple-server](https://github.com/aler9/rtsp-simple-server) | "rtsp-simple-server is a ready-to-use and zero-dependency RTSP / RTMP / HLS server and proxy, a software that allows users to publish, read and proxy live video and audio streams." | This proxy is used so that multiple streams do not overwhelm less capable (cheap) cameras. It runs in Docker independently of Home Assistant, in fact it is running on an old Raspberry Pi. |
[Frigate NVR Add-on](https://github.com/blakeblackshear/frigate) | "A complete and local NVR designed for Home Assistant with AI object detection. Uses OpenCV and Tensorflow to perform realtime object detection locally for IP cameras." | This adds object detection for even cheap cameras (without running it in the cloud), so that events can be triggered based on a person moving rather than leaves and shadows moving. The Google Coral USB Accellerator gives enough performance to run this on a Raspberry Pi. |
[Frigate Integration](https://github.com/blakeblackshear/frigate-hass-integration) | Integrates Frigate with Home Assistant. | Configures all entities to control Frigate and receive updates. Frigate publishes event information in the form of a change feed via MQTT. |
[Wyse Cam V2](https://wyze.com/wyze-cam-v2.html) | A cheap indoor camera with audio. | Using the [alternate Wyse RTSP firmware](https://download.wyzecam.com/firmware/rtsp/demo_4.28.4.51.bin) to access the camera stream locally. I experimented with the [Xiaomi Dafang Hack](https://github.com/EliasKotlyar/Xiaomi-Dafang-Hacks), which was interesting, but could not get any more reliability than the Wyze firmware. |
[Amcrest AD110 Video Doorbell](https://amcrest.com/smarthome-2-megapixel-wireless-doorbell-security-camera-1920-x-1080p-wifi-doorbell-camera-ip55-weatherproof-two-way-audio-ad110.html) | Good quality video doorbell with local RTSP communication and two-way audio. | Have not had any problems with it. |
packages/security_camera.yaml | Configuration and automations | |
www/camera_video.html | This webpage displays the video from a security camera.  It uses a variety of technologies to find one that will work in a particular browser and keeps it running. | Can be used in a Lovelace webpage (iframe) card or panel, as an [iframe-fullscreen custom panel](https://www.technicallywizardry.com/home-assistant-custom-panels/), or stand-alone in a browser.  |


## **Lovelace HomeSeer WD200+ Card**
This card shows the status of the seven LEDs on the HS-WD200+ dimmer switch connected using `zwave_js`. The color and blinking of the LEDs are set as configuration parameters of the Z-Wave device and the current `zwave_js` integration does not reveal them in attributes of a sensor (yet?), so this was kind of a challenge for me.

The code is at: [www/homeseer-wd200-status-card.js](https://raw.githubusercontent.com/rodpayne/home-assistant/main/.homeassistant/www/homeseer-wd200-status-card.js)

With a very basic configuration it looks like this:

![Default card example](docs/images/default-wd200-status2.png)
```yaml
    cards:
      - type: "custom:homeseer-wd200-status-card"
        entity_id: light.node_20
```

Adding a few configuration options makes it look like this:

![Customized card example](docs/images/configured-wd200-status.png)

```yaml
    cards:
      - type: "custom:homeseer-wd200-status-card"
        entity_id: light.node_20
        title: Status Panel
        labels:
          - "Garage Side Door"
          - "Garage House Door"
          - "Garage Car Door"
          - "Front Door"
          - "Basement Door"
          - "Back Door"
          - "Alarm"
```          
FYI, this is what my installed dimmer switch looks like:

![Dimmer as installed](docs/images/installed-wd200-hardware2.png)

## **Set State**
Python Script to set the state or other attributes for the specified entity.

Excellent documentation and HACS installation available from (https://github.com/xannor/hass_py_set_state) readme.

### **Manual Installation Hints**
1. Create `<config>/python_scripts` folder if you haven't already.

2. Copy `set_state.py` into the `<config>/python_scripts` folder.

3. Add `python_script:` to `<config>/configuration.yaml` if you haven't already.

4. Restart Home Assistant.

## **Person Location Custom Integration**

![Sample person location](docs/images/SamplePersonLocation.png)

This custom integration has been moved to its own HACS-compatible repository.

### **Combine the status of multiple device trackers**
This custom integration will look at all device trackers for a particular person and combine them into a single person location sensor, `sensor.<name>_location`. Device tracker state change events are monitored rather than being polled, making a composite, averaging the states, or calculating a probability.

### **Make presence detection not so binary**
When a person is detected as moving between `Home` and `Away`, instead of going straight to `Home` or `Away`, this will temporarily set the person's location state to `Just Arrived` or `Just Left` so that automations can be triggered appropriately.

### **Reverse geocode the location and make distance calculations**
When the person location sensor changes it can be reverse geocoded using Open Street Maps, Google Maps, or Open Street Map and the distance from home (miles and minutes) calculated with `WazeRouteCalculator`.

### **[Open repository README](https://github.com/rodpayne/home-assistant_person_location#home-assistant-person-location-custom-integration) for all available installation and configuration details.**
