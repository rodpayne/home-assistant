# **Person Detection Details**

## **Presence Detection not so Binary**
When a person is detected as moving between Home and Away, instead of going straight to Home or Away, it will temporarily change the person's status to Just Arrived or Just Left so that automations can be triggered appropriately.

![Person State Diagram](images/PersonHomeState.png)

*Inspired by <https://philhawthorne.com/making-home-assistants-presence-detection-not-so-binary/>* 

### **HOME-ASSISTANT/python_scripts/person_sensor_update.py** 
This is a script that is called by automation "Person Sensor Update" following a state change of a device tracker such as a phone, watch, or car.  It creates/updates a Home Assistant sensor named `sensor.<personName>_status`.
	
The sensor will be updated with a state such as "Just Arrived", "Home", "Just Left", "Away", or "Extended Away".  In addition, the attributes from the triggered device tracker will be copied to the sensor.  Attributes `entity_id` (the triggering entity ID), `reported_state` (the state reported by the device tracker), `icon` (for the current zone), and `friendly_name` (the status of the person) will be updated.
	
Note that the person sensor state is triggered by state changes such as a device changing zones, so a phone left at home does not get a vote for "home".  The assumption is that if the device is moving, then the person has it.  An effort is also made to show more respect to devices with a higher GPS accuracy.

### **Person sensor example**
```
	Entity	            State	Attributes
	sensor.rod_status 	Home	source_type: gps 
			                    battery_level: 97 
			                    latitude: xx.136566162109375 
			                    longitude: -xxx.60774422200406 
			                    gps_accuracy: 65 
			                    altitude: xxxx.1041374206543 
			                    vertical_accuracy: 10 
			                    friendly_name: Rod (i.e. Rod's iPhone) is Home 
			                    account_name: rod 
			                    entity_id: device_tracker.crab_apple 
			                    reported_state: Home 
			                    person_name: Rod 
			                    update_time: 2020-12-11 17:08:52.267362 
			                    icon: mdi:home
```

### **HOME-ASSISTANT/automation_folder/presence-detection.yaml**
This automation file contains the automations that call the person_sensor_update.py script.

Note that `Person Sensor Update for router home` and `Person Sensor Update for router not_home` are not currently used because it drives the router crazy to be probed all the time.  The intention here is to give a five minute delay before declaring the device not home, so that temporary WIFI dropoffs do not cause inappropriate actions.

### **Device Trackers**
Each device tracker that is processed needs to have the identity of the person that is being tracked. This is specified in either a `person_name` or `account_name` attribute of the device tracker. This could be done in Configuration Customizations.

![Customizations Example](images/CustomizationsExample.png)

In the case of the [Apple iCloud integration](https://www.home-assistant.io/integrations/icloud/), the account_name can be specified in its configuration and this gets passed thru to the device trackers:
```
# iCloud presence
- platform: icloud
  username: roderickhpayne@gmail.com
  password: !secret icloud_rod
  account_name: Rod
```


### [Back to README](/README.md)