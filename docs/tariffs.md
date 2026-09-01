# Day / night tariffs and cost

The integration only reports kilowatt-hours. Splitting them into a day/night
tariff and turning them into money is done with Home Assistant's built‑in
**Utility Meter** and (optionally) the **Energy dashboard** — nothing
Tuya‑specific.

Below, `sensor.umnyi_schetchik_total_energy` is the meter's lifetime total
energy sensor (adjust the entity id to yours). Example prices: **6.50** per kWh
day, **2.30** per kWh night; day window **07:00–23:00**.

---

## Option A — Energy dashboard with a time‑of‑day price (least effort)

### 1. A price sensor that changes with the clock

`configuration.yaml` (or a package):

```yaml
template:
  - sensor:
      - name: Electricity price
        unique_id: electricity_price
        unit_of_measurement: "RUB/kWh"
        state: >
          {% set h = now().hour %}
          {{ 6.50 if 7 <= h < 23 else 2.30 }}
```

Restart / reload template entities. `sensor.electricity_price` now flips between
6.50 and 2.30.

### 2. Point the Energy dashboard at it

*Settings → Dashboards → Energy → Grid consumption → add
`sensor.umnyi_schetchik_total_energy`.*
For the price choose **“Use an entity tracking the total costs”… → “Use a
price”… → entity → `sensor.electricity_price`**.

Home Assistant now accumulates cost using whichever price is active at each
moment, and the Energy dashboard shows a day/week/month cost breakdown.

> The energy sensor must be `total_increasing` (it is) and only ever go up. If
> the meter is reset, HA handles the drop automatically.

---

## Option B — Separate day / night counters + a cost sensor

Use this if you want explicit “peak kWh” / “off‑peak kWh” / “cost” entities
(e.g. for a custom dashboard card or to match the utility's bill).

### 1. Utility meter with two tariffs

```yaml
utility_meter:
  house_energy:
    source: sensor.umnyi_schetchik_total_energy
    cycle: monthly
    tariffs:
      - day
      - night
```

This creates `sensor.house_energy_day` and `sensor.house_energy_night`
(only the *currently selected* tariff accumulates), plus a
`select.house_energy` to switch tariffs.

### 2. Switch the tariff on schedule

```yaml
automation:
  - alias: "Electricity tariff -> day"
    triggers:
      - trigger: time
        at: "07:00:00"
      - trigger: homeassistant
        event: start
    conditions:
      - condition: time
        after: "07:00:00"
        before: "23:00:00"
    actions:
      - action: select.select_option
        target: { entity_id: select.house_energy }
        data: { option: day }

  - alias: "Electricity tariff -> night"
    triggers:
      - trigger: time
        at: "23:00:00"
      - trigger: homeassistant
        event: start
    conditions:
      - condition: time
        after: "23:00:00"
        before: "07:00:00"
    actions:
      - action: select.select_option
        target: { entity_id: select.house_energy }
        data: { option: night }
```

(The `homeassistant start` trigger + time condition makes sure the right tariff
is selected after a restart.)

### 3. Cost

```yaml
template:
  - sensor:
      - name: Electricity cost this month
        unique_id: electricity_cost_month
        unit_of_measurement: "RUB"
        state_class: total
        state: >
          {{ (states('sensor.house_energy_day')  | float(0) * 6.50
            + states('sensor.house_energy_night')| float(0) * 2.30) | round(2) }}
```

---

## If the meter itself keeps day/night registers

Some KWS‑3xxWF firmware tracks tariff totals internally (T1/T2 on the LCD). If
your meter's display shows separate day/night kWh, those values are probably in
one of the still‑unmapped diagnostic DPs. Run
`Developer Tools → Actions → tuya_lan.dump_dps`, note which DP numbers match the
LCD's T1/T2 figures, and they can be added to the profile as proper
`total_increasing` energy sensors — then you skip the utility‑meter tariff
switching entirely.
