# **Home Assistant Configuration**

## **Set State**
Python Script to set the state or other attributes for the specified entity.

Excellent documentation and HACS installation available from (https://github.com/xannor/hass_py_set_state) readme.

### **Manual Installation Hints**
1. Create `<config>/python_scripts` folder if you haven't already.

2. Copy `set_state.py` into the `<config>/python_scripts` folder.

3. Add `python_script:` to `<config>/configuration.yaml` if you haven't already.

4. Restart Home Assistant.

## **Person Status Sensor**
This custom integration will look at all device trackers for a particular person and combine them into a single person sensor, `sensor.<name>_status`. Device tracker state change events are monitored rather than polling, making a composite, averaging the states, or calculating a probability.

Optionally, when the person sensor changes it can be reverse geocoded using Open Street Maps or Google Maps and the distance from home (miles and minutes) calculated with `WazeRouteCalculator`.

When a person is detected as moving between `Home` and `Away`, instead of going straight to `Home` or `Away`, this will temporarily set the person's status to `Just Arrived` or `Just Left` so that automations can be triggered appropriately.

![Person State Diagram](docs/images/PersonHomeState.png)

*Inspired by <https://philhawthorne.com/making-home-assistants-presence-detection-not-so-binary/>* 

### [Go to Person Detection Details](docs/PersonDetection_person_location.md#table-of-contents)
