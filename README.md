# **Home Assistant Configuration**

## **Set State**
Python Script to set the state or other attributes for the specified entity.

Excellent documentation available in (https://github.com/xannor/hass_py_set_state) readme.


## **Presence Detection not so Binary**
When a person is detected as moving between Home and Away, instead of going straight to Home or Away, it will temporarily change the person's status to Just Arrived or Just Left so that automations can be triggered appropriately.

![Person State Diagram](docs/images/PersonHomeState.png)

[Person Detection Details](docs/PersonDetection.md) *Inspired by <https://philhawthorne.com/making-home-assistants-presence-detection-not-so-binary/>* 

