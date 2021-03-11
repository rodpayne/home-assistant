# **Home Assistant Configuration**

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
