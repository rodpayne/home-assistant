
var CARDNAME = "homeseer-wd200-status-card";
var VERSION = "2023.02.24";
var MODEL = "HS-WD200+";
var DESCRIPTION = "This card shows the status of the seven LEDs on the HS-WD200+ dimmer switch connected using zwave_js.";
var DOC_URL = "https://github.com/rodpayne/home-assistant#lovelace-homeseer-wd200-card";


// import { dump } from "js-yaml";
// import { css, CSSResultGroup, html, LitElement, TemplateResult } from "lit";
// import { dump } from "https://raw.githubusercontent.com/nodeca/js-yaml/master/dist/js-yaml.min.js";
import { 
  LitElement, 
  html,
} from "https://unpkg.com/lit?module";

class HomeSeerWD200StatusCard extends HTMLElement {

  constructor() {
    super();
  }

  // ============================================
  //  Get device information and update the card
  // ============================================

  async _render(firstTime) {
    if (firstTime || typeof this._timeDisplayed == 'undefined') {
      // -----------------------------------------------------------------
      //  first-time initialization that had to wait until we had 'hass':
      // -----------------------------------------------------------------
      console.debug("first-time initialization");
      var entityId;
      var state;
      var friendlyName;
      if (typeof this._config.entity_id ==='undefined' || !this._config.entity_id) {
        //  let message = 'You need to define an entity_id.';
        //  this._showError(message);
        //  return
      } else {
        entityId = this._config.entity_id;
        state = this._hass.states[entityId];
        if (typeof state === 'undefined') {
          let message = 'No entity with entity_id of "' + entityId + '" was found.';
          this._showError(message);
          return
        }
        friendlyName = 'friendly_name' in state.attributes ? state.attributes['friendly_name'] : entityId;
      }

      this.zwave_device_id = this._config.zwave_device_id;
      this.zwave_node_id = this._config.zwave_node_id;
      var callResult;
      if ( (typeof this.zwave_device_id === 'undefined') || (typeof this.zwave_node_id === 'undefined') || (!this.zwave_device_id) || (!this.zwave_node_id) ) {
        // ----------------------------------------------------------------------
        //  Retrieve zwave_device_id and zwave_node_id from the device registry:
        // ----------------------------------------------------------------------
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
        console.debug("deviceList = ", deviceList);
        /* default to the first or only device */
        var selectedDevice = deviceList[0];
        this.zwave_device_id = deviceList[0].id;
        this.zwave_node_id = +deviceList[0].identifiers[0][1].split('-')[1];  
        /* look for one that matches the entity_id friendlyName */
        var device = _zwaveDeviceThatMatchesName(deviceList, friendlyName)
        if (device) {
          selectedDevice = device;          
        } else {
          let entityNameMismatch = friendlyName ? "No model " + MODEL + " devices with name " + friendlyName + " were found. " : "";
          let entityIdSpecified = (entityId) ? 
          "You may need to specify zwave_device_id and zwave_node_id configuration parameters " +
            "or rename device so that device name and entity friendly name match." :
            MODEL + " device with name " + selectedDevice['name_by_user'] + " was selected. "
          let deviceSpecifiedInConfig = (entityId || this._config.zwave_device_id || this._config.zwave_node_id) ? "" : "Specify either entity_id or zwave_device_id and zwave_node_id. ";
          console.warn(entityNameMismatch + entityIdSpecified + deviceSpecifiedInConfig);
        }
        console.debug("selectedDevice = ", selectedDevice);
        this.zwave_device_id = selectedDevice.id;
        this.zwave_node_id = +selectedDevice.identifiers[0][1].split('-')[1];

        var title = (this._config.title) ? this._config.title : friendlyName ? friendlyName : selectedDevice['name_by_user'];
        this.querySelector('span').innerHTML = `
          <ha-card header="${title}">
            <div class="card-content"></div>
          </ha-card>`;
        this.content = this.querySelector('div');  
      }
    } else if ((new Date() - this._timeDisplayed) <= 1000) {
      // ---- update no more frequently than every second
      return;
    }
    this._timeDisplayed = new Date();

    // ---------------------------------------------------
    //  Retrieve the current Z-Wave Device Configuration:
    // ---------------------------------------------------
    callResult = await this._hass.callWS({
      type: "zwave_js/get_config_parameters",
      device_id: this.zwave_device_id,
    })
    if (_compareEqualValues(this.previousParameterCallResult, callResult)) {
      return
    }
    this.previousParameterCallResult = callResult;

    console.debug("New zwave_js/get_config_parameters web call result =", callResult);

    // ---------------------
    //  Format the Display:
    // ---------------------
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

    // -------------------------------
    // ---- functions for _render ----
    // -------------------------------

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

    function _compareEqualValues(object1, object2) {
      if (typeof object1 == 'undefined' || !object1) {
        console.debug("Changed: previous object undefined");
        return false;
      }
      // See https://dmitripavlutin.com/how-to-compare-objects-in-javascript/
      const keys1 = Object.keys(object1);
      const keys2 = Object.keys(object2);
      if (keys1.length !== keys2.length) {
        console.debug("Changed: " + keys1.length + " vs " + keys2.length);
        return false;
      }
      for (let key of keys1) {
        if (object1[key].value !== object2[key].value) {
          console.debug("Changed: " + key + " = " + object2[key].value);
          return false;
        }
      }
      return true;
    }

    function _overrideLabel(config, i, deviceLabel) {
      return ('labels' in config && config.labels && config.labels[i - 1]) ? config.labels[i - 1] : deviceLabel;
    }

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

  // ========================================================================
  //  Whenever any state changes, a new `set` is done for the `hass` object.
  // ========================================================================

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
      this._showError("Exception rendering card: " + err.message);
    });
  }

  // =================================================================
  //  Accept the user supplied configuration and define the basics.
  //  Lovelace will render an error card when an exception is thrown.
  // =================================================================

  setConfig(config) {

    console.info("%c %s %c %s",
      "color: white; background: forestgreen; font-weight: 700;",
      CARDNAME.toUpperCase(),
      "color: forestgreen; background: white; font-weight: 700;",
      VERSION,
    );

    if (config.labels && config.labels.length != 7 && config.labels.length != 0) {
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

    this.previousParameterCallResult = null;

    if (typeof this._hass !== "object") {
      return;
    };

    this._render(true)
    .catch(err => {
      console.debug("error caught in _render"); 
      console.debug(err); 
      this._showError("Exception rendering card: " + err.message);
    });

  }

  // ==========================================================================
  //  Home Assistant uses this to distribute cards over the available columns.
  // ==========================================================================
  getCardSize() {
    return 7;
  }

  // =============================
  //  Display in the card editor:
  // =============================

  static getConfigElement() {
    return document.createElement(CARDNAME + "-editor");
  }

  static getStubConfig() {
    return { 
      entity_id: "",
      zwave_device_id: "",
      zwave_node_id: "",
      title: "",
      labels: [],
    }
  }

}
customElements.define(CARDNAME, HomeSeerWD200StatusCard);

class HomeSeerWD200StatusCardEditor extends LitElement {
  static get properties() {
    return {
      hass: {},
      _config: {},
    };
  }

  // setConfig works the same way as for the card itself
  async setConfig(config) {
    this._config = config;
  //  this._selector = 0;

    // https://github.com/thomasloven/hass-config/wiki/PreLoading-Lovelace-Elements
    if (!customElements.get("ha-entity-picker") || !customElements.get("ha-selector-text")) {
      console.debug("preloading helpers");
      // First we get an entities card element
      const cardHelpers = await window.loadCardHelpers();
      const entitiesCard = await cardHelpers.createCardElement({type: "entities", entities: []}); // A valid config avoids errors
      // Then we make it load its editor through the static getConfigElement method
      entitiesCard.constructor.getConfigElement();
    }
  }

  // This function is called when the input element of the editor loses focus
  entityChanged(ev) {

    // We make a copy of the current config so we don't accidentally overwrite anything too early
    const _config = Object.assign({}, this._config);
    // Then we update the entity value with what we just got from the input field
    _config.entity_id = ev.target.value;
    // And finally write back the updated configuration all at once
    this._config = _config;

    // A config-changed event will tell lovelace we have made changed to the configuration
    // this make sure the changes are saved correctly later and will update the preview
    const event = new CustomEvent("config-changed", {
      detail: { config: _config },
      bubbles: true,
      composed: true,
    });
    this.dispatchEvent(event);
  }

  render() {
    if (!this.hass || !this._config) {
      return html``;
    }

    // @focusout below will call entityChanged when the input field loses focus (e.g. the user tabs away or clicks outside of it)
    return html`
    <p>${DESCRIPTION} Visit the <a href="${DOC_URL}" target="_blank" class="mdc-button">README</a> for more details.</p>
    <ha-entity-picker
      label="Entity"
      allow-custom-entity
      .hass=${this.hass}
      .configValue=${'entity'}
      .value=${this._config.entity_id}
      include-domains=["light"]
      @value-changed=${this.entityChanged}
    ></ha-entity-picker>
    `;
//    <ha-selector-text
//      label="Title"
//      allow-custom-entity
//      .required=false
//      .hass=${this.hass}
//      .value=${this._config.title}
//      .selector=${this._selector}
//    ></ha-selector-text>
  }
}

customElements.define(CARDNAME + "-editor", HomeSeerWD200StatusCardEditor);
window.customCards = window.customCards || [];
window.customCards.push({
  type: CARDNAME,
  name: "HomeSeer WD200 Status Card",
  preview: true, // Optional - defaults to false
  description: DESCRIPTION,
});