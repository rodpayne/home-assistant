
var CARDNAME = "homeseer-wd200-status-card";
var VERSION = "0.2.9";
var MODEL = "HS-WD200+";

class HomeSeerWD200StatusCard extends HTMLElement {

  constructor() {
    super();
  }

  // -----------------------------------------------------
  // Whenever a state changes, a new `hass` object is set.
  // -----------------------------------------------------

  async _setHass(hass) {
    if (typeof this.timeDisplayed == 'undefined') {
      // ---------------------------------------------------------------
      // first-time initialization that had to wait until we had 'hass':
      // ---------------------------------------------------------------
      var entityId = this.config.entity_id;
      var state = hass.states[entityId];
      if (typeof state === 'undefined') {
        throw "No entity with entity_id of " + entityId + " was found."
      }
      var friendlyName = 'friendly_name' in state.attributes ? state.attributes['friendly_name'] : entityId;
      var title = (this.config.title) ? this.config.title : friendlyName;
      this.innerHTML += `
        <ha-card header="${title}">
          <div class="card-content"></div>
        </ha-card>
      `;
      this.content = this.querySelector('div');

      function _zwaveDeviceThatMatchesName(deviceList, nameByUser) {
        var returnDevice = null;
        for (let i = 0; i < deviceList.length; i++) {
          let listNameByUser = deviceList[i]['name_by_user'];
          if ((listNameByUser === nameByUser)) {
            returnDevice = deviceList[i];
          }
        }
        return returnDevice;
      }

      this.zwave_entry_id = this.config.zwave_entry_id
      this.zwave_node_id = this.config.zwave_node_id
      var callResult;
      if ((typeof this.zwave_entry_id === 'undefined') || (typeof this.zwave_node_id === 'undefined')) {
        // -------------------------------------------------------------
        // Retrieve zwave entry_id and node_id from the device registry:
        // -------------------------------------------------------------
        callResult = await hass.callWS({
          type: "config/device_registry/list",
        })
        var deviceList = callResult.filter(obj => {
          return obj.model === MODEL && obj.identifiers[0][0] === 'zwave_js';
        })
        if (!deviceList) {
          throw "No model " + MODEL + " devices were found."
        }
        var device = _zwaveDeviceThatMatchesName(deviceList, friendlyName)
        if (!device) {
          throw "No model " + MODEL + " devices with name '" + friendlyName +
          " were found.  " +
          "You may need to specify zwave_entry_id and zwave_node_id configutation parameters."
          // It may be easiest to just rename so that device name and entity name match.
        }
        console.log("device = ", device);
        this.zwave_entry_id = device.config_entries[0];
        this.zwave_node_id = +device.identifiers[0][1].split('-')[1];
      }
    } else if ((new Date() - this.timeDisplayed) <= 1000) {
      // update no more frequently than every second
      return;
    }
    this.timeDisplayed = new Date();

    if ((typeof this.zwave_entry_id === 'undefined') || (typeof this.zwave_node_id === 'undefined')) {
      return;
    }

    function _compareEqualValues(object1, object2) {
      if (typeof object1 == 'undefined') {
        console.log("Changed: object1 undefined")
        return false;
      }
      // See https://dmitripavlutin.com/how-to-compare-objects-in-javascript/
      const keys1 = Object.keys(object1);
      const keys2 = Object.keys(object2);
      if (keys1.length !== keys2.length) {
        console.log("Changed: " + keys1.length + " vs " + keys2.length)
        return false;
      }
      for (let key of keys1) {
        if (object1[key].value !== object2[key].value) {
          console.log("Changed: " + key)
          return false;
        }
      }
      return true;
    }

    function _overrideLabel(config, i, deviceLabel) {
      return 'labels' in config ? config.labels[i - 1] : deviceLabel;
    }

    // -----------------------------------------
    // Retrieve the Z-Wave Device Configuration:
    // -----------------------------------------
    callResult = await hass.callWS({
      type: "zwave_js/get_config_parameters",
      entry_id: this.zwave_entry_id,
      node_id: this.zwave_node_id,
    })
    if (_compareEqualValues(this.lastParameterCallResult, callResult)) {
      return
    }
    this.lastParameterCallResult = callResult;

    console.log("Web call result = ", callResult);

    // Format the Display:
    let tableForIndicators = '<div class="grid-container">';
    for (let i = 7; i > 0; i--) {
      let colorParam = callResult[this.zwave_node_id + '-112-0-2' + i];
      let f = 2 ** (i - 1);
      let blinkParam = callResult[this.zwave_node_id + '-112-0-31-' + f];

      let indicatorHTML = '<div class="blink' + blinkParam.value + ' color' + this.colorState[colorParam.value] + '";">' + this.colorHint[colorParam.value] + '</div><div>' + _overrideLabel(this.config, i, colorParam.metadata.label) + '</div>';
      tableForIndicators += indicatorHTML;
    }
    tableForIndicators += '</div>';

    this.content.innerHTML = tableForIndicators;
  }

  set hass(hass) {

    this._setHass(hass)
  }

  // ----------------------------------------------------------
  // Accept the user supplied configuration.
  // Throw an exception and Lovelace will render an error card.
  // ----------------------------------------------------------
  setConfig(config) {

    console.info("%c %s %c %s",
      "color: white; background: forestgreen; font-weight: 700;",
      CARDNAME.toUpperCase(),
      "color: forestgreen; background: white; font-weight: 700;",
      VERSION,
    );

    if (!config.entity_id) {
      throw new Error('You need to define an entity_id');
    }
    if (config.labels && config.labels.length != 7) {
      throw new Error('If labels option is specified, seven labels are needed.');
    }
    this.config = config;

    // what the color values mean:
    this.colorState = { 0: "Off", 1: "Red", 2: "Green", 3: "Blue", 4: "Magenta", 5: "Yellow", 6: "Cyan", 7: "White" }
    // hints for colorblind people:
    this.colorHint = { 0: "*", 1: "R", 2: "G", 3: "B", 4: "M", 5: "Y", 6: "C", 7: "W" }

    this.innerHTML = `
    <style>
    .grid-container {
      display: grid;
      grid-gap: 4px;
      justify-content: center;
      grid-template-columns: auto auto;
    }
    .grid-container > div {
      text-align: center;
      padding: 4px 10px;
      text-align: left;
    }
    .colorOff {
      x-background-color: white;
    }
    .colorRed {
      background-color: red;
      background-image: radial-gradient(circle, white 10%, pink 30%, red 40%, var(--card-background-color) 20%);
      color: rgba(0,0,0,0.2);
      font-size: 8px;
    }
    .colorGreen {
      background-color: lightGreen;
      background-image: radial-gradient(circle, white 10%, lightGreen 30%, green 40%, var(--card-background-color) 20%);
      color: rgba(0,0,0,0.2);
      font-size: 8px;
    }
    .colorBlue {
      background-color: blue;
      background-image: radial-gradient(circle, white 10%, lightBlue 30%, blue 40%, var(--card-background-color) 20%);
      color: rgba(0,0,0,0.2);
      font-size: 8px;
    }
    .colorMagenta {
      background-color: magenta;
      background-image: radial-gradient(circle, white 10%, thistle 30%, magenta 40%, var(--card-background-color) 20%);
      color: black;
      color: rgba(0,0,0,0.2);
      font-size: 8px;
    }
    .colorYellow {
      background-color: yellow;
      background-image: radial-gradient(circle, lightyellow 10%, yellow 30%, gold 40%, var(--card-background-color) 20%);
      color: rgba(0,0,0,0.2);
      font-size: 8px;
    }
    .colorCyan {
      background-color: cyan;
      background-image: radial-gradient(circle, white 10%, lightCyan 30%, cyan 40%, var(--card-background-color) 20%);
      color: rgba(0,0,0,0.5);
      font-size: 8px;
    }
    .colorWhite {
      background-color: white;
      background-image: radial-gradient(circle, white 10%, white 30%, gray 40%, var(--card-background-color) 20%);
      x-border: 1px solid black;
      color: rgba(0,0,0,0.5);
      font-size: 8px;
    }
    .blink1 {
      -webkit-animation: NAME-YOUR-ANIMATION 1s infinite;  /* Safari 4+ */
      -moz-animation: NAME-YOUR-ANIMATION 1s infinite;  /* Fx 5+ */
      -o-animation: NAME-YOUR-ANIMATION 1s infinite;  /* Opera 12+ */
      animation: NAME-YOUR-ANIMATION 1s infinite;  /* IE 10+, Fx 29+ */
    }
    
    @-webkit-keyframes NAME-YOUR-ANIMATION {
      0%, 49% {
        color: black;
        border: 2px solid #e50000;
      }
      50%, 100% {
        color: #e50000;
        border: 2px solid black;
      }
    }
    </style>
    `;
  }

  // The height of your card. Home Assistant uses this to automatically
  // distribute all cards over the available columns.
  getCardSize() {
    return 3;
  }

}
customElements.define(CARDNAME, HomeSeerWD200StatusCard);