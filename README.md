# **Home Assistant Configuration**

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
