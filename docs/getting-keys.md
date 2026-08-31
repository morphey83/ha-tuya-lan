# Getting a device's local key — offline methods

Tuya's local protocol encrypts every packet with a **per-device local key**
(16 bytes, shown as a 16–24 character string). This integration never contacts
Tuya's cloud, so you provide the key. All of the methods below are on-device or
on-LAN — nothing is sent to a Tuya server by *you* beyond what the device and
app already do.

> The device id (`gwId`, 22 characters) is broadcast in the clear and is filled
> in automatically by discovery. Only the key must be supplied.

## 1. You already have it

If you previously used **LocalTuya**, **tinytuya**, `tuya-cli`, or Tuya's own
developer tools, the key is in:

* `tinytuya` → `devices.json` / `tuya-raw.json` (`"key"` field)
* LocalTuya → `.storage/core.config_entries` (`local_key`)
* `tuya-cli wizard` output

## 2. From an Android backup of the Smart Life / Tuya app (no root)

1. Pair the device normally with the app once (this is the only time the app
   talks to the cloud; you can put the phone in airplane mode afterwards).
2. `adb backup -f smartlife.ab -noapk com.tuya.smartlife`
   (or `com.thingclips.smartlife`, or the vendor-branded package).
3. Unpack: `dd if=smartlife.ab bs=1 skip=24 | zlib-flate -uncompress | tar -xvf -`
   (or use `android-backup-extractor`).
4. Look in `apps/<pkg>/sp/` and `apps/<pkg>/f/` — the `local_key` values are in
   the cached device list JSON.
5. `tools/tuya_lan_probe.py --extract-keys <unpacked-dir>` will scan for them.

## 3. From a packet capture during pairing

The key is delivered to the device over the LAN during activation. Capture the
device's traffic (e.g. `tcpdump` on your router, or a mitmproxy on the phone
with the Tuya cert pinning bypassed) while pairing, and extract `localKey` from
the activation response.

## 4. cloudcutter (fully local, exploits older firmware)

<https://github.com/tuya-cloudcutter/tuya-cloudcutter> puts a device into a mode
where it hands you its config — including the key — without any cloud, and can
optionally flash open firmware (ESPHome / OpenBeken). Best when you want to keep
the device permanently off Tuya's servers.

## 5. Devices still on the default key

Some very old firmware (protocol 3.1) accepts the well-known default key while in
AP/pairing mode. Discovery tries this automatically and will mark such a device
as "no key needed".

---

Once you have the key, add the integration, pick the discovered device, and
paste the key into the **Local key** field.
