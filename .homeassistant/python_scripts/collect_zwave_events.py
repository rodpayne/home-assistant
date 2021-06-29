"""Make sensors to record the zwave_js lock events that the integration does not record."""

# ========================================================================================
# python_scripts/collect_zwave_events.py
# ========================================================================================

trigger_event = data.get("trigger_event")
if trigger_event is None:
    logger.warning("===== trigger_event is required.")
else:
    logger.debug(trigger_event)
    
    event_type = ""
    start_pos = trigger_event.find("<Event ")
    if start_pos == -1:
        logger.debug("event_type start_pos not found.")
    else:
        end_pos = trigger_event.find("[",start_pos)
        if end_pos == -1:
            logger.debug("event_type end_pos not found.")
        else:
            event_type = trigger_event[start_pos + 7:end_pos]
    
    outputAttributesObject = {}
    start_pos = trigger_event.find(": ",end_pos)
    end_pos = trigger_event.find(">",start_pos)
    event_item_list = trigger_event[start_pos + 2:end_pos].split(", ")
    for event_item in event_item_list:
        event_item_pair = event_item.split("=",1)
        outputAttributesObject[event_item_pair[0]] = event_item_pair[1]
            
    outputEntity = "sensor."+event_type+"_node"+outputAttributesObject['node_id']+'_'+outputAttributesObject['label'].lower().replace(' ','_')
    outputState = outputAttributesObject['event_label']
    outputAttributesObject['trigger_event'] = trigger_event

    hass.states.set(outputEntity, outputState, outputAttributesObject)
