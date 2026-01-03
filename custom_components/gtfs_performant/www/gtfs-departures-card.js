/**
 * GTFS Departures Card - Custom Lovelace Card
 * Shows real-time transit departures in a beautiful table format
 * Version: 1.1.0
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
    };
  }

  setConfig(config) {
    if (!config.entity) {
      throw new Error("Please define an entity");
    }
    this.config = config;
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
        delayBadge = `<span class="on-time"></span>`;
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

    this.innerHTML = `
      <ha-card>
        <div class="card-header">
          <ha-icon icon="mdi:bus-stop"></ha-icon>
          <span>${stopName}</span>
        </div>
        <div class="card-content">
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
          width: 50px;
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

// Card Editor with Home Assistant entity selector
class GTFSDeparturesCardEditor extends HTMLElement {
  constructor() {
    super();
    this._config = {};
    this._hass = null;
  }

  setConfig(config) {
    this._config = { ...config };
    this._updateSelector();
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._rendered) {
      this._render();
    }
    this._updateSelector();
  }

  _updateSelector() {
    if (this._selector && this._hass) {
      this._selector.hass = this._hass;
      this._selector.value = this._config.entity || "";
    }
  }

  _render() {
    if (!this._hass) return;
    this._rendered = true;

    this.innerHTML = `
      <style>
        .card-config {
          padding: 0;
        }
        .row {
          margin-bottom: 16px;
        }
        .row label {
          display: block;
          margin-bottom: 8px;
          font-weight: 500;
          color: var(--primary-text-color);
        }
        .row input, .row select {
          width: 100%;
          padding: 10px 12px;
          border: 1px solid var(--divider-color, #e0e0e0);
          border-radius: 4px;
          background: var(--input-fill-color, var(--card-background-color, #fff));
          color: var(--primary-text-color, #212121);
          font-size: 16px;
          box-sizing: border-box;
        }
        .row select {
          cursor: pointer;
        }
        ha-selector {
          display: block;
          margin-bottom: 16px;
        }
      </style>
      <div class="card-config">
        <div class="row">
          <label>Transit Stop Entity</label>
          <select id="entity-select"></select>
        </div>
        <div class="row">
          <label>Title (optional)</label>
          <input type="text" id="title" placeholder="Leave empty to use entity name">
        </div>
        <div class="row">
          <label>Max departures to show</label>
          <input type="number" id="max_items" min="1" max="20" value="8">
        </div>
      </div>
    `;

    // Populate entity dropdown with sensor entities that have departures
    const select = this.querySelector("#entity-select");
    select.innerHTML = '<option value="">-- Select a transit sensor --</option>';

    const entities = Object.keys(this._hass.states)
      .filter(id => {
        const state = this._hass.states[id];
        return id.startsWith("sensor.") &&
               (state.attributes.departures !== undefined ||
                state.attributes.stop_name !== undefined);
      })
      .sort();

    entities.forEach(entityId => {
      const state = this._hass.states[entityId];
      const name = state.attributes.friendly_name || state.attributes.stop_name || entityId;
      const option = document.createElement("option");
      option.value = entityId;
      option.textContent = name;
      if (entityId === this._config.entity) {
        option.selected = true;
      }
      select.appendChild(option);
    });

    select.addEventListener("change", (ev) => {
      this._config = { ...this._config, entity: ev.target.value };
      this._fireConfigChanged();
    });

    // Title input
    const titleInput = this.querySelector("#title");
    titleInput.value = this._config.title || "";
    titleInput.addEventListener("input", (ev) => {
      this._config = { ...this._config, title: ev.target.value };
      this._fireConfigChanged();
    });

    // Max items input
    const maxInput = this.querySelector("#max_items");
    maxInput.value = this._config.max_items || 8;
    maxInput.addEventListener("change", (ev) => {
      this._config = { ...this._config, max_items: parseInt(ev.target.value) || 8 };
      this._fireConfigChanged();
    });
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
});

console.info(
  "%c GTFS-DEPARTURES-CARD %c v1.0 ",
  "color: white; background: #03a9f4; font-weight: bold; padding: 2px 4px;",
  "color: #03a9f4; background: white; font-weight: bold; padding: 2px 4px;"
);
