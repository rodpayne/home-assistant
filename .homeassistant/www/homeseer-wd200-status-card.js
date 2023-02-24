
var CARDNAME = "homeseer-wd200-status-card";
var VERSION = "2023.02.21";
var MODEL = "HS-WD200+";

// import { dump } from "js-yaml";
// import { css, CSSResultGroup, html, LitElement, TemplateResult } from "lit";
// import { dump } from "https://raw.githubusercontent.com/nodeca/js-yaml/master/dist/js-yaml.min.js";
import {
  LitElement,
} from "https://unpkg.com/lit-element@2.0.1/lit-element.js?module";

class HomeSeerWD200StatusCard extends HTMLElement {

  constructor() {
    super();
  }

  // ----------------------------------------------------------------------
  // Whenever any state changes, a new `set` is done for the `hass` object.
  // ----------------------------------------------------------------------

  set hass(hass) {
    this._hass = hass;
    if (typeof this._config !== "object") {
      console.debug("_config not set before _hass set");
      return;
    };
    this._render(false)
    .catch(err => {
      console.debug("error caught in _render"); 
      console.debug(err); 
    })
  }

  async _render(firstTime) {
    if (firstTime || typeof this._timeDisplayed == 'undefined') {
      // ---------------------------------------------------------------
      // first-time initialization that had to wait until we had 'hass':
      // ---------------------------------------------------------------
      console.debug("first-time initialization");
      var entityId = this._config.entity_id;
      var state = this._hass.states[entityId];
      if (typeof state === 'undefined') {
        let message = 'No entity with entity_id of "' + entityId + '" was found.';
        this._showError(message);
        return
      }
      var friendlyName = 'friendly_name' in state.attributes ? state.attributes['friendly_name'] : entityId;
      var title = (this._config.title) ? this._config.title : friendlyName;
      this.querySelector('span').innerHTML = `
        <ha-card header="${title}">
          <div class="card-content"></div>
        </ha-card>`;
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

      this.zwave_entry_id = this._config.zwave_entry_id
      this.zwave_node_id = this._config.zwave_node_id
      var callResult;
      if ((typeof this.zwave_entry_id === 'undefined') || (typeof this.zwave_node_id === 'undefined')) {
        // -------------------------------------------------------------
        // Retrieve zwave entry_id and node_id from the device registry:
        // -------------------------------------------------------------
        callResult = await this._hass.callWS({
          type: "config/device_registry/list",
        })
        var deviceList = callResult.filter(obj => {
          return obj.model === MODEL && obj.identifiers[0][0] === 'zwave_js';
        })
        if (!deviceList) {
          this._showError("No model " + MODEL + " devices were found.");
          return;
        }
        var device = _zwaveDeviceThatMatchesName(deviceList, friendlyName)
        if (!device) {
          this._showError("No model " + MODEL + " devices with name " + friendlyName +
          " were found. " +
          "You may need to specify zwave_entry_id and zwave_node_id configutation parameters. " +
          "(Or rename device so that device name and entity name match.)");
          return;
        }
        console.debug("device = ", device);
        this.zwave_device_id = device.id;
        this.zwave_entry_id = device.config_entries[0];
        this.zwave_node_id = +device.identifiers[0][1].split('-')[1];
      }
    } else if ((new Date() - this._timeDisplayed) <= 1000) {
      // update no more frequently than every second
      return;
    }
    this._timeDisplayed = new Date();

    if ((typeof this.zwave_entry_id === 'undefined') || (typeof this.zwave_node_id === 'undefined')) {
      return;
    }

    function _compareEqualValues(object1, object2) {
      if (typeof object1 == 'undefined') {
        console.debug("Changed: object1 undefined")
        return false;
      }
      // See https://dmitripavlutin.com/how-to-compare-objects-in-javascript/
      const keys1 = Object.keys(object1);
      const keys2 = Object.keys(object2);
      if (keys1.length !== keys2.length) {
        console.debug("Changed: " + keys1.length + " vs " + keys2.length)
        return false;
      }
      for (let key of keys1) {
        if (object1[key].value !== object2[key].value) {
          console.debug("Changed: " + key)
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
    callResult = await this._hass.callWS({
      type: "zwave_js/get_config_parameters",
    //  entry_id: this.zwave_entry_id,
    //  node_id: this.zwave_node_id,
      device_id: this.zwave_device_id,
    })
    if (_compareEqualValues(this.lastParameterCallResult, callResult)) {
      return
    }
    this.lastParameterCallResult = callResult;

    console.debug("Web call result = ", callResult);

    // -------------------
    // Format the Display:
    // -------------------
    let tableForIndicators = '<div class="grid-container">';
    for (let i = 7; i > 0; i--) {
      let colorParam = callResult[this.zwave_node_id + '-112-0-2' + i];
      let f = 2 ** (i - 1);
      let blinkParam = callResult[this.zwave_node_id + '-112-0-31-' + f];

      let indicatorHTML = '<div class="blink' + blinkParam.value + ' color' + this._colorState[colorParam.value] + '";">' + this._colorHint[colorParam.value] + '</div><div>' + _overrideLabel(this._config, i, colorParam.metadata.label) + '</div>';
      tableForIndicators += indicatorHTML;
    }
    tableForIndicators += '</div>';

    this.content.innerHTML = tableForIndicators;
  }

  _showError(title) {
    console.debug("_showError(" + title + ")");
    let dumped = undefined;
    if (this._config) {
      try {
        console.debug(this._config);
        // todo: format with dump() ?
        dumped = JSON.stringify(this._config, null, 4);
        //dumped = dump(this._config);
      } catch (err) {
        dumped = `[Error dumping ${this._config}]`;
      }
    } else {
      dumped = `[No this._config]`;
    }
    console.debug("dumped=" + dumped);
    this.querySelector('span').innerHTML = `
    <ha-alert alert-type="error" title='${title}'>
    ${dumped ? `<pre>${dumped}<pre>` : ""}
    </ha-alert>`;
    return;
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
    this._config = config;

    // what the color values mean:
    this._colorState = { 0: "Off", 1: "Red", 2: "Green", 3: "Blue", 4: "Magenta", 5: "Yellow", 6: "Cyan", 7: "White" }
    // hints for colorblind people:
    this._colorHint = { 0: "*", 1: "R", 2: "G", 3: "B", 4: "M", 5: "Y", 6: "C", 7: "W" }

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
    <span></span>
    `;
    if (typeof this._hass !== "object") {
      console.debug("_hass not set before _config set");
      return;
    };
    this._render(true)
  }

  // The height of your card. Home Assistant uses this to automatically
  // distribute all cards over the available columns.
  getCardSize() {
    return 7;
  }

  // ---------------------------
  // Display in the card editor:
  // ---------------------------

  static getConfigElement() {
    return document.createElement(CARDNAME + "-editor");
  }

  static getStubConfig() {
    return { 
      entity_id: "light.node_20",
      title: "Status Panel",
    }
  }

}
customElements.define(CARDNAME, HomeSeerWD200StatusCard);

class HomeSeerWD200StatusCardEditor extends LitElement {
  setConfig(config) {
    this._config = config;
  }

  configChanged(newConfig) {
    const event = new Event("config-changed", {
      bubbles: true,
      composed: true,
    });
    event.detail = { config };
    this.dispatchEvent(event);
  }
}

customElements.define(CARDNAME + "-editor", HomeSeerWD200StatusCardEditor);
window.customCards = window.customCards || [];
window.customCards.push({
  type: CARDNAME,
  name: "HomeSeer WD200 Status Card",
  preview: true, // Optional - defaults to false
  description: "The HomeSeer WD200 Status Card shows the current status of the seven LEDs.", // Optional
});