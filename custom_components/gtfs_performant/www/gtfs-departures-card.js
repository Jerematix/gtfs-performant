/**
 * GTFS Departures Card - Custom Lovelace Card
 * Shows real-time transit departures in a beautiful table format
 * Version: 1.2.0
 */

class GTFSDeparturesCard extends HTMLElement {
  static getConfigElement() {
    return document.createElement("gtfs-departures-card-editor");
  }

  static getStubConfig(hass) {
    // Try to find a GTFS sensor
    const gtfsSensor = Object.keys(hass.states).find(
      (e) => e.startsWith("sensor.") && hass.states[e].attributes.departures
    );
    return {
      entity: gtfsSensor || "",
      title: "",
      max_items: 8,
      route_color: "#03a9f4",
      show_header: true,
    };
  }

  setConfig(config) {
    if (!config.entity) {
      throw new Error("Please define an entity");
    }
    this.config = {
      max_items: 8,
      route_color: "#03a9f4",
      show_header: true,
      ...config,
    };
  }

  set hass(hass) {
    this._hass = hass;
    this.render();
  }

  render() {
    if (!this._hass || !this.config) return;

    const entity = this._hass.states[this.config.entity];
    if (!entity) {
      this.innerHTML = `
        <ha-card>
          <div class="card-content" style="padding: 16px; color: var(--error-color);">
            Entity not found: ${this.config.entity}
          </div>
        </ha-card>`;
      return;
    }

    const departures = entity.attributes.departures || [];
    const stopName = this.config.title || entity.attributes.stop_name || "Departures";
    const maxItems = this.config.max_items || 8;
    const showHeader = this.config.show_header !== false;

    let tableRows = "";
    departures.slice(0, maxItems).forEach((dep) => {
      const route = dep.route || "?";
      const destination = dep.destination || "-";
      const minutes = dep.minutes_until;
      const delay = dep.delay_minutes || 0;

      let timeDisplay = minutes !== null && minutes !== undefined
        ? `${minutes} min`
        : dep.expected || "--:--";

      let delayBadge = "";
      if (delay > 0) {
        delayBadge = `<span class="delay">+${delay}</span>`;
      } else if (minutes !== null) {
        delayBadge = `<span class="on-time">On time</span>`;
      }

      const routeColor = this.config.route_color || "#03a9f4";

      tableRows += `
        <tr>
          <td class="route"><span class="route-badge" style="background: ${routeColor}">${route}</span></td>
          <td class="destination">${destination}</td>
          <td class="time">${timeDisplay}</td>
          <td class="delay-cell">${delayBadge}</td>
        </tr>
      `;
    });

    if (departures.length === 0) {
      tableRows = `<tr><td colspan="4" class="no-data">No upcoming departures</td></tr>`;
    }

    const headerHtml = showHeader ? `
      <div class="card-header">
        <ha-icon icon="mdi:bus-stop"></ha-icon>
        <span>${stopName}</span>
      </div>` : '';

    this.innerHTML = `
      <ha-card>
        ${headerHtml}
        <div class="card-content ${showHeader ? '' : 'no-header'}">
          <table class="departures-table">
            <thead>
              <tr>
                <th>Line</th>
                <th>Destination</th>
                <th>Departs</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              ${tableRows}
            </tbody>
          </table>
        </div>
      </ha-card>
      <style>
        ha-card {
          padding: 0;
        }
        .card-header {
          display: flex;
          align-items: center;
          gap: 8px;
          padding: 16px 16px 8px;
          font-size: 1.2em;
          font-weight: 500;
        }
        .card-header ha-icon {
          color: var(--primary-color);
        }
        .card-content {
          padding: 0 16px 16px;
        }
        .card-content.no-header {
          padding-top: 16px;
        }
        .departures-table {
          width: 100%;
          border-collapse: collapse;
        }
        .departures-table th {
          text-align: left;
          padding: 8px 4px;
          font-size: 0.85em;
          color: var(--secondary-text-color);
          border-bottom: 1px solid var(--divider-color);
        }
        .departures-table td {
          padding: 12px 4px;
          border-bottom: 1px solid var(--divider-color);
          vertical-align: middle;
        }
        .departures-table tr:last-child td {
          border-bottom: none;
        }
        .route-badge {
          display: inline-block;
          padding: 4px 10px;
          border-radius: 4px;
          color: white;
          font-weight: bold;
          font-size: 0.95em;
          min-width: 36px;
          text-align: center;
        }
        .destination {
          max-width: 180px;
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
        }
        .time {
          font-weight: 500;
          white-space: nowrap;
          font-size: 1.05em;
        }
        .delay-cell {
          text-align: right;
          width: 60px;
        }
        .delay {
          color: #f44336;
          font-size: 0.85em;
          font-weight: 500;
        }
        .on-time {
          color: #4caf50;
          font-size: 0.75em;
        }
        .no-data {
          text-align: center;
          color: var(--secondary-text-color);
          padding: 24px;
          font-style: italic;
        }
      </style>
    `;
  }

  getCardSize() {
    const maxItems = this.config?.max_items || 8;
    return Math.ceil(maxItems / 2) + 1;
  }
}

// Card Editor with proper HA form elements
class GTFSDeparturesCardEditor extends HTMLElement {
  constructor() {
    super();
    this._config = {};
    this._hass = null;
  }

  setConfig(config) {
    this._config = { ...config };
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  _getGtfsEntities() {
    if (!this._hass) return [];
    return Object.keys(this._hass.states)
      .filter(id => {
        const state = this._hass.states[id];
        return id.startsWith("sensor.") &&
               (state.attributes.departures !== undefined ||
                state.attributes.stop_name !== undefined ||
                state.attributes.stop_id !== undefined);
      })
      .sort();
  }

  _render() {
    if (!this._hass) return;

    const entities = this._getGtfsEntities();
    const currentEntity = this._config.entity || "";
    const currentTitle = this._config.title || "";
    const currentMaxItems = this._config.max_items || 8;
    const currentRouteColor = this._config.route_color || "#03a9f4";
    const currentShowHeader = this._config.show_header !== false;

    // Build entity options
    let entityOptions = '<option value="">-- Select a transit sensor --</option>';
    entities.forEach(entityId => {
      const state = this._hass.states[entityId];
      const name = state.attributes.friendly_name || state.attributes.stop_name || entityId;
      const selected = entityId === currentEntity ? 'selected' : '';
      entityOptions += `<option value="${entityId}" ${selected}>${name}</option>`;
    });

    this.innerHTML = `
      <style>
        .editor-container {
          display: flex;
          flex-direction: column;
          gap: 16px;
        }
        .form-row {
          display: flex;
          flex-direction: column;
          gap: 4px;
        }
        .form-row label {
          font-weight: 500;
          font-size: 14px;
          color: var(--primary-text-color);
        }
        .form-row .hint {
          font-size: 12px;
          color: var(--secondary-text-color);
          margin-top: 2px;
        }
        .form-row select,
        .form-row input[type="text"],
        .form-row input[type="number"] {
          padding: 10px 12px;
          border: 1px solid var(--divider-color, #e0e0e0);
          border-radius: 4px;
          background: var(--input-fill-color, var(--card-background-color, #fff));
          color: var(--primary-text-color);
          font-size: 14px;
          width: 100%;
          box-sizing: border-box;
        }
        .form-row select:focus,
        .form-row input:focus {
          outline: none;
          border-color: var(--primary-color);
        }
        .form-row input[type="color"] {
          width: 60px;
          height: 40px;
          padding: 4px;
          border: 1px solid var(--divider-color, #e0e0e0);
          border-radius: 4px;
          cursor: pointer;
        }
        .color-row {
          display: flex;
          align-items: center;
          gap: 12px;
        }
        .color-preview {
          display: inline-block;
          padding: 4px 12px;
          border-radius: 4px;
          color: white;
          font-weight: bold;
          font-size: 14px;
        }
        .checkbox-row {
          display: flex;
          align-items: center;
          gap: 8px;
        }
        .checkbox-row input[type="checkbox"] {
          width: 18px;
          height: 18px;
          cursor: pointer;
        }
        .checkbox-row label {
          cursor: pointer;
        }
        .no-entities {
          padding: 16px;
          text-align: center;
          color: var(--error-color);
          background: var(--error-color-light, rgba(244, 67, 54, 0.1));
          border-radius: 4px;
        }
      </style>
      <div class="editor-container">
        ${entities.length === 0 ? `
          <div class="no-entities">
            No GTFS transit sensors found. Please set up the GTFS Performant integration first.
          </div>
        ` : `
          <div class="form-row">
            <label for="entity">Transit Stop Sensor *</label>
            <select id="entity">
              ${entityOptions}
            </select>
            <span class="hint">Select the sensor for the transit stop you want to display</span>
          </div>

          <div class="form-row">
            <label for="title">Card Title</label>
            <input type="text" id="title" value="${currentTitle}" placeholder="Leave empty to use stop name">
            <span class="hint">Custom title for the card header</span>
          </div>

          <div class="form-row">
            <label for="max_items">Maximum Departures</label>
            <input type="number" id="max_items" min="1" max="20" value="${currentMaxItems}">
            <span class="hint">Number of departures to show (1-20)</span>
          </div>

          <div class="form-row">
            <label>Route Badge Color</label>
            <div class="color-row">
              <input type="color" id="route_color" value="${currentRouteColor}">
              <span class="color-preview" style="background: ${currentRouteColor}">18</span>
            </div>
            <span class="hint">Color for the route/line badges</span>
          </div>

          <div class="form-row">
            <div class="checkbox-row">
              <input type="checkbox" id="show_header" ${currentShowHeader ? 'checked' : ''}>
              <label for="show_header">Show card header with stop name</label>
            </div>
          </div>
        `}
      </div>
    `;

    // Add event listeners
    this._addEventListeners();
  }

  _addEventListeners() {
    const entitySelect = this.querySelector("#entity");
    const titleInput = this.querySelector("#title");
    const maxItemsInput = this.querySelector("#max_items");
    const routeColorInput = this.querySelector("#route_color");
    const showHeaderCheckbox = this.querySelector("#show_header");

    if (entitySelect) {
      entitySelect.addEventListener("change", (e) => {
        this._updateConfig("entity", e.target.value);
      });
    }

    if (titleInput) {
      titleInput.addEventListener("input", (e) => {
        this._updateConfig("title", e.target.value);
      });
    }

    if (maxItemsInput) {
      maxItemsInput.addEventListener("change", (e) => {
        this._updateConfig("max_items", parseInt(e.target.value) || 8);
      });
    }

    if (routeColorInput) {
      routeColorInput.addEventListener("input", (e) => {
        this._updateConfig("route_color", e.target.value);
        // Update preview
        const preview = this.querySelector(".color-preview");
        if (preview) {
          preview.style.background = e.target.value;
        }
      });
    }

    if (showHeaderCheckbox) {
      showHeaderCheckbox.addEventListener("change", (e) => {
        this._updateConfig("show_header", e.target.checked);
      });
    }
  }

  _updateConfig(key, value) {
    this._config = { ...this._config, [key]: value };
    this._fireConfigChanged();
  }

  _fireConfigChanged() {
    const event = new CustomEvent("config-changed", {
      detail: { config: this._config },
      bubbles: true,
      composed: true,
    });
    this.dispatchEvent(event);
  }
}

// Register elements
customElements.define("gtfs-departures-card", GTFSDeparturesCard);
customElements.define("gtfs-departures-card-editor", GTFSDeparturesCardEditor);

// Register with HA card picker
window.customCards = window.customCards || [];
window.customCards.push({
  type: "gtfs-departures-card",
  name: "GTFS Departures",
  description: "Display real-time transit departures with line, destination, and time",
  preview: true,
  documentationURL: "https://github.com/jerematix/gtfs-performant",
});

console.info(
  "%c GTFS-DEPARTURES-CARD %c v1.2.0 ",
  "color: white; background: #03a9f4; font-weight: bold; padding: 2px 4px;",
  "color: #03a9f4; background: white; font-weight: bold; padding: 2px 4px;"
);
